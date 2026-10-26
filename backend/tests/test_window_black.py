"""window_black: a 5x5 grid of the game window's own pixels decides black."""
from __future__ import annotations

from types import SimpleNamespace

from backend.services import window_black


class FakeWindow:
    def __init__(self, paint):
        self.paint = paint     # (x, y) -> (r, g, b)

    def get_geometry(self):
        return SimpleNamespace(width=1920, height=1080)

    def get_image(self, x, y, w, h, fmt, mask):
        r, g, b = self.paint(x, y)
        return SimpleNamespace(data=bytes([b, g, r, 0]))     # BGRX


def _with_window(monkeypatch, win):
    monkeypatch.setattr(window_black.window_focus, "_XLIB_OK", True)
    monkeypatch.setattr(window_black.window_focus, "X", SimpleNamespace(ZPixmap=2), raising=False)
    monkeypatch.setattr(window_black.window_focus, "_open", lambda: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(window_black, "_game_window", lambda disp, pgid: win)


def test_black_with_a_line_of_small_text_is_black(monkeypatch):
    # God of War 3's copyright screen: one row of white text across black.
    _with_window(monkeypatch, FakeWindow(lambda x, y: (255, 255, 255) if y == 540 and x == 960 else (2, 2, 2)))
    assert window_black.is_black(4242) is True


def test_ryujinxs_grey_loading_screen_is_not_black(monkeypatch):
    _with_window(monkeypatch, FakeWindow(lambda x, y: (45, 45, 45)))
    assert window_black.is_black(4242) is False


def test_rpcs3s_loading_art_with_a_black_margin_is_not_black(monkeypatch):
    # Measured: the game's art on the right, black down the left fifth.
    _with_window(monkeypatch, FakeWindow(lambda x, y: (0, 0, 0) if x < 384 else (140, 30, 30)))
    assert window_black.is_black(4242) is False


def test_no_window_or_no_x_cannot_be_told(monkeypatch):
    _with_window(monkeypatch, None)
    assert window_black.is_black(4242) is None
    monkeypatch.setattr(window_black.window_focus, "_XLIB_OK", False)
    assert window_black.is_black(4242) is None


# ── covers_screen: the game's windows fill the screen ────────────────────────

class Placed:
    def __init__(self, x, y, w, h, viewable=True):
        self.x, self.y, self.w, self.h, self.viewable = x, y, w, h, viewable
        self.id = id(self)

    def get_attributes(self):
        return SimpleNamespace(map_state=2 if self.viewable else 0)

    def get_geometry(self):
        return SimpleNamespace(width=self.w, height=self.h)

    def translate_coords(self, src, x, y):
        return SimpleNamespace(x=-self.x, y=-self.y)


def _with_windows(monkeypatch, wins):
    root = SimpleNamespace(get_geometry=lambda: SimpleNamespace(width=1920, height=1080))
    disp = SimpleNamespace(close=lambda: None, screen=lambda: SimpleNamespace(root=root))
    monkeypatch.setattr(window_black.window_focus, "_XLIB_OK", True)
    monkeypatch.setattr(window_black.window_focus, "X", SimpleNamespace(IsViewable=2), raising=False)
    monkeypatch.setattr(window_black.window_focus, "_open", lambda: disp)
    monkeypatch.setattr(window_black.window_focus, "_pids_of", lambda pgid: {1})
    monkeypatch.setattr(window_black.window_focus, "_find_all_by_pids", lambda d, pids: wins)
    monkeypatch.setattr(window_black.window_focus, "_client_windows", lambda d: wins + others)


others: list = []


def test_a_small_window_about_to_go_fullscreen_does_not_cover(monkeypatch):
    _with_windows(monkeypatch, [Placed(640, 300, 640, 480)])
    assert window_black.covers_screen(4242) is False


def test_a_fullscreen_window_covers(monkeypatch):
    _with_windows(monkeypatch, [Placed(0, 0, 1920, 1080)])
    assert window_black.covers_screen(4242) is True


def test_melonds_side_by_side_windows_cover_together(monkeypatch):
    _with_windows(monkeypatch, [Placed(0, 0, 960, 1080), Placed(960, 0, 960, 1080), Placed(0, 0, 50, 50, viewable=False)])
    assert window_black.covers_screen(4242) is True


def test_a_window_spilling_off_screen_counts_only_what_shows(monkeypatch):
    _with_windows(monkeypatch, [Placed(1000, 0, 1920, 1080)])
    assert window_black.covers_screen(4242) is False


def test_a_game_outside_the_session_group_is_found_by_its_class(monkeypatch):
    # FIFA22.exe under Lutris: its own process group, the pack's wmClass names it.
    exe = Placed(0, 0, 1920, 1080)
    exe.get_wm_class = lambda: ("steam_app_default", "steam_app_default")
    _with_windows(monkeypatch, [])
    others.append(exe)
    try:
        assert window_black.covers_screen(4242) is False
        assert window_black.covers_screen(4242, ("steam_app_default",)) is True
    finally:
        others.clear()
