"""One pack per system: gamecube + wii on Dolphin, gb + gbc + gba on mGBA.

The old packs (`dolphin`, `mgba`) stay as `supersededBy` packs so a box that
has not run scripts/split-systems.py keeps launching its old tile. These are
the rules that make that safe: the old pack is never offered, its successors
never appear as empty twins beside its tile, and the owner's controller
switch follows the emulator across the rename.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.services import controller_autoconfig as ac             # noqa: E402
from backend.services.catalog import load_catalog, selected          # noqa: E402
from backend.services.catalog.merge import merge_systems             # noqa: E402
from backend.services.configgen import superseded_ids                # noqa: E402

CATALOG = ROOT / "catalog"


@pytest.fixture(scope="module")
def packs():
    return load_catalog(CATALOG, ROOT / "config" / "catalog.d")


def _tile(sid):
    return {"id": sid, "type": "emulator", "label": sid, "platform": sid,
            "color": "#000000", "path": "flatpak", "args": "run @APPID@ -b",
            "romsPath": f"emu/{sid}/", "extensions": [], "libretroSystems": ["x"]}


# ── the OTA merge ───────────────────────────────────────────────────────────

def test_an_unmigrated_box_keeps_its_old_tile_and_gains_no_empty_twin(packs, tmp_path):
    merged, notes = merge_systems([_tile("dolphin"), _tile("mgba")], packs, tmp_path,
                                  present=lambda p: True)
    ids = [e["id"] for e in merged]
    assert ids[:2] == ["dolphin", "mgba"]
    for successor in ("gamecube", "wii", "gb", "gbc", "gba"):
        assert successor not in ids
        assert any(n.startswith(f"{successor}: not added") for n in notes)


def test_a_fresh_grid_gets_the_systems_and_never_the_old_packs(packs, tmp_path):
    merged, _ = merge_systems([], packs, tmp_path, present=lambda p: True)
    ids = {e["id"] for e in merged}
    assert {"gamecube", "wii", "gb", "gbc", "gba"} <= ids
    assert not ids & {"dolphin", "mgba"}


def test_declining_dolphin_declined_its_successors_too(packs, tmp_path):
    merged, _ = merge_systems([], packs, tmp_path, removed={"dolphin"}, present=lambda p: True)
    assert not {e["id"] for e in merged} & {"gamecube", "wii"}


def test_the_old_tile_still_resolves_to_a_pack_that_launches(packs):
    for old, owner in (("dolphin", "gamecube"), ("mgba", "gba")):
        assert packs[old].app_ids == packs[owner].app_ids
        assert packs[old].data["launch"] == packs[owner].data["launch"]


# ── what an install acts on ─────────────────────────────────────────────────

def test_everything_means_every_current_pack(packs):
    ids = {p.id for p in selected(packs)}
    assert {"gamecube", "wii", "gba"} <= ids
    assert not ids & {"dolphin", "mgba"}


def test_ticking_wii_alone_brings_the_pack_that_owns_dolphin(packs):
    assert {p.id for p in selected(packs, {"wii"})} == {"gamecube", "wii"}
    assert {p.id for p in selected(packs, {"gbc"})} == {"gba", "gbc"}


def test_an_old_install_conf_naming_dolphin_still_installs_it(packs):
    assert {p.id for p in selected(packs, {"dolphin"})} == {"dolphin", "gamecube"}


# ── the controller switch follows the emulator ──────────────────────────────

@pytest.fixture
def switch(tmp_path, monkeypatch):
    f = tmp_path / "controller-autoconfig.json"
    monkeypatch.setattr(ac, "state_file", lambda: f)
    return f


def test_dolphin_switched_off_before_the_split_keeps_gamecube_off(packs, switch):
    switch.write_text(json.dumps({"enabled": True, "packs": {"dolphin": False}}))
    assert superseded_ids(packs, "gamecube") == ("dolphin",)
    assert ac.enabled_for("gamecube", superseded_ids(packs, "gamecube")) is False


def test_switching_gamecube_back_on_clears_the_old_record_too(packs, switch):
    switch.write_text(json.dumps({"enabled": True, "packs": {"dolphin": False}}))
    ac.set_pack("gamecube", True, superseded_ids(packs, "gamecube"))
    assert ac.state()["packs"] == {}
    assert ac.enabled_for("gamecube", ("dolphin",)) is True


# ── the validator ───────────────────────────────────────────────────────────

def _checker(tmp_path, monkeypatch, *ids):
    spec = importlib.util.spec_from_file_location("check_catalog_split",
                                                  ROOT / "scripts" / "check-catalog.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for pid in ids:
        shutil.copytree(CATALOG / pid, tmp_path / "catalog" / pid)
    monkeypatch.setattr(mod, "CATALOG", tmp_path / "catalog")
    return mod


def test_the_split_packs_validate(tmp_path, monkeypatch):
    mod = _checker(tmp_path, monkeypatch, "dolphin", "gamecube", "wii")
    assert mod.check(None) == []


def test_a_pack_sharing_an_emulator_may_not_launch_it_differently(tmp_path, monkeypatch):
    mod = _checker(tmp_path, monkeypatch, "gamecube", "wii")
    manifest = tmp_path / "catalog" / "wii" / "pack.json"
    pack = json.loads(manifest.read_text())
    pack["launch"]["args"] = "run @APPID@"
    manifest.write_text(json.dumps(pack))
    assert any(p.startswith("wii: launch differs") for p in mod.check(None))


def test_only_the_owner_writes_the_emulator_config(tmp_path, monkeypatch):
    mod = _checker(tmp_path, monkeypatch, "gamecube", "wii")
    (tmp_path / "catalog" / "wii" / "generator.py").write_text("")
    assert any(p.startswith("wii: generator.py belongs to 'gamecube'") for p in mod.check(None))


def test_an_unrelated_pack_still_may_not_share_an_app_id(tmp_path, monkeypatch):
    mod = _checker(tmp_path, monkeypatch, "gamecube", "wii")
    manifest = tmp_path / "catalog" / "wii" / "pack.json"
    pack = json.loads(manifest.read_text())
    del pack["sharesEmulator"]
    manifest.write_text(json.dumps(pack))
    assert any("already claimed by gamecube" in p for p in mod.check(None))


# ── the logo an unmigrated tile asks for ────────────────────────────────────

def test_an_unmigrated_mgba_tile_keeps_its_own_logo(monkeypatch):
    """Its systems.json row says `gba.png`, which is now also a pack id."""
    from fastapi.testclient import TestClient

    from backend.main import app
    from backend.routers import systems as systems_router

    monkeypatch.setattr(systems_router, "list_all",
                        lambda: [{"id": "mgba", "iconPath": "assets/logos/gba.png"}])
    r = TestClient(app).get("/assets/logos/gba.png")
    assert r.status_code == 200
    assert r.content == (CATALOG / "mgba" / "logo.png").read_bytes()
