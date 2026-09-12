"""The Store's Games tab, on the backend side.

Nothing here reaches the network, and nothing here writes a byte. Both are
asserted rather than assumed: the provider under test is the demo one, whose
whole point is that it invents its rows, and the last test in this file stands
guard over the ROM directory the later ingestion steps will write into.

What is pinned:

  · **system first** — a search is scoped to one console, and an uninstalled
    one is refused. That is the decision the whole Games tab is built on
    (`docs/architecture/14-store-ingestion-matrix.md` §0: the strategy is keyed
    on the pair (system, incoming format), so the system cannot be discovered
    afterwards);
  · **honest about itself** — `live` is false and travels with every answer;
  · **deterministic** — the same search twice is the same rows, so a cursor
    standing on one does not find a different game underneath it;
  · **the pair is visible** — the formats offered are the console's own plus
    the archives an indexer really serves, which is what makes a row useful to
    §5 later without classifying anything now.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.main import app                                   # noqa: E402
from backend.services import paths                             # noqa: E402
from backend.services.store import (                           # noqa: E402
    SearchSystem, get_provider, searchable_systems, system_for)
from backend.services.store.demo import DemoSearchProvider     # noqa: E402

# Four consoles chosen because they are four different answers to "what does a
# download have to become" — matrix §5.1 classes A, C, D/E and F.
INSTALLED = ["nes", "mame", "duckstation", "rpcs3"]


@pytest.fixture
def box(tmp_path, monkeypatch):
    """A box with four consoles on its grid and nothing else.

    Only the DATA root moves: the catalogue is shipped code and is read from
    where `loader.CATALOG_DIR` bound it at import (the suite's throwaway root,
    which conftest symlinks at the real `catalog/`). Moving that too would
    leave every pack unreadable and the tests green about an empty box.
    """
    monkeypatch.setattr(paths, "GAMECORE_DATA", tmp_path)
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "config" / "systems.json").write_text(
        json.dumps([{"id": i} for i in INSTALLED]))
    return tmp_path


@pytest.fixture
def client(box):
    return TestClient(app)


def _search(client, system: str, q: str = "zelda"):
    return client.get("/api/store/search", params={"system": system, "q": q})


# ── which provider answers ─────────────────────────────────────────────────

def test_the_box_ships_the_demo_provider_and_says_the_rows_are_not_real(client):
    """`live` is the field that stops this being a lie.

    A tab that could not tell an invented row from an indexer's would invite a
    player to press ✕ on a game that does not exist.
    """
    info = client.get("/api/store/provider").json()
    assert info["name"] == "demo"
    assert info["live"] is False
    assert info["systemFirst"] is True


def test_an_unknown_provider_name_falls_back_rather_than_going_quiet(monkeypatch):
    """A typo in the variable must not be how the Games tab goes silent."""
    monkeypatch.setenv("GAMECORE_STORE_SEARCH_PROVIDER", "prowlar")
    assert get_provider().name == "demo"


def test_a_real_provider_that_is_not_configured_falls_back_the_same_way(
        monkeypatch):
    """`prowlarr` is a name this box knows and an instance it does not have.

    Selected-and-not-ready lands on the demo provider for the same reason an
    unknown name does: rows that are honestly labelled invented beat a client
    with no URL, which can only turn every search into a 502. What it takes to
    be ready is `test_store_prowlarr.py`'s business.
    """
    monkeypatch.setenv("GAMECORE_STORE_SEARCH_PROVIDER", "prowlarr")
    assert get_provider().name == "demo"


def test_naming_the_demo_provider_explicitly_selects_it(monkeypatch):
    monkeypatch.setenv("GAMECORE_STORE_SEARCH_PROVIDER", "demo")
    assert get_provider().name == "demo"


# ── only installed consoles ────────────────────────────────────────────────

def test_only_the_installed_emulators_are_searchable(client):
    rows = client.get("/api/store/systems").json()
    assert {r["id"] for r in rows} == set(INSTALLED)
    # The target directory travels with the console, because it is a property
    # of the console and of nothing else — matrix §1.3.
    assert {r["romsDir"] for r in rows} == {
        "emu/nes", "emu/mame", "emu/duckstation", "emu/rpcs3"}


def test_the_list_is_ordered_the_way_a_cursor_walks_it(client):
    labels = [r["label"] for r in client.get("/api/store/systems").json()]
    assert labels == sorted(labels, key=str.lower)


def test_a_console_that_is_not_installed_is_refused(client):
    """Not searched and not silently empty.

    A Saturn game on a box with no Saturn is a download into a directory
    nothing scans, for a tile that is not on the grid.
    """
    r = _search(client, "saturn")
    assert r.status_code == 409
    assert "saturn" in r.json()["detail"]


def test_a_pack_that_is_not_an_emulator_is_not_a_console(box):
    """`steam` is installed software, not a machine games are searched for."""
    (box / "config" / "systems.json").write_text(
        json.dumps([{"id": "nes"}, {"id": "steam"}]))
    assert system_for("steam") is None
    assert system_for("nes") is not None


def test_a_box_with_no_systems_file_is_searchable_nowhere(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "GAMECORE_DATA", tmp_path)
    assert searchable_systems() == []


# ── what the endpoint refuses ──────────────────────────────────────────────

@pytest.mark.parametrize("system", ["../etc", "NES", "nes;rm", ""])
def test_a_system_id_that_is_not_one_is_refused(client, system):
    assert _search(client, system).status_code in (400, 422)


@pytest.mark.parametrize("q", ["", "   "])
def test_an_empty_query_is_refused(client, q):
    assert _search(client, "nes", q).status_code == 400


def test_an_enormous_query_is_refused_before_it_reaches_a_provider(client):
    """The cap is here for the provider that is not written yet: a query is a
    request to somebody else's indexer once one is wired up."""
    assert _search(client, "nes", "z" * 500).status_code == 400


def test_a_provider_that_throws_is_a_502_and_says_nothing_about_why(client, monkeypatch):
    """The reason is logged, never returned — it may carry a URL or a key."""
    async def boom(self, system, query, limit=40):
        raise RuntimeError("http://indexer.invalid?apikey=hunter2")

    monkeypatch.setattr(DemoSearchProvider, "search", boom)
    r = _search(client, "nes")
    assert r.status_code == 502
    assert "hunter2" not in r.text


# ── what a search answers ──────────────────────────────────────────────────

def test_a_search_answers_rows_for_the_console_it_was_scoped_to(client):
    body = _search(client, "nes").json()
    assert body["system"] == "nes"
    assert body["romsDir"] == "emu/nes"
    assert body["live"] is False
    assert body["results"]
    assert all(r["systemId"] == "nes" for r in body["results"])
    assert all(r["title"] and r["filename"] and r["size"] > 0
               for r in body["results"])
    # Enough to find it again, and deliberately not a URL anything follows.
    assert all(r["source"].startswith("demo://") for r in body["results"])


def test_the_same_search_twice_is_the_same_rows(client):
    """A cursor standing on row four must not find a different game under it."""
    first = _search(client, "nes").json()["results"]
    second = _search(client, "nes").json()["results"]
    assert first == second


def test_two_consoles_do_not_answer_the_same_thing(client):
    """The console is part of the seed, not decoration on the answer."""
    nes = _search(client, "nes").json()["results"]
    mame = _search(client, "mame").json()["results"]
    assert [r["filename"] for r in nes] != [r["filename"] for r in mame]


def test_a_query_with_nothing_to_search_for_answers_empty(client):
    """The empty state has to exist before step 10 produces it for real."""
    assert _search(client, "nes", "---").json()["results"] == []


# ── the pair (system, format), which is what all of this is for ────────────

def _formats(client, system, q="zelda"):
    return {r["format"] for r in _search(client, system, q).json()["results"]}


def test_a_console_is_offered_its_own_formats_and_the_archives_too(client):
    """Matrix §2.3 — the case that bites.

    `nes` declares no `*.zip`, so a `.zip` is invisible to its scan and the
    download must be unpacked or it is silently wasted. The tab has to be able
    to show that row long before anything can unpack it, so the demo provider
    offers it: across enough queries both shapes turn up.
    """
    seen: set[str] = set()
    for q in ("zelda", "mario", "metroid", "castlevania", "contra", "kirby"):
        seen |= _formats(client, "nes", q)
    assert "nes" in seen                       # what the pack declares
    assert seen & {"zip", "7z"}                # and what an indexer serves


def test_an_arcade_romset_is_only_ever_an_archive(client):
    """Matrix §2.1 — on `mame` the archive IS the ROM, and it declares nothing
    else that a search could plausibly offer."""
    seen: set[str] = set()
    for q in ("street fighter", "neogeo", "pacman"):
        seen |= _formats(client, "mame", q)
    assert seen <= {"zip", "7z"}


def test_the_cmd_extension_is_never_offered(client):
    """Matrix §6.4: `*.cmd` is declared by `catalog/mame/pack.json` and
    explained nowhere, and until it is known "the Store should neither produce
    nor rewrite one". Inventing a plausible `.cmd` row is producing one."""
    seen: set[str] = set()
    for q in ("street fighter", "neogeo", "pacman", "galaga", "1942"):
        seen |= _formats(client, "mame", q)
    assert "cmd" not in seen


def test_a_folder_console_is_offered_a_folder(client):
    """Matrix §5.1 F — on `rpcs3` the game is a directory, and a result that
    is one carries no extension at all."""
    seen: set[str] = set()
    for q in ("demons souls", "ratchet", "uncharted"):
        seen |= _formats(client, "rpcs3", q)
    assert "folder" in seen
    folders = [r for r in _search(client, "rpcs3", "demons souls").json()["results"]
               if r["format"] == "folder"]
    assert folders
    assert all(not Path(r["filename"]).suffix for r in folders)


def test_a_disc_console_is_offered_a_descriptor(client):
    """Matrix §5.1 E — `duckstation` declares `*.cue`, so a result can be a
    descriptor naming files beside it rather than a self-contained image."""
    seen: set[str] = set()
    for q in ("crash", "tekken", "final fantasy", "gran turismo"):
        seen |= _formats(client, "duckstation", q)
    assert "cue" in seen


def test_sizes_are_scaled_to_the_console_and_not_to_the_extension(client):
    """A cartridge is not a disc.

    The size column is the one thing a player compares between two rows of the
    same game, so it has to be plausible for the machine. This is also the
    regression it was written from: a per-extension table answered 8 GB for a
    PlayStation 1 `.iso`, because `.iso` means an Xbox 360 disc somewhere else
    in the same table.
    """
    nes = [r["size"] for r in _search(client, "nes").json()["results"]]
    ps1 = [r["size"] for r in _search(client, "duckstation").json()["results"]]
    ps3 = [r["size"] for r in _search(client, "rpcs3").json()["results"]]
    assert nes and max(nes) < 8 * 1024 * 1024              # a cartridge
    assert ps1 and max(ps1) < 4 * 1024 ** 3                # a CD, or a set
    assert ps3 and max(ps3) > 1 * 1024 ** 3               # a Blu-ray


def test_the_rows_of_one_search_are_not_all_the_same_weight(client):
    sizes = [r["size"] for r in _search(client, "duckstation").json()["results"]]
    assert len(set(sizes)) > 1


# ── the line this step does not cross ──────────────────────────────────────

def test_searching_writes_nothing_anywhere(box, client):
    """The guard over the directory the ingestion steps will write into.

    Searching answers a question. Downloading, placing and validating are
    separate steps (matrix §5), and the moment any of them leaks backwards
    into this one, the failure it produces is a half-written file that
    `list_games()` turns into a tile on the next grid open (§1.1).
    """
    before = sorted(p.relative_to(box).as_posix() for p in box.rglob("*"))
    for system in INSTALLED:
        assert _search(client, system).status_code == 200
    after = sorted(p.relative_to(box).as_posix() for p in box.rglob("*"))
    assert before == after
    assert not (box / "emu").exists()


def test_what_a_console_carries_beyond_its_own_pack(client):
    """The one field a pack cannot fill in on its own.

    `unique_suffixes` is the suffixes **no other pack in the catalogue**
    declares, which is what lets a provider read a release name as naming one
    console rather than guessing. It is catalogue-wide and not box-wide: `.iso`
    is not evidence of a PlayStation 1 game on a box where `duckstation`
    happens to be the only console installed.
    """
    rows = {r["id"]: r for r in client.get("/api/store/systems").json()}
    assert set(rows) == set(INSTALLED)

    nes = system_for("nes")
    assert set(nes.unique_suffixes) == {"nes", "unf", "unif"}
    # `mame` declares `*.zip`, `*.7z` and `*.cmd`. The first two are shared
    # with sixteen other packs and the third is the one matrix §6.4 says must
    # neither be produced nor rewritten — so it has none, and is recognisable
    # by name alone.
    assert system_for("mame").unique_suffixes == ()
    # `rpcs3` declares no extensions at all: the game is a directory (§5.1 F).
    assert system_for("rpcs3").unique_suffixes == ()

    # The field is additive. A provider that never heard of it — and the test
    # below, which builds a console by hand — is unaffected.
    assert SearchSystem(id="x", label="X", platform="X",
                        roms_dir="emu/x").unique_suffixes == ()


def test_a_provider_is_handed_a_console_and_a_query_and_nothing_else():
    """The interface is the whole of what a provider may know.

    Written as a test because it is the seam step 10 replaces: a provider that
    needed the app, the request or the filesystem would be a provider whose
    credential handling could not stay on this side of the router.
    """
    system = SearchSystem(id="nes", label="NES", platform="NES",
                          roms_dir="emu/nes", extensions=("*.nes",))
    rows = asyncio.run(DemoSearchProvider().search(system, "zelda"))
    assert rows and all(r.system_id == "nes" for r in rows)
    assert all(r.format in {"nes", "zip", "7z"} for r in rows)
