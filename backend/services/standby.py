"""Soft standby — low power without losing SSH or the backend.

Not suspend-to-RAM: the box stays up, we just cut what actually draws
power. Two stages, driven by controller inactivity (evdev events fed by
gamepad_monitor):

  active ──idle──▶ screensaver (UI slideshow, ws "standby:screensaver")
         ──idle──▶ sleep       (DPMS screen off + powersave governor,
                                ws "standby:sleep")

Any controller button exits both stages (DPMS on, governor restored,
ws "standby:exit"). A running game blocks the whole machine.

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
    # Screen-off always comes after (or with) the screensaver stage
    merged["sleep_mins"] = max(merged["screensaver_mins"], int(merged["sleep_mins"]))
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


def on_input() -> None:
    """Any controller button — called from gamepad_monitor's evdev loop."""
    global _last_input
    _last_input = time.monotonic()
    if _state != "active":
        # Fire-and-forget: we're inside the evdev read loop
        task = asyncio.create_task(exit_standby())
        task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)


async def _tick(cfg: dict) -> None:
    """One pass of the watcher. A function so a test can ask for one.

    Otherwise the only way to exercise any of this is to wait _POLL_SECS of real
    time for the loop to come round, which is why none of it was covered.
    """
    global _last_input
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
        return
    idle_mins = (time.monotonic() - _last_input) / 60
    if idle_mins >= cfg["sleep_mins"]:
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
