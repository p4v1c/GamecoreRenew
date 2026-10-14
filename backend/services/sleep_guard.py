"""Close every game before ANY sleep, not only Rest mode's.

The power button, the desktop's menu, a lid or an idle timer all suspend
through logind without asking GameCore. A logind "delay" inhibitor makes them
wait: logind sends PrepareForSleep(true), then holds the sleep until every
delay lock is released or InhibitDelayMaxSec runs out (15 s with GameCore's
logind drop-in, 5 s without). So the backend holds one lock while awake, runs
Rest mode's sweep when the sleep is announced, and lets go.

The lock is an fd; `systemd-inhibit ... cat` holds it for as long as its
stdin is open, which makes releasing it closing a pipe. Delay locks for sleep
need no privilege (polkit allows them to any user).

The Rest mode button goes through here too: its own sweep has already
emptied the box, so the second one finds nothing and releases at once.
"""
import asyncio
import logging
import shutil

from . import launch, rest_mode

log = logging.getLogger(__name__)

INHIBIT_CMD = ("systemd-inhibit", "--what=sleep", "--mode=delay", "--who=GameCore",
               "--why=Closing games before sleep", "cat")
#: Kept under the 15 s InhibitDelayMaxSec of install/system/logind-gamecore.conf.
SLEEP_EXIT_WAIT_SECS = 6.0
SLEEP_FORCE_WAIT_SECS = 2.0
SLEEP_BUDGET_SECS = 12.0
RELEASE_WAIT_SECS = 2.0

_holder: asyncio.subprocess.Process | None = None
_swept_for_sleep = False


def holding() -> bool:
    return _holder is not None and _holder.returncode is None


async def take() -> bool:
    """Hold the delay lock. Idempotent; False when it cannot be taken."""
    global _holder
    if holding():
        return True
    if not shutil.which(INHIBIT_CMD[0]):
        log.warning("sleep_guard: systemd-inhibit not found; games survive a sleep "
                    "started outside Rest mode")
        return False
    try:
        _holder = await asyncio.create_subprocess_exec(
            *INHIBIT_CMD, stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    except OSError as e:
        log.warning("sleep_guard: could not take the sleep lock: %s", e)
        _holder = None
        return False
    return True


async def release() -> None:
    """Let the sleep proceed: end `cat`, and with it the lock."""
    global _holder
    proc, _holder = _holder, None
    if proc is None or proc.returncode is not None:
        return
    try:
        proc.stdin.close()
        await asyncio.wait_for(proc.wait(), RELEASE_WAIT_SECS)
    except (OSError, asyncio.TimeoutError):
        await kill_bounded(proc)


async def kill_bounded(proc) -> None:
    """SIGKILL and wait, bounded: an exit status reaped elsewhere (another
    waitpid(-1) in the process) never reaches asyncio, and an unbounded wait
    here hangs the backend's shutdown."""
    try:
        proc.kill()
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(proc.wait(), RELEASE_WAIT_SECS)
    except asyncio.TimeoutError:
        log.warning("sleep_guard: pid %s did not report its exit", proc.pid)


async def _sweep() -> None:
    survivors = await rest_mode.close_everything(SLEEP_EXIT_WAIT_SECS, SLEEP_FORCE_WAIT_SECS)
    if survivors:
        log.error("sleep_guard: %s still alive as the box goes to sleep", survivors)


async def before_sleep() -> None:
    """PrepareForSleep(true): refuse launches, close everything, release the lock."""
    global _swept_for_sleep
    _swept_for_sleep = True
    launch.close_gate(rest_mode.GATE_REASON)
    try:
        await asyncio.wait_for(_sweep(), SLEEP_BUDGET_SECS)
    except asyncio.TimeoutError:
        log.error("sleep_guard: sweep not done in %ss; releasing anyway, "
                  "finishing after the wake", SLEEP_BUDGET_SECS)
    except Exception:
        log.exception("sleep_guard: sweep failed")
    finally:
        await release()


async def after_wake() -> None:
    """Sweep again (a sleep that outran the lock, a launch that slipped in), re-lock."""
    global _swept_for_sleep
    if _swept_for_sleep:
        _swept_for_sleep = False
        await rest_mode.close_everything(SLEEP_EXIT_WAIT_SECS, SLEEP_FORCE_WAIT_SECS)
    await take()
