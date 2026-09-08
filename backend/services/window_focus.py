"""Give the screen back to a session that has just been resumed.

A suspended emulator does not lose its window. SIGSTOP freezes the client, and
the window manager goes on drawing the last frame it was handed — so a game put
in the background is still a fullscreen picture covering the interface, which
is the opposite of what the player asked for. Something has to move the screen,
and it cannot be the frozen client: it will not run again until it is resumed.

So the window manager is asked directly, through EWMH messages sent to the
root window. That works on a client that is not running, because the WM is the
one doing the work.

X11/XWayland only, and deliberately best effort: python-xlib may not be
installed, `DISPLAY` may not answer, and the compositor may refuse. A resume
whose window merely stayed behind the interface is a game the player can still
reach with one more press. A resume that raised an exception after the process
was already thawed would be a lie about what happened.
"""
import asyncio
import logging
import os

from .process_manager import _display_env

log = logging.getLogger(__name__)

try:
    from Xlib import X, display as xdisplay
    from Xlib.protocol import event as xevent
    _XLIB_OK = True
except ImportError:
    _XLIB_OK = False

_NET_WM_STATE_ADD = 1
_NET_WM_STATE_REMOVE = 0

#: What the interface's own window is called. Raising it is how a backgrounded
#: game stops covering the screen — see `hide()`.
#:
#: Electron derives WM_CLASS from the `name` in electron/package.json, so these
#: are not free-form: `gamecore-electron` is that name and the rest are the
#: shapes a window manager may report it in. Matched case-insensitively, which
#: covers the capitalised second half of the WM_CLASS pair. A test pins the
#: package name to this tuple — get it wrong and nothing raises, the interface
#: simply stays under a frozen game, which is a symptom nobody would connect
#: back to a rename.
SHELL_WM_CLASSES = ("gamecore", "gamecore-electron", "GameCore")


def _open():
    env = _display_env()
    for key in ("DISPLAY", "XAUTHORITY"):
        if env.get(key):
            os.environ.setdefault(key, env[key])
    return xdisplay.Display(env.get("DISPLAY"))


def _client_windows(disp):
    root = disp.screen().root
    prop = root.get_full_property(disp.intern_atom("_NET_CLIENT_LIST"), 0)
    if not (prop and prop.value):
        return
    for wid in prop.value:
        try:
            yield disp.create_resource_object("window", wid)
        except Exception:
            continue


def _pids_of(pgid: int) -> set[int]:
    """Every pid in the process group, so a window can be matched to a session.

    `_NET_WM_PID` names the process that owns the window, and for a Flatpak
    emulator that is the application deep inside the sandbox — not the `flatpak`
    wrapper the launcher knows about. The group is the link between them: the
    measurement on the reference box showed all five sandbox processes sharing
    one group, so the window's pid is always one of these.
    """
    pids: set[int] = set()
    try:
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            try:
                if os.getpgid(int(entry)) == pgid:
                    pids.add(int(entry))
            except (OSError, ProcessLookupError):
                continue
    except OSError:
        pass
    return pids


def _window_pid(disp, win) -> int:
    try:
        prop = win.get_full_property(disp.intern_atom("_NET_WM_PID"), 0)
        return int(prop.value[0]) if prop and prop.value else 0
    except Exception:
        return 0


def _find_by_pids(disp, pids: set[int]):
    for win in _client_windows(disp):
        if _window_pid(disp, win) in pids:
            return win
    return None


def _find_by_class(disp, wm_classes) -> object | None:
    targets = {c.lower() for c in wm_classes}
    for win in _client_windows(disp):
        try:
            cls = win.get_wm_class()
        except Exception:
            continue
        if cls and any(c.lower() in targets for c in cls):
            return win
    return None


def _send(disp, win, type_name: str, data: list[int]) -> None:
    root = disp.screen().root
    msg = xevent.ClientMessage(window=win,
                               client_type=disp.intern_atom(type_name),
                               data=(32, data))
    root.send_event(msg, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
    disp.flush()


def _activate(disp, win) -> None:
    """Raise, focus, and put fullscreen back on.

    All three, because they are three different things and a resumed game
    needs all of them: `_NET_ACTIVE_WINDOW` raises and focuses,
    `_NET_WM_STATE_FULLSCREEN` is re-asserted because a compositor that
    un-fullscreened the frozen window while it was behind would otherwise give
    the player their game back in a small box in the corner.
    """
    # 2 = the request comes from a pager, which is the source WMs honour
    # without applying focus-stealing prevention to it.
    _send(disp, win, "_NET_ACTIVE_WINDOW", [2, X.CurrentTime, 0, 0, 0])
    _send(disp, win, "_NET_WM_STATE",
          [_NET_WM_STATE_ADD, disp.intern_atom("_NET_WM_STATE_FULLSCREEN"), 0, 1, 0])


def _activate_sync(system_id: str, pgid: int) -> bool:
    disp = _open()
    try:
        win = _find_by_pids(disp, _pids_of(pgid)) if pgid else None
        if win is None:
            log.info("window_focus[%s]: no window found for pgid %s", system_id, pgid)
            return False
        _activate(disp, win)
        log.info("window_focus[%s]: resumed window raised", system_id)
        return True
    finally:
        disp.close()


def _hide_sync(system_id: str, pgid: int) -> bool:
    """Put the interface in front of a session that has just been frozen.

    The frozen window is NOT unmapped or iconified. Both are requests the
    client would have to co-operate with on the way back — an SDL or Vulkan
    application handles an unmap by tearing down its swapchain, and asking a
    stopped process to do that leaves it half-way through the teardown until it
    is resumed. Raising the interface *over* it changes nothing inside the
    frozen client at all, which is the only thing here that is certainly safe.
    """
    disp = _open()
    try:
        shell = _find_by_class(disp, SHELL_WM_CLASSES)
        if shell is None:
            log.info("window_focus[%s]: the interface's own window was not "
                     "found — the suspended game may stay on top", system_id)
            return False
        # Fullscreen is dropped from the frozen window rather than added to the
        # interface: two fullscreen windows on one output is a stacking fight
        # some compositors resolve by keeping the older one on top.
        frozen = _find_by_pids(disp, _pids_of(pgid)) if pgid else None
        if frozen is not None:
            _send(disp, frozen, "_NET_WM_STATE",
                  [_NET_WM_STATE_REMOVE,
                   disp.intern_atom("_NET_WM_STATE_FULLSCREEN"), 0, 1, 0])
        _send(disp, shell, "_NET_ACTIVE_WINDOW", [2, X.CurrentTime, 0, 0, 0])
        log.info("window_focus[%s]: interface raised over the frozen session",
                 system_id)
        return True
    finally:
        disp.close()


async def activate(system_id: str, pgid: int) -> bool:
    """Bring a resumed session's window back to the front."""
    if not _XLIB_OK:
        log.info("window_focus: python-xlib unavailable — skipping")
        return False
    try:
        return await asyncio.to_thread(_activate_sync, system_id, pgid)
    except Exception as e:
        log.warning("window_focus[%s]: %s", system_id, e)
        return False


async def hide(system_id: str, pgid: int) -> bool:
    """Raise the interface over a session that has just been suspended."""
    if not _XLIB_OK:
        log.info("window_focus: python-xlib unavailable — skipping")
        return False
    try:
        return await asyncio.to_thread(_hide_sync, system_id, pgid)
    except Exception as e:
        log.warning("window_focus[%s]: %s", system_id, e)
        return False
