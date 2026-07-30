"""Tests for the gamemedia tier — the one that adds media types beyond the jacket.

Everything here is offline. The two things that would need the network — a
ScreenScraper call and the 106 MB LaunchBox dump — are exactly what the tier
refuses to do without being configured, and *that refusal* is what most of
these tests check: an unconfigured box must behave as if this code did not
exist.

Run under pytest:  pytest backend/tests/test_gamemedia.py
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

# Same handshake as test_covers: conftest sets the throwaway root before any
# backend import, and this branch covers running the file directly.
_root = os.environ.get("GAMECORE_TEST_ROOT")
if _root is None:
    _root = str(Path(tempfile.mkdtemp(prefix="gamecore-test-")) / "fake_root")
    os.environ["GAMECORE_TEST_ROOT"] = _root
    os.environ["GAMECORE_PATH"] = _root
ROOT = Path(_root)

import pytest

from backend.services import gamemedia
from backend.services.gamemedia import gamemedia as gm


def await_(coro):
    """Run one coroutine to completion from a sync test.

    Same helper as test_covers, and for the same reason: nothing in this suite
    depends on pytest-asyncio, and the release workflow installs only
    `requirements.txt` + `pytest`. A `@pytest.mark.asyncio` here would pass on a
    developer's machine and do nothing on the runner — where a red pytest step
    is what stops a broken release from being published.
    """
    return asyncio.run(coro)


# ── The tier is inert until it is configured ─────────────────────────────────

def test_unconfigured_box_reports_no_source():
    """conftest strips the credentials, so this is the default install.

    It matters more than it reads: `available()` returning True on a box with
    no account would put every cover request behind a scraper that cannot
    answer, and a tier that cannot answer reports `unreachable`, which
    suppresses the negative cache the cover pipeline relies on.
    """
    assert gamemedia.available() is False
    status = gamemedia.status()
    assert status["screenscraper"] is False
    assert status["available"] is False


def test_resolve_is_a_noop_without_a_source():
    assert await_(gamemedia.resolve("rpcs3", "Uncharted 2")) is None


def test_caches_live_under_emu_and_not_in_the_home_directory():
    """emu/ is excluded from the OTA rsync and from git.

    Upstream defaults to ~/.cache, which under systemd resolves against
    whatever HOME the unit happens to have — and would put a 234 MB index and
    the artwork somewhere an update does not protect.
    """
    assert gm.CACHE_ROOT == ROOT / "emu" / "gamemedia"
    assert gm.SYSTEMS_CACHE.parent == gm.CACHE_ROOT
    assert gamemedia.gs.DB_PATH == ROOT / "emu" / "gamescrape" / "launchbox.sqlite"


# ── Credentials never reach the disk ─────────────────────────────────────────

SS_URL = ("https://api.screenscraper.fr/api2/mediaJeu.php?devid=someone"
          "&devpassword=hunter2&ssid=player&sspassword=alsosecret"
          "&jeuid=24733&media=box-3D(wor)")


def test_a_stored_url_carries_no_credentials():
    """A deferred media keeps its URL in game.json — a file on disk.

    ScreenScraper puts all four credential values in the query of every media
    URL it returns. Writing one as received would put the developer account
    into the cache, and into every bug report that attaches a manifest.
    """
    stored = gm.strip_creds(SS_URL)
    for secret in ("someone", "hunter2", "player", "alsosecret"):
        assert secret not in stored, stored
    # What identifies the media is still there — that is the point of keeping it.
    assert "jeuid=24733" in stored
    assert "media=box-3D" in stored


def test_credentials_are_restored_from_the_live_configuration(monkeypatch):
    monkeypatch.setenv("SCREENSCRAPER_DEV_ID", "someone")
    monkeypatch.setenv("SCREENSCRAPER_DEV_PASSWORD", "hunter2")
    monkeypatch.setenv("SCREENSCRAPER_USER", "player")
    monkeypatch.setenv("SCREENSCRAPER_PASSWORD", "alsosecret")

    restored = gm.with_creds(gm.strip_creds(SS_URL))
    for secret in ("devid=someone", "devpassword=hunter2",
                   "ssid=player", "sspassword=alsosecret"):
        assert secret in restored, restored


def test_a_non_screenscraper_url_is_left_alone(monkeypatch):
    """The LaunchBox CDN carries no credentials and must not be handed any."""
    monkeypatch.setenv("SCREENSCRAPER_DEV_ID", "someone")
    monkeypatch.setenv("SCREENSCRAPER_DEV_PASSWORD", "hunter2")
    cdn = "https://images.launchbox-app.com/1234-abcd.png"
    assert gm.with_creds(cdn) == cdn


def test_the_api_never_republishes_a_media_url():
    """The frontend gets descriptors and a route of ours, never the source URL.

    Even stripped of credentials it still points at ScreenScraper, and handing
    it to the browser would spend the box's quota from any page that can reach
    the backend.
    """
    manifest = {"media": {"box-3d": {"url": SS_URL, "deferred": True,
                                     "category": "box", "kind": "image",
                                     "region": "wor"}}}
    exposed = gamemedia.media_index(manifest)
    assert "url" not in exposed["box-3d"]
    assert exposed["box-3d"] == {"category": "box", "kind": "image",
                                 "region": "wor", "cached": False}


# ── Deferred media: the difference from `pending` ────────────────────────────

def test_a_deferred_media_does_not_make_the_entry_incomplete(tmp_path):
    """`deferred` is deliberate, `pending` is an accident.

    Confusing the two costs one jeuInfos out of the daily quota every single
    time a theme draws a cover, because an incomplete manifest is rescraped.
    """
    (tmp_path / "box-front.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    manifest = {"found": True, "media": {
        "box-front": {"file": "box-front.png"},
        "box-3d": {"deferred": True, "url": gm.strip_creds(SS_URL)},
    }}
    assert gm._manifest_complete(tmp_path, manifest) is True


def test_a_pending_media_still_makes_the_entry_incomplete(tmp_path):
    manifest = {"found": True, "media": {"box-front": {"pending": True}}}
    assert gm._manifest_complete(tmp_path, manifest) is False


def test_a_media_whose_file_vanished_makes_the_entry_incomplete(tmp_path):
    manifest = {"found": True, "media": {"box-front": {"file": "box-front.png"}}}
    assert gm._manifest_complete(tmp_path, manifest) is False


def test_a_deferred_media_without_a_url_is_not_servable(tmp_path):
    """Nothing could fetch it, so it must not be reported as complete."""
    manifest = {"found": True, "media": {"box-3d": {"deferred": True}}}
    assert gm._manifest_complete(tmp_path, manifest) is False


def test_fetch_media_refuses_a_slug_that_could_escape_the_cache():
    """A slug arrives from a URL and becomes a filename."""
    for hostile in ("../../etc/passwd", "box/front", "", "Box-Front", "box_front"):
        assert await_(gamemedia.media_file("rpcs3", "Uncharted 2", hostile)) is None


def test_fetch_media_returns_nothing_for_a_type_the_game_does_not_have(tmp_path,
                                                                      monkeypatch):
    monkeypatch.setattr(gm, "CACHE_ROOT", tmp_path)
    d = gm.entry_dir("rpcs3", "Uncharted 2")
    gm.write_json(d / gm.MANIFEST, {"found": True, "media": {"box-front": {}}})
    assert gm.fetch_media("rpcs3", "Uncharted 2", "video") is None


def test_fetch_media_serves_a_file_already_on_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(gm, "CACHE_ROOT", tmp_path)
    d = gm.entry_dir("rpcs3", "Uncharted 2")
    d.mkdir(parents=True, exist_ok=True)
    (d / "box-3d.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    gm.write_json(d / gm.MANIFEST,
                  {"found": True, "media": {"box-3d": {"file": "box-3d.png"}}})
    assert gm.fetch_media("rpcs3", "Uncharted 2", "box-3d") == d / "box-3d.png"


def test_a_failed_on_demand_fetch_keeps_the_url_for_next_time(tmp_path, monkeypatch):
    """A media that could not be fetched today must not force a rescrape tomorrow.

    Recording it as `failed` — the state a bulk download uses — would make the
    manifest incomplete, and the next request would spend a jeuInfos rebuilding
    metadata that is already correct.
    """
    monkeypatch.setattr(gm, "CACHE_ROOT", tmp_path)
    monkeypatch.setattr(gm.gs, "fetch", lambda url, dest, verbose: None)
    d = gm.entry_dir("rpcs3", "Uncharted 2")
    stored = gm.strip_creds(SS_URL)
    gm.write_json(d / gm.MANIFEST, {"found": True, "media": {
        "box-3d": {"deferred": True, "url": stored, "category": "box"}}})

    assert gm.fetch_media("rpcs3", "Uncharted 2", "box-3d") is None

    written = json.loads((d / gm.MANIFEST).read_text())
    entry = written["media"]["box-3d"]
    assert entry["url"] == stored, "the URL survives a failure"
    assert entry.get("last_error"), "and the failure is recorded, not hushed"
    assert gm._manifest_complete(d, written) is True


# ── The metadata shape the frontend already reads ────────────────────────────

MANIFEST_SS = {
    "found": True, "source": "screenscraper", "matched_by": "hash",
    "meta": {
        "title": "Uncharted 2 : Among Thieves",
        "description": "Treasure hunter Nathan Drake returns…",
        "developer": "Naughty Dog", "publisher": "Sony Computer Entertainment",
        "released": "2009-10-16", "year": "2009", "genres": ["Adventure"],
        "players": "1-3", "rating": 0.95, "rating_20": "19",
        "rating_count": None, "esrb": "T",
        "classifications": {"PEGI": "16", "ESRB": "T", "USK": "16"},
        "platform": "Playstation 3",
    },
    "media": {},
}


def test_the_seven_original_keys_keep_their_type():
    """GameMetaPanel and every theme already read these — they cannot move.

    `players` in particular is a number the panel compares to 1; ScreenScraper
    writes a range ("1-3"). Passing the string straight through would not
    crash, it would silently stop showing the player-count chip.
    """
    meta = gamemedia.to_game_meta(MANIFEST_SS)
    assert meta["found"] is True
    assert isinstance(meta["title"], str) and meta["title"]
    assert isinstance(meta["description"], str)
    assert meta["year"] == "2009"
    assert meta["genres"] == ["Adventure"]
    assert meta["players"] == 3
    assert isinstance(meta["rating"], str)


def test_rating_stays_an_age_rating_and_the_score_arrives_beside_it():
    """TheGamesDB's `rating` is a label ("E - Everyone"), gamemedia's is 0–1.

    Putting a 0.95 where a theme expects "T" would render "0.95" as an age
    rating; putting "T" where a star widget expects a number would render no
    stars. So the meanings are kept apart: `rating` stays the label, `score`
    is the number.
    """
    meta = gamemedia.to_game_meta(MANIFEST_SS)
    assert meta["rating"] == "T"
    assert meta["score"] == 0.95
    assert meta["classifications"]["PEGI"] == "16"


@pytest.mark.parametrize("raw,expected", [
    ("1-3", 3), ("4", 4), ("1", 1), ("", 0), (None, 0), ("2+", 2), ("1-8", 8),
])
def test_player_counts_are_read_off_every_shape_the_sources_use(raw, expected):
    assert gamemedia._players_count(raw) == expected


def test_a_missing_field_never_becomes_a_missing_key():
    """The panel reads meta.genres.slice() without checking it exists."""
    meta = gamemedia.to_game_meta({"found": True, "meta": {}})
    assert meta["genres"] == [] and meta["title"] == "" and meta["players"] == 0


# ── The API surface ──────────────────────────────────────────────────────────

def test_media_endpoint_says_no_source_rather_than_no_game(client):
    """A theme must be able to tell the two apart.

    Reporting "game not found" on a box that simply has no ScreenScraper
    account would make every theme show "no artwork" where the honest message
    is "nothing is configured".
    """
    r = client.get("/api/media/rpcs3/BLUS30443")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["found"] is False
    assert body["available"] is False
    assert body["media"] == {}


def test_media_file_endpoint_404s_without_a_source(client):
    r = client.get("/api/media/rpcs3/BLUS30443/media/box-3d")
    assert r.status_code == 404


def test_media_endpoint_rejects_an_unknown_system(client):
    assert client.get("/api/media/nope/Game.nds").status_code == 404


def test_covers_are_untouched_by_all_of_this(client):
    """The whole point: an unconfigured box resolves covers as it always did."""
    r = client.get("/api/covers/rpcs3/BLUS30443")
    assert r.status_code == 200
    assert r.content.startswith(b"\x89PNG")


# The fixtures come from test_covers: the same synthetic library, built once.
from backend.tests.test_covers import client, fake_root  # noqa: E402,F401
