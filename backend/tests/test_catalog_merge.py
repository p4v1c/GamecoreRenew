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
    REMOVED_FILE, merge_file, merge_systems,
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
    assert merged[0]["args"] == "run @APPID@ -f -n -q"
    assert any("gopher64: launcher updated" in n for n in notes)


def test_a_launcher_hardcoding_a_live_app_id_is_migrated_to_the_token(packs, tmp_path):
    """The launchers every box installed before `install.appIds` existed.

    `run net.rpcs3.RPCS3` is not broken — it is exactly what is installed — and
    the old rule therefore left it alone. That is the trap: it keeps working
    right up until the catalogue drops that candidate, and then the tile is the
    one thing still naming it. The player gets flatpak's "app not installed"
    for an emulator the box installed successfully under another name.

    An OTA merge is the only moment an installed box gets migrated, so a live
    but frozen id has to count as stale BEFORE it breaks, not after.
    """
    live = [_entry("rpcs3", "flatpak", "run net.rpcs3.RPCS3 --fullscreen --no-gui")]
    merged, notes = merge_systems(live, packs, tmp_path)
    assert merged[0]["args"] == "run @APPID@ --fullscreen --no-gui"
    assert any("hardcodes net.rpcs3.RPCS3" in n for n in notes)


def test_a_launcher_already_on_the_token_is_left_alone(packs, tmp_path):
    """The migration must be idempotent: an OTA a week later must not report
    the same tile as changed again, or every update looks like it did work."""
    live = [_entry("rpcs3", "flatpak", "run @APPID@ --fullscreen --no-gui")]
    merged, notes = merge_systems(live, packs, tmp_path)
    assert merged[0]["args"] == "run @APPID@ --fullscreen --no-gui"
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
    mine = _entry("myemu", "/opt/mine/run.sh", "--go", label="My emulator")
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


def test_new_emulators_arrive_in_the_curated_order(packs, tmp_path):
    """Appended by pack `order`, like the .dist — not alphabetically by folder."""
    merged, _ = merge_systems([], packs, tmp_path)
    dist = json.loads((ROOT / "install/generated/systems.json.dist").read_text())
    assert [e["id"] for e in merged] == [e["id"] for e in dist]


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
    assert json.loads(f.read_text())[0]["args"].startswith("run @APPID@")


def test_dry_run_changes_nothing(packs, tmp_path):
    f = tmp_path / "systems.json"
    f.write_text(json.dumps([_entry("gopher64", "flatpak",
                                    "run io.github.gopher64.gopher64 -f")]))
    before = f.read_text()
    notes = merge_file(f, packs, tmp_path, dry_run=True)
    assert any("dry run" in n for n in notes)
    assert f.read_text() == before


# ── consoles: the only way roms.consoles reaches a box that already exists ──

def test_a_box_gains_the_consoles_of_a_multi_console_pack(packs, tmp_path):
    """`config/` is excluded from the OTA rsync, so a release that adds
    `roms.consoles` to mgba changes nothing in a systems.json already on a box.
    This merge is the whole delivery mechanism — without it the console level
    ships and no installed machine ever sees it."""
    live = [_entry("mgba", "flatpak", "run io.mgba.mGBA --fullscreen")]
    merged, notes = merge_systems(live, packs, tmp_path)

    assert [c["id"] for c in merged[0]["consoles"]] == ["gba", "gbc", "gb"]
    assert any("mgba: consoles filled in" in n for n in notes)
    # And every extension a console claims is one the pack really scans, or the
    # console would name files the library never lists.
    for console in merged[0]["consoles"]:
        assert set(console["extensions"]) <= set(merged[0]["extensions"])


def test_a_mono_console_pack_gains_nothing(packs, tmp_path):
    """Eleven of the thirteen. The key is that no `consoles` appears at all —
    an empty list would be indistinguishable from "this entry predates the
    field", which is the state the fill-in above has to be able to detect."""
    live = [_entry("pcsx2", "flatpak", "run net.pcsx2.PCSX2 -fullscreen -nogui")]
    merged, notes = merge_systems(live, packs, tmp_path)
    assert "consoles" not in merged[0]
    assert not any("consoles" in n for n in notes)


def test_a_console_list_the_operator_edited_is_left_alone(packs, tmp_path):
    """Same rule as `libretroSystems`: filled in only when the box has none.
    A list somebody changed by hand is a list they meant, and an OTA that
    overwrote it would undo the edit on every update, silently."""
    mine = [{"id": "gba", "label": "Mon GBA", "extensions": ["*.gba", "*.zip"]}]
    live = [_entry("mgba", "flatpak", "run io.mgba.mGBA --fullscreen",
                   consoles=mine)]
    merged, _ = merge_systems(live, packs, tmp_path)
    assert merged[0]["consoles"] == mine


# ── two roots ───────────────────────────────────────────────────────────────

def test_the_removed_list_is_read_from_the_data_root_when_given(packs, tmp_path):
    """`catalog-removed.json` lives beside the grid — on the data side. A
    box whose data has moved keeps a stale copy under the install that lists
    nothing, and reading THAT would resurrect every declined system."""
    code, data = tmp_path / "code", tmp_path / "data"
    (code / "config").mkdir(parents=True)
    (data / "config").mkdir(parents=True)
    grid = data / "config" / "systems.json"
    grid.write_text("[]")
    (data / "config" / REMOVED_FILE).write_text(json.dumps(["cemu", "xenia", "ryujinx"]))
    (code / "config" / REMOVED_FILE).write_text("[]")           # the stale copy

    merge_file(grid, packs, code, data_root=data)
    ids = {s["id"] for s in json.loads(grid.read_text())}
    assert not ids & {"cemu", "xenia", "ryujinx"}, ids

    # Without data_root the old behaviour is exactly preserved.
    grid.write_text("[]")
    merge_file(grid, packs, code)
    ids = {s["id"] for s in json.loads(grid.read_text())}
    assert {"cemu", "xenia", "ryujinx"} <= ids


def test_a_missing_console_ratio_is_filled_in_and_a_set_one_is_kept(packs, tmp_path):
    """The gentler half of the fill-in rule: a box that already carries the
    console list gains a MISSING ratio and nothing else — adding an absent key
    cannot undo an operator's edit; rewriting a present one could."""
    mine = [{"id": "gba", "label": "Game Boy Advance", "extensions": ["*.gba"]},
            {"id": "gb", "label": "Game Boy", "ratio": "8:7",
             "extensions": ["*.gb", "*.gbc"]}]
    live = [_entry("mgba", "flatpak", "run io.mgba.mGBA --fullscreen",
                   consoles=mine)]
    merged, notes = merge_systems(live, packs, tmp_path)
    by = {c["id"]: c for c in merged[0]["consoles"]}
    assert by["gba"]["ratio"] == "3:2"                # absent → filled from the pack
    assert by["gb"]["ratio"] == "8:7"                 # the operator's SGB choice, kept
    assert any("console ratio filled in (gba)" in n for n in notes)
    # And the extensions the operator merged into one console are untouched.
    assert by["gb"]["extensions"] == ["*.gb", "*.gbc"]


# ── bezels: config/overlays.json and assets/overlays/ are never rsynced ───────

def test_new_bezels_reach_an_installed_box_and_nothing_is_overwritten(tmp_path):
    from backend.services.catalog.merge import merge_overlays
    shipped, data = tmp_path / "release", tmp_path / "userdata"
    (shipped / "config").mkdir(parents=True)
    (shipped / "assets/overlays").mkdir(parents=True)
    (data / "config").mkdir(parents=True)
    (data / "assets/overlays").mkdir(parents=True)
    (shipped / "config/overlays.json").write_text(json.dumps(
        {"pcsx2": {"hole": "shipped"}, "nes": {"hole": "new"}}))
    (data / "config/overlays.json").write_text(json.dumps({"pcsx2": {"hole": "mine"}}))
    (shipped / "assets/overlays/pcsx2.png").write_bytes(b"shipped")
    (shipped / "assets/overlays/nes.png").write_bytes(b"new")
    (data / "assets/overlays/pcsx2.png").write_bytes(b"uploaded")

    notes = merge_overlays(shipped, data)

    live = json.loads((data / "config/overlays.json").read_text())
    assert live == {"pcsx2": {"hole": "mine"}, "nes": {"hole": "new"}}
    assert (data / "assets/overlays/pcsx2.png").read_bytes() == b"uploaded"
    assert (data / "assets/overlays/nes.png").read_bytes() == b"new"
    assert sorted(notes) == ["nes: bezel added", "nes: bezel geometry added"]
    assert merge_overlays(shipped, data) == []


def test_the_updater_merges_bezels_from_the_release_tree():
    text = (ROOT / "update/linux.sh").read_text()
    assert '"${GAMECORE_PATH}" "${SRC_DIR}" "${GAMECORE_DATA}"' in text
    assert "merge_overlays(Path(sys.argv[2]), Path(sys.argv[3]))" in text


def test_pack_present_by_provider(packs, tmp_path):
    from backend.services.catalog.merge import pack_present
    dolphin, duck = packs["dolphin"], packs["duckstation"]
    assert pack_present(dolphin, tmp_path, None)        # flatpak unseen: keep the tile
    assert not pack_present(dolphin, tmp_path, frozenset())
    assert pack_present(dolphin, tmp_path, frozenset(dolphin.app_ids[:1]))
    assert not pack_present(duck, tmp_path, None)
    dest = tmp_path / duck.data["install"]["dest"]
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"\x7fELF")
    assert pack_present(duck, tmp_path, None)
    native = tmp_path / "native"
    (native / "lib").mkdir(parents=True)
    (native / "lib" / "duck").write_bytes(b"\x7fELF")   # preferIfPresent: lib/duck
    assert pack_present(duck, native, None)


def test_merge_keeps_an_absent_newcomer_off_the_grid(packs, tmp_path):
    merged, notes = merge_systems([], packs, tmp_path, present=lambda p: p.id != "nes")
    assert "nes" not in {e["id"] for e in merged}
    assert "nes: not added — its emulator is not installed" in notes
