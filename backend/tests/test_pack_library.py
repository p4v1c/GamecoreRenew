"""A pack's say in its library listing: the Lutris stubs, the hidden extension,
and PC games looked up by name as "PC Windows"."""
import sqlite3
from pathlib import Path

import pytest

from backend.routers import games
from backend.services import configgen, pack_library
from backend.services.gamemedia import registry, ss_client

APP = "net.lutris.Lutris"

# systemesListe entries 135-138 as ScreenScraper publishes them (names trimmed),
# copied from the cache Skyscraper ships (screenscraper_platforms.json).
SS_SYSTEMS = [
    {"id": 135, "noms": {"nom_eu": "PC Dos", "nom_recalbox": "pc", "nom_retropie": "pc",
                         "nom_launchbox": "MS-Dos", "noms_commun": "DOS,MS-DOS,PC"}},
    {"id": 136, "noms": {"nom_eu": "PC Win3.xx", "nom_launchbox": "Windows 3.X"}},
    {"id": 137, "noms": {"nom_eu": "PC Win9X", "noms_commun": "Windows 95,Windows 98"}},
    {"id": 138, "noms": {"nom_eu": "PC Windows", "nom_launchbox": "Windows",
                         "noms_commun": "Microsoft Windows,Windows,Windows 10"}},
]


@pytest.fixture
def lutris_box(tmp_path, monkeypatch):
    """A home with a Flatpak Lutris library, and a `lutris` tile on the grid."""
    home = tmp_path / "home"
    db = home / ".var/app" / APP / "data/lutris/pga.db"
    db.parent.mkdir(parents=True)
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE games (id INTEGER, name TEXT, slug TEXT, runner TEXT,"
                " service TEXT, installed INTEGER)")
    con.executemany("INSERT INTO games VALUES (?, ?, ?, 'wine', 'gog', ?)",
                    [(1, "Celeste", "celeste", 1), (2, "Hades", "hades", 1),
                     (3, "Gone", "gone", 0)])
    con.commit()
    con.close()
    roms = tmp_path / "emu" / "lutris"
    system = {"id": "lutris", "romsPath": str(roms), "extensions": ["*.lutris"]}
    monkeypatch.setattr(configgen, "HOME", home)
    monkeypatch.setattr(games, "find", lambda sid: system if sid == "lutris" else None)
    monkeypatch.setattr(games, "resolve_path", lambda raw: Path(raw))
    return db, roms


def test_the_pc_library_lists_lutris_games_without_an_extension(lutris_box):
    _db, roms = lutris_box
    listed = games.list_games("lutris")
    assert [(g["display_name"], g["ext"]) for g in listed] == [("Celeste", ""), ("Hades", "")]
    assert sorted(p.name for p in roms.iterdir()) == ["Celeste.lutris", "Hades.lutris"]


def test_a_game_uninstalled_in_lutris_is_gone_at_the_next_listing(lutris_box):
    db, _roms = lutris_box
    games.list_games("lutris")
    con = sqlite3.connect(db)
    con.execute("UPDATE games SET installed = 0 WHERE id = 1")
    con.commit()
    con.close()
    assert [g["filename"] for g in games.list_games("lutris")] == ["Hades.lutris"]


def test_other_systems_keep_their_extension_and_have_no_hook():
    assert pack_library.shows_extension("snes9x") is True
    assert pack_library.shows_extension("not-a-pack") is True
    assert pack_library.shows_extension("lutris") is False
    pack_library.sync("snes9x", Path("/nonexistent"))        # no hook: nothing happens


def test_a_failing_hook_never_breaks_the_listing(monkeypatch, tmp_path):
    class Broken:
        @staticmethod
        def sync_library(**kwargs):
            raise RuntimeError("boom")
    monkeypatch.setattr(configgen, "load_generator", lambda pack: Broken)
    pack_library.sync("lutris", tmp_path)


def test_pc_games_are_looked_up_as_pc_windows_not_dos(monkeypatch):
    monkeypatch.setattr(registry, "fetch_systems", lambda force=False: SS_SYSTEMS)
    monkeypatch.setattr(registry, "_registry", None)
    sid, info = registry.detect_system("Celeste.lutris", "lutris")
    assert sid == 138 and info["launchbox"] == "Windows"
    assert registry.system_candidates("Celeste.lutris", "lutris") == [138]


def test_a_stub_is_never_hashed_for_screenscraper(tmp_path):
    stub = tmp_path / "Celeste.lutris"
    stub.write_text('{"lutrisId": 1}')
    assert ss_client.hashes_for(stub) is None
