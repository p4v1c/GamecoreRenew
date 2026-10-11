"""A `.lutris` stub reaches ScreenScraper as its title, on PC Windows (138).

On the box, FIFA 22 (stub `FIFA 22.lutris`) got no metadata at all. The stub
was sent as `romnom=FIFA 22.lutris`, an extension ScreenScraper knows nothing
of; a PS3 folder is sent by its bare title and found.
"""
import json

import pytest

from backend.services.gamemedia import gamemedia as gm
from backend.services.gamemedia import registry
from backend.services.gamemedia.helpers import entry_dir

PC_WINDOWS = [{"id": 135, "noms": {"nom_eu": "PC Dos", "nom_recalbox": "pc"}},
              {"id": 138, "noms": {"nom_eu": "PC Windows", "nom_launchbox": "Windows"}}]


@pytest.fixture
def ss(monkeypatch, tmp_path):
    asked = []

    def fake_request(endpoint, params, verbose=False):
        asked.append(dict(params))
        if params.get("romnom") == "FIFA 22" and params.get("systemeid") == 138:
            return {"response": {"jeu": {
                "id": "1", "noms": [{"region": "wor", "text": "FIFA 22"}],
                "systeme": {"text": "PC Windows"}, "medias": [],
                "developpeur": {"text": "EA Vancouver"}, "dates": [{"region": "wor", "text": "2021"}]}}}
        return None

    monkeypatch.setattr(gm, "ss_request", fake_request)
    monkeypatch.setattr(gm.gs, "ss_credentials", lambda: {"devid": "x"})
    monkeypatch.setattr(gm.gs, "lb_index_ready", lambda: False)
    monkeypatch.setattr(registry, "fetch_systems", lambda force=False: PC_WINDOWS)
    monkeypatch.setattr(registry, "_registry", None)
    stub = tmp_path / "emu" / "lutris" / "FIFA 22.lutris"
    stub.parent.mkdir(parents=True)
    stub.write_text('{"lutrisId": 4, "name": "FIFA 22"}')
    return asked, stub


def test_a_stub_is_searched_by_its_title_on_pc_windows(ss):
    asked, stub = ss
    manifest = gm.resolve("lutris", str(stub), download=False)
    assert manifest["found"] is True
    assert manifest["meta"]["developer"] == "EA Vancouver"
    assert [(a["romnom"], a.get("systemeid")) for a in asked] == [("FIFA 22", 138)]
    assert not any(k in asked[0] for k in ("crc", "md5", "sha1"))


def test_a_negative_from_the_old_query_is_asked_again_once(ss):
    asked, stub = ss
    old = {"system": "lutris", "filename": str(stub), "found": False,
           "parsed": {"source": str(stub), "title": "FIFA 22"},
           "tiers_tried": ["screenscraper"], "unreachable": False, "media": {}}
    d = entry_dir("lutris", str(stub))
    d.mkdir(parents=True, exist_ok=True)
    (d / gm.MANIFEST).write_text(json.dumps(old))
    assert gm.resolve("lutris", str(stub), download=False)["found"] is True
    # A negative written by the new query is final like any other.
    assert gm._manifest_complete(d, {**old, "parsed": {"romnom": "FIFA 22"}}) is True


def test_a_metadata_negative_from_the_old_query_is_not_kept_for_a_week(tmp_path, monkeypatch):
    import asyncio
    from backend.services import metadata
    monkeypatch.setattr(metadata, "METADATA_DIR", tmp_path)
    monkeypatch.setattr(metadata, "rom_in_root", lambda system, filename: None)
    monkeypatch.setattr(metadata.gamemedia, "available", lambda: True)
    asked = []

    async def found(sid, target):
        asked.append(target)
        return {"found": True}
    monkeypatch.setattr(metadata.gamemedia, "resolve", found)
    monkeypatch.setattr(metadata.gamemedia, "to_game_meta",
                        lambda m: {"found": True, "title": "FIFA 22", "source": "gamemedia"})
    (tmp_path / "lutris").mkdir()
    (tmp_path / "lutris" / "FIFA 22.json").write_text(
        json.dumps({"found": False, "tiers_tried": ["gamemedia"]}))
    (tmp_path / "lutris" / "Hades.json").write_text(
        json.dumps({"found": False, "tiers_tried": ["gamemedia"], "by_title": True}))

    assert asyncio.run(metadata.resolve({"id": "lutris"}, "FIFA 22.lutris"))["title"] == "FIFA 22"
    assert asyncio.run(metadata.resolve({"id": "lutris"}, "Hades.lutris")) is None
    assert asked == ["FIFA 22.lutris"]
