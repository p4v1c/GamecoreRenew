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
