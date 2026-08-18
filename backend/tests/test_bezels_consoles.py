"""One pack, several consoles — the level the cascade was missing.

`mgba` runs three consoles of three different shapes (Game Boy and Game Boy
Color in 10:9, Game Boy Advance in 3:2) behind a single system id, and every
level below this file used to answer that id and nothing else. One PNG, one
hole, one ratio, therefore one drift-correction key: whichever console happened
to be played first taught the box a rectangle, `for_launch` set
`"measure": False` because the answer was now known, and the other two consoles
inherited it permanently.

Measured on the reference box before this change: `bezel-corrections.json` held
exactly one entry, `mgba@1:1` → `1234x1080+343+0`. 1234/1080 is 1.14 — a Game
Boy. A Game Boy Advance game drawn 1080 pixels tall is 1620 wide, so that
correction cuts 193 pixels off each side of every GBA game, forever, and the
`measure: False` guarantees the box never looks again.

The two directions this file proves are opposite, and the second is the one
that costs a release:

  * two consoles of one pack must be able to resolve two different bezels and
    file their corrections under two different keys;
  * a pack that declares no console must behave EXACTLY as it did before —
    byte-for-byte on `describe()` and on the correction key, because that is
    every system on every box that exists today.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from backend.services import bezel_capture, bezels, consoles, paths
from backend.tests.test_bezels import write_png


# `roms.consoles` as a pack declares it, reduced to what systems.json carries.
MGBA = {
    "id": "mgba", "platform": "GBA",
    "extensions": ["*.gba", "*.gbc", "*.gb", "*.zip"],
    "consoles": [
        {"id": "gba", "label": "Game Boy Advance", "extensions": ["*.gba"]},
        {"id": "gbc", "label": "Game Boy Color", "extensions": ["*.gbc"]},
        {"id": "gb", "label": "Game Boy", "extensions": ["*.gb"]},
    ],
}
# The pack that is every other pack: no `consoles` key at all.
PCSX2 = {"id": "pcsx2", "platform": "PS2", "extensions": ["*.iso", "*.chd"]}


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "GAMECORE_ROOT", tmp_path)
    monkeypatch.setattr(paths, "GAMECORE_DATA", tmp_path)
    bezels.forget()
    consoles.forget()
    (tmp_path / "assets" / "overlays").mkdir(parents=True)
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "config" / "systems.json").write_text(json.dumps([MGBA, PCSX2]))
    yield tmp_path
    bezels.forget()
    consoles.forget()


# ── Which console a ROM belongs to ──────────────────────────────────────────

@pytest.mark.parametrize("rom, want", [
    ("Pokemon Emerald (USA).gba", "gba"),
    ("Zelda Oracle of Ages (USA).gbc", "gbc"),
    ("Tetris (World).gb", "gb"),
    # Declared by the pack, claimed by no console: `.zip` can hold any of the
    # three and the pack says so by leaving it out. Undetermined is an answer.
    ("Some Compilation (Europe).zip", None),
    ("Nothing To Do With mGBA.iso", None),
])
def test_the_extension_names_the_console(library, rom, want):
    assert consoles.for_rom("mgba", rom) == want


def test_a_pack_that_declares_no_console_never_has_one(library):
    assert consoles.for_rom("pcsx2", "God of War (USA).iso") is None
    assert consoles.declared("pcsx2") == []


def test_an_unknown_system_answers_rather_than_raising(library):
    assert consoles.for_rom("nintendo-virtual-boy", "Whatever.vb") is None


# ── The console level of the cascade ────────────────────────────────────────

def test_two_consoles_of_one_pack_resolve_two_different_bezels(library):
    """The failure this whole change exists for.

    Before the console level, both of these came back `mgba.png` — the same
    file, the same hole, the same everything. The assertion that matters is the
    inequality; the names are only there to say which is which.
    """
    overlays = library / "assets" / "overlays"
    write_png(overlays / "mgba.png", 192, 108, (42, 0, 108, 108))        # 1:1
    write_png(overlays / "mgba.gb.png", 192, 108, (36, 0, 120, 108))     # 10:9
    write_png(overlays / "mgba.gba.png", 192, 108, (15, 0, 162, 108))    # 3:2

    gb, gb_level = bezels.resolve("mgba", "Tetris (World).gb")
    gba, gba_level = bezels.resolve("mgba", "Pokemon Emerald (USA).gba")

    assert (gb_level, gba_level) == ("console", "console")
    assert gb.name == "mgba.gb.png"
    assert gba.name == "mgba.gba.png"
    assert gb != gba

    # And the holes they hand back are the shapes of two different consoles.
    assert bezels.describe("mgba", "Tetris (World).gb")["hole"]["w"] == 120
    assert bezels.describe("mgba", "Pokemon Emerald (USA).gba")["hole"]["w"] == 162


def test_a_console_without_its_own_bezel_falls_back_to_the_system(library):
    overlays = library / "assets" / "overlays"
    write_png(overlays / "mgba.png", 192, 108, (42, 0, 108, 108))
    write_png(overlays / "mgba.gba.png", 192, 108, (15, 0, 162, 108))

    png, level = bezels.resolve("mgba", "Tetris (World).gb")
    assert (level, png.name) == ("system", "mgba.png")


def test_a_game_bezel_still_beats_its_console(library):
    """The order of the cascade, at the one seam this change opens."""
    overlays = library / "assets" / "overlays"
    write_png(overlays / "mgba.png", 192, 108, (42, 0, 108, 108))
    write_png(overlays / "mgba.gb.png", 192, 108, (36, 0, 120, 108))
    write_png(overlays / "mgba" / "Tetris (World).png", 192, 108, (50, 0, 92, 108))

    png, level = bezels.resolve("mgba", "Tetris (World).gb")
    assert (level, png.name) == ("game", "Tetris (World).png")


def test_off_still_beats_a_console_bezel(library):
    """`off` wins over everything, and this level must not become an exception.

    Falling through to a console bezel here would put artwork back on a game
    the player had explicitly cleared — the same mistake `describe()` already
    refuses to make with `declared`.
    """
    overlays = library / "assets" / "overlays"
    write_png(overlays / "mgba.gb.png", 192, 108, (36, 0, 120, 108))
    bezels.set_preference("mgba", "Tetris (World).gb", "off")

    assert bezels.resolve("mgba", "Tetris (World).gb") == (None, "off")
    assert bezels.describe("mgba", "Tetris (World).gb") == {
        "source": "off", "asset": None, "hole": None}


def test_a_console_bezel_is_not_reachable_by_a_pack_that_declared_no_console(library):
    """A stray `pcsx2.<something>.png` must not be picked up by name alone.

    Otherwise a per-game bezel that happened to be filed at the top level, or
    a leftover from a rename, would silently outrank the system bezel.
    """
    overlays = library / "assets" / "overlays"
    write_png(overlays / "pcsx2.png", 192, 108, (24, 0, 144, 108))
    write_png(overlays / "pcsx2.ps2.png", 192, 108, (10, 0, 172, 108))

    png, level = bezels.resolve("pcsx2", "God of War (USA).iso")
    assert (level, png.name) == ("system", "pcsx2.png")


# ── The drift-correction key ────────────────────────────────────────────────

def test_two_consoles_of_one_pack_do_not_share_a_correction(library):
    """The half of the bug that survives even when the bezels are right.

    A correction is keyed by the ratio of the ANNOUNCED hole. Two consoles
    sharing one PNG announce one ratio, so without the console in the key the
    first game played teaches the box a rectangle and the other two consoles
    are stuck with it — which is precisely the state the reference box was
    found in.
    """
    hole = {"x": 420, "y": 0, "w": 1080, "h": 1080}          # the shared 1:1
    assert (bezel_capture.key_for("mgba", hole, "gb")
            != bezel_capture.key_for("mgba", hole, "gba"))

    bezel_capture.record("mgba", hole, (343, 0, 1234, 1080), console="gb")
    assert bezel_capture.correction_for("mgba", hole, "gb") is not None
    assert bezel_capture.correction_for("mgba", hole, "gba") is None


def test_a_correction_learned_before_this_change_is_not_reused(library):
    """`mgba@1:1` was learned for a console nobody recorded.

    Keeping it would apply one console's measurement to three. It is left on
    disk rather than deleted — reverting this change must bring the box back
    exactly as it was — but it can no longer be found.
    """
    (library / "config" / "bezel-corrections.json").write_text(
        json.dumps({"mgba@1:1": {"x": 343, "y": 0, "w": 1234, "h": 1080}}))
    hole = {"x": 420, "y": 0, "w": 1080, "h": 1080}

    assert bezel_capture.correction_for("mgba", hole, "gb") is None
    assert bezel_capture.correction_for("mgba", hole, None) is None
    assert "mgba@1:1" in bezel_capture.corrections()


def test_for_launch_answers_differently_for_two_consoles(library):
    """1.1, as a test. This is the command the report opens with."""
    overlays = library / "assets" / "overlays"
    write_png(overlays / "mgba.png", 1920, 1080, (420, 0, 1080, 1080))
    write_png(overlays / "mgba.gb.png", 1920, 1080, (360, 0, 1200, 1080))
    write_png(overlays / "mgba.gba.png", 1920, 1080, (150, 0, 1620, 1080))

    gb = bezels.for_launch("mgba", "Tetris (World).gb")
    gba = bezels.for_launch("mgba", "Pokemon Emerald (USA).gba")

    assert gb != gba
    assert (gb["console"], gba["console"]) == ("gb", "gba")
    assert gb["hole"]["w"] == 1200 and gba["hole"]["w"] == 1620


# ── Non-regression: a mono-console pack, to the byte ────────────────────────

def test_a_mono_console_pack_is_untouched(library):
    """Every system on every box that exists today takes this path.

    `describe()` is compared as a whole rather than field by field: a new key
    in that dict is a change to what Electron receives, and the point of this
    assertion is that nothing there moved.
    """
    overlays = library / "assets" / "overlays"
    write_png(overlays / "pcsx2.png", 192, 108, (24, 0, 144, 108))

    assert bezels.describe("pcsx2", "God of War (USA).iso") == {
        "source": "system",
        "asset": "/assets/overlays/pcsx2.png",
        "hole": {"x": 24, "y": 0, "w": 144, "h": 108,
                 "frame_w": 192, "frame_h": 108},
    }


def test_a_mono_console_correction_keeps_its_old_key(library):
    """The migration that must not be needed.

    Boxes carry corrections learned under `<system>@<ratio>`. For a pack with
    no consoles that string has to come out identical, or every system on every
    box silently re-measures — and re-measuring is the operation that can go
    wrong.
    """
    hole = {"x": 240, "y": 52, "w": 1440, "h": 968}
    assert bezel_capture.key_for("pcsx2", hole) == "pcsx2@180:121"
    assert bezel_capture.key_for("pcsx2", hole, None) == "pcsx2@180:121"
