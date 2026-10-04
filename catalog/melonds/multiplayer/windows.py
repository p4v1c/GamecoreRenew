"""Place the melonDS instance windows side by side (X11, ctypes, stdlib only).

melonDS titles each window "[pN] ..." as soon as a second instance exists, so
the player number is read from the title, never from creation order.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import re
import time

# Two DS screens stacked: 256 x 384.
DS_WIDTH, DS_HEIGHT = 2, 3
_TITLE_RE = re.compile(r"^\[p(\d+)\]")
_ANY_PROPERTY_TYPE = 0
_MWM_HINTS_DECORATIONS = 2
XK_F11 = 0xFFC8
_KEY_PRESS, _KEY_RELEASE, _CLIENT_MESSAGE = 2, 3, 33
_KEY_MASKS = 1 | 2                       # KeyPressMask | KeyReleaseMask
_WM_REDIRECT = (1 << 19) | (1 << 20)     # SubstructureNotify | SubstructureRedirect
_NET_WM_STATE_REMOVE = 0
_SOURCE_PAGER = 2        # EWMH: a request the WM must not treat as focus stealing
_REVERT_TO_PARENT = 2
# melonDS samples hotkeys once per emulated frame; a press shorter than a frame
# (or a slowed-down one) is never seen.
KEY_HOLD = 0.15


def columns(players: int, screen_w: int, screen_h: int) -> list[tuple[int, int, int, int]]:
    """(x, y, w, h) per player: touching columns in the DS shape, as large as
    the screen allows, the block centred. The menu bar is hidden."""
    width = min(screen_w // players, screen_h * DS_WIDTH // DS_HEIGHT)
    height = min(screen_h, width * DS_HEIGHT // DS_WIDTH)
    left = (screen_w - width * players) // 2
    top = (screen_h - height) // 2
    return [(left + i * width, top, width, height) for i in range(players)]


class _KeyEvent(ctypes.Structure):
    _fields_ = [("type", ctypes.c_int), ("serial", ctypes.c_ulong),
                ("send_event", ctypes.c_int), ("display", ctypes.c_void_p),
                ("window", ctypes.c_ulong), ("root", ctypes.c_ulong),
                ("subwindow", ctypes.c_ulong), ("time", ctypes.c_ulong),
                ("x", ctypes.c_int), ("y", ctypes.c_int),
                ("x_root", ctypes.c_int), ("y_root", ctypes.c_int),
                ("state", ctypes.c_uint), ("keycode", ctypes.c_uint),
                ("same_screen", ctypes.c_int)]


class _ClientMessage(ctypes.Structure):
    _fields_ = [("type", ctypes.c_int), ("serial", ctypes.c_ulong),
                ("send_event", ctypes.c_int), ("display", ctypes.c_void_p),
                ("window", ctypes.c_ulong), ("message_type", ctypes.c_ulong),
                ("format", ctypes.c_int), ("data", ctypes.c_long * 5)]


class _Event(ctypes.Union):
    """XEvent: every event shares one 24-long buffer."""
    _fields_ = [("key", _KeyEvent), ("client", _ClientMessage), ("pad", ctypes.c_long * 24)]


def player_of(title: str) -> int | None:
    m = _TITLE_RE.match(title)
    return int(m.group(1)) if m else None


class X11:
    """The handful of Xlib calls this needs."""

    def __init__(self):
        name = ctypes.util.find_library("X11") or "libX11.so.6"
        self.lib = lib = ctypes.CDLL(name)
        lib.XOpenDisplay.restype = ctypes.c_void_p
        lib.XOpenDisplay.argtypes = [ctypes.c_char_p]
        lib.XDefaultRootWindow.restype = ctypes.c_ulong
        lib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        lib.XInternAtom.restype = ctypes.c_ulong
        lib.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        lib.XGetWindowProperty.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_long,
            ctypes.c_long, ctypes.c_int, ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.c_void_p)]
        lib.XQueryTree.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_uint)]
        lib.XChangeProperty.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong,
            ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_int]
        lib.XMoveResizeWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong,
                                          ctypes.c_int, ctypes.c_int,
                                          ctypes.c_uint, ctypes.c_uint]
        lib.XFree.argtypes = [ctypes.c_void_p]
        lib.XFlush.argtypes = [ctypes.c_void_p]
        lib.XCloseDisplay.argtypes = [ctypes.c_void_p]
        lib.XSendEvent.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int,
                                   ctypes.c_long, ctypes.POINTER(_Event)]
        lib.XSetInputFocus.argtypes = [ctypes.c_void_p, ctypes.c_ulong,
                                       ctypes.c_int, ctypes.c_ulong]
        lib.XKeysymToKeycode.restype = ctypes.c_ubyte
        lib.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        lib.XDisplayWidth.argtypes = [ctypes.c_void_p, ctypes.c_int]
        lib.XDisplayHeight.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.dpy = lib.XOpenDisplay(None)
        if not self.dpy:
            raise OSError("cannot open the X display")
        self.root = lib.XDefaultRootWindow(self.dpy)

    def close(self) -> None:
        self.lib.XCloseDisplay(self.dpy)

    def atom(self, name: str) -> int:
        return self.lib.XInternAtom(self.dpy, name.encode(), 0)

    def screen_size(self) -> tuple[int, int]:
        return self.lib.XDisplayWidth(self.dpy, 0), self.lib.XDisplayHeight(self.dpy, 0)

    def _property(self, win: int, name: str) -> tuple[int, bytes]:
        """(format, raw bytes) of a window property; (0, b'') when unset."""
        kind, fmt = ctypes.c_ulong(), ctypes.c_int()
        count, after, data = ctypes.c_ulong(), ctypes.c_ulong(), ctypes.c_void_p()
        status = self.lib.XGetWindowProperty(
            self.dpy, win, self.atom(name), 0, 1 << 16, 0, _ANY_PROPERTY_TYPE,
            ctypes.byref(kind), ctypes.byref(fmt), ctypes.byref(count),
            ctypes.byref(after), ctypes.byref(data))
        if status != 0 or not data.value:
            return 0, b""
        # Format 32 is stored as C longs, whatever their size.
        unit = {8: 1, 16: 2, 32: ctypes.sizeof(ctypes.c_long)}.get(fmt.value, 1)
        raw = ctypes.string_at(data.value, count.value * unit)
        self.lib.XFree(data)
        return fmt.value, raw

    def title(self, win: int) -> str:
        for name in ("_NET_WM_NAME", "WM_NAME"):
            _fmt, raw = self._property(win, name)
            if raw:
                return raw.decode("utf-8", "replace")
        return ""

    def top_windows(self) -> list[int]:
        """Managed client windows (EWMH), or the root's children with no WM."""
        fmt, raw = self._property(self.root, "_NET_CLIENT_LIST")
        if fmt == 32 and raw:
            n = len(raw) // ctypes.sizeof(ctypes.c_ulong)
            return list((ctypes.c_ulong * n).from_buffer_copy(raw))
        root, parent = ctypes.c_ulong(), ctypes.c_ulong()
        kids, count = ctypes.c_void_p(), ctypes.c_uint()
        if not self.lib.XQueryTree(self.dpy, self.root, ctypes.byref(root),
                                   ctypes.byref(parent), ctypes.byref(kids),
                                   ctypes.byref(count)):
            return []
        wins = list((ctypes.c_ulong * count.value).from_address(kids.value)) if kids.value else []
        if kids.value:
            self.lib.XFree(kids)
        return wins

    def send_key(self, win: int, keysym: int, kind: int) -> None:
        """A core key event straight to `win`; Qt takes it from any origin."""
        ev = _Event()
        ev.key.type, ev.key.window, ev.key.root = kind, win, self.root
        ev.key.keycode = self.lib.XKeysymToKeycode(self.dpy, keysym)
        ev.key.same_screen = 1
        self.lib.XSendEvent(self.dpy, win, 1, _KEY_MASKS, ctypes.byref(ev))
        self.lib.XFlush(self.dpy)

    def activate(self, win: int) -> None:
        """Give `win` the keyboard: Qt drops key events sent to an inactive
        window under a WM. EWMH request for the WM, direct focus without one."""
        ev = _Event()
        ev.client.type, ev.client.window, ev.client.format = _CLIENT_MESSAGE, win, 32
        ev.client.message_type = self.atom("_NET_ACTIVE_WINDOW")
        ev.client.data[0] = _SOURCE_PAGER
        self.lib.XSendEvent(self.dpy, self.root, 0, _WM_REDIRECT, ctypes.byref(ev))
        self.lib.XSetInputFocus(self.dpy, win, _REVERT_TO_PARENT, 0)
        self.lib.XFlush(self.dpy)

    def leave_fullscreen(self, win: int) -> None:
        """Ask the WM to drop fullscreen (EWMH: a ClientMessage to the root)."""
        ev = _Event()
        ev.client.type, ev.client.window, ev.client.format = _CLIENT_MESSAGE, win, 32
        ev.client.message_type = self.atom("_NET_WM_STATE")
        ev.client.data[0] = _NET_WM_STATE_REMOVE
        ev.client.data[1] = self.atom("_NET_WM_STATE_FULLSCREEN")
        ev.client.data[3] = 1
        self.lib.XSendEvent(self.dpy, self.root, 0, _WM_REDIRECT, ctypes.byref(ev))
        self.lib.XFlush(self.dpy)

    def place(self, win: int, x: int, y: int, w: int, h: int) -> None:
        """Drop the WM frame so columns touch, then move and size."""
        hints = (ctypes.c_long * 5)(_MWM_HINTS_DECORATIONS, 0, 0, 0, 0)
        motif = self.atom("_MOTIF_WM_HINTS")
        self.lib.XChangeProperty(self.dpy, win, motif, motif, 32, 0, hints, 5)
        self.lib.XMoveResizeWindow(self.dpy, win, x, y, w, h)
        self.lib.XFlush(self.dpy)


def melonds_windows(x11: X11) -> dict[int, int]:
    """player number → window, for every titled melonDS instance window."""
    found: dict[int, int] = {}
    for win in x11.top_windows():
        player = player_of(x11.title(win))
        if player is not None and "melonDS" in x11.title(win):
            found[player] = win
    return found


def press_fullscreen_key(player: int) -> bool:
    """Send F11 (melonDS's fullscreen hotkey, set by setup.py) to one player's
    window: the only path that makes melonDS hide its menu bar. `tile` then
    takes the window out of fullscreen. False when the window is not there."""
    x11 = X11()
    try:
        win = melonds_windows(x11).get(player)
        if win is None:
            return False
        x11.activate(win)
        time.sleep(KEY_HOLD)
        for kind in (_KEY_PRESS, _KEY_RELEASE):
            x11.send_key(win, XK_F11, kind)
            time.sleep(KEY_HOLD)
        return True
    finally:
        x11.close()


def tile(players: int) -> int:
    """Place every instance window that exists. Returns how many were placed."""
    x11 = X11()
    try:
        wins = melonds_windows(x11)
        slots = columns(players, *x11.screen_size())
        placed = 0
        for player, win in wins.items():
            if 1 <= player <= players:
                x11.leave_fullscreen(win)
                x11.place(win, *slots[player - 1])
                placed += 1
        return placed
    finally:
        x11.close()
