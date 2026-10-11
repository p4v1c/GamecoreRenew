"""A PC game's minimum spec from the Steam store.

Offline: `steam_store._get_json` is replaced in every test that would reach
the store. The HTML below is FIFA 22's real `pc_requirements.minimum`.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import pytest

from backend.services.gamemedia import gamemedia as gm
from backend.services.gamemedia import steam_store as ss

FIFA22_MINIMUM = (
    '<strong>Minimum:</strong><br><ul class="bb_ul"><li>Requires a 64-bit processor and '
    'operating system<br></li><li><strong>OS:</strong> Windows 10 - 64-Bit (Latest Update)'
    '<br></li><li><strong>Processor:</strong> Intel Core i3-6100 @ 3.7GHz or AMD Athlon X4 '
    '880K @4GHz<br></li><li><strong>Memory:</strong> 8 GB RAM<br></li><li><strong>Graphics:'
    '</strong> NVIDIA GTX 660 2GB or AMD Radeon HD 7850 2GB<br></li><li><strong>Storage:'
    '</strong> 50 GB available space</li></ul>')


def _store(search_items, details):
    """A fake `_get_json`: storesearch answers `search_items`, appdetails `details`."""
    calls = []

    def get_json(url, params):
        calls.append(url)
        if url == ss.SEARCH_URL:
            return {"total": len(search_items), "items": search_items}
        return details
    get_json.calls = calls
    return get_json


def _details(appid, type_="game", minimum=FIFA22_MINIMUM):
    return {str(appid): {"success": True, "data": {
        "type": type_, "name": "x", "pc_requirements": {"minimum": minimum}}}}


def test_fifa_22_minimum_spec_is_read_short_enough_for_one_line():
    assert ss.parse_requirements(FIFA22_MINIMUM) == {
        "os": "Windows 10 - 64-Bit", "cpu": "Intel Core i3-6100", "ram": "8 GB",
        "gpu": "NVIDIA GTX 660 2GB", "disk": "50 GB"}


def test_other_label_spellings_and_marks_are_understood():
    raw = ("<ul><li><strong>Operating System *:</strong> Windows® 7 SP1, Windows 10</li>"
           "<li><strong>Video Card:</strong> GeForce 8800 / Radeon HD 2900</li>"
           "<li><strong>Hard Drive:</strong> 1.5 GB HD space</li>"
           "<li><strong>DirectX:</strong> Version 9.0c</li></ul>")
    assert ss.parse_requirements(raw) == {
        "os": "Windows 7 SP1", "gpu": "GeForce 8800", "disk": "1.5 GB"}


def test_plain_text_requirements_give_nothing_rather_than_garbage():
    assert ss.parse_requirements("Minimum: a computer") == {}
    assert ss.parse_requirements("") == {}


@pytest.mark.parametrize("title,name,same", [
    ("FIFA 22", "FIFA 22", True),
    ("FIFA 22", "FIFA 23", False),
    ("Grand Theft Auto V", "Grand Theft Auto IV", False),   # 0.97 by text alone
    ("Hollow Knight", "Hollow Knight: Silksong", False),
    ("Portal 2", "Portal™ 2", True),
])
def test_a_store_entry_is_accepted_only_when_it_is_the_same_game(title, name, same):
    assert ss.same_game(title, name) is same


def test_fifa_22_never_takes_fifa_23s_app_id(monkeypatch):
    monkeypatch.setattr(ss, "_get_json", _store([{"id": 1849250, "name": "FIFA 23"}], {}))
    assert ss.find_appid("FIFA 22") is None


def test_the_matching_entry_is_picked_among_the_results(monkeypatch):
    items = [{"id": 1, "name": "FIFA 22 Soundtrack x"}, {"id": 1506830, "name": "FIFA 22"}]
    monkeypatch.setattr(ss, "_get_json", _store(items, {}))
    assert ss.find_appid("FIFA 22") == 1506830


def test_a_dlc_or_an_empty_list_gives_no_spec(monkeypatch):
    monkeypatch.setattr(ss, "_get_json", _store([], _details(7, type_="dlc")))
    assert ss.requirements_for(7) == {}
    empty = {"7": {"success": True, "data": {"type": "game", "pc_requirements": []}}}
    monkeypatch.setattr(ss, "_get_json", _store([], empty))
    assert ss.requirements_for(7) == {}


def _manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(ss, "entry_dir", lambda system, filename: tmp_path)
    return {"found": True, "filename": "/x/FIFA 22.lutris", "meta": {"title": "FIFA 22"},
            "media": {}, "cached": True}


def test_the_spec_and_the_answer_are_saved_in_the_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(ss, "_get_json",
                        _store([{"id": 1506830, "name": "FIFA 22"}], _details(1506830)))
    out = ss.add_requirements("lutris", _manifest(tmp_path, monkeypatch))
    assert out["meta"]["requirements"]["cpu"] == "Intel Core i3-6100"
    saved = json.loads((tmp_path / "game.json").read_text("utf-8"))
    assert saved["steam"]["appid"] == 1506830
    assert saved["meta"]["requirements"] == out["meta"]["requirements"]
    assert saved["cached"] is False


def test_a_miss_is_cached_so_the_store_is_asked_once(tmp_path, monkeypatch):
    fake = _store([], {})
    monkeypatch.setattr(ss, "_get_json", fake)
    out = ss.add_requirements("lutris", _manifest(tmp_path, monkeypatch))
    assert out["steam"]["appid"] is None and "requirements" not in out["meta"]
    ss.add_requirements("lutris", out)
    assert len(fake.calls) == 1


def test_offline_stores_nothing_and_does_not_raise(tmp_path, monkeypatch):
    def offline(url, params):
        raise ss.SteamUnreachable("URLError: no route")
    monkeypatch.setattr(ss, "_get_json", offline)
    out = ss.add_requirements("lutris", _manifest(tmp_path, monkeypatch))
    assert "steam" not in out
    assert not (tmp_path / "game.json").exists()


def test_a_network_error_is_reported_as_unreachable(monkeypatch):
    def refuse(*a, **k):
        raise OSError("connection refused")
    monkeypatch.setattr(ss.urllib.request, "urlopen", refuse)
    with pytest.raises(ss.SteamUnreachable):
        ss.find_appid("FIFA 22")


def test_only_packs_that_opt_in_are_looked_up(monkeypatch):
    class Pack:
        def __init__(self, id_, scraper):
            self.id, self.data = id_, {"scraper": scraper}
    packs = {"lutris": Pack("lutris", {"steamStore": True}), "pcsx2": Pack("pcsx2", {})}
    import backend.services.catalog as catalog
    monkeypatch.setattr(catalog, "load_catalog", lambda: packs)
    assert ss.opted_in_systems() == frozenset({"lutris"})


def test_the_lutris_pack_opts_in():
    pack = json.loads((REPO / "catalog/lutris/pack.json").read_text("utf-8"))
    assert pack["scraper"]["steamStore"] is True


def test_resolve_asks_the_store_for_opted_in_systems_only(monkeypatch):
    import asyncio
    from backend.services import gamemedia
    seen = []
    monkeypatch.setattr(gamemedia, "available", lambda: True)
    monkeypatch.setattr(gamemedia, "STEAM_STORE_SYSTEMS", frozenset({"lutris"}))
    monkeypatch.setattr(gm, "resolve", lambda system, name, **k: {"found": True, "system": system})
    monkeypatch.setattr(ss, "add_requirements", lambda system, m: seen.append(system) or m)
    asyncio.run(gamemedia.resolve("lutris", "/x/FIFA 22.lutris"))
    asyncio.run(gamemedia.resolve("pcsx2", "/x/Ico.iso"))
    assert seen == ["lutris"]
