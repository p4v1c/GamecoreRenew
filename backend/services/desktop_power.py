"""Who decides when the television goes dark.

Two standby systems were configured on the reference box and neither knew the
other existed: GameCore at 4 and 6 minutes, and KDE's own power manager at
900 s. Only one of them could actually reach the screen, and it was not the one
with the settings page — so the number the owner set from the sofa was quietly
capped by a second, invisible timer. "Never" meant fifteen minutes. Thirty
minutes meant fifteen minutes.

This module hands the decision to GameCore: it disables the desktop's own
screen-off and remembers what it was, so it can be handed back. The settings
page then means what it says.

## It must be handed back

Claiming without releasing is the worse bug, not the safer one. Turning
GameCore's standby OFF while the desktop's is still disabled leaves NOBODY
turning the screen off: the television stays lit all night and the switch that
looks responsible does the opposite of what it promises. So the previous value
is written down before it is overwritten, and `release()` is called on exactly
the transitions where GameCore stops managing the screen.

## The failure this deliberately accepts

If the backend dies while holding the claim, the desktop's timer stays
disabled and nothing turns the screen off until GameCore comes back. That is
the price of having one owner instead of two, and it is the right way round:
a screen that stays on is visible and annoying, where the fault we came from —
a screen that will not come back — is invisible and strands the player.

## Not KDE

`available()` answers no, everything here is a no-op, and GameCore's own
timings simply work as they always did. This is a reconciliation between two
specific systems, not a general power policy.
"""
import asyncio
import json
import logging
import shutil

from .paths import config_dir
from .session import wayland_env

log = logging.getLogger(__name__)

# `[AC][Display] TurnOffDisplayIdleTimeoutSec` in powerdevilrc — addressed
# through KDE's own tools rather than by editing the INI, because the file is
# the desktop's and its nesting is the desktop's business.
_FILE = "powerdevilrc"
_GROUPS = ("--group", "AC", "--group", "Display")
_KEY = "TurnOffDisplayIdleTimeoutSec"
_OFF = "-1"

# What the desktop had before GameCore took over, so it can be given back.
# In GameCore's config dir, which survives OTA updates: a claim outlives any
# single run of the backend, so the note that undoes it has to as well.
_HANDOFF = config_dir() / "display-timeout-handoff.json"


async def _run(*argv: str) -> tuple[int, str]:
    """THE way this module leaves the process. One door, so the test suite has
    one thing to close (tests/conftest.py)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=wayland_env() or None,
        )
        out, _ = await proc.communicate()
        return proc.returncode or 0, out.decode(errors="replace").strip()
    except Exception as e:
        log.info("desktop_power: could not run %s — %s", argv[0], e)
        return 1, ""


def available() -> bool:
    """A KDE session whose power manager we can actually reach."""
    return (bool(shutil.which("kreadconfig6")) and bool(shutil.which("kwriteconfig6"))
            and wayland_env() is not None)


async def _read() -> str | None:
    code, out = await _run("kreadconfig6", "--file", _FILE, *_GROUPS, "--key", _KEY)
    return out if code == 0 and out else None


async def _write(value: str) -> bool:
    code, _ = await _run("kwriteconfig6", "--file", _FILE, *_GROUPS, "--key", _KEY, value)
    if code != 0:
        return False
    # Applied live. Without this the desktop goes on using the value it read at
    # login, and the handover would only take effect at the next session — which
    # on a box that is never logged out of means never.
    await _run("gdbus", "call", "--session",
               "--dest", "org.kde.Solid.PowerManagement",
               "--object-path", "/org/kde/Solid/PowerManagement",
               "--method", "org.kde.Solid.PowerManagement.reparseConfiguration")
    return True


def _remembered() -> str | None:
    try:
        return json.loads(_HANDOFF.read_text())["previous"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return None


def _remember(previous: str) -> None:
    try:
        _HANDOFF.parent.mkdir(parents=True, exist_ok=True)
        _HANDOFF.write_text(json.dumps({"previous": previous}, indent=2))
    except OSError:
        log.warning("desktop_power: could not write %s — the desktop's own "
                    "screen-off will not be restorable", _HANDOFF)


async def claim() -> bool:
    """Disable the desktop's screen-off, remembering what it was.

    Idempotent: a box that is already claimed re-reads as -1 and is left alone,
    which matters because this runs on every startup. The note is NOT rewritten
    then — overwriting it with -1 would erase the only record of the owner's
    real setting.
    """
    if not available():
        return False
    current = await _read()
    if current is None:
        return False
    if current == _OFF:
        return True                     # already ours
    _remember(current)
    if not await _write(_OFF):
        log.warning("desktop_power: could not disable the desktop's screen-off — "
                    "its timer still caps GameCore's (was %s s)", current)
        return False
    log.info("desktop_power: desktop screen-off disabled (was %s s) — GameCore's "
             "standby timings now decide", current)
    return True


async def release() -> bool:
    """Give the desktop its own screen-off back.

    Called wherever GameCore stops managing the screen, because the two
    together disarmed is the state nobody wants: a television that never goes
    dark, behind a switch that says standby is off.
    """
    previous = _remembered()
    if previous is None:
        return False
    if not available():
        return False
    if not await _write(previous):
        return False
    try:
        _HANDOFF.unlink()
    except OSError:
        pass
    log.info("desktop_power: desktop screen-off restored to %s s", previous)
    return True
