"""Merging the shipped catalogue into a box's own systems.json.

Offline and pure: `merge_systems` writes nothing, so every rule below is
asserted on data rather than on a machine.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.services.catalog import load_catalog                    # noqa: E402
from backend.services.catalog.merge import (                          # noqa: E402
    merge_file, merge_systems,
)

CATALOG = ROOT / "catalog"
LOCAL = ROOT / "config" / "catalog.d"


@pytest.fixture(scope="module")
def packs():
    return load_catalog(CATALOG, LOCAL)


def _entry(sid, path, args, **kw):
    return {"id": sid, "type": "emulator", "label": sid, "platform": sid,
            "color": "#000000", "path": path, "args": args,
            "romsPath": f"emu/{sid}/", "extensions": [], "libretroSystems": [],
            **kw}


# ── the case this exists for ───────────────────────────────────────────────

def test_the_n64_launcher_is_repaired(packs, tmp_path):
    """The box says gopher64, the installer installs RMG.

    `update/linux.sh` used to detect exactly this and PRINT the commands the
    owner was expected to type. flatpakify cannot catch it either: the path is
    `flatpak`, which always exists.
    """
    live = [_entry("gopher64", "flatpak", "run io.github.gopher64.gopher64 -f")]
    merged, notes = merge_systems(live, packs, tmp_path)
    assert merged[0]["args"] == "run com.github.Rosalie241.RMG -f -n -q"
    assert any("gopher64: launcher updated" in n for n in notes)


def test_a_launcher_naming_a_declared_app_is_left_alone(packs, tmp_path):
    live = [_entry("rpcs3", "flatpak", "run net.rpcs3.RPCS3 --fullscreen --no-gui")]
    merged, notes = merge_systems(live, packs, tmp_path)
    assert merged[0]["args"] == "run net.rpcs3.RPCS3 --fullscreen --no-gui"
    assert not [n for n in notes if "rpcs3: launcher" in n]


def test_a_native_launcher_that_exists_is_never_overwritten(packs, tmp_path):
    """flatpakify rewrites launchers to what the box HAS. A box legitimately
    running the native binary from lib/ must not be pushed back to Flatpak."""
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "rpcs3").touch()
    live = [_entry("rpcs3", "lib/rpcs3", "--fullscreen --no-gui")]
    merged, notes = merge_systems(live, packs, tmp_path)
    assert merged[0]["path"] == "lib/rpcs3"
    assert not [n for n in notes if "rpcs3: launcher" in n]


def test_a_launcher_pointing_at_nothing_is_repaired(packs, tmp_path):
    """lib/rpcs3 is kept out of git — on a fresh box it does not exist."""
    live = [_entry("rpcs3", "lib/rpcs3", "--fullscreen --no-gui")]
    merged, notes = merge_systems(live, packs, tmp_path)
    assert merged[0]["path"] == "flatpak"
    assert any("does not exist on this box" in n for n in notes)


# ── what must never be lost ────────────────────────────────────────────────

def test_a_tile_the_operator_added_by_hand_is_untouched(packs, tmp_path):
    mine = _entry("myemu", "/opt/mine/run.sh", "--go", label="Mon émulateur")
    merged, _ = merge_systems([mine], packs, tmp_path)
    # The catalogue's own emulators are added alongside it; the point is that
    # the operator's entry comes through byte for byte, and first.
    assert merged[0] == mine
    assert sum(1 for e in merged if e["id"] == "myemu") == 1


def test_operator_edits_to_a_known_entry_survive(packs, tmp_path):
    """Only the launcher and the missing extensions are ours."""
    live = [_entry("rpcs3", "flatpak", "run net.rpcs3.RPCS3 --fullscreen --no-gui",
                   label="PS3 de Papa", color="#ff00ff")]
    merged, _ = merge_systems(live, packs, tmp_path)
    assert merged[0]["label"] == "PS3 de Papa"
    assert merged[0]["color"] == "#ff00ff"


def test_extensions_are_merged_additively(packs, tmp_path):
    """A machine installed before *.cue was added to duckstation scanned *.bin
    and not *.cue. The .cue shadowed the .bin, and was then filtered out — the
    library went from one PS1 game to none."""
    live = [_entry("duckstation", "flatpak", "run x", extensions=["*.bin", "*.moi"])]
    merged, notes = merge_systems(live, packs, tmp_path)
    ext = merged[0]["extensions"]
    assert "*.moi" in ext, "an extension the operator added must never be dropped"
    assert "*.cue" in ext and "*.chd" in ext
    assert ext.index("*.bin") < ext.index("*.cue"), "existing order preserved"
    assert any("extensions gained" in n for n in notes)


def test_a_new_emulator_reaches_an_installed_box(packs, tmp_path):
    merged, notes = merge_systems([], packs, tmp_path)
    ids = {e["id"] for e in merged}
    assert "rpcs3" in ids and "xenia" in ids
    assert any("new in this release" in n for n in notes)


def test_apps_are_not_added_to_the_systems_grid(packs, tmp_path):
    merged, _ = merge_systems([], packs, tmp_path)
    assert "twitch" not in {e["id"] for e in merged}
    assert "steam" not in {e["id"] for e in merged}


def test_a_clean_box_produces_no_notes(packs, tmp_path):
    """An update that changes nothing must say nothing — a NOTE the owner sees
    every single time is a NOTE they stop reading."""
    merged, _ = merge_systems([], packs, tmp_path)
    again, notes = merge_systems(merged, packs, tmp_path)
    assert notes == [], notes
    assert again == merged


# ── the file-level wrapper ─────────────────────────────────────────────────

def test_a_malformed_systems_json_is_left_alone(packs, tmp_path):
    """An update must not take the grid down because a hand edit left a
    trailing comma."""
    f = tmp_path / "systems.json"
    f.write_text("[{'not': 'json',}]")
    notes = merge_file(f, packs, tmp_path)
    assert "unreadable" in notes[0]
    assert f.read_text() == "[{'not': 'json',}]"


def test_the_previous_file_is_backed_up(packs, tmp_path):
    f = tmp_path / "systems.json"
    f.write_text(json.dumps([_entry("gopher64", "flatpak",
                                    "run io.github.gopher64.gopher64 -f")]))
    original = f.read_text()
    merge_file(f, packs, tmp_path)
    assert (tmp_path / "systems.json.bak-merge").read_text() == original
    assert json.loads(f.read_text())[0]["args"].startswith("run com.github.Rosalie241.RMG")


def test_dry_run_changes_nothing(packs, tmp_path):
    f = tmp_path / "systems.json"
    f.write_text(json.dumps([_entry("gopher64", "flatpak",
                                    "run io.github.gopher64.gopher64 -f")]))
    before = f.read_text()
    notes = merge_file(f, packs, tmp_path, dry_run=True)
    assert any("dry run" in n for n in notes)
    assert f.read_text() == before
