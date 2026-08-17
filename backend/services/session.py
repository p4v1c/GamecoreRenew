"""The desktop session, as seen from a systemd service.

Under systemd the backend inherits none of a session's environment, so every
tool that has to talk to the desktop — a compositor, a screen, a bus — has to
be handed one built by hand. `process_manager.display_env()` does that for X11
clients; this does it for Wayland ones, and the two are NOT interchangeable.
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
import os
import shutil
from pathlib import Path


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
