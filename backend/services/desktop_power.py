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

## Two timers, not one

There are two invisible timers, not one, and the second is the one that
actually blanked a film. GameCore's own session is an X11 session
(`/usr/share/xsessions/gamecore.desktop` → `gamecore-session` → `kwin_x11`),
and Plasma's power manager is NOT running in it — nothing starts PowerDevil
there. What IS running is a real X server, with its own screen saver and its
own DPMS timeouts, and nothing ever reset them: a DualShock 4's buttons are
tagged `ID_INPUT_JOYSTICK`, which the X server does not count as input at all.
A film in a kiosk browser and a game in an emulator are both perfect silence
to it, so it blanked the television mid-play on its own default timeout.

So the claim has two arms, tried independently, because a box has one or the
other and never quite both:

  · PowerDevil's `TurnOffDisplayIdleTimeoutSec` — the desktop session.
  · The X server's `xset s` and `xset dpms` timeouts — GameCore's own session.

`xset dpms 0 0 0` and not `xset -dpms`: zeroing the timeouts stops them from
ever firing while leaving the extension enabled, so standby's own
`xset dpms force off` still reaches the screen. Disabling the extension would
have taken GameCore's sleep stage down with the bug it was fixing.

The X arm needs nothing handed back for its own sake — an X server's settings
die with the X server — but it is written down all the same, because the
switch marked "standby" has to be able to give the screen back to whoever had
it, and within one session that is still the X server's own timeout.

## Not KDE, not X

`available()` answers no, everything here is a no-op, and GameCore's own
timings simply work as they always did. This is a reconciliation between
specific systems, not a general power policy.
"""
import asyncio
import json
import logging
import re
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

# The X server's two idle timers, as `xset` spells them. Zero is "never", and
# for DPMS that is deliberately not the same thing as `-dpms`: see the module
# docstring — the extension has to stay enabled for standby's own screen-off.
_X_OFF = {"s": "0 0", "dpms": "0 0 0"}

# `xset q` is not translated, so these read the same on any box. Both are
# optional and looked for separately: XWayland prints the screen-saver block
# and then "Server does not have the DPMS Extension", which is a box with one
# timer, not a box with none.
_X_SAVER = re.compile(r"timeout:\s*(\d+)\s+cycle:\s*(\d+)")
_X_DPMS = re.compile(r"Standby:\s*(\d+)\s+Suspend:\s*(\d+)\s+Off:\s*(\d+)")

# What the desktop had before GameCore took over, so it can be given back.
# In GameCore's config dir, which survives OTA updates: a claim outlives any
# single run of the backend, so the note that undoes it has to as well.
_HANDOFF = config_dir() / "display-timeout-handoff.json"


async def _run(*argv: str, x11: bool = False) -> tuple[int, str]:
    """THE way this module leaves the process. One door, so the test suite has
    one thing to close (tests/conftest.py).

    `x11=True` for the tools that talk to the X server rather than to the
    desktop's bus. The env is resolved HERE and not by the caller, and that is
    the point: `display_env()` may probe X with a subprocess of its own, so a
    caller that built the env itself would reach a real machine from a suite
    that has this one function closed.
    """
    try:
        # Imported here and not at module scope: process_manager pulls in the
        # database and the websocket layer, and this module is otherwise light
        # enough that its own tests need neither.
        from .process_manager import display_env

        env = await display_env() if x11 else (wayland_env() or None)
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
        )
        out, _ = await proc.communicate()
        return proc.returncode or 0, out.decode(errors="replace").strip()
    except Exception as e:
        log.info("desktop_power: could not run %s — %s", argv[0], e)
        return 1, ""


def _kde_available() -> bool:
    """A KDE session whose power manager we can actually reach."""
    return (bool(shutil.which("kreadconfig6")) and bool(shutil.which("kwriteconfig6"))
            and wayland_env() is not None)


def _x_available() -> bool:
    """`xset` is here. Whether an X server answers is decided by `_x_read()`.

    Deliberately not a second display probe: the probe belongs to the one call
    that needs it, and a box where `xset q` says nothing useful is handled by
    that call returning None — same shape as a desktop that will not answer.
    """
    return bool(shutil.which("xset"))


def available() -> bool:
    """Anything here whose idle timer GameCore can take over."""
    return _kde_available() or _x_available()


async def _kde_read() -> str | None:
    code, out = await _run("kreadconfig6", "--file", _FILE, *_GROUPS, "--key", _KEY)
    return out if code == 0 and out else None


async def _x_read() -> dict | None:
    """What the X server's idle timers are set to, or None if it will not say.

    A dict with the halves the server actually has: `{"s": "600 600",
    "dpms": "600 600 600"}` on a real X server, `{"s": "0 0"}` on XWayland,
    which has no DPMS extension. The halves are kept apart all the way through
    so that a server with one of them is claimed for that one rather than
    skipped for the other's absence.
    """
    code, out = await _run("xset", "q", x11=True)
    if code != 0:
        return None
    saver, dpms = _X_SAVER.search(out), _X_DPMS.search(out)
    current: dict = {}
    if saver:
        current["s"] = f"{saver[1]} {saver[2]}"
    if dpms:
        current["dpms"] = f"{dpms[1]} {dpms[2]} {dpms[3]}"
    return current or None


async def _x_write(values: dict) -> bool:
    """Set the idle timers back to whatever `values` says. All or nothing."""
    ok = True
    for key in ("s", "dpms"):
        if key in values:
            code, _ = await _run("xset", key, *values[key].split(), x11=True)
            ok = ok and code == 0
    return ok


async def _kde_write(value: str) -> bool:
    # `--` before the value, and it is not cosmetic: the value we care most
    # about writing is `-1`, and without the separator kwriteconfig6 reads it as
    # a command-line option and refuses the whole call —
    #
    #     $ kwriteconfig6 --file powerdevilrc … --key TurnOff… -1
    #     kwriteconfig6: Unknown option '1'.        (exit 1)
    #
    # which is exactly how this shipped, and exactly what the box reported the
    # first time it ran for real: "could not disable the desktop's screen-off —
    # its timer still caps GameCore's (was 900 s)". Every positive value worked,
    # so nothing in the tests noticed: they drive a fake `_run` and never meet
    # the real argument parser.
    code, _ = await _run("kwriteconfig6", "--file", _FILE, *_GROUPS, "--key", _KEY,
                         "--", value)
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


def _note() -> dict:
    """What is outstanding, per arm: `previous` for KDE, `x_previous` for X.

    One note for both, because "there is a note" is what `release()` reads as
    "we hold the claim" and two files would be two answers to that. A note
    written before the X arm existed has only `previous` in it and still reads
    correctly — the arms are looked up by key, not by count.
    """
    try:
        note = json.loads(_HANDOFF.read_text())
        return note if isinstance(note, dict) else {}
    except (OSError, json.JSONDecodeError, TypeError):
        return {}


def _save(note: dict) -> None:
    """Persist what is still outstanding — or remove the note once nothing is.

    An empty note has to DELETE the file rather than write `{}`: a file that
    exists is the claim, and one holding nothing would make `release()` answer
    "I gave something back" for ever.
    """
    if not note:
        _forget()
        return
    try:
        _HANDOFF.parent.mkdir(parents=True, exist_ok=True)
        _HANDOFF.write_text(json.dumps(note, indent=2))
    except OSError:
        log.warning("desktop_power: could not write %s — the timers taken over "
                    "here will not be restorable", _HANDOFF)


def _forget() -> None:
    try:
        _HANDOFF.unlink()
    except OSError:
        pass


async def _claim_kde(note: dict) -> bool:
    """Take the desktop's screen-off timeout, remembering what it was.

    No availability guard of its own, deliberately: the read below IS the test.
    A box with no KDE cannot answer `kreadconfig6`, gets None, and is skipped —
    which is how this module has always decided, and it keeps the arms honest
    on a machine where the tools happen to be installed but nothing is running
    them. `available()` holds the one cheap short-circuit, for the box that has
    neither arm.
    """
    current = await _kde_read()
    if current is None:
        return False
    if current == _OFF:
        return True                     # already ours
    # Written BEFORE the attempt: a write that half-succeeds must not take the
    # only record of the owner's real setting with it.
    note["previous"] = current
    _save(note)
    if not await _kde_write(_OFF):
        # And withdrawn when the attempt fails, because "there is a note" is
        # what release() reads as "we hold the claim". Leaving one behind for a
        # claim that never happened means a later release writes a value back
        # over a desktop that was never touched — harmless today, since it
        # rewrites what is already there, but it makes the note lie about who
        # owns the timeout, and that note is the whole safety mechanism.
        note.pop("previous", None)
        _save(note)
        log.warning("desktop_power: could not disable the desktop's screen-off — "
                    "its timer still caps GameCore's (was %s s)", current)
        return False
    log.info("desktop_power: desktop screen-off disabled (was %s s) — GameCore's "
             "standby timings now decide", current)
    return True


async def _claim_x(note: dict) -> bool:
    """Take the X server's own idle timers — the ones that blanked the film.

    Only the halves this server has, and only when they are not already zero:
    XWayland reports `timeout: 0 cycle: 0` and no DPMS at all, so on a desktop
    session this arm finds nothing to do and says so by returning True without
    writing a note. The claim that matters is the one in GameCore's own X11
    session, where the server ships real timeouts and nothing resets them.

    Ungated for the same reason as `_claim_kde`: `xset q` not answering is the
    test, and it is the one that works on a box where xset is installed but no
    X server is listening.
    """
    current = await _x_read()
    if current is None:
        return False
    wanted = {key: _X_OFF[key] for key in current}
    if current == wanted:
        return True                     # already ours, or nothing to take
    note["x_previous"] = current
    _save(note)
    if not await _x_write(wanted):
        note.pop("x_previous", None)
        _save(note)
        log.warning("desktop_power: could not stop the X server's idle timers — "
                    "they still blank the screen under GameCore (were %s)", current)
        return False
    log.info("desktop_power: X server idle timers stopped (were %s) — GameCore's "
             "standby timings now decide", current)
    return True


async def claim() -> bool:
    """Take over whatever idle timers this box has, remembering what they were.

    Idempotent, which matters because it runs on startup AND on every standby
    tick that finds itself unclaimed: an arm that is already ours re-reads as
    zero and is left alone, and its note is NOT rewritten — overwriting it
    would erase the only record of the owner's real setting.

    True when at least one arm was taken or was already held. A box with
    neither — no KDE, no X server answering — says False and GameCore's own
    timings work as they always did.
    """
    if not available():
        return False
    # One note, passed through both arms: they add their own key to it and
    # persist it themselves, so a claim that half-succeeds still leaves a
    # record of the half it took.
    note = _note()
    kde = await _claim_kde(note)
    x = await _claim_x(note)
    return kde or x


async def release() -> bool:
    """Give every timer back to whoever had it.

    Called wherever GameCore stops managing the screen, because the two
    together disarmed is the state nobody wants: a television that never goes
    dark, behind a switch that says standby is off.

    Per arm, and only the arms actually written down. An arm that cannot be
    reached right now keeps its note, so the next release still has the value
    to hand back — the note is only dropped once there is nothing left in it.
    """
    note = _note()
    if not note or not available():
        return False
    released = False
    if "previous" in note:
        if await _kde_write(note["previous"]):
            log.info("desktop_power: desktop screen-off restored to %s s",
                     note.pop("previous"))
            released = True
    if "x_previous" in note:
        if await _x_write(note["x_previous"]):
            log.info("desktop_power: X server idle timers restored to %s",
                     note.pop("x_previous"))
            released = True
    if released:
        _save(note)
    return released
