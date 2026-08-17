"""Soft standby — low power without losing SSH or the backend.

Not suspend-to-RAM: the box stays up, we just cut what actually draws
power. Two stages, driven by controller inactivity (evdev events fed by
gamepad_monitor):

  active ──idle──▶ screensaver (UI slideshow, ws "standby:screensaver")
         ──idle──▶ sleep       (DPMS screen off + powersave governor,
                                ws "standby:sleep")

Any controller button exits both stages (DPMS on, governor restored,
ws "standby:exit"). A running game blocks the whole machine.

Controller input is ALSO reported to the desktop session, via
_signal_user_activity(). That is not a duplicate of the above: on a Plasma
box the session's own power manager blanks the screen on a timer of its own,
and it cannot see a gamepad — libinput does not handle joystick devices. The
two mechanisms cover different halves and neither replaces the other.

Governor switching uses `sudo -n cpupower` — best effort: without a
sudoers rule it silently does nothing (the big saving is the screen).
Config lives in config/standby.json (kept across OTA updates).
"""
import asyncio
import json
import logging
import os
import time

from .paths import config_dir
from .process_manager import display_env

log = logging.getLogger(__name__)

CONFIG_FILE = config_dir() / "standby.json"

DEFAULTS = {"enabled": True, "screensaver_mins": 10, "sleep_mins": 20}

_POLL_SECS = 15

# How often, at most, the compositor is told somebody is at the controller.
#
# The call below is cheap but not free, and `on_input()` fires per RETAINED
# event — a stick swung hard produces a burst of them, where a button press
# produces one. Two seconds is three orders of magnitude below the timeout it
# has to keep resetting (PowerDevil ships 900 s on this box), so throttling
# costs nothing and a game's worth of stick movement no longer means a D-Bus
# call per frame.
_ACTIVITY_SIGNAL_GAP = 2.0
_last_activity_signal = 0.0

# state: "active" | "screensaver" | "sleep"
_state = "active"
_last_input = time.monotonic()


def load_config() -> dict:
    try:
        cfg = json.loads(CONFIG_FILE.read_text())
        return {**DEFAULTS, **cfg}
    except (OSError, json.JSONDecodeError):
        return dict(DEFAULTS)


def save_config(cfg: dict) -> dict:
    merged = {**load_config(), **{k: v for k, v in cfg.items() if k in DEFAULTS}}
    merged["screensaver_mins"] = max(1, int(merged["screensaver_mins"]))
    # 0 means NEVER turn the screen off, and it has to survive this function.
    #
    # The settings screen offers it — SLEEP_MINS ends in 0, labelled "Never" —
    # and the clamp below used to swallow it whole: max(screensaver_mins, 0) is
    # screensaver_mins, so choosing "never" set screen-off to the SAME minute as
    # the screensaver. The most cautious option on the page produced the most
    # aggressive setting there is, and it took the slideshow down with it —
    # _tick tests sleep_mins first, so the screensaver stage became unreachable.
    # Picking "Never" on a box at 4 minutes blacked the television at 4 minutes.
    merged["sleep_mins"] = max(0, int(merged["sleep_mins"]))
    if merged["sleep_mins"]:
        # Otherwise screen-off always comes after (or with) the screensaver
        merged["sleep_mins"] = max(merged["screensaver_mins"], merged["sleep_mins"])
    # tmp + os.replace, like auth._write_private: write_text truncates first,
    # so an interrupted write left a half-written standby.json and load_config
    # fell back to the defaults, quietly undoing the player's timings.
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_FILE.with_name(CONFIG_FILE.name + ".tmp")
    tmp.write_text(json.dumps(merged, indent=2))
    os.replace(tmp, CONFIG_FILE)
    return merged


def get_state() -> str:
    return _state


async def _run_cmd(*argv: str) -> bool:
    try:
        # Same DISPLAY/XAUTHORITY resolution as game launches — under systemd
        # there is no X env at all, and xset needs the xauth cookie, not just a
        # DISPLAY guess. Awaited: the probe behind it can block for seconds the
        # first time, and this runs on every standby transition.
        env = await display_env()
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            env=env,
        )
        await proc.wait()
        return proc.returncode == 0
    except Exception:
        return False


async def _screen(on: bool) -> None:
    ok = await _run_cmd("xset", "dpms", "force", "on" if on else "off")
    if not ok:
        log.warning("standby: xset dpms force %s failed", "on" if on else "off")


async def _signal_user_activity() -> None:
    """Tell the desktop session that somebody is at the controller.

    This is the fix for "pressing a button does not wake the box", and the
    reason it cannot be done with DPMS is that DPMS is not what put the screen
    out. The box runs Plasma on Wayland; the screen is turned off by the
    session's own power manager, on a timer GameCore never sees, and that timer
    is reset by input the COMPOSITOR sees. It never sees a gamepad: the kernel
    tags a DualShock 4's buttons `ID_INPUT_JOYSTICK`, and libinput does not
    handle joysticks at all.

    That is the whole of the reported fault, and it is why it looked like it
    was "only the controller". The same physical pad exposes its touchpad as a
    separate `ID_INPUT_TOUCHPAD` node, which libinput DOES handle — so sliding
    a thumb across the pad woke the television and pressing any button on it
    did not. Nothing in GameCore could produce that asymmetry, because
    GameCore's own screen control (`xset dpms`) is inert here: XWayland carries
    no DPMS extension, and `xset` reports success anyway.

    So we say it out loud, on the session bus, in the one vocabulary the power
    manager is listening to. `SimulateUserActivity` both resets the idle timer
    and lifts a screen already blanked, which is exactly the pair of things a
    button press is supposed to do.
    """
    if not await _run_cmd(
            "gdbus", "call", "--session",
            "--dest", "org.freedesktop.ScreenSaver",
            "--object-path", "/org/freedesktop/ScreenSaver",
            "--method", "org.freedesktop.ScreenSaver.SimulateUserActivity"):
        # Best effort, and deliberately quiet at INFO: a box with no session bus
        # (headless, a test, X11 without a screensaver service) is a legitimate
        # state, and this runs off every button press.
        log.debug("standby: could not signal user activity to the session")


async def _governor(gov: str) -> None:
    # Best effort — needs a sudoers rule for cpupower; the screen is the
    # real power sink, so failure here is fine
    if not await _run_cmd("sudo", "-n", "cpupower", "frequency-set", "-g", gov):
        log.debug("standby: cpupower %s not permitted (no sudoers rule)", gov)


async def _enter(stage: str) -> None:
    global _state
    from .. import ws
    if _state == stage:
        return
    log.info("standby: %s → %s", _state, stage)
    _state = stage
    if stage == "screensaver":
        await ws.broadcast("standby:screensaver", {})
    elif stage == "sleep":
        await ws.broadcast("standby:sleep", {})
        await _screen(False)
        await _governor("powersave")


async def exit_standby() -> None:
    """Wake the box. Deliberately unconditional — see resume_after_restart().

    It used to return immediately when _state was already "active", which is
    exactly the case where waking matters: the screen can be off while this
    process believes it is on, and POST /api/standby/exit then did nothing at
    all. Asking to wake up is never a no-op.
    """
    global _state, _last_input
    from .. import ws
    _last_input = time.monotonic()
    was = _state
    _state = "active"
    if was != "active":
        log.info("standby: wake from %s", was)
    await _screen(True)
    await _governor("performance")
    await ws.broadcast("standby:exit", {})


async def resume_after_restart() -> None:
    """Undo, at startup, any standby the previous process left on the screen.

    _state is in memory; its effect is not. `xset dpms force off` is a property
    of the X server, and X belongs to SDDM — it does not restart with the
    backend. So after a crash, a `systemctl restart`, or the end of an OTA
    (update/linux.sh restarts the service), the box came back holding
    _state == "active" with the screen still off. on_input() tests
    `_state != "active"` before waking, so a button press did nothing; gamepad
    events arrive over evdev rather than X, so DPMS never re-armed by itself
    either. The TV stayed black until someone SSH'd in or plugged a keyboard.

    Called from the lifespan before the watcher starts, so it also repairs a box
    that is already in that state — restarting the backend is what a stuck user
    will try, and now it works.
    """
    global _state, _last_input
    _state = "active"
    _last_input = time.monotonic()
    await _screen(True)
    await _governor("performance")


def _spawn(coro) -> None:
    """Fire-and-forget from the evdev read loop, without an unretrieved warning."""
    task = asyncio.create_task(coro)
    task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)


def on_input() -> None:
    """Any controller button — called from gamepad_monitor's evdev loop."""
    global _last_input, _last_activity_signal
    now = time.monotonic()
    _last_input = now

    # Unconditional, and NOT folded into the `_state != "active"` branch below.
    # That branch asks whether GAMECORE thinks it is asleep, and the screen
    # being out is not GameCore's opinion to hold: on this box the session's
    # power manager blanks the television on its own timer, while _state sits
    # at "active" throughout. Waking only when GameCore believed itself asleep
    # is precisely the bug exit_standby() already had to be cured of — the same
    # mistake one layer up. Throttled instead, which costs a press nothing.
    if now - _last_activity_signal >= _ACTIVITY_SIGNAL_GAP:
        _last_activity_signal = now
        _spawn(_signal_user_activity())

    if _state != "active":
        _spawn(exit_standby())


async def _tick(cfg: dict) -> None:
    """One pass of the watcher. A function so a test can ask for one.

    Otherwise the only way to exercise any of this is to wait _POLL_SECS of real
    time for the loop to come round, which is why none of it was covered.
    """
    global _last_input, _last_activity_signal
    from .process_manager import process_manager

    if not cfg["enabled"]:
        # The clock stops with the switch, and this line is the fix.
        #
        # It used to `continue` and leave `_last_input` where it was, so the
        # counter went on accumulating against a threshold nobody was
        # measuring. Turn standby off, use the box all afternoon, turn it back
        # on — and it slept within one poll, straight past the screensaver,
        # because it believed nobody had touched it since lunchtime.
        _last_input = time.monotonic()
        return
    if process_manager.is_running:
        # A game counts as activity — idle starts when it exits
        _last_input = time.monotonic()
        # And the session has to be told, because the line above only holds OUR
        # standby off. The box also runs a desktop power manager with a timer of
        # its own, which knows nothing about games and cannot see the pad: a
        # cutscene, a pause menu, or a long turn in a strategy game is fifteen
        # minutes of perfect silence to it, and it blanks the television in the
        # middle of a session that never stopped.
        #
        # Said on every tick rather than held as a D-Bus inhibition on purpose.
        # An inhibition would have to survive in a connection we do not keep —
        # `gdbus call` closes its own the moment it returns, dropping the lock —
        # and a lock we DID manage to hold would outlive a crashed emulator or a
        # restarted backend, leaving a box that never sleeps again. That failure
        # is silent and permanent; this one is neither. If the watcher stops,
        # the box simply goes back to sleeping normally.
        _last_activity_signal = _last_input
        await _signal_user_activity()
        return
    idle_mins = (time.monotonic() - _last_input) / 60
    # `cfg["sleep_mins"] and` — 0 is "never turn the screen off", not "turn it
    # off at zero minutes". Without the guard the box goes straight to sleep on
    # the first tick, which is what the option is there to prevent.
    if cfg["sleep_mins"] and idle_mins >= cfg["sleep_mins"]:
        await _enter("sleep")
    elif idle_mins >= cfg["screensaver_mins"]:
        await _enter("screensaver")


async def run() -> None:
    log.info("standby: watcher started")
    while True:
        await asyncio.sleep(_POLL_SECS)
        try:
            await _tick(load_config())
        except Exception:
            log.exception("standby: tick failed")
