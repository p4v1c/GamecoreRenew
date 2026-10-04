"""Place the melonDS instance windows side by side (X11, ctypes, stdlib only).

melonDS titles each window "[pN] ..." as soon as a second instance exists, so
the player number is read from the title, never from creation order.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import re

# melonDS keeps its menu bar outside fullscreen; Breeze draws it ~30 px tall.
# An error here only adds a thin black bar: melonDS letterboxes the screens.
MENU_BAR_HEIGHT = 30
# Two DS screens stacked: 256 x 384.
DS_WIDTH, DS_HEIGHT = 2, 3
_TITLE_RE = re.compile(r"^\[p(\d+)\]")
_ANY_PROPERTY_TYPE = 0
_MWM_HINTS_DECORATIONS = 2


def columns(players: int, screen_w: int, screen_h: int,
            menu_h: int = MENU_BAR_HEIGHT) -> list[tuple[int, int, int, int]]:
    """(x, y, w, h) per player: touching columns, as wide as the DS aspect
    allows, the block centred on screen."""
    width = min(screen_w // players, (screen_h - menu_h) * DS_WIDTH // DS_HEIGHT)
    height = min(screen_h, menu_h + width * DS_HEIGHT // DS_WIDTH)
    left = (screen_w - width * players) // 2
    top = (screen_h - height) // 2
    return [(left + i * width, top, width, height) for i in range(players)]


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


def tile(players: int) -> int:
    """Place every instance window that exists. Returns how many were placed."""
    x11 = X11()
    try:
        wins = melonds_windows(x11)
        slots = columns(players, *x11.screen_size())
        placed = 0
        for player, win in wins.items():
            if 1 <= player <= players:
                x11.place(win, *slots[player - 1])
                placed += 1
        return placed
    finally:
        x11.close()
