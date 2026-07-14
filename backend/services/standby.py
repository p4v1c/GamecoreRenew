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

from ..config import GAMECORE_ROOT

log = logging.getLogger(__name__)

CONFIG_FILE = GAMECORE_ROOT / "config" / "standby.json"

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
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(merged, indent=2))
    return merged


def get_state() -> str:
    return _state


async def _run_cmd(*argv: str) -> bool:
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            env={**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")},
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
    global _state, _last_input
    from .. import ws
    _last_input = time.monotonic()
    if _state == "active":
        return
    was = _state
    log.info("standby: wake from %s", was)
    _state = "active"
    if was == "sleep":
        await _screen(True)
        await _governor("performance")
    await ws.broadcast("standby:exit", {})


def on_input() -> None:
    """Any controller button — called from gamepad_monitor's evdev loop."""
    global _last_input
    _last_input = time.monotonic()
    if _state != "active":
        # Fire-and-forget: we're inside the evdev read loop
        task = asyncio.create_task(exit_standby())
        task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)


async def run() -> None:
    from .process_manager import process_manager

    log.info("standby: watcher started")
    global _last_input
    while True:
        await asyncio.sleep(_POLL_SECS)
        try:
            cfg = load_config()
            if not cfg["enabled"]:
                continue
            if process_manager.is_running:
                # A game counts as activity — idle starts when it exits
                _last_input = time.monotonic()
                continue
            idle_mins = (time.monotonic() - _last_input) / 60
            if idle_mins >= cfg["sleep_mins"]:
                await _enter("sleep")
            elif idle_mins >= cfg["screensaver_mins"]:
                await _enter("screensaver")
        except Exception:
            log.exception("standby: tick failed")
