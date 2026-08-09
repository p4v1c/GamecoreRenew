"""The bezel cascade, and the hole measured out of a PNG's alpha channel.

Two things are proved here and they fail in opposite directions.

The cascade must not over-reach: a game with no bezel of its own takes the
system's, and a system with no bezel takes nothing at all. "Nothing" is the
one that matters — a fallback frame invented for a system nobody measured puts
black bars over a game that was filling the screen correctly, and from a sofa
that is indistinguishable from a broken emulator.

The measurement must not under-reach. The alpha decoder is hand-written, so
every one of the five PNG row filters is exercised against an image whose hole
is known by construction, and the whole thing is pinned against ImageMagick on
the assets this repository actually ships. A decoder that silently returns the
wrong rectangle draws a frame over the game — the same visible failure as the
cascade over-reaching, from the other end.
"""
from __future__ import annotations

import json
import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from backend.services import bezels, paths

SHIPPED_ASSETS = REPO / "assets" / "overlays"
OVERLAYS_JSON = REPO / "config" / "overlays.json"


# ── A PNG writer, so the fixtures are built rather than committed ───────────
#
# Bezel artwork is other people's box art and cannot live in this repository
# (same rule as BIOS files). Building the fixtures here also means the hole is
# known by construction instead of by having looked at a picture once.

def _encode(rows: list[bytearray], filt: int, bpp: int) -> bytes:
    """Forward-filter scanlines, so the decoder has something to undo."""
    out = bytearray()
    prev = bytearray(len(rows[0]))
    for raw in rows:
        out.append(filt)
        line = bytearray(len(raw))
        for i, v in enumerate(raw):
            a = raw[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            if filt == 0:
                pred = 0
            elif filt == 1:
                pred = a
            elif filt == 2:
                pred = b
            elif filt == 3:
                pred = (a + b) >> 1
            else:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if pa <= pb and pa <= pc else b if pb <= pc else c
            line[i] = (v - pred) & 255
        out += line
        prev = raw
    return bytes(out)


def _chunk(kind: bytes, body: bytes) -> bytes:
    return (struct.pack(">I", len(body)) + kind + body
            + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF))


def write_png(path: Path, w: int, h: int, hole: tuple[int, int, int, int] | None,
              *, filt: int = 0, colour: int = 6, depth: int = 8,
              interlace: int = 0) -> Path:
    """An opaque image with one transparent rectangle punched out of it.

    `hole` is (x, y, w, h) or None for a fully opaque frame.
    """
    channels = 4 if colour == 6 else 2
    bpp = channels * (depth // 8)
    rows = []
    for y in range(h):
        row = bytearray()
        for x in range(w):
            inside = hole is not None and (
                hole[0] <= x < hole[0] + hole[2] and hole[1] <= y < hole[1] + hole[3])
            alpha = 0 if inside else 255
            unit = [0x40] * (channels - 1) + [alpha]
            for v in unit:
                row += bytes([v] * (depth // 8))
        rows.append(row)
    ihdr = struct.pack(">IIBBBBB", w, h, depth, colour, 0, 0, interlace)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n"
                     + _chunk(b"IHDR", ihdr)
                     + _chunk(b"IDAT", zlib.compress(_encode(rows, filt, bpp)))
                     + _chunk(b"IEND", b""))
    return path


@pytest.fixture
def library(tmp_path, monkeypatch):
    """A throwaway DATA root, with the module's caches cleared around it.

    `bezels` memoises by absolute path, and tmp_path differs per test, but the
    on-disk cache is read once per process — a test that did not clear it would
    read the previous test's file and pass for the wrong reason.
    """
    monkeypatch.setattr(paths, "GAMECORE_ROOT", tmp_path)
    monkeypatch.setattr(paths, "GAMECORE_DATA", tmp_path)
    bezels.forget()
    (tmp_path / "assets" / "overlays").mkdir(parents=True)
    (tmp_path / "config").mkdir(parents=True)
    yield tmp_path
    bezels.forget()


# ── The cascade ─────────────────────────────────────────────────────────────

def test_a_game_with_its_own_bezel_gets_it(library):
    overlays = library / "assets" / "overlays"
    write_png(overlays / "duckstation.png", 40, 20, (10, 0, 20, 20))
    write_png(overlays / "duckstation" / "Crash Bandicoot (USA).png", 40, 20, (5, 0, 30, 20))

    png, source = bezels.resolve("duckstation", "Crash Bandicoot (USA).cue")
    assert source == "game"
    assert png.name == "Crash Bandicoot (USA).png"


def test_two_games_on_one_system_get_two_different_bezels(library):
    """The whole phase, in one assertion: no intervention between the two."""
    overlays = library / "assets" / "overlays"
    write_png(overlays / "duckstation.png", 40, 20, (10, 0, 20, 20))
    write_png(overlays / "duckstation" / "Crash Bandicoot (USA).png", 40, 20, (5, 0, 30, 20))
    write_png(overlays / "duckstation" / "Silent Hill (USA).png", 40, 20, (8, 2, 24, 16))

    crash = bezels.describe("duckstation", "Crash Bandicoot (Europe) (v1.1).bin")
    hill = bezels.describe("duckstation", "Silent Hill (USA) (Disc 1).chd")

    assert crash["source"] == hill["source"] == "game"
    assert crash["asset"] != hill["asset"]
    assert crash["hole"] != hill["hole"]
    # …and the region and revision tags on the ROMs did not stop either match.
    assert "Crash" in crash["asset"] and "Silent" in hill["asset"]


def test_the_asset_url_is_encoded(library):
    """Pack filenames are game titles. Spaces, parentheses and apostrophes are
    the normal case, and an unencoded src attribute is a bezel that silently
    does not load — with the resolution having worked perfectly."""
    overlays = library / "assets" / "overlays"
    write_png(overlays / "gopher64" / "Conker's Bad Fur Day (USA).png", 40, 20, (5, 0, 30, 20))

    url = bezels.describe("gopher64", "Conker's Bad Fur Day (USA).z64")["asset"]
    assert url == ("/assets/overlays/gopher64/"
                   "Conker%27s%20Bad%20Fur%20Day%20%28USA%29.png")
    # The directory separator survives; only the segments are quoted.
    assert url.count("/") == 4


def test_a_game_without_its_own_bezel_falls_back_to_the_system(library):
    overlays = library / "assets" / "overlays"
    write_png(overlays / "duckstation.png", 40, 20, (10, 0, 20, 20))
    write_png(overlays / "duckstation" / "Crash Bandicoot (USA).png", 40, 20, (5, 0, 30, 20))

    png, source = bezels.resolve("duckstation", "Some Obscure Import (Japan).chd")
    assert source == "system"
    assert png.name == "duckstation.png"


def test_a_system_without_a_bezel_resolves_to_nothing(library):
    assert bezels.resolve("pcsx2", "Whatever (USA).iso") == (None, "none")


def test_nothing_is_drawn_when_nothing_resolves(library):
    """The end of the cascade must be empty, not a frame.

    A declared hole is only ever right for a system somebody measured. Handing
    one back for a system with no bezel at all is how a game that filled the
    screen correctly acquires black bars nobody asked for.
    """
    out = bezels.describe("pcsx2", "Whatever (USA).iso", declared=None)
    assert out == {"source": "none", "asset": None, "hole": None}


def test_a_declared_hole_is_used_only_when_there_is_no_png(library):
    declared = {"x": 240, "y": 0, "w": 1440, "h": 1080}
    out = bezels.describe("pcsx2", "Whatever (USA).iso", declared=declared)
    assert out["source"] == "declared"
    assert out["asset"] is None
    assert out["hole"] == {**declared, "frame_w": 1920, "frame_h": 1080}


def test_a_measured_hole_beats_the_declared_one(library):
    """The gopher64 defect, as a test.

    `config/overlays.json` said 1407x888+258+90 while the shipped PNG was
    transparent over 1440x1080+240+0, and the declared value won because
    nothing else had an opinion. `config/` is excluded from the OTA rsync, so
    a corrected JSON can never reach a box that already exists — the PNG on
    that box can, and it is the copy that gets believed.
    """
    write_png(library / "assets" / "overlays" / "gopher64.png", 40, 20, (10, 0, 20, 20))
    out = bezels.describe("gopher64", None, declared={"x": 1, "y": 1, "w": 2, "h": 2})
    assert out["source"] == "system"
    assert out["hole"] == {"x": 10, "y": 0, "w": 20, "h": 20,
                           "frame_w": 40, "frame_h": 20}


def test_a_pack_file_that_is_not_a_png_is_ignored(library):
    """Bezel Project packs ship a `.info` next to every image."""
    pack = library / "assets" / "overlays" / "duckstation"
    pack.mkdir(parents=True)
    (pack / "Crash Bandicoot (USA).info").write_text("1440 1080 240 0")
    assert bezels.resolve("duckstation", "Crash Bandicoot (USA).cue") == (None, "none")


# ── The decoder ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("filt", [0, 1, 2, 3, 4],
                         ids=["none", "sub", "up", "average", "paeth"])
def test_every_png_row_filter_is_undone_correctly(tmp_path, filt):
    """The decoder unfilters the alpha byte alone, on the grounds that all five
    filters reference bytes exactly one pixel away and therefore never cross a
    channel. If that reasoning were wrong it would be wrong per filter, so each
    one gets an image whose hole is known by construction."""
    png = write_png(tmp_path / f"f{filt}.png", 64, 32, (12, 5, 30, 20), filt=filt)
    assert bezels._alpha_bbox(png) == (12, 5, 30, 20, 64, 32)


def test_greyscale_plus_alpha_is_read_too(tmp_path):
    """Colour type 4 — two channels, not four. A hand-cut mask is often saved
    this way and the stride slice has to follow."""
    png = write_png(tmp_path / "grey.png", 32, 16, (4, 2, 20, 10), colour=4, filt=4)
    assert bezels._alpha_bbox(png) == (4, 2, 20, 10, 32, 16)


def test_a_fully_opaque_png_measures_no_hole(tmp_path):
    """Not a hole of zero size — no answer at all, so the caller keeps the
    declared geometry instead of drawing a bezel with nothing to see through."""
    png = write_png(tmp_path / "solid.png", 32, 16, None)
    assert bezels._alpha_bbox(png) is None
    assert bezels.measure_hole(png) is None


def test_a_fully_transparent_png_is_refused(tmp_path):
    """What an interrupted download leaves, and what an image with its alpha
    channel accidentally inverted looks like. A hole the size of the frame is
    not a bezel, and reporting one would read as "it works"."""
    png = write_png(tmp_path / "empty.png", 32, 16, (0, 0, 32, 16))
    assert bezels._alpha_bbox(png) == (0, 0, 32, 16, 32, 16)
    assert bezels.measure_hole(png) is None


@pytest.mark.parametrize("kwargs,why", [
    ({"depth": 16}, "16 bits per channel"),
    ({"interlace": 1}, "Adam7"),
])
def test_a_png_the_decoder_cannot_read_defers_instead_of_guessing(tmp_path, kwargs, why):
    """None means "no answer", never "no hole" — the caller falls back to the
    declared geometry. Guessing here would paint a frame from a number nobody
    computed."""
    png = write_png(tmp_path / "odd.png", 16, 8, (2, 2, 8, 4), **kwargs)
    assert bezels._alpha_bbox(png) is None, why


def test_a_truncated_png_does_not_raise(tmp_path):
    """A download killed mid-write is a file, and it arrives in front of a
    game starting."""
    png = write_png(tmp_path / "cut.png", 32, 16, (4, 4, 8, 8))
    # Cut inside the IDAT body. Signature, IHDR and one chunk header come to
    # 41 bytes, so anything just past that is a chunk whose declared length
    # runs off the end of the file — which is what a killed download leaves.
    png.write_bytes(png.read_bytes()[:48])
    assert bezels._alpha_bbox(png) is None


def test_a_png_missing_only_its_IEND_is_still_read(tmp_path):
    """The complement of the test above, and the reason it had to cut deeper.

    Losing the trailing marker loses no pixels, so the decoder answers rather
    than discarding a bezel it can see perfectly well. Worth pinning: the first
    version of the truncation test cut off exactly this much and passed while
    proving nothing.
    """
    png = write_png(tmp_path / "no-end.png", 32, 16, (4, 4, 8, 8))
    png.write_bytes(png.read_bytes()[:-12])
    assert bezels._alpha_bbox(png) == (4, 4, 8, 8, 32, 16)


def test_something_that_is_not_a_png_does_not_raise(tmp_path):
    junk = tmp_path / "nope.png"
    junk.write_bytes(b"<!doctype html>a 404 page saved by a downloader")
    assert bezels._alpha_bbox(junk) is None


def test_a_replaced_bezel_is_measured_again(library):
    """The cache is keyed on mtime AND size.

    The upload endpoint replaces a bezel in place, so the path is unchanged. A
    cache keyed on the path alone would keep serving the old hole — a frame
    over the wrong part of the screen, with nothing on screen to explain it.
    """
    png = library / "assets" / "overlays" / "duckstation.png"
    write_png(png, 40, 20, (10, 0, 20, 20))
    assert bezels.measure_hole(png)["w"] == 20

    write_png(png, 40, 20, (5, 0, 30, 20))
    assert bezels.measure_hole(png)["w"] == 30


def test_the_hole_carries_the_frame_it_was_measured_in(tmp_path):
    """A pack cut for 1280x960 is not wrong, it is just not 1920x1080. The
    consumer scales, and cannot without knowing what the numbers mean."""
    png = write_png(tmp_path / "small.png", 1280, 96, (160, 0, 960, 96))
    assert bezels.measure_hole(png) == {"x": 160, "y": 0, "w": 960, "h": 96,
                                        "frame_w": 1280, "frame_h": 96}


# ── What a launch actually receives ─────────────────────────────────────────

def _declare(library: Path, entry: dict) -> None:
    (library / "config" / "overlays.json").write_text(json.dumps(entry))


def test_a_pack_cut_for_a_smaller_frame_still_lands_on_the_game(library):
    """The failure that looks like success.

    A 1280x960 pack stretched over a 1920x1080 window draws its artwork
    correctly — `objectFit: fill` sees to that — and then punches its hole
    where 1280x960 said it was. The picture looks right and the game is behind
    the frame.
    """
    _declare(library, {"duckstation": {"window_rect": {"x": 0, "y": 0,
                                                       "w": 1920, "h": 1080}}})
    write_png(library / "assets" / "overlays" / "duckstation.png",
              1280, 960, (160, 0, 960, 960))

    out = bezels.for_launch("duckstation")
    assert out["frame"] == {"w": 1280, "h": 960}
    assert out["hole"] == {"x": 240, "y": 0, "w": 1440, "h": 1080}


def test_a_pack_already_in_window_space_is_left_alone(library):
    _declare(library, {"pcsx2": {"window_rect": {"x": 0, "y": 0, "w": 1920, "h": 1080}}})
    write_png(library / "assets" / "overlays" / "pcsx2.png", 1920, 1080, (240, 0, 1440, 1080))

    assert bezels.for_launch("pcsx2")["hole"] == {"x": 240, "y": 0, "w": 1440, "h": 1080}


def test_a_system_the_config_never_heard_of_answers_rather_than_raising(library):
    """The launcher hands over whatever system the tile names. An overlays.json
    that predates a pack — `config/` is excluded from the OTA rsync, so that is
    the normal state of an upgraded box — must not turn a launch into an
    exception."""
    _declare(library, {})
    out = bezels.for_launch("some-new-emulator", "Whatever (USA).iso")
    assert out == {"system_id": "some-new-emulator", "source": "none",
                   "asset": None, "hole": None, "frame": None,
                   # Nothing to look at, so nothing to look for.
                   "measure": False}


def test_a_missing_overlays_json_is_not_fatal(library):
    assert bezels.for_launch("duckstation")["source"] == "none"


# ── Against what this repository actually ships ─────────────────────────────

def _shipped() -> list[tuple[str, Path, dict]]:
    declared = json.loads(OVERLAYS_JSON.read_text())
    out = []
    for system_id, cfg in sorted(declared.items()):
        png = SHIPPED_ASSETS / f"{system_id}.png"
        if png.is_file() and "hole" in cfg:
            out.append((system_id, png, cfg["hole"]))
    return out


@pytest.mark.parametrize("system_id,png,declared", _shipped(),
                         ids=[s for s, _, _ in _shipped()])
def test_a_shipped_bezel_and_its_declared_hole_agree(system_id, png, declared):
    """The drift that started this phase.

    `gopher64.png` is transparent over 1440x1080+240+0; overlays.json declared
    1407x888+258+90 — a frame 33 px too narrow and 192 px too short, drawn on
    top of the game. Nothing caught it because the PNG and the JSON had no way
    to disagree out loud, and `config/` is excluded from the OTA rsync so no
    release could have corrected it either.

    A box now measures the PNG and ignores the declared value entirely. This
    test is for the fresh installs that still get the JSON, and for the next
    person who cuts a bezel without updating both halves.
    """
    bezels.forget()
    measured = bezels._alpha_bbox(png)
    assert measured is not None, f"{png.name} has no transparent region at all"
    x, y, w, h, _, _ = measured
    assert (x, y, w, h) == (declared["x"], declared["y"], declared["w"], declared["h"]), (
        f"{system_id}: PNG is transparent over {w}x{h}+{x}+{y}, "
        f"overlays.json declares "
        f"{declared['w']}x{declared['h']}+{declared['x']}+{declared['y']}")


@pytest.mark.skipif(not shutil.which("magick"),
                    reason="ImageMagick is the reference, not a dependency")
@pytest.mark.parametrize("png", sorted(SHIPPED_ASSETS.glob("*.png")),
                         ids=lambda p: p.name)
def test_the_decoder_agrees_with_imagemagick(png):
    """The README tells the operator to check a hole with

        magick overlay.png -alpha extract -threshold 50% -negate -format "%@" info:

    and the box computes the same number without ImageMagick installed. If the
    two ever disagree, one of the two recipes is lying to somebody.
    """
    out = subprocess.run(
        ["magick", str(png), "-alpha", "extract", "-threshold", "50%",
         "-negate", "-format", "%@", "info:"],
        capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    w, rest = out.stdout.strip().split("x")
    h, x, y = rest.split("+")
    bezels.forget()
    assert bezels._alpha_bbox(png)[:4] == (int(x), int(y), int(w), int(h))
