"""The Prowlarr search provider, against recorded answers and nothing else.

**No test here reaches the network.** Every request is served by an
`httpx.MockTransport` handler that answers from a literal in this file, so the
whole suite runs on a box with the cable out, and a regression that started
making a real request would fail rather than quietly succeed on somebody's
desk.

**No real credential appears anywhere.** The URL is `prowlarr.invalid`, which
cannot resolve by RFC 2606, and the key is a row of zeros.

What is pinned, in the order it matters:

  · **an unconfigured box is unchanged** — no `config/store-prowlarr.json`
    means the demo provider, its `live = false`, and the banner the Games tab
    draws from it. That is the property every other decision in this step was
    made around, so it is the first test in the file;
  · **the key stays on this side** — it travels as a header, never in a URL,
    never in a raised exception, never in a `SearchResult`. Prowlarr's own
    `downloadUrl` carries `?apikey=<the box's key>`, so the last of those is a
    real leak and not a hypothetical one;
  · **a result proves which console it is for** — matrix §0 keys everything on
    the pair (system, format), and `services/store/search.py` says in writing
    that guessing the console is a guess this repository would have to be right
    about every time. A row with no evidence is dropped;
  · **every failure is a 502 with a useful journal line** — down, refused,
    slow, and answering something unexpected are four different log lines and
    one answer to the browser.
"""
from __future__ import annotations

import asyncio
import json
import stat
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.main import app                                        # noqa: E402
from backend.routers import store as store_router                   # noqa: E402
from backend.services import paths                                  # noqa: E402
from backend.services.store import get_provider, system_for         # noqa: E402
from backend.services.store.prowlarr import (                       # noqa: E402
    CONFIG_FILENAME, ProwlarrConfig, ProwlarrError, ProwlarrSearchProvider,
    config_file, console_terms, load_config, save_config)

INSTALLED = ["nes", "mame", "duckstation", "rpcs3", "gopher64", "dolphin"]

#: Reserved by RFC 2606 — it cannot resolve, so a test that started making a
#: real request fails instead of reaching a stranger.
FAKE_URL = "http://prowlarr.invalid:9696"
#: Obviously not a key. Distinctive enough to grep a response body for.
FAKE_KEY = "0000000000000000000000000000dead"


@pytest.fixture
def box(tmp_path, monkeypatch):
    """A box with six consoles on its grid and no Prowlarr configured."""
    monkeypatch.setattr(paths, "GAMECORE_DATA", tmp_path)
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "config" / "systems.json").write_text(
        json.dumps([{"id": i} for i in INSTALLED]))
    return tmp_path


@pytest.fixture
def configured(box):
    """…and now it is, with a URL that cannot resolve and a key of zeros."""
    save_config(ProwlarrConfig(url=FAKE_URL, api_key=FAKE_KEY))
    return box


def _provider(handler) -> ProwlarrSearchProvider:
    """The provider, wired to answers from this file."""
    return ProwlarrSearchProvider(transport=httpx.MockTransport(handler))


def _answering(rows, *, status=200, capture=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if capture is not None:
            capture.append(request)
        return httpx.Response(status, json=rows)
    return handler


def _search(provider, system_id, query="zelda", limit=40):
    return asyncio.run(provider.search(system_for(system_id), query, limit))


def _release(**over) -> dict:
    """One Prowlarr release, shaped as its API answers them."""
    row = {
        "guid": "https://tracker.invalid/details/1",
        "indexerId": 3,
        "indexer": "An indexer the owner configured",
        "title": "The Legend of Zelda - Ocarina of Time (USA) (Nintendo 64)",
        "size": 32 * 1024 * 1024,
        "seeders": 12,
        "protocol": "torrent",
        "publishDate": "2020-01-01T00:00:00Z",
    }
    row.update(over)
    return row


# ── an unconfigured box is exactly what it was ─────────────────────────────

def test_a_box_with_no_configuration_keeps_the_demo_provider_and_its_banner(box):
    """The property the whole step was built around.

    Nothing about adding a real provider may change what a box that has not
    configured one does. It answers invented rows and says so — the alternative
    is a Games tab that goes quiet on every box that has never heard of
    Prowlarr, which is all of them.
    """
    assert not config_file().exists()
    assert load_config() is None
    assert ProwlarrSearchProvider.configured() is False

    provider = get_provider()
    assert provider.name == "demo"
    assert provider.live is False

    info = TestClient(app).get("/api/store/provider").json()
    assert info == {"name": "demo", "label": "Demo results",
                    "live": False, "systemFirst": True}


def test_configuring_it_is_what_turns_it_on(configured):
    """No environment variable, no unit to edit, no OTA to survive.

    The file *is* the switch. An environment variable would live in a systemd
    unit the owner has to edit as root and the updater may replace; `config/`
    is excluded from the OTA rsync, so this survives an update by itself.
    """
    provider = get_provider()
    assert provider.name == "prowlarr"
    assert provider.live is True

    info = TestClient(app).get("/api/store/provider").json()
    assert info["name"] == "prowlarr" and info["live"] is True


def test_naming_the_demo_provider_turns_a_configured_box_back_off(
        configured, monkeypatch):
    """Without deleting the credentials to do it."""
    monkeypatch.setenv("GAMECORE_STORE_SEARCH_PROVIDER", "demo")
    assert get_provider().name == "demo"


def test_asking_for_prowlarr_on_an_unconfigured_box_falls_back(box, monkeypatch):
    """Selected and not ready is the demo provider, not a 502 machine.

    A client with no URL can only turn every search into a failure, and rows
    that are honestly labelled invented are better than that.
    """
    monkeypatch.setenv("GAMECORE_STORE_SEARCH_PROVIDER", "prowlarr")
    assert get_provider().name == "demo"


# ── the configuration file ─────────────────────────────────────────────────

def test_the_file_is_written_private_and_atomically(box):
    path = save_config(ProwlarrConfig(url=FAKE_URL, api_key=FAKE_KEY))
    assert path == config_file()
    assert path.name == CONFIG_FILENAME
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    # `os.replace` over a private temp file, the way auth.py writes a secret —
    # so no half-written file is ever left behind for a reader to parse.
    assert not list(path.parent.glob("*.tmp"))


def test_it_lives_beside_the_other_secret_in_config(box):
    assert config_file().parent == paths.config_dir()


def test_both_spellings_of_every_key_are_accepted(box):
    """The file has no editor behind it; somebody types it over SSH."""
    (box / "config" / CONFIG_FILENAME).write_text(json.dumps({
        "url": FAKE_URL, "api_key": FAKE_KEY,
        "indexer_ids": [1, "2"], "timeout_seconds": 9,
    }))
    cfg = load_config()
    assert cfg is not None
    assert cfg.api_key == FAKE_KEY
    assert cfg.indexer_ids == (1, 2)
    assert cfg.timeout == 9


@pytest.mark.parametrize("body", [
    pytest.param({"url": FAKE_URL}, id="no key"),
    pytest.param({"apiKey": FAKE_KEY}, id="no url"),
    pytest.param({"url": "prowlarr.invalid:9696", "apiKey": FAKE_KEY},
                 id="no scheme"),
    pytest.param({"url": "file:///etc/passwd", "apiKey": FAKE_KEY},
                 id="not http"),
    pytest.param({"url": FAKE_URL, "apiKey": "   "}, id="blank key"),
    pytest.param(["not", "an", "object"], id="not an object"),
])
def test_an_incomplete_file_falls_back_rather_than_breaking_the_tab(box, body):
    """Absent, malformed and half-written are one answer on purpose.

    The caller does the same thing for all of them, and a Games tab that 500s
    because a JSON file lost a brace is a screen the player cannot leave.
    """
    (box / "config" / CONFIG_FILENAME).write_text(json.dumps(body))
    assert load_config() is None
    assert get_provider().name == "demo"


def test_a_file_that_is_not_json_at_all_falls_back(box):
    (box / "config" / CONFIG_FILENAME).write_text("{not json")
    assert load_config() is None
    assert get_provider().name == "demo"


def test_a_key_pasted_into_the_url_is_dropped_before_it_can_be_sent(box):
    """The shape this guard is really for.

    A URL keeps its query string on every request and in every log line that
    ever prints it. Path, query and fragment all go; scheme, host and port are
    what a base URL is.
    """
    (box / "config" / CONFIG_FILENAME).write_text(json.dumps({
        "url": f"{FAKE_URL}/api/v1/?apikey={FAKE_KEY}#x", "apiKey": FAKE_KEY}))
    cfg = load_config()
    assert cfg is not None
    assert cfg.url == FAKE_URL
    assert FAKE_KEY not in cfg.url


@pytest.mark.parametrize("written,expected", [(0, 1.0), (99999, 120.0),
                                              ("nonsense", 20.0)])
def test_the_timeout_is_clamped_to_something_a_television_can_wait_for(
        box, written, expected):
    (box / "config" / CONFIG_FILENAME).write_text(json.dumps({
        "url": FAKE_URL, "apiKey": FAKE_KEY, "timeout": written}))
    assert load_config().timeout == expected


def test_a_world_readable_file_is_reported_and_still_used(box, caplog):
    """Said out loud, never silently refused.

    A hand-created file is 0644 under a default umask. A Store that quietly
    stayed on the demo provider over a permission bit is a box that looks
    broken with no way to find out why.
    """
    path = save_config(ProwlarrConfig(url=FAKE_URL, api_key=FAKE_KEY))
    path.chmod(0o644)
    with caplog.at_level("WARNING"):
        assert load_config() is not None
    assert any("readable by other accounts" in r.message for r in caplog.records)
    assert FAKE_KEY not in caplog.text


# ── the question this step had to answer: is the pack enough? ──────────────

def test_a_console_is_named_by_more_than_its_platform_field(box):
    """`platform` and `label` are display strings and need splitting.

    Four packs join two machines with a slash and one holds a second name in
    parentheses. Unsplit, "GameCube/Wii" and "Arcade (MAME)" are terms that
    have never appeared in a release name.
    """
    assert console_terms(system_for("gopher64")) == ("N64", "Nintendo 64")
    assert console_terms(system_for("dolphin")) == ("GameCube", "Wii")
    assert console_terms(system_for("mame")) == ("Arcade", "MAME")


def test_which_extensions_name_one_console_is_not_a_property_of_one_pack(box):
    """The reason `SearchSystem` grew a field rather than none.

    `.z64` is declared by `gopher64` and by nothing else, so a release named
    with it is a Nintendo 64 game. `.iso` is declared by nine packs, so it is
    evidence of nothing — and a single pack cannot tell those two apart,
    because it cannot see the other thirty.
    """
    n64 = system_for("gopher64")
    assert set(n64.unique_suffixes) == {"n64", "z64", "v64"}

    ps1 = system_for("duckstation")
    assert "iso" in ps1.suffixes and "iso" not in ps1.unique_suffixes
    assert "cue" in ps1.suffixes and "cue" not in ps1.unique_suffixes

    # And the `.cmd` matrix §6.4 refuses to produce is refused as evidence
    # too: reading a release as an arcade romset *because* it is named one
    # would put that guess back where the demo provider took it out.
    assert system_for("mame").unique_suffixes == ()


def test_the_demo_provider_still_works_with_the_grown_interface(box):
    """The half that guarantees an unconfigured box stays usable."""
    body = TestClient(app).get(
        "/api/store/search", params={"system": "nes", "q": "zelda"}).json()
    assert body["provider"] == "demo" and body["live"] is False
    assert body["results"] and all(r["format"] for r in body["results"])


# ── what a search sends ────────────────────────────────────────────────────

def test_the_key_travels_in_a_header_and_never_in_the_url(configured):
    """A URL is what proxies log, shells remember and exceptions print."""
    seen: list[httpx.Request] = []
    _search(_provider(_answering([_release()], capture=seen)), "gopher64")

    assert len(seen) == 1
    request = seen[0]
    assert request.headers["X-Api-Key"] == FAKE_KEY
    assert FAKE_KEY not in str(request.url)
    assert request.url.path == "/api/v1/search"


def test_the_query_is_what_the_player_typed_and_not_more(configured):
    """The console is applied to the *answer*, not bolted onto the question.

    Appending "Nintendo 64" would lose "Super Mario 64 (USA).z64" — a release
    that names the console in its extension and nowhere else, and the single
    most likely correct hit. An indexer's search is an AND over words, so a
    word added here is results removed at the source, where nothing can get
    them back.
    """
    seen: list[httpx.Request] = []
    _search(_provider(_answering([_release()], capture=seen)),
            "gopher64", "  ocarina of time  ")
    assert seen[0].url.params["query"] == "ocarina of time"


def test_no_indexer_and_no_category_is_shipped_by_this_repository(configured):
    """Both are the owner's, read off their own instance.

    Absent by default and absent from the request: an empty `categories` means
    Prowlarr searches what the owner configured, which is the only place that
    can know what they have access to. 17 of the 31 consoles have no console
    category at all, so a mapping shipped here would return nothing for most
    of the library.
    """
    seen: list[httpx.Request] = []
    _search(_provider(_answering([_release()], capture=seen)), "gopher64")
    assert "indexerIds" not in seen[0].url.params
    assert "categories" not in seen[0].url.params


def test_the_owner_can_narrow_to_their_own_indexers_and_categories(box):
    save_config(ProwlarrConfig(url=FAKE_URL, api_key=FAKE_KEY,
                               indexer_ids=(3, 7), categories=(1090,)))
    seen: list[httpx.Request] = []
    _search(_provider(_answering([_release()], capture=seen)), "gopher64")
    assert seen[0].url.params.get_list("indexerIds") == ["3", "7"]
    assert seen[0].url.params.get_list("categories") == ["1090"]


def test_more_rows_are_asked_for_than_are_shown(configured):
    """The console filter runs after the answer arrives.

    Asking for forty would mean forty rows about every console and three about
    this one.
    """
    seen: list[httpx.Request] = []
    _search(_provider(_answering([_release()], capture=seen)), "gopher64",
            limit=5)
    assert int(seen[0].url.params["limit"]) > 5


# ── what a search keeps ────────────────────────────────────────────────────

def test_a_release_that_names_the_console_by_extension_is_kept(configured):
    rows = _search(_provider(_answering(
        [_release(title="Super Mario 64 (USA).z64")])), "gopher64")
    assert len(rows) == 1
    assert rows[0].system_id == "gopher64"
    assert rows[0].format == "z64"
    # The extension is the file's, not the title's — a row shows both, and
    # showing "Super Mario 64 (USA).z64" twice is noise.
    assert rows[0].title == "Super Mario 64 (USA)"
    assert rows[0].filename == "Super Mario 64 (USA).z64"


def test_a_release_that_names_the_console_by_name_is_kept(configured):
    rows = _search(_provider(_answering(
        [_release(title="Ocarina of Time - Nintendo 64 - USA")])), "gopher64")
    assert len(rows) == 1
    # Nothing in the name says what the download is, and nothing here invents
    # it: the bytes decide and the bytes have not been fetched.
    assert rows[0].format == ""


def test_a_release_that_names_no_console_is_dropped(configured):
    """The rule `search.py` committed to in writing.

    "zelda" answers the Nintendo 64 game, the 3DS remake, a Wii U port, a
    soundtrack and a film. Deciding which machine a bare title is for is a
    guess this repository would have to be right about every time, and the
    player is the one who pays for a wrong one.
    """
    assert _search(_provider(_answering([
        _release(title="The Legend of Zelda - Ocarina of Time"),
        _release(title="Zelda Symphony of the Goddesses 2016 1080p"),
    ])), "gopher64") == []


def test_evidence_by_extension_is_ranked_above_evidence_by_name(configured):
    """"PlayStation" is a whole word inside "PlayStation 2", and "Wii" inside
    "Wii U" — a name-only row on a console family can be the wrong member, so
    the rows that carry a suffix only this console declares come first."""
    rows = _search(_provider(_answering([
        _release(guid="a", title="Mario Kart 64 - Nintendo 64"),
        _release(guid="b", title="Mario Kart 64 (USA).z64"),
    ])), "gopher64")
    assert [r.filename for r in rows] == [
        "Mario Kart 64 (USA).z64", "Mario Kart 64 - Nintendo 64"]


def test_a_console_with_no_distinctive_extension_is_found_by_name(configured):
    """Eight packs have nothing else — `mame` among them, since matrix §6.4
    takes its only unique suffix off the table."""
    rows = _search(_provider(_answering(
        [_release(title="Street Fighter II - MAME 0.245 romset.zip")])),
        "mame")
    assert len(rows) == 1 and rows[0].format == "zip"


def test_the_cmd_extension_is_not_read_as_proof_of_anything(configured):
    """Matrix §6.4 — neither produce nor rewrite one, and not recognise one
    either: accepting a release as an arcade romset because it is called
    `.cmd` would put the guess back that `demo.py` took out."""
    assert _search(_provider(_answering(
        [_release(title="something (USA).cmd")])), "mame") == []


def test_an_archive_is_a_format_even_where_the_pack_declares_none(configured):
    """Matrix §2.3, the case that bites: `nes` declares no `*.zip`, so that
    download must be unpacked or it is silently wasted. It still has to be
    visible long before anything can unpack it."""
    rows = _search(_provider(_answering(
        [_release(title="Super Mario Bros - NES.7z")])), "nes")
    assert len(rows) == 1 and rows[0].format == "7z"


def test_a_name_that_only_looks_like_it_ends_in_an_extension_does_not(
        configured):
    rows = _search(_provider(_answering(
        [_release(title="Mario Kart 64 - Nintendo 64 - v1.02")])), "gopher64")
    assert len(rows) == 1 and rows[0].format == ""


def test_the_region_and_languages_a_release_names_are_carried(configured):
    rows = _search(_provider(_answering(
        [_release(title="Mario Kart 64 (Europe) (En,Fr,De).z64")])), "gopher64")
    assert rows[0].region == "Europe"
    assert rows[0].languages == ("en", "fr", "de")


def test_a_release_that_names_no_region_gets_none_invented(configured):
    rows = _search(_provider(_answering(
        [_release(title="Mario Kart 64.z64")])), "gopher64")
    assert rows[0].region == "" and rows[0].languages == ()


def test_a_row_the_indexer_mangled_is_skipped_and_the_rest_answer(configured):
    """One bad row out of ten must not be a failed search."""
    rows = _search(_provider(_answering([
        "not an object",
        _release(guid="a", title=None),
        _release(guid="b", title="   "),
        _release(guid="c", title="Mario Kart 64 (USA).z64", size="enormous"),
        _release(guid="d", title="Goldeneye 007 (USA).z64", size=None),
    ])), "gopher64")
    assert [r.title for r in rows] == ["Mario Kart 64 (USA)",
                                       "Goldeneye 007 (USA)"]
    # Matrix §5.1: a size the source does not give is 0, which the tab reads
    # as "unknown" — never a small download.
    assert all(r.size == 0 for r in rows)


def test_the_limit_the_router_asks_for_is_the_limit_it_gets(configured):
    rows = _search(_provider(_answering(
        [_release(guid=str(i), title=f"Game {i} (USA).z64") for i in range(30)])),
        "gopher64", limit=7)
    assert len(rows) == 7


def test_identical_searches_answer_identical_ids(configured):
    handler = _answering([_release(title="Mario Kart 64 (USA).z64")])
    first = _search(_provider(handler), "gopher64")
    second = _search(_provider(handler), "gopher64")
    assert [r.id for r in first] == [r.id for r in second]


# ── the leak that would actually happen ────────────────────────────────────

def test_the_box_key_in_a_download_url_never_reaches_a_result(configured):
    """Prowlarr's own `downloadUrl` carries `?apikey=<this box's key>`.

    `SearchResult.source` travels to the browser inside every answer, so a
    provider that used that field would have published the key to the page
    source of a television nobody logs out of. Neither `downloadUrl` nor
    `magnetUrl` is read, and what is read is redacted anyway — a guid is
    whatever the indexer chose to put there.
    """
    rows = _search(_provider(_answering([_release(
        title="Mario Kart 64 (USA).z64",
        downloadUrl=f"{FAKE_URL}/3/download?apikey={FAKE_KEY}&link=abc",
        magnetUrl=f"magnet:?xt=urn:btih:abc&passkey={FAKE_KEY}",
        guid=f"https://tracker.invalid/rss?rss_key={FAKE_KEY}&id=9",
    )])), "gopher64")

    assert len(rows) == 1
    blob = json.dumps(rows[0].to_json())
    assert FAKE_KEY not in blob
    assert "<redacted>" in rows[0].source


def test_a_search_writes_nothing_anywhere(configured):
    """The guard `test_store_search.py` stands over the ROM directory, kept
    across the provider that actually reaches something."""
    before = sorted(p.relative_to(configured).as_posix()
                    for p in configured.rglob("*"))
    _search(_provider(_answering([_release(title="Mario Kart 64 (USA).z64")])),
            "gopher64")
    after = sorted(p.relative_to(configured).as_posix()
                   for p in configured.rglob("*"))
    assert before == after
    assert not (configured / "emu").exists()


# ── every way it can fail ──────────────────────────────────────────────────

def _raising(exc):
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc
    return handler


FAILURES = [
    pytest.param(_raising(httpx.ConnectError("nope")), "could not be reached",
                 id="prowlarr is down"),
    pytest.param(_raising(httpx.ConnectTimeout("slow")), "within",
                 id="prowlarr is slow"),
    pytest.param(_raising(httpx.ReadTimeout("slow")), "within",
                 id="the indexers are slow"),
    pytest.param(_answering([], status=401), "refused the API key",
                 id="the key is wrong"),
    pytest.param(_answering([], status=403), "refused the API key",
                 id="the key lost its permissions"),
    pytest.param(_answering([], status=404), "Prowlarr root",
                 id="the url points at something else"),
    pytest.param(_answering([], status=500), "HTTP 500",
                 id="prowlarr broke"),
    pytest.param(_answering({"page": 1}), "not a list",
                 id="an answer of the wrong shape"),
]


@pytest.mark.parametrize("handler,expected", FAILURES)
def test_every_failure_is_named_in_the_journal_and_carries_no_secret(
        configured, handler, expected):
    with pytest.raises(ProwlarrError) as e:
        _search(_provider(handler), "gopher64")
    reason = str(e.value)
    assert expected in reason
    # The message goes straight into `routers/store.py`'s log line, which is
    # the half of the 502 contract that lives in the provider.
    assert FAKE_KEY not in reason
    assert "prowlarr.invalid" in reason


def test_an_answer_that_is_not_json_at_all_is_named_too(configured):
    def handler(request):
        return httpx.Response(200, text="<html>a login page</html>")

    with pytest.raises(ProwlarrError, match="not JSON"):
        _search(_provider(handler), "gopher64")


def test_a_redirect_is_a_failure_and_not_a_step_on_the_way_somewhere(
        configured):
    """Following one would hand `X-Api-Key` to whatever host it named."""
    def handler(request):
        return httpx.Response(302, headers={"Location": "http://elsewhere.invalid/"})

    with pytest.raises(ProwlarrError, match="HTTP 302"):
        _search(_provider(handler), "gopher64")


def test_the_credentials_disappearing_mid_flight_is_a_failure_not_a_crash(
        configured):
    config_file().unlink()
    with pytest.raises(ProwlarrError, match=CONFIG_FILENAME):
        _search(_provider(_answering([])), "gopher64")


@pytest.mark.parametrize("handler,_expected", FAILURES)
def test_the_endpoint_answers_502_and_says_nothing_about_why(
        configured, monkeypatch, handler, _expected):
    """The other half of the contract, end to end.

    The reason is logged and never returned: it carries an address, and a
    different provider's could carry a key.
    """
    monkeypatch.setattr(store_router, "get_provider",
                        lambda *a, **k: _provider(handler))
    r = TestClient(app).get("/api/store/search",
                            params={"system": "gopher64", "q": "zelda"})
    assert r.status_code == 502
    assert r.json()["detail"] == "the search provider did not answer"
    assert FAKE_KEY not in r.text
    assert "prowlarr.invalid" not in r.text


def test_a_working_search_reaches_the_endpoint_whole(configured, monkeypatch):
    monkeypatch.setattr(store_router, "get_provider", lambda *a, **k: _provider(
        _answering([_release(title="Mario Kart 64 (USA).z64")])))
    body = TestClient(app).get("/api/store/search",
                               params={"system": "gopher64", "q": "mario"}).json()
    assert body["provider"] == "prowlarr"
    assert body["live"] is True
    assert body["romsDir"] == "emu/gopher64"
    assert [r["title"] for r in body["results"]] == ["Mario Kart 64 (USA)"]
    assert FAKE_KEY not in json.dumps(body)
