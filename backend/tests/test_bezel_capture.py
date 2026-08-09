"""Believing the screen — and, mostly, refusing to.

A bezel's hole is cut for the ratio a system is supposed to render at, and the
emulator does not always oblige. The only witness is what is on screen, so a
frame is captured a second into the game and the drawn region measured out of
it.

That measurement is a guess about a moving picture, and this file is mostly
about the ways it is wrong. A wrong correction is worse than none: it moves a
hole that was right, and the player sees a frame drift across their game with
nothing to explain it. So the interesting tests here are the refusals — the
loading screen, the logo, the fade, the menu — and each of them is a frame that
`content_bbox` happily measures a perfectly good rectangle out of.

The X11 capture itself is NOT exercised here and cannot be: it needs a screen
and a running emulator. What is exercised is every rule applied to what it
brings back, which is where the decisions are.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.services import bezel_capture as cap, paths        # noqa: E402


# ── A frame, built the way X hands one over ─────────────────────────────────

def frame(w: int, h: int, lit: tuple[int, int, int, int] | None,
          *, bpp: int = 4, stride: int | None = None, level: int = 200) -> bytes:
    """Black, with one lit rectangle. `stride` may exceed the row's pixels —
    X pads rows, and a measurement that assumed otherwise would read a picture
    sheared diagonally across the frame."""
    stride = stride if stride is not None else w * bpp
    out = bytearray()
    for y in range(h):
        row = bytearray(stride)
        if lit and lit[1] <= y < lit[1] + lit[3]:
            for x in range(lit[0], lit[0] + lit[2]):
                p = x * bpp
                row[p] = row[p + 1] = row[p + 2] = level
        out += row
    return bytes(out)


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "GAMECORE_ROOT", tmp_path)
    monkeypatch.setattr(paths, "GAMECORE_DATA", tmp_path)
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    yield tmp_path


# ── Measuring one frame ─────────────────────────────────────────────────────

def test_a_pillarboxed_picture_is_measured(store):
    """4:3 inside a 16:9 window — the case the whole feature exists for."""
    px = frame(1920, 1080, (240, 0, 1440, 1080))
    assert cap.content_bbox(px, 1920, 1080, 1920 * 4) == (240, 0, 1440, 1080)


def test_a_letterboxed_picture_is_measured(store):
    px = frame(1920, 1080, (0, 120, 1920, 840))
    assert cap.content_bbox(px, 1920, 1080, 1920 * 4) == (0, 120, 1920, 840)


def test_padded_rows_do_not_skew_the_measurement(store):
    """X pads scanlines to a word boundary. Reading `w * bpp` per row instead
    of `stride` walks diagonally through the image and measures a parallelogram
    — which still looks like a rectangle to everything downstream."""
    px = frame(100, 40, (20, 5, 60, 30), stride=100 * 4 + 12)
    assert cap.content_bbox(px, 100, 40, 100 * 4 + 12) == (20, 5, 60, 30)


def test_an_all_black_frame_measures_nothing(store):
    """A loading screen. None, not a zero-size box — the caller must be able to
    tell "nothing drawn" from "drawn at 0,0"."""
    assert cap.content_bbox(frame(320, 240, None), 320, 240, 320 * 4) is None


def test_a_very_dark_picture_still_counts_as_drawn(store):
    """The floor separates a letterbox bar from a night scene. Set too high, a
    dark game measures as its own HUD."""
    px = frame(64, 48, (8, 8, 48, 32), level=40)
    assert cap.content_bbox(px, 64, 48, 64 * 4) == (8, 8, 48, 32)


def test_a_truncated_capture_is_refused(store):
    """A GetImage that came back short. Measuring it would read past the end
    of the buffer or invent rows of black."""
    px = frame(64, 48, (8, 8, 48, 32))[:1000]
    assert cap.content_bbox(px, 64, 48, 64 * 4) is None


# ── Refusing to believe it ──────────────────────────────────────────────────

def test_a_logo_on_a_loading_screen_is_not_a_game(store):
    """It measures as a perfectly good centred rectangle. It is 4 % of the
    window, and correcting a hole to it would shrink the game to a stamp."""
    box = (860, 470, 200, 140)
    assert cap.content_bbox(frame(1920, 1080, box), 1920, 1080, 1920 * 4) == box
    assert not cap.is_plausible(box, 1920, 1080)


def test_a_full_window_measurement_has_nothing_to_correct(store):
    assert not cap.is_plausible((0, 0, 1920, 1080), 1920, 1080)


def test_a_picture_hard_against_one_edge_is_not_letterboxing(store):
    """Letterboxing is symmetric — whatever is trimmed left is trimmed right.
    A menu sliding in from the side is not, and neither is a fade."""
    assert not cap.is_plausible((0, 0, 1440, 1080), 1920, 1080)
    assert cap.is_plausible((240, 0, 1440, 1080), 1920, 1080)


def test_two_samples_must_agree(store):
    """A second in is very often a loading screen, and the frame after it is a
    different picture. One sample would learn whichever it happened to catch."""
    assert cap.agree((240, 0, 1440, 1080), (240, 0, 1440, 1080)) == (240, 0, 1440, 1080)
    assert cap.agree((240, 0, 1440, 1080), (0, 0, 1920, 1080)) is None
    assert cap.agree(None, (240, 0, 1440, 1080)) is None
    assert cap.agree((240, 0, 1440, 1080), None) is None


def test_samples_a_couple_of_pixels_apart_still_agree(store):
    """A scrolling edge moves by a pixel between frames. Demanding exactness
    would mean never learning anything on a game with motion at the border."""
    assert cap.agree((240, 0, 1440, 1080), (242, 0, 1438, 1080)) == (242, 0, 1438, 1080)


def test_a_difference_too_small_to_see_is_not_written_down(store):
    """Otherwise every launch rewrites the hole by a pixel and the cache never
    settles."""
    hole = {"x": 240, "y": 0, "w": 1440, "h": 1080}
    assert not cap.worth_applying((242, 1, 1438, 1079), hole)
    assert cap.worth_applying((0, 0, 1920, 1080), hole)


# ── Remembering it ──────────────────────────────────────────────────────────

def test_a_correction_is_filed_under_the_ratio_that_was_announced(store):
    """Keyed by ratio and not by pixel size: the same mismatch cut at two
    resolutions is one thing to learn."""
    assert cap.ratio_of({"x": 0, "y": 0, "w": 1440, "h": 1080}) == "4:3"
    assert cap.ratio_of({"x": 0, "y": 0, "w": 1920, "h": 1080}) == "16:9"
    assert cap.key_for("duckstation", {"x": 0, "y": 0, "w": 1440, "h": 1080}) \
        == "duckstation@4:3"


def test_a_learned_correction_comes_back(store):
    hole = {"x": 240, "y": 0, "w": 1440, "h": 1080}
    assert cap.correction_for("duckstation", hole) is None

    assert cap.record("duckstation", hole, (0, 120, 1920, 840))
    assert cap.correction_for("duckstation", hole) == {"x": 0, "y": 120,
                                                       "w": 1920, "h": 840}


def test_a_correction_does_not_leak_to_another_system_or_ratio(store):
    hole43 = {"x": 240, "y": 0, "w": 1440, "h": 1080}
    hole169 = {"x": 0, "y": 0, "w": 1920, "h": 1080}
    cap.record("duckstation", hole43, (0, 120, 1920, 840))

    assert cap.correction_for("pcsx2", hole43) is None
    assert cap.correction_for("duckstation", hole169) is None


def test_replacing_the_artwork_retires_the_old_answer(store):
    """A new bezel with a differently shaped hole is a different question, so
    it does not inherit the answer measured against the old one."""
    old = {"x": 240, "y": 0, "w": 1440, "h": 1080}          # 4:3
    cap.record("duckstation", old, (0, 120, 1920, 840))
    new = {"x": 240, "y": 52, "w": 1440, "h": 968}          # 180:121
    assert cap.correction_for("duckstation", new) is None


def test_a_zero_sized_hole_does_not_divide_by_zero(store):
    """`config/overlays.json` is hand-edited and excluded from the OTA rsync,
    so a nonsense hole on a box is not hypothetical."""
    assert cap.ratio_of({"x": 0, "y": 0, "w": 0, "h": 0}) == "0:0"


def test_an_unreadable_cache_is_not_fatal(store):
    """Whatever else happens, a game starts."""
    (store / "config" / "bezel-corrections.json").write_text("{ truncated")
    assert cap.corrections() == {}
    assert cap.correction_for("duckstation", {"x": 0, "y": 0, "w": 4, "h": 3}) is None
