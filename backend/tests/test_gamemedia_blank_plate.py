"""The media that is a picture of nothing, and the tier that has a real one.

ScreenScraper does not omit a `box-2D-back` it lacks: it answers 200 with a
CHROMA-KEY PLATE, a valid PNG of flat #00FF00 cut to the exact box dimensions
of the system. It downloads, it decodes and it draws, so nothing downstream
could tell — the shelf theme ended up recognising them in the BROWSER, by
quantising the pixels, and every other consumer showed a green slab.

Measured on the reference box: nine titles across five systems (a 3DS, three
DS, a PSP, a PS3 and three Switch), four distinct files, one per box shape. And
of those nine, **seven have a real `Box - Back` in the LaunchBox index already
sitting on that box** — but the tier fallback was per GAME and all-or-nothing,
so a title ScreenScraper knew kept every gap ScreenScraper had.

These tests pin both halves: a plate is recognised without an image decoder,
and a blank slug is what makes the other tier worth asking.

Run under pytest:  pytest backend/tests/test_gamemedia_blank_plate.py
"""
import os
import struct
import sys
import tempfile
import zlib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

_root = os.environ.get("GAMECORE_TEST_ROOT")
if _root is None:
    _root = str(Path(tempfile.mkdtemp(prefix="gamecore-test-")) / "fake_root")
    os.environ["GAMECORE_TEST_ROOT"] = _root
    os.environ["GAMECORE_PATH"] = _root

import pytest

from backend.services import gamemedia
from backend.services.gamemedia import gamemedia as gm
from backend.services.gamemedia import gamescrape as gs


# ── building the two kinds of PNG, without an image library ──────────────────
#
# The same primitives the detector refuses to go beyond: struct for the header,
# zlib for the data. If a test needed Pillow to describe its input, it would be
# describing something the backend cannot see.

def _png(width: int, height: int, rows: list[bytes]) -> bytes:
    def chunk(tag: bytes, body: bytes) -> bytes:
        return (struct.pack(">I", len(body)) + tag + body
                + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)   # 8-bit RGB
    raw = b"".join(b"\x00" + r for r in rows)                       # filter 0
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def plate(tmp: Path, w: int = 421, h: int = 680, name: str = "box-back.png") -> Path:
    """ScreenScraper's answer for a back it does not have: flat #00FF00.

    421x680 is the Switch plate measured on the reference box, byte-identical
    across Mario Party Superstars, Jamboree and Breath of the Wild.
    """
    p = tmp / name
    p.write_bytes(_png(w, h, [b"\x00\xff\x00" * w] * h))
    return p


def scan(tmp: Path, w: int = 421, h: int = 680, name: str = "box-back.png") -> Path:
    """A real back: noise, which is what a barcode and a paragraph of small
    print look like to a compressor."""
    p = tmp / name
    rnd = 1
    rows = []
    for _ in range(h):
        row = bytearray()
        for _ in range(w * 3):
            rnd = (rnd * 1103515245 + 12345) & 0x7FFFFFFF
            row.append((rnd >> 16) & 0xFF)
        rows.append(bytes(row))
    p.write_bytes(_png(w, h, rows))
    return p


# ── the detector ─────────────────────────────────────────────────────────────

def test_the_ihdr_gives_the_size_without_decoding_anything(tmp_path):
    head = plate(tmp_path).read_bytes()[:24]
    assert gs.png_dimensions(head) == (421, 680)


def test_a_flat_plate_is_a_picture_of_nothing(tmp_path):
    assert gs.looks_like_flat_plate(plate(tmp_path)) is True


def test_a_real_scan_is_kept(tmp_path):
    assert gs.looks_like_flat_plate(scan(tmp_path)) is False


def test_every_box_shape_the_reference_box_produced(tmp_path):
    """One plate per system, and they are the four sizes actually measured."""
    for i, (w, h) in enumerate([(513, 458), (421, 680), (578, 680), (395, 680)]):
        assert gs.looks_like_flat_plate(plate(tmp_path, w, h, f"p{i}.png")) is True


def test_the_margin_is_not_a_hair(tmp_path):
    """The threshold sits between two measured populations, not on a guess: the
    nine plates reach 0.0093 byte per pixel, the 52 real scans start at 1.3055.
    A rule that only just separated them would be a rule about this library."""
    p, s = plate(tmp_path, name="a.png"), scan(tmp_path, name="b.png")
    bpp = lambda f: f.stat().st_size / (421 * 680)   # noqa: E731
    assert bpp(p) < gs.FLAT_PLATE_BPP / 5
    assert bpp(s) > gs.FLAT_PLATE_BPP * 20


def test_anything_that_is_not_a_png_is_left_alone(tmp_path):
    """JPEG would need its SOF scanned and every plate measured was a PNG.
    Answering False keeps today's behaviour, which is to trust the file."""
    j = tmp_path / "box-back.jpg"
    j.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 40)
    assert gs.looks_like_flat_plate(j) is False


def test_a_file_that_is_not_there_is_not_a_plate(tmp_path):
    assert gs.looks_like_flat_plate(tmp_path / "nope.png") is False


def test_a_truncated_header_is_not_a_plate(tmp_path):
    p = tmp_path / "short.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n")
    assert gs.looks_like_flat_plate(p) is False
    assert gs.png_dimensions(p.read_bytes()) is None


# ── what the download does with one ───────────────────────────────────────────

def test_a_downloaded_plate_is_recorded_blank_and_not_kept(tmp_path, monkeypatch):
    """`failed` would mean "retry me", and this one comes back identical every
    time. The file goes: it is a picture of nothing taking up the name of a
    scan."""
    def fake_fetch(url, dest, verbose):
        return plate(dest.parent, name=dest.name + ".png")

    monkeypatch.setattr(gs, "fetch", fake_fetch)
    got = gm._download_media(tmp_path, {"box-back": {"url": "https://x/back"}},
                             1, False)

    assert got["box-back"]["blank"] is True
    assert got["box-back"]["url"] == "https://x/back"
    assert "file" not in got["box-back"]
    assert not list(tmp_path.glob("box-back.*"))


def test_a_downloaded_scan_is_kept_as_before(tmp_path, monkeypatch):
    monkeypatch.setattr(gs, "fetch",
                        lambda url, dest, verbose: scan(dest.parent,
                                                        name=dest.name + ".png"))
    got = gm._download_media(tmp_path, {"box-back": {"url": "https://x/back"}},
                             1, False)

    assert got["box-back"]["file"] == "box-back.png"
    assert "blank" not in got["box-back"]


# ── the other tier ───────────────────────────────────────────────────────────

def _manifest(**media):
    return {"media": dict(media)}


def test_the_second_tier_is_asked_for_the_blank_slug_only(tmp_path, monkeypatch):
    """Narrow on purpose. A deferred media has a URL that works and a failure
    deserves a retry; neither is a hole in the record."""
    manifest = _manifest(**{
        "box-back": {"blank": True, "url": "https://ss/back"},
        "box-front": {"file": "box-front.png"},
        "box-3d": {"deferred": True, "url": "https://ss/3d"},
    })
    asked = {}

    monkeypatch.setattr(gm, "lb_index_ready", lambda: True, raising=False)
    monkeypatch.setattr(gs, "lb_index_ready", lambda: True)
    monkeypatch.setattr(gm, "lb_everything", lambda parsed, cutoff: {
        "media": {"box-back": {"url": "https://lb/back"},
                  "box-3d": {"url": "https://lb/3d"},
                  "box-front": {"url": "https://lb/front"}}})

    def fake_download(d, wanted, workers, verbose, throttle=False):
        asked.update(wanted)
        return {k: {"file": f"{k}.jpg"} for k in wanted}

    monkeypatch.setattr(gm, "_download_media", fake_download)
    notes = []
    gm._top_up_blanks(tmp_path, manifest, {"source": "screenscraper"}, {},
                      0.72, notes, False)

    assert list(asked) == ["box-back"], "a deferred or cached slug was re-asked"
    assert manifest["media"]["box-back"]["file"] == "box-back.jpg"
    assert manifest["media"]["box-3d"]["deferred"] is True
    assert any("launchbox" in n for n in notes)


def test_a_game_with_nothing_blank_costs_nothing(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(gs, "lb_index_ready", lambda: True)
    monkeypatch.setattr(gm, "lb_everything",
                        lambda parsed, cutoff: called.append(1) or {})
    gm._top_up_blanks(tmp_path, _manifest(**{"box-back": {"file": "b.png"}}),
                      {"source": "screenscraper"}, {}, 0.72, [], False)
    assert called == []


def test_launchbox_is_not_asked_to_replace_its_own_blank(tmp_path, monkeypatch):
    """It is the tier that answered. Asking it again is the same answer."""
    called = []
    monkeypatch.setattr(gs, "lb_index_ready", lambda: True)
    monkeypatch.setattr(gm, "lb_everything",
                        lambda parsed, cutoff: called.append(1) or {})
    gm._top_up_blanks(tmp_path, _manifest(**{"box-back": {"blank": True}}),
                      {"source": "launchbox"}, {}, 0.72, [], False)
    assert called == []


def test_no_index_is_not_a_failure_worth_a_note(tmp_path, monkeypatch):
    """A box that never built the 234 MB dump has one tier, and that is a
    configuration, not a fault. It must cost nothing and say nothing."""
    monkeypatch.setattr(gs, "lb_index_ready", lambda: False)
    notes = []
    gm._top_up_blanks(tmp_path, _manifest(**{"box-back": {"blank": True}}),
                      {"source": "screenscraper"}, {}, 0.72, notes, False)
    assert notes == []


def test_the_other_tier_having_nothing_is_said_rather_than_hushed(tmp_path,
                                                                  monkeypatch):
    """Two of the nine really are unavailable everywhere. The manifest should
    read as a settled answer, not as a step that quietly did not happen."""
    monkeypatch.setattr(gs, "lb_index_ready", lambda: True)
    monkeypatch.setattr(gm, "lb_everything", lambda parsed, cutoff: None)
    manifest = _manifest(**{"box-back": {"blank": True}})
    notes = []
    gm._top_up_blanks(tmp_path, manifest, {"source": "screenscraper"}, {},
                      0.72, notes, False)
    assert manifest["media"]["box-back"]["blank"] is True
    assert notes and "launchbox" in notes[0]


# ── what a blank means afterwards ────────────────────────────────────────────

def test_a_blank_does_not_make_the_game_look_unscraped(tmp_path):
    """The state is SETTLED, not incomplete. Read as a hole it would rescrape
    the game — one jeuInfos out of the daily quota — every time a theme drew a
    cover, to be handed the same plate again."""
    m = {"found": True, "lang": gm.LANG_PREF[0],
         "media": {"box-back": {"blank": True, "url": "https://ss/back"}}}
    assert gm._manifest_complete(tmp_path, m) is True


def test_a_plate_filed_before_this_existed_is_revisited(tmp_path):
    """The nine on the reference box are recorded as ordinary scans, and
    nothing would ever look again: the manifest is complete, the file is there,
    and the greenness is only visible to something that reads pixels."""
    p = plate(tmp_path)
    m = {"found": True, "lang": gm.LANG_PREF[0],
         "media": {"box-back": {"file": p.name, "bytes": p.stat().st_size}}}
    assert gm._manifest_complete(tmp_path, m) is False


def test_a_real_scan_is_not_revisited(tmp_path):
    s = scan(tmp_path)
    m = {"found": True, "lang": gm.LANG_PREF[0],
         "media": {"box-back": {"file": s.name, "bytes": s.stat().st_size}}}
    assert gm._manifest_complete(tmp_path, m) is True


def test_a_big_media_is_never_even_opened(tmp_path, monkeypatch):
    """The gate is the size the manifest already stores, so a PS3 game's 152
    media stay 152 integer comparisons rather than 152 file reads."""
    monkeypatch.setattr(gs, "looks_like_flat_plate",
                        lambda p: pytest.fail("a large media was opened"))
    s = scan(tmp_path)
    m = {"found": True, "lang": gm.LANG_PREF[0],
         "media": {"box-back": {"file": s.name, "bytes": 900_000}}}
    assert gm._manifest_complete(tmp_path, m) is True


def test_a_tiny_icon_is_opened_and_kept(tmp_path):
    """Icons ARE tiny, which is why the size gate alone would not do. A 24x24
    icon carries a picture, so it fails the bytes-per-pixel test."""
    icon = tmp_path / "icon-color.png"
    rows = [bytes(range(24 * 3)) for _ in range(24)]
    icon.write_bytes(_png(24, 24, rows))
    m = {"found": True, "lang": gm.LANG_PREF[0],
         "media": {"icon-color": {"file": icon.name,
                                  "bytes": icon.stat().st_size}}}
    assert icon.stat().st_size < 8192, "the fixture must go through the gate"
    assert gm._manifest_complete(tmp_path, m) is True


def test_a_blank_is_never_fetched_on_demand(tmp_path, monkeypatch):
    """Its URL still works and still serves the same plate."""
    d = gm.entry_dir("ryujinx", "Game.nsp")
    d.mkdir(parents=True, exist_ok=True)
    (d / gm.MANIFEST).write_text(
        '{"media": {"box-back": {"blank": true, "url": "https://ss/back"}}}',
        encoding="utf-8")
    monkeypatch.setattr(gs, "fetch", lambda *a, **k: pytest.fail(
        "a picture of nothing was downloaded again"))

    assert gm.fetch_media("ryujinx", "Game.nsp", "box-back") is None


def test_a_blank_is_not_offered_to_the_frontend():
    """Listing it is what makes a consumer ask for it, get a picture of
    nothing, and have to work that out from the pixels. Absent means "this game
    has no back cover", which is true and directly actionable."""
    index = gamemedia.media_index({"media": {
        "box-front": {"file": "box-front.png", "category": "box"},
        "box-back": {"blank": True, "url": "https://ss/back", "category": "box"},
    }})
    assert "box-front" in index
    assert "box-back" not in index
