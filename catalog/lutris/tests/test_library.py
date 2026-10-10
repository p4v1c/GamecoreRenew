"""The PC library: Lutris's installed games as stubs, keys kept stable."""
import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

PACK = Path(__file__).resolve().parents[1]
APP = "net.lutris.Lutris"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


lib = _load("test_lutris_library", PACK / "files" / "lutris_library.py")
generator = _load("test_lutris_generator", PACK / "generator.py")


def make_db(path: Path, games, hidden=()):
    """A pga.db with Lutris 0.5.23's columns that the sync reads."""
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(
        "CREATE TABLE games (id INTEGER PRIMARY KEY, name TEXT, slug TEXT, runner TEXT,"
        " service TEXT, installed INTEGER);"
        "CREATE TABLE categories (id INTEGER PRIMARY KEY, name TEXT UNIQUE);"
        "CREATE TABLE games_categories (game_id INTEGER, category_id INTEGER);")
    con.executemany("INSERT INTO games VALUES (?, ?, ?, ?, ?, ?)", games)
    con.execute("INSERT INTO categories VALUES (1, '.hidden')")
    con.executemany("INSERT INTO games_categories VALUES (?, 1)", [(g,) for g in hidden])
    con.commit()
    con.close()
    return path


def game(gid, name, slug=None, runner="wine", service="gog"):
    return lib.Game(gid, name, slug or name.lower().replace(" ", "-"), runner, service)


def names(folder: Path):
    return sorted(p.name for p in folder.iterdir())


def test_installed_visible_games_are_read_and_hidden_ones_skipped(tmp_path):
    db = make_db(tmp_path / "pga.db", [
        (1, "Celeste", "celeste", "wine", "gog", 1),
        (2, "Hades", "hades", "wine", "epic", 1),
        (3, "Not Installed", "not-installed", "wine", "", 0),
        (4, "Secret", "secret", "linux", "", 1),
    ], hidden=[4])
    games = lib.installed_games(db)
    assert [(g.id, g.name) for g in games] == [(1, "Celeste"), (2, "Hades")]


def test_an_unreadable_library_answers_none(tmp_path):
    assert lib.installed_games(tmp_path / "missing.db") is None
    bad = tmp_path / "pga.db"
    bad.write_bytes(b"not a database at all" * 100)
    assert lib.installed_games(bad) is None


def test_a_library_without_categories_still_lists_its_games(tmp_path):
    db = tmp_path / "pga.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE games (id INTEGER, name TEXT, slug TEXT, runner TEXT,"
                " service TEXT, installed INTEGER)")
    con.execute("INSERT INTO games VALUES (7, 'Doom', 'doom', 'dosbox', '', 1)")
    con.commit()
    con.close()
    assert [g.name for g in lib.installed_games(db)] == ["Doom"]


def test_sync_writes_one_stub_per_game_and_is_idempotent(tmp_path):
    roms = tmp_path / "emu" / "lutris"
    games = [game(1, "Celeste"), game(2, "Hades", service="epic")]
    report = lib.sync(roms, games)
    assert names(roms) == ["Celeste.lutris", "Hades.lutris"]
    assert report["written"] == ["Celeste.lutris", "Hades.lutris"]
    stub = json.loads((roms / "Celeste.lutris").read_text())
    assert stub == {"lutrisId": 1, "name": "Celeste", "slug": "celeste",
                    "runner": "wine", "service": "gog"}
    assert lib.sync(roms, games) == {"written": [], "removed": [], "covers": []}


def test_a_renamed_game_keeps_its_file_name_so_playtime_follows(tmp_path):
    roms = tmp_path / "roms"
    lib.sync(roms, [game(1, "Celeste")])
    lib.sync(roms, [game(1, "Celeste (Farewell edition)", slug="celeste")])
    assert names(roms) == ["Celeste.lutris"]
    assert json.loads((roms / "Celeste.lutris").read_text())["name"].startswith("Celeste (")


def test_a_game_removed_in_lutris_leaves_the_library(tmp_path):
    roms = tmp_path / "roms"
    lib.sync(roms, [game(1, "Celeste"), game(2, "Hades")])
    (roms / "notes.txt").write_text("the owner's")
    (roms / "Mine.lutris").write_text("not json")
    report = lib.sync(roms, [game(2, "Hades")])
    assert report["removed"] == ["Celeste.lutris"]
    assert names(roms) == ["Hades.lutris", "Mine.lutris", "notes.txt"]


def test_a_reinstalled_game_takes_back_its_old_stub(tmp_path):
    roms = tmp_path / "roms"
    lib.sync(roms, [game(1, "Celeste")])
    report = lib.sync(roms, [game(9, "Celeste")])
    assert names(roms) == ["Celeste.lutris"]
    assert report["removed"] == []
    assert json.loads((roms / "Celeste.lutris").read_text())["lutrisId"] == 9


def test_two_games_with_one_title_get_two_names(tmp_path):
    roms = tmp_path / "roms"
    lib.sync(roms, [game(1, "Celeste"), game(2, "Celeste", service="itchio"),
                    game(3, "Celeste", service="itchio")])
    assert names(roms) == ["Celeste - 3.lutris", "Celeste - itchio.lutris", "Celeste.lutris"]


@pytest.mark.parametrize("title, stem", [
    ("Half-Life 2: Episode One", "Half-Life 2: Episode One"),
    ("AC/DC Rockband", "AC DC Rockband"),
    ("...hidden", "hidden"),
    ("S.T.A.L.K.E.R.", "S.T.A.L.K.E.R"),
    ("  ", "slug-fallback"),
])
def test_titles_become_safe_file_names(title, stem):
    assert lib.safe_stem(title, "slug-fallback") == stem


def test_a_very_long_title_is_cut_on_a_character_boundary():
    stem = lib.safe_stem("É" * 400, "x")
    assert len(stem.encode()) <= lib.MAX_NAME_BYTES
    stem.encode().decode()


def test_lutris_cover_becomes_the_cover_unless_one_exists(tmp_path):
    roms, covers, art = tmp_path / "roms", tmp_path / "covers", tmp_path / "coverart"
    art.mkdir()
    (art / "celeste.jpg").write_bytes(b"\xff\xd8celeste")
    (art / "hades.jpg").write_bytes(b"\xff\xd8hades")
    covers.mkdir()
    (covers / "Hades.webp").write_bytes(b"scraped")
    report = lib.sync(roms, [game(1, "Celeste"), game(2, "Hades")],
                      covers_dir=covers, coverart_dir=art)
    assert report["covers"] == ["Celeste.lutris"]
    assert (covers / "Celeste.jpg").read_bytes() == b"\xff\xd8celeste"
    assert not (covers / "Hades.jpg").exists()


def test_a_slug_cannot_reach_outside_the_cover_folder(tmp_path):
    art = tmp_path / "coverart"
    art.mkdir()
    (tmp_path / "secret.jpg").write_bytes(b"x")
    report = lib.sync(tmp_path / "roms", [game(1, "Evil", slug="../secret")],
                      covers_dir=tmp_path / "covers", coverart_dir=art)
    assert report["covers"] == []


def test_the_hook_reads_the_flatpak_library_and_keeps_stubs_when_it_cannot(tmp_path):
    home, roms = tmp_path / "home", tmp_path / "roms"
    data = home / ".var/app" / APP / "data/lutris"
    make_db(data / "pga.db", [(5, "Celeste", "celeste", "wine", "gog", 1)])
    report = generator.sync_library(roms_dir=roms, covers_dir=tmp_path / "covers", home=home)
    assert report["written"] == ["Celeste.lutris"]

    (data / "pga.db").write_bytes(b"garbage" * 512)
    assert generator.sync_library(roms_dir=roms, covers_dir=tmp_path / "c", home=home) is None
    assert names(roms) == ["Celeste.lutris"]


def test_the_hook_does_nothing_without_lutris(tmp_path):
    roms = tmp_path / "roms"
    assert generator.sync_library(roms_dir=roms, covers_dir=tmp_path / "c",
                                  home=tmp_path / "home") is None
    assert not roms.exists()


def test_a_custom_library_path_in_lutris_conf_is_followed(tmp_path):
    home = tmp_path / "home"
    data = home / ".var/app" / APP / "data/lutris"
    data.mkdir(parents=True)
    elsewhere = make_db(tmp_path / "disk" / "pga.db", [(1, "Hades", "hades", "wine", "", 1)])
    (data / "lutris.conf").write_text(f"[lutris]\npga_path = {elsewhere}\n")
    # The library is found through lutris.conf, which lives in data/ on a fresh box.
    paths = generator.paths
    assert paths.db_path(home, APP) == elsewhere
    assert lib.installed_games(paths.db_path(home, APP))[0].name == "Hades"
