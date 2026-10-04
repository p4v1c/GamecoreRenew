"""One on-screen arrow per player, drawn as a tiny shaped X window.

Plain windows rather than X pointers: extra X pointers (XInput2 masters)
crash kwin_x11 when removed and Electron's GTK3 when added in a hurry. A
window is something every client already copes with, and the X server
destroys it with its owner, so a killed launcher leaves nothing behind.

The window is override-redirect (KWin leaves it alone), takes no input (a
touch under the tip goes to the DS below) and sits with its tip on the
player's touch point.
"""
from __future__ import annotations

import ctypes
import ctypes.util

from windows import X11

# The classic arrow, tip at (0, 0), drawn on a 16 x 25 grid and scaled:
# a desktop-sized arrow is lost on a TV seen from the sofa.
SCALE = 2
OUTLINE = [(x * SCALE, y * SCALE) for x, y in
           [(0, 0), (0, 21), (5, 16), (9, 24), (12, 23), (8, 15), (15, 15)]]
INNER = [(x * SCALE, y * SCALE) for x, y in
         [(1, 2), (1, 18), (5, 14), (9, 22), (11, 21), (7, 14), (12, 14)]]
SIZE = (16 * SCALE, 25 * SCALE)
# Player colours: red, blue, green, yellow, like the DS's own player marks.
COLOURS = {1: 0xE4202E, 2: 0x2A6FE8, 3: 0x2BB24C, 4: 0xF2C61F}
OUTLINE_COLOUR = 0x000000

_CW_OVERRIDE_REDIRECT = 1 << 9
_SHAPE_BOUNDING, _SHAPE_INPUT, _SHAPE_SET = 0, 2, 0
_COMPLEX, _COORD_ORIGIN = 0, 0


class _Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_short), ("y", ctypes.c_short)]


class _SetWindowAttributes(ctypes.Structure):
    _fields_ = [("background_pixmap", ctypes.c_ulong), ("background_pixel", ctypes.c_ulong),
                ("border_pixmap", ctypes.c_ulong), ("border_pixel", ctypes.c_ulong),
                ("bit_gravity", ctypes.c_int), ("win_gravity", ctypes.c_int),
                ("backing_store", ctypes.c_int), ("backing_planes", ctypes.c_ulong),
                ("backing_pixel", ctypes.c_ulong), ("save_under", ctypes.c_int),
                ("event_mask", ctypes.c_long), ("do_not_propagate_mask", ctypes.c_long),
                ("override_redirect", ctypes.c_int), ("colormap", ctypes.c_ulong),
                ("cursor", ctypes.c_ulong)]


def _points(polygon):
    return (_Point * len(polygon))(*[_Point(x, y) for x, y in polygon]), len(polygon)


class Arrows:
    """The players' arrows on one X connection."""

    def __init__(self, x11: X11):
        self.x11 = x11
        lib = x11.lib
        self.ext = ext = ctypes.CDLL(ctypes.util.find_library("Xext") or "libXext.so.6")
        lib.XCreateWindow.restype = ctypes.c_ulong
        lib.XCreateWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int,
                                      ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_int,
                                      ctypes.c_uint, ctypes.c_void_p, ctypes.c_ulong,
                                      ctypes.POINTER(_SetWindowAttributes)]
        lib.XCreatePixmap.restype = ctypes.c_ulong
        lib.XCreatePixmap.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_uint,
                                      ctypes.c_uint, ctypes.c_uint]
        lib.XCreateGC.restype = ctypes.c_void_p
        lib.XCreateGC.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p]
        lib.XSetForeground.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
        lib.XFillRectangle.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p,
                                       ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.c_uint]
        lib.XFillPolygon.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p,
                                     ctypes.POINTER(_Point), ctypes.c_int, ctypes.c_int, ctypes.c_int]
        lib.XFreeGC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        lib.XFreePixmap.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        lib.XSetWindowBackgroundPixmap.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong]
        lib.XMapRaised.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        lib.XMoveWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int]
        lib.XRaiseWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        lib.XDestroyWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        lib.XDefaultDepth.argtypes = [ctypes.c_void_p, ctypes.c_int]
        lib.XWarpPointer.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_int,
                                     ctypes.c_int, ctypes.c_uint, ctypes.c_uint, ctypes.c_int,
                                     ctypes.c_int]
        ext.XShapeCombineMask.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int,
                                          ctypes.c_int, ctypes.c_int, ctypes.c_ulong, ctypes.c_int]
        ext.XShapeCombineRectangles.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int,
                                                ctypes.c_int, ctypes.c_int, ctypes.c_void_p,
                                                ctypes.c_int, ctypes.c_int, ctypes.c_int]
        self.windows: dict[int, int] = {}

    def _polygon(self, drawable, gc, colour, polygon) -> None:
        pts, n = _points(polygon)
        self.x11.lib.XSetForeground(self.x11.dpy, gc, colour)
        self.x11.lib.XFillPolygon(self.x11.dpy, drawable, gc, pts, n, _COMPLEX, _COORD_ORIGIN)

    def show(self, player: int, x: int, y: int) -> None:
        """Create player N's arrow, tip at (x, y)."""
        lib, dpy, w, h = self.x11.lib, self.x11.dpy, *SIZE
        attrs = _SetWindowAttributes(override_redirect=1)
        win = lib.XCreateWindow(dpy, self.x11.root, x, y, w, h, 0, 0, 0, None,
                                _CW_OVERRIDE_REDIRECT, ctypes.byref(attrs))
        # Shape: the outline polygon, on a 1-bit mask.
        mask = lib.XCreatePixmap(dpy, win, w, h, 1)
        gc = lib.XCreateGC(dpy, mask, 0, None)
        lib.XSetForeground(dpy, gc, 0)
        lib.XFillRectangle(dpy, mask, gc, 0, 0, w, h)
        self._polygon(mask, gc, 1, OUTLINE)
        self.ext.XShapeCombineMask(dpy, win, _SHAPE_BOUNDING, 0, 0, mask, _SHAPE_SET)
        lib.XFreeGC(dpy, gc)
        lib.XFreePixmap(dpy, mask)
        # No input region: touches and clicks fall through to the DS.
        self.ext.XShapeCombineRectangles(dpy, win, _SHAPE_INPUT, 0, 0, None, 0, _SHAPE_SET, 0)
        # Picture: black outline, the player's colour inside; the server repaints it.
        art = lib.XCreatePixmap(dpy, win, w, h, lib.XDefaultDepth(dpy, 0))
        gc = lib.XCreateGC(dpy, art, 0, None)
        self._polygon(art, gc, OUTLINE_COLOUR, OUTLINE)
        self._polygon(art, gc, COLOURS.get(player, 0xFFFFFF), INNER)
        lib.XSetWindowBackgroundPixmap(dpy, win, art)
        lib.XFreeGC(dpy, gc)
        lib.XFreePixmap(dpy, art)
        lib.XMapRaised(dpy, win)
        lib.XFlush(dpy)
        self.windows[player] = win

    def move(self, player: int, x: int, y: int) -> None:
        win = self.windows.get(player)
        if win:
            # Raised on every move: a game window raised later would hide it.
            self.x11.lib.XMoveWindow(self.x11.dpy, win, x, y)
            self.x11.lib.XRaiseWindow(self.x11.dpy, win)
            self.x11.lib.XFlush(self.x11.dpy)

    def hide_system_pointer(self, width: int, height: int) -> None:
        """Send X's own arrow to the last pixel, where it is drawn off screen:
        with every mouse routed, nothing else would ever move it."""
        self.x11.lib.XWarpPointer(self.x11.dpy, 0, self.x11.root, 0, 0, 0, 0,
                                  width - 1, height - 1)
        self.x11.lib.XFlush(self.x11.dpy)

    def close(self) -> None:
        for win in self.windows.values():
            self.x11.lib.XDestroyWindow(self.x11.dpy, win)
        self.windows.clear()
        self.x11.lib.XFlush(self.x11.dpy)
