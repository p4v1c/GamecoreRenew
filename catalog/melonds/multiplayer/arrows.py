"""One on-screen arrow per player, drawn as a tiny shaped X window wearing the
box's own cursor theme (cursor_theme.py).

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

import cursor_theme
from windows import X11

# The classic arrow, tip at (0, 0), drawn on a 16 x 25 grid and scaled:
# a desktop-sized arrow is lost on a TV seen from the sofa.
SCALE = 2
OUTLINE = [(x * SCALE, y * SCALE) for x, y in
           [(0, 0), (0, 21), (5, 16), (9, 24), (12, 23), (8, 15), (15, 15)]]
INNER = [(x * SCALE, y * SCALE) for x, y in
         [(1, 2), (1, 18), (5, 14), (9, 22), (11, 21), (7, 14), (12, 14)]]
SIZE = (16 * SCALE, 25 * SCALE)
# One look for every player, the classic white arrow: each stays in its own
# column anyway (owner's choice over per-player colours).
FILL_COLOUR = 0xFFFFFF
OUTLINE_COLOUR = 0x000000

_CW_OVERRIDE_REDIRECT = 1 << 9
_Z_PIXMAP, _COORD_MODE_ORIGIN = 2, 0
# A theme pixel this opaque is part of the arrow; softer edges are dropped,
# since a shaped window is all-or-nothing.
_ALPHA_SOLID = 128
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
        ulong_p, int_p = ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_int)
        lib.XQueryPointer.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ulong_p, ulong_p, int_p,
                                      int_p, int_p, int_p, ctypes.POINTER(ctypes.c_uint)]
        ext.XShapeCombineMask.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int,
                                          ctypes.c_int, ctypes.c_int, ctypes.c_ulong, ctypes.c_int]
        ext.XShapeCombineRectangles.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int,
                                                ctypes.c_int, ctypes.c_int, ctypes.c_void_p,
                                                ctypes.c_int, ctypes.c_int, ctypes.c_int]
        lib.XDrawPoints.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p,
                                    ctypes.POINTER(_Point), ctypes.c_int, ctypes.c_int]
        lib.XDefaultVisual.restype = ctypes.c_void_p
        lib.XDefaultVisual.argtypes = [ctypes.c_void_p, ctypes.c_int]
        lib.XCreateImage.restype = ctypes.c_void_p
        lib.XCreateImage.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_int,
                                     ctypes.c_int, ctypes.c_char_p, ctypes.c_uint, ctypes.c_uint,
                                     ctypes.c_int, ctypes.c_int]
        lib.XPutImage.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p,
                                  ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_uint, ctypes.c_uint]
        self.windows: dict[int, int] = {}
        # The box's own pointer look (owner's theme); None: the drawn arrow.
        self.image = cursor_theme.load_arrow()
        self.hot = (self.image.hot_x, self.image.hot_y) if self.image else (0, 0)

    def _polygon(self, drawable, gc, colour, polygon) -> None:
        pts, n = _points(polygon)
        self.x11.lib.XSetForeground(self.x11.dpy, gc, colour)
        self.x11.lib.XFillPolygon(self.x11.dpy, drawable, gc, pts, n, _COMPLEX, _COORD_ORIGIN)

    def show(self, player: int, x: int, y: int) -> None:
        """Create player N's arrow, tip at (x, y)."""
        lib, dpy = self.x11.lib, self.x11.dpy
        w, h = (self.image.width, self.image.height) if self.image else SIZE
        attrs = _SetWindowAttributes(override_redirect=1)
        win = lib.XCreateWindow(dpy, self.x11.root, x - self.hot[0], y - self.hot[1], w, h,
                                0, 0, 0, None, _CW_OVERRIDE_REDIRECT, ctypes.byref(attrs))
        mask = lib.XCreatePixmap(dpy, win, w, h, 1)
        art = lib.XCreatePixmap(dpy, win, w, h, lib.XDefaultDepth(dpy, 0))
        if self.image:
            self._paint_theme(mask, art)
        else:
            self._paint_drawn(mask, art, w, h)
        self.ext.XShapeCombineMask(dpy, win, _SHAPE_BOUNDING, 0, 0, mask, _SHAPE_SET)
        # No input region: touches and clicks fall through to the DS.
        self.ext.XShapeCombineRectangles(dpy, win, _SHAPE_INPUT, 0, 0, None, 0, _SHAPE_SET, 0)
        lib.XSetWindowBackgroundPixmap(dpy, win, art)   # the server repaints it
        lib.XFreePixmap(dpy, mask)
        lib.XFreePixmap(dpy, art)
        lib.XMapRaised(dpy, win)
        lib.XFlush(dpy)
        self.windows[player] = win

    def _paint_drawn(self, mask, art, w, h) -> None:
        lib, dpy = self.x11.lib, self.x11.dpy
        gc = lib.XCreateGC(dpy, mask, 0, None)
        lib.XSetForeground(dpy, gc, 0)
        lib.XFillRectangle(dpy, mask, gc, 0, 0, w, h)
        self._polygon(mask, gc, 1, OUTLINE)
        lib.XFreeGC(dpy, gc)
        gc = lib.XCreateGC(dpy, art, 0, None)
        self._polygon(art, gc, OUTLINE_COLOUR, OUTLINE)
        self._polygon(art, gc, FILL_COLOUR, INNER)
        lib.XFreeGC(dpy, gc)

    def _paint_theme(self, mask, art) -> None:
        lib, dpy, img = self.x11.lib, self.x11.dpy, self.image
        gc = lib.XCreateGC(dpy, mask, 0, None)
        lib.XSetForeground(dpy, gc, 0)
        lib.XFillRectangle(dpy, mask, gc, 0, 0, img.width, img.height)
        solid = [(i % img.width, i // img.width) for i in range(img.width * img.height)
                 if img.argb[i * 4 + 3] >= _ALPHA_SOLID]
        if solid:
            pts, n = _points(solid)
            lib.XSetForeground(dpy, gc, 1)
            lib.XDrawPoints(dpy, mask, gc, pts, n, _COORD_MODE_ORIGIN)
        lib.XFreeGC(dpy, gc)
        # 32-bit ZPixmap: Xcursor's little-endian ARGB words are the server's layout.
        self._pixels = ctypes.create_string_buffer(img.argb, len(img.argb))
        ximage = lib.XCreateImage(dpy, lib.XDefaultVisual(dpy, 0), lib.XDefaultDepth(dpy, 0),
                                  _Z_PIXMAP, 0, self._pixels, img.width, img.height, 32, 0)
        gc = lib.XCreateGC(dpy, art, 0, None)
        lib.XPutImage(dpy, art, gc, ximage, 0, 0, 0, 0, img.width, img.height)
        lib.XFreeGC(dpy, gc)
        lib.XFree(ximage)                        # the pixels stay ours

    def move(self, player: int, x: int, y: int) -> None:
        win = self.windows.get(player)
        if win:
            self.x11.lib.XMoveWindow(self.x11.dpy, win, x - self.hot[0], y - self.hot[1])

    def raise_all(self) -> None:
        """A game window raised later would hide the arrows. Done now and
        then, not on every move: each raise makes the compositor restack."""
        for win in self.windows.values():
            self.x11.lib.XRaiseWindow(self.x11.dpy, win)

    def flush(self) -> None:
        self.x11.lib.XFlush(self.x11.dpy)

    def park_system_pointer(self, width: int, height: int) -> bool:
        """Put X's own arrow on the last pixel, drawn off screen, unless it is
        there already. True once it is. The players' touch screens drive the
        core pointer, so each touch leaves it at the touch point; hiding it
        (XFixesHideCursor) did not hold on the box, unclutter runs too."""
        lib, dpy = self.x11.lib, self.x11.dpy
        root_x, root_y = ctypes.c_int(), ctypes.c_int()
        other, mask = ctypes.c_int(), ctypes.c_uint()
        child, root = ctypes.c_ulong(), ctypes.c_ulong()
        lib.XQueryPointer(dpy, self.x11.root, ctypes.byref(root), ctypes.byref(child),
                          ctypes.byref(root_x), ctypes.byref(root_y), ctypes.byref(other),
                          ctypes.byref(other), ctypes.byref(mask))
        if (root_x.value, root_y.value) == (width - 1, height - 1):
            return True
        lib.XWarpPointer(dpy, 0, self.x11.root, 0, 0, 0, 0, width - 1, height - 1)
        lib.XFlush(dpy)
        return False

    def close(self) -> None:
        for win in self.windows.values():
            self.x11.lib.XDestroyWindow(self.x11.dpy, win)
        self.windows.clear()
        self.x11.lib.XFlush(self.x11.dpy)
