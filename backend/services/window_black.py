"""Is the game's own window showing black? Read off that window, under the cover.

The launch cover's hand-over (launch_ready.py): RPCS3 and Ryujinx keep their
own loading screen up after their log says the game runs, then go to black
before the game's first picture (measured on the reference box: God of War 3,
Animal Crossing). The window's own pixels are readable while the cover sits
over it: the compositor keeps them.

A grid of single pixels rather than the whole picture: a 1080p grab is 8 MB
for a yes or no.
"""
from __future__ import annotations

from . import window_focus

GRID = 5
# Max channel of a pixel that counts as black (JPEG-free, but games dither).
DARK = 24
# Small text on black (a copyright line) still reads as black.
SHARE = 0.9


def _game_window(disp, pgid: int):
    """The session's biggest window: the game's, not a dialog or a tooltip."""
    best, area = None, 0
    for win in window_focus._find_all_by_pids(disp, window_focus._pids_of(pgid)):
        try:
            g = win.get_geometry()
        except Exception:
            continue
        if g.width * g.height > area:
            best, area = win, g.width * g.height
    return best


def is_black(pgid: int) -> bool | None:
    """True or False, or None when it cannot be told (no X, no window yet)."""
    if not window_focus._XLIB_OK or pgid <= 1:
        return None
    try:
        disp = window_focus._open()
    except Exception:
        return None
    try:
        win = _game_window(disp, pgid)
        if win is None:
            return None
        g = win.get_geometry()
        points = [(int(g.width * (i + 0.5) / GRID), int(g.height * (j + 0.5) / GRID))
                  for i in range(GRID) for j in range(GRID)]
        dark = 0
        for x, y in points:
            px = win.get_image(x, y, 1, 1, window_focus.X.ZPixmap, 0xFFFFFFFF).data
            dark += max(px[0], px[1], px[2]) <= DARK
        return dark >= SHARE * len(points)
    except Exception:
        return None
    finally:
        disp.close()
