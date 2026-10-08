"""A superseded pack is profiled only while its old tile is on the grid.

The reference box moved its Switch games from `ryujinx` to `switch` and then
uninstalled Ryujinx. The `ryujinx` pack stayed profilable, failed on every pad
("cannot locate io.github.ryubing.Ryujinx"), and every Switch launch waited 8 s
and showed "Wireless Controller was not configured in time".

`ryujinx` now shares the `switch` pack's emulator and profiles nothing, so the
pack under test is that old one rebuilt: a superseded pack with its own
controllers block.
"""
import dataclasses
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.services import configgen, controller_autoconfig  # noqa: E402
from backend.services.catalog import load_catalog  # noqa: E402


@pytest.fixture
def box(tmp_path, monkeypatch):
    grid = tmp_path / "systems.json"
    monkeypatch.setattr(configgen, "SYSTEMS_FILE", grid, raising=False)
    monkeypatch.setattr(controller_autoconfig, "state_file",
                        lambda: tmp_path / "controller-autoconfig.json")
    return grid


@pytest.fixture(scope="module")
def packs():
    packs = load_catalog(ROOT / "catalog", ROOT / "config" / "catalog.d")
    old = packs["ryujinx"]
    data = {k: v for k, v in old.data.items() if k != "sharesEmulator"}
    data["controllers"] = packs["switch"].data["controllers"]
    packs["ryujinx"] = dataclasses.replace(old, data=data)
    return packs


def _on(packs) -> set[str]:
    on, _off = configgen.autoconfigured_packs(packs)
    return {p.id for p in on}


def test_a_superseded_pack_without_its_tile_is_not_profiled(box, packs):
    box.write_text(json.dumps([{"id": "switch"}, {"id": "gamecube"}]))
    on = _on(packs)
    assert "ryujinx" not in on
    assert "switch" in on


def test_a_superseded_pack_is_profiled_while_its_tile_is_on_the_grid(box, packs):
    box.write_text(json.dumps([{"id": "ryujinx"}]))
    assert "ryujinx" in _on(packs)


def test_an_unreadable_grid_changes_nothing(box, packs):
    # No grid file: the fixtures of the characterisation harness, and a box
    # whose config is damaged. Guessing "no tile" there would unbind real pads.
    assert "ryujinx" in _on(packs)
    box.write_text("{not json")
    assert "ryujinx" in _on(packs)
