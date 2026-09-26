"""Display mode (resolution + refresh) and UI scale, with a revert timer.

Backends, chosen at runtime:
  · `kscreen-doctor` when a Wayland session answers (XWayland cannot set modes);
  · `xrandr` otherwise.
kscreen modes are addressed by ID: `WxH@rate` is not unique on real outputs.

Applying a mode arms a revert timer HERE, in the backend: a mode the TV refuses
is a black screen, and the settings screen is exactly what disappears behind
it. Only an explicit player action (`confirm`) keeps the mode.

Refused while a game is resident (running or suspended): changing the mode
under an emulator's swapchain kills it.
"""
import asyncio
import json
import logging
import re

from .paths import config_dir
from .process_manager import display_env, process_manager
from .session import kscreen_available, wayland_env

log = logging.getLogger(__name__)


class DisplayError(Exception):
    """A refused request. `status` is the HTTP code the router returns."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail

# Long enough to read a sentence and find a button on a pad, short enough that
# a black screen is an inconvenience rather than a reinstall.
REVERT_SECS = 12

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_OUTPUT_RE = re.compile(r"^(\S+)\s+connected\b")
# "Output: 1 HDMI-A-1 <uuid>"
_KS_OUTPUT_RE = re.compile(r"^Output:\s+\d+\s+(\S+)")
# "  12:1280x800@60.00*!"  — id, geometry, rate, then the current/preferred marks
_KS_MODE_RE = re.compile(r"(\d+):(\d+)x(\d+)@([\d.]+)([*!]*)")
# "   1920x1080     60.00*+  50.00    59.94"
_MODE_RE = re.compile(r"^\s+(\d+)x(\d+)\s+(.*)$")
_RATE_RE = re.compile(r"(\d+\.\d+)([*+]*)")


# Module-level aliases so tests can swap the session probes.
_wayland_env = wayland_env
_kscreen_available = kscreen_available


#: How long a display tool may take before it counts as failed. Measured on the
#: reference box: `kscreen-doctor -o` from the backend service never answers at
#: all, and with no bound the whole Display page waited on it forever — Scale,
#: on its own endpoint, was the only row that ever arrived.
PROBE_SECS = 5
_kscreen_hangs = False


async def _communicate(proc, name: str) -> tuple[int, str]:
    """(returncode, output), or (124, "") when the tool hangs — killed, not left behind."""
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), PROBE_SECS)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        log.warning("display: %s did not answer in %ss", name, PROBE_SECS)
        return 124, ""
    return proc.returncode or 0, out.decode(errors="replace")


async def _run_env(env: dict, *args: str) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env,
    )
    code, out = await _communicate(proc, args[0])
    return code, _ANSI_RE.sub("", out)


def parse_kscreen(text: str) -> dict:
    """The first enabled output, its modes, and which one is live.

    `*` marks the current mode and `!` the preferred one, and both can sit on
    the same entry — matched as a group rather than compared, the same hazard as
    xrandr's `60.00*+`.
    """
    output = ""
    modes: list[dict] = []
    current: dict | None = None
    for line in text.splitlines():
        m = _KS_OUTPUT_RE.match(line.strip())
        if m:
            if output:            # a second output: stop at the first
                break
            output = m.group(1)
            continue
        if not output or "Modes:" not in line:
            continue
        for mid, w, h, rate, flags in _KS_MODE_RE.findall(line):
            entry = {"id": mid, "width": int(w), "height": int(h), "rate": float(rate)}
            modes.append(entry)
            if "*" in flags:
                current = dict(entry)
    return {"output": output, "modes": modes, "current": current}


async def _run(*args: str) -> tuple[int, str]:
    env = await display_env()
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env,
    )
    return await _communicate(proc, args[0])


def parse_modes(text: str) -> dict:
    """The connected output, its modes, and which one is live.

    Only the FIRST connected output is read. A box with two screens is not a
    case this can serve honestly — `xrandr` would need a layout, not a mode —
    and picking one at random would move a picture the owner cannot see.

    A rate carries `*` when it is current and `+` when it is the monitor's
    preferred one. Both markers can appear on the same rate, which is why they
    are matched as a group rather than tested for equality.
    """
    output = ""
    modes: list[dict] = []
    current: dict | None = None
    in_output = False

    for line in text.splitlines():
        m = _OUTPUT_RE.match(line)
        if m:
            if output:            # a second connected output: stop at the first
                break
            output = m.group(1)
            in_output = True
            continue
        if not in_output:
            continue
        m = _MODE_RE.match(line)
        if not m:
            # Any non-indented line ends this output's mode list.
            if line.strip() and not line.startswith(" "):
                in_output = False
            continue
        w, h = int(m.group(1)), int(m.group(2))
        for rate, flags in _RATE_RE.findall(m.group(3)):
            entry = {"width": w, "height": h, "rate": float(rate)}
            modes.append(entry)
            if "*" in flags:
                current = dict(entry)
    return {"output": output, "modes": modes, "current": current}


# What to go back to, and the task that will do it. Module state rather than a
# request-scoped value on purpose: the timer has to outlive the request that
# armed it, and a second request has to be able to find it.
_pending: dict | None = None
_revert_task: asyncio.Task | None = None
# One transaction at a time. Two clients — or one client and the revert timer —
# could otherwise be inside `_apply` at the same moment, and which mode the
# screen ends up in would be decided by whichever tool returned last.
_mode_lock = asyncio.Lock()
# Which transaction a timer belongs to. A task cancelled while it waits for the
# lock never reaches its body, but the check costs nothing and says out loud
# that a timer may not act for a transaction that is over.
_pending_seq = 0


def _cancel_pending() -> None:
    global _pending, _revert_task
    if _revert_task and not _revert_task.done():
        _revert_task.cancel()
    _revert_task = None
    _pending = None


async def read_state() -> dict:
    """What the session's own tool says, whichever that is."""
    global _kscreen_hangs
    env = _wayland_env() if _kscreen_available() and not _kscreen_hangs else None
    if env is not None:
        code, out = await _run_env(env, "kscreen-doctor", "-o")
        # A tool that hung once hangs again: pay the timeout once per backend,
        # not every time the page opens.
        _kscreen_hangs = code == 124
        if code == 0:
            data = parse_kscreen(out)
            if data["output"]:
                return dict(data, backend="kscreen")
        log.warning("display: kscreen-doctor failed (%s) — falling back to xrandr", code)
    code, out = await _run("xrandr", "--query")
    if code != 0:
        return {"output": "", "modes": [], "current": None, "backend": ""}
    return dict(parse_modes(out), backend="xrandr")


async def _apply(state_backend: str, output: str, mode: dict) -> tuple[bool, str]:
    """Put one mode on screen.

    kscreen is addressed by mode ID: `1920x1080@60.00` appears twice in the
    reference box's list, so the name is not a handle. xrandr has no IDs and
    takes the geometry, which is unambiguous there.
    """
    if state_backend == "kscreen":
        env = _wayland_env()
        if env is None:
            return False, "no Wayland session"
        code, out = await _run_env(env, "kscreen-doctor",
                                   f"output.{output}.mode.{mode['id']}")
        return code == 0, out.strip()
    code, out = await _run(
        "xrandr", "--output", output,
        "--mode", f"{mode['width']}x{mode['height']}", "--rate", f"{mode['rate']:g}",
    )
    return code == 0, out.strip()


async def _revert_after(delay: float, previous: dict, seq: int = 0) -> None:
    """Put the old mode back unless someone confirms first.

    Cancellation is the success path: `/confirm` cancels this task, so arriving
    at the `_apply` below means nobody was able to answer — which is what a
    screen showing nothing looks like from here.
    """
    try:
        await asyncio.sleep(delay)
    except asyncio.CancelledError:
        return
    async with _mode_lock:
        if _pending is not None and _pending.get("seq") != seq:
            # A transaction of its own now owns the screen. Cancellation
            # normally gets here first — a task waiting for the lock is
            # cancelled where it waits — and this is what says so out loud.
            return
        ok, detail = await _apply(previous["backend"], previous["output"], previous)
        log.warning("display: no confirmation in %ss — reverted to %sx%s@%s (%s)",
                    delay, previous["width"], previous["height"], previous["rate"],
                    "ok" if ok else detail)
        _cancel_pending()


async def state() -> dict:
    """Modes, current mode, backend, and whether a change awaits confirmation."""
    # No display at all → empty mode list, which the screen shows as such.
    data = await read_state()
    data["pending"] = _pending is not None
    data["revert_secs"] = REVERT_SECS
    return data


async def set_mode(width: int, height: int, rate: float) -> dict:
    """Put a mode on screen, keeping a way back to the last CONFIRMED mode.

    Nothing is given up until the new mode is actually on: a refused second
    change keeps the first one's timer.
    """
    # is_running, not is_foreground: a suspended emulator still holds its GPU
    # context and dies on a mode change.
    if process_manager.is_running:
        raise DisplayError(409, "A game is running — close it before changing the display mode.")

    async with _mode_lock:
        return await _set_mode_locked(width, height, rate)


async def _set_mode_locked(width: int, height: int, rate: float) -> dict:
    global _pending, _revert_task, _pending_seq
    data = await read_state()
    if not data["output"] or not data["current"]:
        raise DisplayError(503, "No connected output reports a mode.")

    # Refused rather than passed through: these tools take any geometry, and a
    # mode the monitor never advertised is the black screen this endpoint
    # exists to make survivable — no reason to walk into it deliberately.
    wanted = next((m for m in data["modes"]
                   if m["width"] == width and m["height"] == height
                   and abs(m["rate"] - rate) < 0.01), None)
    if wanted is None:
        raise DisplayError(400, "That mode is not one this output advertises.")

    previous = dict(data["current"], output=data["output"], backend=data["backend"])
    if (previous["width"], previous["height"]) == (width, height) \
            and abs(previous["rate"] - rate) < 0.01:
        return {"ok": True, "changed": False, "revert_secs": REVERT_SECS}

    # The mode to come back to, which is not necessarily the one on screen.
    fallback = _pending["previous"] if _pending else previous

    ok, detail = await _apply(data["backend"], data["output"], wanted)
    if not ok:
        # The transaction already waiting keeps its timer: nothing about this
        # refusal makes the screen it left any safer to be stuck on.
        raise DisplayError(500, detail or "The compositor refused that mode.")

    _cancel_pending()
    _pending_seq += 1
    _pending = {"previous": fallback, "seq": _pending_seq,
                "wanted": dict(wanted, output=data["output"], backend=data["backend"])}
    _revert_task = asyncio.create_task(_revert_after(REVERT_SECS, fallback, _pending_seq))
    return {"ok": True, "changed": True, "revert_secs": REVERT_SECS}


#: Where a confirmed mode is written down, on the data side with the rest of
#: the player's choices.
PREFERENCE_FILE = "display.json"


def _preference_path():
    return config_dir() / PREFERENCE_FILE


def preferred_mode() -> dict | None:
    """The mode the player last confirmed, or None.

    Read at graphical startup by gamecore-xsetup. Until this
    existed, nothing wrote the choice down at all: `gamecore-xsetup` forces
    1080p at every boot for the pre-session X server, so a player who picked
    1280x720 in the settings — and confirmed it, on a screen they could read —
    found 1080p again at the next start, with nothing to say why.
    """
    try:
        data = json.loads(_preference_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    try:
        return {"width": int(data["width"]), "height": int(data["height"]),
                "rate": float(data["rate"]), "output": str(data.get("output", ""))}
    except (KeyError, TypeError, ValueError):
        log.warning("display: %s is not a mode I can read — ignoring it",
                    _preference_path())
        return None


def _remember(mode: dict) -> None:
    """Only ever called from /confirm.

    Confirmation is the whole difference between a mode that works and a mode
    that was merely accepted by the compositor: somebody read the screen and
    pressed a button on it. Writing an UNconfirmed mode down would persist
    exactly the black screens the revert exists to undo.
    """
    try:
        path = _preference_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "width": mode["width"], "height": mode["height"],
            "rate": mode["rate"], "output": mode.get("output", ""),
        }, indent=2) + "\n", encoding="utf-8")
    except (OSError, KeyError, TypeError) as e:
        log.warning("display: could not remember the confirmed mode — %s", e)


#: Interface size on this screen, as a zoom factor of the whole front end.
#: A fixed list rather than a free value: each one is a size someone checked
#: the themes at, and a pad cycles through four choices, not a slider.
SCALES = (0.9, 1.0, 1.25, 1.5)
SCALE_FILE = "ui-scale.json"


def ui_scale() -> float:
    """The scale the player chose, 1.0 when nothing (valid) was written."""
    try:
        value = float(json.loads((config_dir() / SCALE_FILE).read_text(encoding="utf-8"))["scale"])
    except (OSError, ValueError, KeyError, TypeError):
        return 1.0
    return value if value in SCALES else 1.0


def set_scale(scale: float) -> dict:
    """Remember the interface size. The front end applies it itself: it is a
    zoom of the page, nothing on the output changes, so there is no revert."""
    if scale not in SCALES:
        raise DisplayError(400, f"Scale must be one of {', '.join(f'{int(s * 100)} %' for s in SCALES)}.")
    path = config_dir() / SCALE_FILE
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"scale": scale}) + "\n", encoding="utf-8")
    except OSError as e:
        raise DisplayError(500, f"Could not save the scale — {e}")
    return {"ok": True, "scale": scale}


async def confirm() -> dict:
    """Keep the mode that is on screen.

    Only reachable by someone who can read the screen — which is the entire
    point. Calling it with nothing pending is not an error: a second press, or
    a reload after the timer already fired, means the same thing.
    """
    async with _mode_lock:
        pending = _pending is not None
        wanted = _pending["wanted"] if pending else None
        _cancel_pending()
    if wanted:
        _remember(wanted)
    return {"ok": True, "confirmed": pending}


async def revert_now() -> dict:
    """Go back immediately, without waiting out the timer.

    For the player who can see the screen and simply does not want the mode.
    """
    async with _mode_lock:
        if _pending is None:
            return {"ok": True, "reverted": False}
        previous = _pending["previous"]
        _cancel_pending()
        ok, detail = await _apply(previous["backend"], previous["output"], previous)
        if not ok:
            raise DisplayError(500, detail or "Could not restore the previous mode.")
    return {"ok": True, "reverted": True}
