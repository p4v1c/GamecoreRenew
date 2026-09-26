"""The desktop session, as seen from a systemd service.

Under systemd the backend inherits none of a session's environment, so every
tool that has to talk to the desktop — a compositor, a screen, a bus — has to
be handed one built by hand. `display_env()` does that for X11 clients and
`wayland_env()` for Wayland ones; the two are NOT interchangeable.
display_env() deliberately strips WAYLAND_DISPLAY, because the emulators it
serves are Qt/SDL applications that would otherwise pick a backend nobody
configured them for.

Lived here rather than in routers/settings/display.py, where it was written.
That module discovered the problem — the reference box runs Plasma on Wayland,
XWayland cannot set modes, so the resolution page has to choose kscreen-doctor
at runtime — and standby.py has exactly the same problem for exactly the same
reason. A service importing from a router to get it would have been the wrong
way round, and a second copy would have been a second answer to "is this box
Wayland".
"""
import asyncio
import glob
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path

log = logging.getLogger(__name__)


def wayland_env() -> dict | None:
    """The session env a Wayland client needs, or None if there is no Wayland.

    Discovered rather than assumed: the socket is `wayland-0` on most boxes and
    is not guaranteed to be, and a hardcoded name would make callers silently
    fall back to the tool that cannot work here.
    """
    uid = os.getuid()
    runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{uid}"
    try:
        sockets = sorted(p.name for p in Path(runtime).glob("wayland-*")
                         if not p.name.endswith(".lock"))
    except OSError:
        return None
    if not sockets:
        return None
    env = os.environ.copy()
    env["XDG_RUNTIME_DIR"] = runtime
    env["WAYLAND_DISPLAY"] = sockets[0]
    env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path={runtime}/bus")
    return env


def kscreen_available() -> bool:
    """True when KDE's own screen client is here AND there is a Wayland session
    for it to talk to. Both halves matter: kscreen-doctor exists on an X11 KDE
    box too, where xset is the right tool and this one is not."""
    return bool(shutil.which("kscreen-doctor")) and wayland_env() is not None


# Community-maintained button/axis mappings (github.com/mdqinc/SDL_GameControllerDB).
# SDL (2.0.10+ and SDL3 alike) loads the file named by the
# SDL_GAMECONTROLLERCONFIG_FILE hint/env var at init and merges it into its
# built-in database, so any emulator linked against SDL correctly maps a
# controller it doesn't otherwise recognize — no per-emulator manual
# configuration needed. (An earlier revision exported SDL_GAMECONTROLLERDB,
# which is not a variable SDL has ever read — the DB was silently ignored.)
#
# The flatpak'd emulators DO read /opt: five carry an explicit
# `filesystems=/opt/GameCore` override and the rest have `host:ro` in their
# manifest. A comment here used to claim the opposite, which would send the
# next maintainer hunting a sandbox problem that does not exist.
#
# The path now comes from mapping_db.served(), not from the vendored file
# directly: what an emulator must read is the community database WITH the
# owner's own captures appended. Naming the vendored file here would have made
# the mapping wizard write to a database nothing loads.


def _controller_db():
    """Path for SDL_GAMECONTROLLERCONFIG_FILE, or None.

    Imported inside the call rather than at module scope: `configgen` pulls in
    the catalogue loader, and this module is imported from `main` before the
    app has decided anything. Never raises — a database that cannot be built
    must cost the captured mappings, not the launch.
    """
    try:
        from .configgen import mapping_db
        return mapping_db.served()
    except Exception:
        log.warning("session: no controller database to hand to SDL",
                    exc_info=True)
        return None


def _xauth_candidates(uid: int) -> list[str]:
    """Cookie files this uid owns, newest first.

    Where the cookie lives depends on who started X:
        SDDM's X11 session  → /tmp/xauth_XXXXXX
        kwin_wayland        → /run/user/<uid>/xauth_XXXXXX
        startx              → ~/.Xauthority
    """
    found = []
    for path in glob.glob("/tmp/xauth_*") + glob.glob(f"/run/user/{uid}/xauth_*"):
        try:
            if os.stat(path).st_uid == uid:
                found.append(path)
        except OSError:
            continue
    found.sort(key=os.path.getmtime, reverse=True)
    home_xauth = os.path.join(os.path.expanduser("~"), ".Xauthority")
    if os.path.exists(home_xauth):
        found.append(home_xauth)
    return found


def _probe_display(uid: int) -> tuple[str, str] | None:
    """(DISPLAY, XAUTHORITY) of a display we can actually open, or None.

    Guessing was the bug: `:1` was hardcoded, and the first socket in sort
    order is no better — this box has both X0 and X1 and only one answers.
    A wrong DISPLAY makes every emulator exit instantly, with stdout going to
    DEVNULL, so the UI just flashes game:started → game:finished.
    """
    displays = [f":{os.path.basename(s)[1:]}" for s in sorted(glob.glob("/tmp/.X11-unix/X*"))]
    if not displays:
        return None
    cookies: list[str | None] = list(_xauth_candidates(uid))
    cookies.append(None)  # some servers accept a local connection with no cookie
    for display in displays:
        for cookie in cookies:
            env = {**os.environ, "DISPLAY": display}
            if cookie:
                env["XAUTHORITY"] = cookie
            else:
                env.pop("XAUTHORITY", None)
            try:
                probe = subprocess.run(
                    ["xdpyinfo"], env=env, timeout=5,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            except (OSError, subprocess.SubprocessError):
                return None  # no xdpyinfo — fall back to the static defaults
            if probe.returncode == 0:
                return display, (cookie or "")
    return None


# Result of the last SUCCESSFUL _probe_display. The display does not move while
# the session is up, and probing costs up to 5 s of blocked event loop per call
# (see _display_env), so a success is kept for the life of the process.
_probe_cache: tuple[str, str] | None = None

# A failure is NOT kept the same way, and that distinction is the whole point.
#
# The backend wins the boot race against X, every cold boot. Measured on the
# reference box: systemd starts the backend at 14:56:19, main.py's lifespan
# calls standby.resume_after_restart() → xset → display_env() at 14:56:20 —
# and /tmp/.X11-unix/ is still empty. SDDM only starts X at 14:56:22, the
# first socket appears at 14:56:22.8, and :1 — the only display that answers
# on that box — at 14:56:24.3. The probe therefore ran 4.3 s too early.
#
# Latching that failure the way a success is latched left _probe_cache at None
# for the life of the process, _display_env fell through to DISPLAY=":0", and
# every emulator started against a display that does not answer and died
# instantly — stdout to DEVNULL, so the UI just flashed game:started →
# game:finished. Restarting the backend was the only cure, and it worked only
# because by then X had been up for minutes.
#
# A failed probe means "X could not be asked yet", never "there is no display".
# So it is retried; the delay only stops a genuinely headless box from paying
# xdpyinfo's timeout on every call.
_probe_retry_at: float = 0.0
_PROBE_RETRY_SECS = 5.0


def _probe_due() -> bool:
    """True when _display_env() would actually run the probe — and so may block."""
    return _probe_cache is None and time.monotonic() >= _probe_retry_at


def invalidate_display_cache() -> None:
    """Forget the probed display — call when a launch fails and X may have moved."""
    global _probe_cache, _probe_retry_at
    _probe_cache, _probe_retry_at = None, 0.0


def session_env_file(uid: int | None = None) -> Path:
    """Where the graphical session writes down what it is.

    `install/bin/gamecore-session` creates this at login and removes it at
    logout, in the user's own runtime directory. Its absence is meaningful: no
    session, which is exactly what a headless box or an SSH install looks like.
    """
    uid = os.getuid() if uid is None else uid
    runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{uid}"
    return Path(runtime) / "gamecore" / "session.env"


def _session_display(uid: int) -> tuple[str, str] | None:
    """(DISPLAY, XAUTHORITY) as the session itself declared them, or None.

    The backend is a system unit — deliberately, so the API and the web
    interface survive without a graphical session — and a system unit sees
    nothing of one. Which left it probing: every X socket against every cookie
    location, on every launch and every standby transition, with a 20 s bound
    in its own unit for the cold-boot case.

    A session that knows its own DISPLAY writing it down is both cheaper and
    more truthful than this process guessing. The probe below stays for every
    box that has not migrated, for a desktop session that is not ours, and for
    the window between a backend restart and the next login.
    """
    try:
        text = session_env_file(uid).read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None
    values: dict[str, str] = {}
    for line in text.splitlines():
        key, _, value = line.partition("=")
        if key and value:
            values[key.strip()] = value.strip()
    display = values.get("DISPLAY")
    if not display:
        return None
    return display, values.get("XAUTHORITY", "")


def _display_env() -> dict:
    """Build an env dict for launching GUI apps from systemd (DISPLAY, XDG_RUNTIME_DIR, DBUS, XAUTHORITY).

    Synchronous, and it may run xdpyinfo — so callers on the event loop must go
    through _display_env_async(). Under systemd neither DISPLAY nor XAUTHORITY
    is set, so the probe ran on *every* game launch and *every* standby
    transition; with X slow to answer (cold boot, stale xauth cookie, the TV
    resyncing HDMI) each subprocess.run sat there up to its 5 s timeout with the
    whole loop blocked behind it — no WebSocket, no API, no pad events.
    Measured at 4.7 s on an unrelated GET /api/systems during one launch.
    """
    global _probe_cache, _probe_retry_at
    env = os.environ.copy()
    uid = os.getuid()
    if not env.get("SDL_GAMECONTROLLERCONFIG_FILE"):
        db = _controller_db()
        if db:
            env["SDL_GAMECONTROLLERCONFIG_FILE"] = str(db)
    if not env.get("DISPLAY") or not env.get("XAUTHORITY"):
        # Asked first, and it costs a file read. Only if there is no session
        # file does this fall back to looking for a display by hand.
        declared = _session_display(uid)
        if declared:
            env["DISPLAY"] = declared[0]
            if declared[1]:
                env["XAUTHORITY"] = declared[1]
            else:
                env.pop("XAUTHORITY", None)
    if not env.get("DISPLAY") or not env.get("XAUTHORITY"):
        if _probe_due():
            found = _probe_display(uid)
            if found:
                _probe_cache = found
            else:
                _probe_retry_at = time.monotonic() + _PROBE_RETRY_SECS
        probed = _probe_cache
        if probed:
            env["DISPLAY"] = probed[0]
            if probed[1]:
                env["XAUTHORITY"] = probed[1]
            else:
                env.pop("XAUTHORITY", None)
    if not env.get("DISPLAY"):
        env["DISPLAY"] = ":0"
    if not env.get("XDG_RUNTIME_DIR"):
        env["XDG_RUNTIME_DIR"] = f"/run/user/{uid}"
    if not env.get("DBUS_SESSION_BUS_ADDRESS"):
        env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path=/run/user/{uid}/bus"
    if not env.get("XAUTHORITY"):
        for candidate in _xauth_candidates(uid):
            env["XAUTHORITY"] = candidate
            break
    # GameCore is hosted on the machine's own X11 desktop session — remove
    # Wayland to prevent Qt apps from trying WAYLAND_DISPLAY and failing
    # silently under the systemd service.
    #
    # This said "an X11 openbox session" long after openbox stopped being
    # installed (arch.sh lays down plasma-desktop and plasma-x11-session). The
    # line below is still right — the whole stack is X11-only — but a reader who
    # knew openbox was gone would conclude the comment was dead and therefore
    # that the line was too. The session changed; X11-only did not.
    env.pop("WAYLAND_DISPLAY", None)
    return env


async def display_env() -> dict:
    """_display_env() for callers on the event loop.

    The first call may probe X and can take seconds; every later one is served
    from the cache and never leaves the loop. Off-thread even so, because the
    first launch after a cold boot is exactly when the probe is slowest and
    exactly when the UI most needs to stay responsive.
    """
    if os.environ.get("DISPLAY") or not _probe_due():
        return _display_env()
    return await asyncio.to_thread(_display_env)
