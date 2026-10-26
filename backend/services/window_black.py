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


def _session_windows(disp, pgid: int, wm_classes: tuple[str, ...] = ()) -> list:
    """The session's windows, plus any of `wm_classes`: the pack's
    `launch.fullscreen.wmClass`, for a game that leaves the session's process
    group (FIFA22.exe under Lutris runs in its own, measured on the box)."""
    wins = {w.id: w for w in window_focus._find_all_by_pids(disp, window_focus._pids_of(pgid))}
    if wm_classes:
        wanted = {c.lower() for c in wm_classes}
        for w in window_focus._client_windows(disp):
            try:
                if wanted & {c.lower() for c in (w.get_wm_class() or ())}:
                    wins[w.id] = w
            except Exception:
                continue
    return list(wins.values())


def _game_window(disp, pgid: int, wm_classes: tuple[str, ...] = ()):
    """The session's biggest window: the game's, not a dialog or a tooltip."""
    best, area = None, 0
    for win in _session_windows(disp, pgid, wm_classes):
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


# The session's windows must cover this share of the screen: one fullscreen
# window, or melonDS's local multiplayer laid out as several.
COVERED = 0.95


def covers_screen(pgid: int, wm_classes: tuple[str, ...] = ()) -> bool | None:
    """True once the game's windows fill the screen: an emulator that maps a
    small window, then goes fullscreen, is caught between the two by nothing
    else (Dolphin, mGBA, Lutris's gamescope…). None when it cannot be told.

    `wm_classes`: see `_session_windows`."""
    if not window_focus._XLIB_OK or pgid <= 1:
        return None
    try:
        disp = window_focus._open()
    except Exception:
        return None
    try:
        root = disp.screen().root
        screen = root.get_geometry()
        area = 0
        for win in _session_windows(disp, pgid, wm_classes):
            try:
                if win.get_attributes().map_state != window_focus.X.IsViewable:
                    continue
                g = win.get_geometry()
                at = win.translate_coords(root, 0, 0)
            except Exception:
                continue
            # Only the part on the screen counts (translate_coords is negated).
            x0, y0 = max(0, -at.x), max(0, -at.y)
            x1, y1 = min(screen.width, -at.x + g.width), min(screen.height, -at.y + g.height)
            area += max(0, x1 - x0) * max(0, y1 - y0)
        return area >= COVERED * screen.width * screen.height
    except Exception:
        return None
    finally:
        disp.close()


# ── painted: the game draws at the window's size ─────────────────────────────
# A window can fill the screen before the game draws at that size: FIFA 22
# drew its old 1280x720 frame in a corner, Wine's unpainted rest grey then
# white, for ~3 s; Dolphin went black with stale pixels in a bottom band
# until its first frame (recorded on the box, 26/10).

CELLS = (48, 27)
# A light colour shared by this share of the picture is a surface nobody
# drew on (Wine's background), not a game frame.
BLOCK_SHARE = 0.4


def painted(img) -> bool:
    """True once a picture (PIL, RGB) looks drawn by the game at full size:
    something on it, not only in its outer band, and no large flat light block."""
    small = img.convert("RGB").resize(CELLS)
    w, h = CELLS
    px = list(small.getdata())
    lit = [i for i, p in enumerate(px) if max(p) > DARK]
    if not lit:
        return False
    if all(i % w in (0, w - 1) or i // w in (0, h - 1) for i in lit):
        return False
    counts: dict[tuple, int] = {}
    for p in px:
        if max(p) > 40:
            key = (p[0] // 16, p[1] // 16, p[2] // 16)
            counts[key] = counts.get(key, 0) + 1
    return not counts or max(counts.values()) < BLOCK_SHARE * len(px)


def is_painted(pgid: int, wm_classes: tuple[str, ...] = ()) -> bool | None:
    """`painted` on the game's own window, read under the cover; None when it
    cannot be told. One full grab: only while the cover waits, a few seconds."""
    if not window_focus._XLIB_OK or pgid <= 1:
        return None
    try:
        from PIL import Image
        disp = window_focus._open()
    except Exception:
        return None
    try:
        win = _game_window(disp, pgid, wm_classes)
        if win is None:
            return None
        g = win.get_geometry()
        raw = win.get_image(0, 0, g.width, g.height, window_focus.X.ZPixmap, 0xFFFFFFFF)
        return painted(Image.frombytes("RGB", (g.width, g.height), raw.data, "raw", "BGRX"))
    except Exception:
        return None
    finally:
        disp.close()
