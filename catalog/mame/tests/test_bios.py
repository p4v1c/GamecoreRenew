"""Where MAME BIOS sets are declared, pinned to where the libretro core reads them."""
import json
from pathlib import Path

BIOS = json.loads((Path(__file__).parents[1] / "pack.json").read_text())["bios"]


def test_bios_sets_sit_in_the_folder_the_core_adds_to_its_rompath():
    # libretro MAME searches <rom dir>;<system>/mame/bios;<system>/mame/roms
    # (src/osd/libretro/libretro-internal/retro_init.cpp). The ROM folder would
    # also work, but there a BIOS zip shows up as a game tile.
    assert BIOS["dir"] == "@HOME@/.config/gamecore-retroarch/system"
    assert all(f["file"].startswith("mame/bios/") for f in BIOS["files"])


def test_no_bios_set_blocks_a_launch():
    # Each set serves one board family; most MAME games need none of them.
    assert not any(f["required"] for f in BIOS["files"])
