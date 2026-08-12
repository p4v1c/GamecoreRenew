"""Display mode — resolution and refresh rate, with a way back.

`xrandr` acts on the GameCore user's own X session, so nothing here needs a
sudoers rule and none is added: the same unprivileged path `standby.py` already
uses for `xset dpms force off`, and `fullscreen_enforcer.py` for EWMH.

## The revert timer, which is the whole reason this is safe to expose

A mode the television refuses is a black screen, and a black screen on a box
driven from a sofa is a box you cannot use. So applying a mode ARMS A TIMER
here, in the backend, and the previous mode comes back unless something
confirms it is readable.

That the timer lives in the backend is the design, not an implementation
detail. The obvious place to put it is the settings screen — and the settings
screen is exactly what a bad mode makes invisible, so it could never fire. The
backend survives a black screen; the frontend is what disappears behind one.

The confirmation is therefore an ACTION the player takes, not a message the
frontend sends on render: a frontend that confirmed automatically would confirm
a screen nobody can see, which is the failure this exists to prevent.

## Refused while a game is running

Changing the mode under a running emulator is the shortest way to make it
crash, and the player is not looking at this screen then anyway.
"""
import asyncio
import logging
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...services.process_manager import display_env, process_manager

router = APIRouter(prefix="/settings/display", tags=["display"])
log = logging.getLogger(__name__)

# Long enough to read a sentence and find a button on a pad, short enough that
# a black screen is an inconvenience rather than a reinstall.
REVERT_SECS = 12

_OUTPUT_RE = re.compile(r"^(\S+)\s+connected\b")
# "   1920x1080     60.00*+  50.00    59.94"
_MODE_RE = re.compile(r"^\s+(\d+)x(\d+)\s+(.*)$")
_RATE_RE = re.compile(r"(\d+\.\d+)([*+]*)")


async def _run(*args: str) -> tuple[int, str]:
    env = await display_env()
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env,
    )
    out, _ = await proc.communicate()
    return proc.returncode or 0, out.decode(errors="replace")


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


def _cancel_pending() -> None:
    global _pending, _revert_task
    if _revert_task and not _revert_task.done():
        _revert_task.cancel()
    _revert_task = None
    _pending = None


async def _apply(output: str, width: int, height: int, rate: float) -> tuple[bool, str]:
    code, out = await _run(
        "xrandr", "--output", output,
        "--mode", f"{width}x{height}", "--rate", f"{rate:g}",
    )
    return code == 0, out.strip()


async def _revert_after(delay: float, previous: dict) -> None:
    """Put the old mode back unless someone confirms first.

    Cancellation is the success path: `/confirm` cancels this task, so arriving
    at the `_apply` below means nobody was able to answer — which is what a
    screen showing nothing looks like from here.
    """
    try:
        await asyncio.sleep(delay)
    except asyncio.CancelledError:
        return
    ok, detail = await _apply(previous["output"], previous["width"],
                              previous["height"], previous["rate"])
    log.warning("display: no confirmation in %ss — reverted to %sx%s@%s (%s)",
                delay, previous["width"], previous["height"], previous["rate"],
                "ok" if ok else detail)
    _cancel_pending()


@router.get("")
async def get_display():
    code, out = await _run("xrandr", "--query")
    if code != 0:
        # No X yet, or no display at all. An empty mode list is what the screen
        # renders as "nothing to offer here", which is the truth.
        return {"output": "", "modes": [], "current": None,
                "pending": False, "revert_secs": REVERT_SECS}
    data = parse_modes(out)
    data["pending"] = _pending is not None
    data["revert_secs"] = REVERT_SECS
    return data


class ModeRequest(BaseModel):
    width: int
    height: int
    rate: float


@router.post("/mode")
async def set_mode(req: ModeRequest):
    if process_manager.current_game:
        raise HTTPException(409, "A game is running — close it before changing the display mode.")

    code, out = await _run("xrandr", "--query")
    if code != 0:
        raise HTTPException(503, "Cannot reach the display.")
    data = parse_modes(out)
    if not data["output"] or not data["current"]:
        raise HTTPException(503, "No connected output reports a mode.")

    # Refused rather than passed through: xrandr takes any geometry and a mode
    # the monitor never advertised is the black screen this endpoint exists to
    # make survivable — no reason to walk into it deliberately.
    wanted = {"width": req.width, "height": req.height, "rate": req.rate}
    if not any(m["width"] == req.width and m["height"] == req.height
               and abs(m["rate"] - req.rate) < 0.01 for m in data["modes"]):
        raise HTTPException(400, "That mode is not one this output advertises.")

    previous = dict(data["current"], output=data["output"])
    if (previous["width"], previous["height"]) == (req.width, req.height) \
            and abs(previous["rate"] - req.rate) < 0.01:
        return {"ok": True, "changed": False, "revert_secs": REVERT_SECS}

    _cancel_pending()
    ok, detail = await _apply(data["output"], req.width, req.height, req.rate)
    if not ok:
        raise HTTPException(500, detail or "xrandr refused that mode.")

    global _pending, _revert_task
    _pending = {"previous": previous, "wanted": dict(wanted, output=data["output"])}
    _revert_task = asyncio.create_task(_revert_after(REVERT_SECS, previous))
    return {"ok": True, "changed": True, "revert_secs": REVERT_SECS}


@router.post("/confirm")
async def confirm():
    """Keep the mode that is on screen.

    Only reachable by someone who can read the screen — which is the entire
    point. Calling it with nothing pending is not an error: a second press, or
    a reload after the timer already fired, means the same thing.
    """
    pending = _pending is not None
    _cancel_pending()
    return {"ok": True, "confirmed": pending}


@router.post("/revert")
async def revert_now():
    """Go back immediately, without waiting out the timer.

    For the player who can see the screen and simply does not want the mode.
    """
    global _pending
    if _pending is None:
        return {"ok": True, "reverted": False}
    previous = _pending["previous"]
    _cancel_pending()
    ok, detail = await _apply(previous["output"], previous["width"],
                              previous["height"], previous["rate"])
    if not ok:
        raise HTTPException(500, detail or "Could not restore the previous mode.")
    return {"ok": True, "reverted": True}
