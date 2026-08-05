"""The tile contract: one shape, whoever builds it.

A tile is the set of fields `games.py` reads to launch something. It used to be
written down twice — once in `scripts/gen-catalog.py` for the shipped `.dist`,
once in `backend/services/catalog/merge.py` for a tile an OTA adds to a box —
and the two had drifted three ways before anyone looked:

  · Stremio's `fullscreen` block existed only in the first, so the tile was
    fullscreen on a fresh install and windowed on an updated one;
  · `iconPath` was `ps1.png` in one and `duckstation.png` in the other;
  · one crashed on a pack with no `roms` block and the other did not.

None of it was caught, because nothing compared them. This file does.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.services.catalog import load_catalog
from backend.services.catalog.merge import entry_from_pack
from backend.services.catalog.tiles import LOGO_NAME, tile_entry

CATALOG = ROOT / "catalog"
LOCAL = ROOT / "config" / "catalog.d"


@pytest.fixture(scope="module")
def packs():
    return load_catalog(CATALOG, LOCAL)


def test_both_builders_agree_on_the_field_set(packs):
    """The one assertion that would have caught all three divergences.

    The two callers may legitimately differ on the VALUE of path/args — merge
    knows what is installed on this box, the generator does not. They may never
    differ on which fields exist.
    """
    mismatched = {}
    for pack in packs.values():
        shipped = set(tile_entry(pack))
        merged = set(entry_from_pack(pack, ROOT))
        if shipped != merged:
            mismatched[pack.id] = sorted(shipped ^ merged)
    assert not mismatched, f"the two tile builders disagree on fields: {mismatched}"


def test_launch_behaviour_survives_both_paths(packs):
    """Stremio has no fullscreen flag on the command line — the enforcer is the
    only thing that fullscreens it, and it only runs if the tile says so."""
    for build in (lambda p: tile_entry(p), lambda p: entry_from_pack(p, ROOT)):
        tile = build(packs["stremio"])
        assert tile["fullscreen"]["wm_class"], "no wm_class — the enforcer does nothing"
        assert tile["fullscreen"]["timeout_s"] > 0
        assert tile["gamepadTrigger"] is True


def test_every_tile_names_a_logo_that_something_can_serve(packs):
    """`serve_logo` resolves by pack id first, then by the historical file name
    recorded in systems.json. A tile naming neither draws an empty square."""
    for pack in packs.values():
        icon = tile_entry(pack)["iconPath"]
        stem = Path(icon).stem
        assert stem == pack.id or LOGO_NAME.get(pack.id) == Path(icon).name, \
            f"{pack.id}: {icon} matches neither the pack id nor its historical name"
        assert pack.logo is not None, f"{pack.id} declares {icon} but ships no logo"


def test_an_emulator_without_a_roms_block_does_not_crash_the_build(packs):
    """The schema does not require `roms`. One builder read it with [] and the
    other with .get(), so the same pack crashed CI and merged fine on a box."""
    pack = next(p for p in packs.values() if p.kind == "emulator")
    stripped = type(pack)(id=pack.id, data={k: v for k, v in pack.data.items() if k != "roms"},
                          path=pack.path, origin=pack.origin)
    assert tile_entry(stripped)["romsPath"] == f"emu/{pack.id}/"
    assert entry_from_pack(stripped, ROOT)["romsPath"] == f"emu/{pack.id}/"


def test_prefer_if_present_is_the_only_thing_the_box_changes(packs):
    """merge honours `preferIfPresent` only when that binary is really here;
    the generator always records it. That is the one intended difference — and
    it must show up in path/args and nowhere else."""
    for pack in packs.values():
        shipped = tile_entry(pack)
        merged = entry_from_pack(pack, ROOT)
        differing = {k for k in shipped if shipped[k] != merged.get(k)}
        assert differing <= {"path", "args"}, \
            f"{pack.id}: the two builders differ on {differing - {'path', 'args'}}"
