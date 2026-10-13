"""Notice the box waking up, and put back what a sleep can break.

The signal is logind's `PrepareForSleep(false)`, read from `gdbus monitor` on
the system bus. logind sends it for every suspend, Rest mode or not (power
button, desktop menu), and the backend is the process that has to act on it:
the screen, the pads and the launch gate are its state. The interface learns
it from the `power:resumed` event, and from `GET /api/power/state` after a
socket that dropped across the sleep.
"""
import asyncio
import logging
import re
import shutil

from .. import ws
from . import bt_wake, display, gamepad_monitor, rest_mode, standby

log = logging.getLogger(__name__)

#: Signals only, from logind only: no eavesdropping, so it runs unprivileged.
LOGIND_MONITOR = ("gdbus", "monitor", "--system", "--dest", "org.freedesktop.login1",
                  "--object-path", "/org/freedesktop/login1")
_SIGNAL_RE = re.compile(r"\.PrepareForSleep \((true|false),?\)")
#: A monitor that died (bus restart) is started again after this long.
RESTART_SECS = 30.0

_resumes = 0


def resume_count() -> int:
    """How many wakes this backend has seen; the UI replays the splash on a change."""
    return _resumes


def parse_sleep_signal(line: str) -> bool | None:
    """True for "going to sleep", False for "awake again", None for anything else."""
    m = _SIGNAL_RE.search(line)
    return None if m is None else m.group(1) == "true"


async def _step(name: str, coro) -> None:
    # One failed step must not cost the others: a box with no display tool
    # still needs its pads and its launch gate back.
    try:
        await coro
    except Exception:
        log.exception("resume: %s failed", name)


async def on_resume() -> None:
    """Everything a wake owes the player, fastest-visible first."""
    global _resumes
    _resumes += 1
    log.info("resume: the box is awake (wake %d)", _resumes)
    rest_mode.woke()
    await _step("screen", standby.exit_standby())
    await _step("announce", ws.broadcast("power:resumed", {"resumes": _resumes}))
    await _step("display mode", display.restore_preferred())
    gamepad_monitor.request_reprofile()
    await _step("bluetooth wake", bt_wake.allow_paired_pads())


async def _read(proc) -> None:
    async for raw in proc.stdout:
        state = parse_sleep_signal(raw.decode(errors="replace"))
        if state is True:
            log.info("resume: logind says the box is going to sleep")
        elif state is False:
            await on_resume()


async def run() -> None:
    """Follow logind for the life of the backend."""
    if not shutil.which(LOGIND_MONITOR[0]):
        log.warning("resume: gdbus not found; a wake from sleep will not be noticed "
                    "(install glib2)")
        return
    while True:
        proc = await asyncio.create_subprocess_exec(
            *LOGIND_MONITOR, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL)
        try:
            await _read(proc)
        finally:
            if proc.returncode is None:
                proc.kill()
                await proc.wait()
        log.warning("resume: the logind monitor exited (%s); restarting in %ss",
                    proc.returncode, RESTART_SECS)
        await asyncio.sleep(RESTART_SECS)
