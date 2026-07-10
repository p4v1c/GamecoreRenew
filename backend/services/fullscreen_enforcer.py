"""Force apps that lack a fullscreen CLI flag into fullscreen via EWMH.

Some tiles in config/apps.json launch programs with no way to request
fullscreen on the command line (Stremio has none at all). For those, the
entry carries a "fullscreen" block:

    "fullscreen": { "wm_class": ["stremio", "Stremio"], "timeout_s": 60 }

/games/launch fires enforce() as a background task: it waits for a window
whose WM_CLASS matches, then asks the window manager to fullscreen it with
a _NET_WM_STATE client message (the EWMH way — honored by openbox, KWin,
and every other EWMH WM, including XWayland windows).

X11/XWayland only: silently does nothing when python-xlib is missing or
no X display is reachable.
"""
import asyncio
import logging
import os
import time

from .process_manager import _display_env

log = logging.getLogger(__name__)

try:
    from Xlib import X, display as xdisplay
    from Xlib.protocol import event as xevent
    _XLIB_OK = True
except ImportError:
    _XLIB_OK = False

_NET_WM_STATE_ADD = 1


def _iter_client_windows(disp):
    root = disp.screen().root
    atom = disp.intern_atom("_NET_CLIENT_LIST")
    prop = root.get_full_property(atom, 0)
    if not (prop and prop.value):
        return
    for wid in prop.value:
        try:
            yield disp.create_resource_object("window", wid)
        except Exception:
            continue


def _find_window(disp, wm_classes: list[str]):
    targets = {c.lower() for c in wm_classes}
    for win in _iter_client_windows(disp):
        try:
            cls = win.get_wm_class()
            if cls and any(c.lower() in targets for c in cls):
                return win
        except Exception:
            continue
    return None


def _is_fullscreen(disp, win) -> bool:
    try:
        state = win.get_full_property(disp.intern_atom("_NET_WM_STATE"), 0)
        return bool(state) and disp.intern_atom("_NET_WM_STATE_FULLSCREEN") in (state.value or [])
    except Exception:
        return False


def _request_fullscreen(disp, win) -> None:
    """Ask the WM to add _NET_WM_STATE_FULLSCREEN (EWMH client message)."""
    root = disp.screen().root
    msg = xevent.ClientMessage(
        window=win,
        client_type=disp.intern_atom("_NET_WM_STATE"),
        data=(32, [_NET_WM_STATE_ADD,
                   disp.intern_atom("_NET_WM_STATE_FULLSCREEN"),
                   0, 1, 0]),
    )
    root.send_event(msg, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
    disp.flush()


def _enforce_sync(system_id: str, wm_classes: list[str], timeout_s: float) -> None:
    # The backend runs from systemd without X in its own environment —
    # borrow the same DISPLAY/XAUTHORITY resolution used to launch the app.
    env = _display_env()
    for key in ("DISPLAY", "XAUTHORITY"):
        if env.get(key):
            os.environ.setdefault(key, env[key])

    disp = xdisplay.Display(env.get("DISPLAY"))
    try:
        deadline = time.time() + timeout_s
        win = None
        while time.time() < deadline:
            win = _find_window(disp, wm_classes)
            if win:
                break
            time.sleep(0.5)
        if not win:
            log.warning("fullscreen_enforcer[%s]: no window matching %s after %ss",
                        system_id, wm_classes, timeout_s)
            return

        # A request can land while the app is still mapping its window and
        # get lost — re-send until the WM reports the state (or we give up).
        for _ in range(10):
            if _is_fullscreen(disp, win):
                log.info("fullscreen_enforcer[%s]: window is fullscreen", system_id)
                return
            _request_fullscreen(disp, win)
            time.sleep(1.0)
        log.warning("fullscreen_enforcer[%s]: window never reported fullscreen", system_id)
    finally:
        disp.close()


async def enforce(system_id: str, cfg: dict) -> None:
    """Fire-and-forget: fullscreen the launched app's window once it appears."""
    if not _XLIB_OK:
        log.info("fullscreen_enforcer: python-xlib unavailable — skipping")
        return
    wm_classes = cfg.get("wm_class") or []
    if not wm_classes:
        return
    timeout_s = float(cfg.get("timeout_s", 45))
    try:
        await asyncio.to_thread(_enforce_sync, system_id, wm_classes, timeout_s)
    except Exception as e:
        log.warning("fullscreen_enforcer[%s]: %s", system_id, e)
