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
    manifest = {"found": True, "lang": gm.LANG_PREF[0], "media": {
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
    gm.write_json(d / gm.MANIFEST, {"found": True, "lang": gm.LANG_PREF[0], "media": {
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


# ── Negative metadata must not outlive the source that could answer ──────────

def test_a_negative_written_before_gamemedia_is_reconsidered(monkeypatch):
    from backend.services import metadata

    monkeypatch.setattr(metadata.gamemedia, "available", lambda: True)
    monkeypatch.setattr(metadata, "THEGAMESDB_API_KEY", "")

    # The shape every entry cached before this release has.
    assert metadata._worth_another_look({"found": False}) is True
    # And once gamemedia has answered, the TTL governs again.
    assert metadata._worth_another_look(
        {"found": False, "tiers_tried": ["gamemedia"]}) is False


def test_a_negative_stands_when_nothing_new_is_configured(monkeypatch):
    from backend.services import metadata

    monkeypatch.setattr(metadata.gamemedia, "available", lambda: False)
    monkeypatch.setattr(metadata, "THEGAMESDB_API_KEY", "key")
    assert metadata._worth_another_look(
        {"found": False, "tiers_tried": ["thegamesdb"]}) is False
    # A key added since the negative was written is also a reason to retry.
    assert metadata._worth_another_look({"found": False}) is True


# ── Language ─────────────────────────────────────────────────────────────────

def test_english_is_the_default():
    """The interface is in English; the synopses have to match it.

    Upstream prefers French, which is right for its own users and wrong for a
    library whose buttons read "PLAY TIME".
    """
    from backend import config
    assert config.SCRAPER_LANG[0] == "en"
    assert gm.LANG_PREF[0] == "en"


def test_the_preferred_language_wins_and_falls_back():
    gm_pref = gm.LANG_PREF
    try:
        items = [{"langue": "fr", "text": "Deux mondes se rencontrent"},
                 {"langue": "en", "text": "Two worlds collide"}]
        gm.LANG_PREF = ["en", "fr"]
        assert gm._pick_lang(items) == "Two worlds collide"
        gm.LANG_PREF = ["fr", "en"]
        assert gm._pick_lang(items) == "Deux mondes se rencontrent"
        # A game ScreenScraper only has in one language still yields text.
        gm.LANG_PREF = ["de", "en"]
        assert gm._pick_lang(items) == "Two worlds collide"
        gm.LANG_PREF = ["de", "es"]
        assert gm._pick_lang(items) == "Deux mondes se rencontrent", "first entry"
    finally:
        gm.LANG_PREF = gm_pref


def test_a_manifest_scraped_in_another_language_is_rescraped(tmp_path):
    """Otherwise a library keeps whatever language it was first swept in.

    The media already downloaded are kept across that rescrape, so it costs one
    jeuInfos per game and no file transfer.
    """
    assert gm._manifest_complete(tmp_path, {"found": True, "lang": "fr", "media": {}}) is False
    assert gm._manifest_complete(tmp_path, {"found": True, "lang": "en", "media": {}}) is True
    # Written before the field existed → scraped under the old French default.
    assert gm._manifest_complete(tmp_path, {"found": True, "media": {}}) is False


def test_a_metadata_entry_in_the_wrong_language_is_reconsidered():
    from backend.services import metadata
    assert metadata._wrong_language(
        {"found": True, "source": "screenscraper", "lang": "fr"}) is True
    assert metadata._wrong_language(
        {"found": True, "source": "screenscraper", "lang": "en"}) is False
    # TheGamesDB is English-only and carries no source — never invalidated.
    assert metadata._wrong_language({"found": True, "title": "Mario Kart DS"}) is False


# ── A cached hit is only as good as the source that wrote it ─────────────────

def test_a_hit_from_before_gamemedia_is_reconsidered(monkeypatch):
    """45 of 53 entries on the reference box were in this state.

    They were TheGamesDB records that gamemedia had never been given a chance
    to improve, and five had no synopsis at all while ScreenScraper held a full
    one — the N64 game showed a blank description under a perfectly good
    paragraph sitting in the manifest next door.
    """
    from backend.services import metadata

    monkeypatch.setattr(metadata.gamemedia, "available", lambda: True)
    legacy = {"found": True, "title": "Mario Kart 64", "description": ""}
    assert metadata._from_a_weaker_source(legacy) is True


def test_it_happens_once_and_cannot_loop(monkeypatch):
    """Every record written from now on carries a source, TheGamesDB's included.

    Without that stamp a game gamemedia does not know would be re-asked on
    every single call, for ever.
    """
    from backend.services import metadata

    monkeypatch.setattr(metadata.gamemedia, "available", lambda: True)
    for src in ("thegamesdb", "screenscraper", "launchbox"):
        assert metadata._from_a_weaker_source({"found": True, "source": src}) is False


def test_nothing_is_reconsidered_when_gamemedia_cannot_answer(monkeypatch):
    from backend.services import metadata

    monkeypatch.setattr(metadata.gamemedia, "available", lambda: False)
    assert metadata._from_a_weaker_source({"found": True, "title": "x"}) is False


def test_the_language_check_no_longer_catches_thegamesdb(monkeypatch):
    """It is English only and carries no `lang`.

    Testing `entry.get("source")` at all — which is what the first version did
    — would now match it and reconsider it on every call.
    """
    from backend.services import metadata

    assert metadata._wrong_language({"found": True, "source": "thegamesdb"}) is False
    assert metadata._wrong_language(
        {"found": True, "source": "screenscraper", "lang": "fr"}) is True
    assert metadata._wrong_language(
        {"found": True, "source": "screenscraper", "lang": "en"}) is False


# ── One emulator, several consoles ───────────────────────────────────────────

def test_an_emulator_covering_two_consoles_offers_both():
    """Dolphin reads GameCube *and* Wii, and .rvz cannot break the tie.

    The extension was meant to settle it, and does for a real dump format —
    .wbfs is Wii, .gcz is GameCube. It cannot for .rvz, which is Dolphin's own
    container and which ScreenScraper lists under no system at all. With the
    alias naming one console, every Dolphin game was looked up as a GameCube
    game: Skyward Sword, New Super Mario Bros. Wii and Super Smash Bros. Brawl
    came back "not in the database" because they are Wii only.
    """
    assert gm._alias_names("dolphin") == ["gamecube", "wii"]
    assert gm._alias_names("mgba") == ["gba", "gbc", "gb"]
    # A plain string still means one console, which is most of the table.
    assert gm._alias_names("rpcs3") == ["ps3"]
    # And an id that is not an emulator passes straight through.
    assert gm._alias_names("ps3") == ["ps3"]


# ── The best candidate wins, not the first to answer ─────────────────────────

def _jeu(*titles):
    return {"id": 1, "noms": [{"region": "wor", "text": t} for t in titles]}


def test_a_fuzzy_hit_on_the_wrong_console_scores_badly():
    """ScreenScraper's name search always answers something.

    Asked for Mario Kart Wii on GameCube it returns Mario Kart: Double Dash,
    and since any answer used to end the loop, that is what the box displayed.
    """
    parsed = {"title": "Mario Kart Wii"}
    assert gm._title_score(parsed, _jeu("Mario Kart Wii")) == 1.0
    assert gm._title_score(parsed, _jeu("Mario Kart : Double Dash!!")) < 0.7


def test_the_rom_naming_convention_does_not_count_against_a_match():
    """Dumps put the article at the end; ScreenScraper puts it in front.

    Scoring the raw strings would reject the correct answer — which is why this
    goes through the same normalise() the LaunchBox search uses.
    """
    parsed = {"title": "Legend of Zelda, The - Skyward Sword"}
    assert gm._title_score(parsed, _jeu("The Legend of Zelda - Skyward Sword")) == 1.0


def test_two_games_in_one_series_are_a_threshold_apart():
    """Mario Party 4 against Mario Party 7 scores 0.909.

    One character apart, two genuinely different games — so a threshold alone
    cannot decide this, and the acceptance bar sits above it. What settles it
    is comparing the candidates with each other.
    """
    score = gm._title_score({"title": "Mario Party 4"}, _jeu("Mario Party 7"))
    assert 0.85 < score < gm.NAME_ACCEPT


def test_a_confirmed_hash_is_never_second_guessed():
    """The server echoed our digest. No title can improve on that."""
    hashes = {"crc": "ABCD1234", "md5": "", "sha1": ""}
    echoed = {"id": 1, "rom": {"romcrc": "abcd1234"}, "noms": []}
    assert gm._hash_confirmed(echoed, hashes) is True
    # A different digest is a name match dressed up as a hash one.
    assert gm._hash_confirmed({"id": 1, "rom": {"romcrc": "0000"}}, hashes) is False


# ── warming ──────────────────────────────────────────────────────────────────
# What makes the detail panel instant: the media a theme draws beyond the cover
# are fetched at boot rather than the first time someone looks at the game.

def test_warming_fetches_only_what_is_missing(tmp_path, monkeypatch):
    """Already-downloaded media must not be re-fetched.

    Warming runs on every boot over the whole library. If it asked for what it
    already had, a 47-game box would spend ~280 requests at 1.2 s each on every
    single start — six minutes of the scraper's budget for nothing.
    """
    monkeypatch.setattr(gm, "CACHE_ROOT", tmp_path)
    d = gm.entry_dir("rpcs3", "Uncharted 2")
    gm.write_json(d / gm.MANIFEST, {"found": True, "media": {
        "box-front": {"file": "box-front.png"},                 # already here
        "box-3d": {"deferred": True, "url": gm.strip_creds(SS_URL)},
        "screenshot-gameplay": {"deferred": True, "url": gm.strip_creds(SS_URL)},
    }})

    asked = []

    async def fake_media_file(system_id, filename, slug):
        asked.append(slug)
        return tmp_path / f"{slug}.png"

    monkeypatch.setattr(gamemedia, "media_file", fake_media_file)
    got = await_(gamemedia.warm("rpcs3", "Uncharted 2",
                                {"box-front", "box-3d", "screenshot-gameplay"}))

    assert got == 2
    assert sorted(asked) == ["box-3d", "screenshot-gameplay"]


def test_warming_never_asks_for_a_media_the_game_does_not_have(tmp_path,
                                                               monkeypatch):
    """A slug absent from the manifest is absent from the game.

    Asking anyway would cost a request per game per type that system never
    carries — box-spine alone is missing from most arcade titles.
    """
    monkeypatch.setattr(gm, "CACHE_ROOT", tmp_path)
    d = gm.entry_dir("rpcs3", "Uncharted 2")
    gm.write_json(d / gm.MANIFEST,
                  {"found": True, "media": {"box-front": {"file": "b.png"}}})

    async def refuse(*a):
        raise AssertionError("warming asked for a media that was never recorded")

    monkeypatch.setattr(gamemedia, "media_file", refuse)
    assert await_(gamemedia.warm("rpcs3", "Uncharted 2", {"box-3d"})) == 0


def test_warming_skips_a_game_with_no_manifest(tmp_path, monkeypatch):
    """It never scrapes: a game the cover pipeline has not reached costs nothing."""
    monkeypatch.setattr(gm, "CACHE_ROOT", tmp_path)

    async def refuse(*a):
        raise AssertionError("warming tried to fetch without a manifest")

    monkeypatch.setattr(gamemedia, "media_file", refuse)
    assert await_(gamemedia.warm("rpcs3", "Never Scraped")) == 0



# ── where the index lives: one fact, one answer ────────────────────────────

def test_the_cli_and_the_backend_agree_on_where_the_index_lives(tmp_path):
    """Found on a real box, and invisible from everywhere else.

    The backend imports services/gamemedia/__init__.py, which moves the index
    into GAMECORE_PATH/emu/gamescrape — inside the installation, excluded from
    the OTA rsync so it survives updates. `gamescrape.py` run as a plain script
    never executes that __init__, so `--refresh` built the 234 MB index in
    ~/.cache/gamescrape instead.

    Nothing said so. `status()` reported `launchbox_index: False` with the
    index on disk two directories away, the LaunchBox tier had been silently
    off since the day it was populated, and every lookup fell through to
    ScreenScraper alone — which needs an account the free tier does not have.

    Both sides are asked in a subprocess, through the same seam a person uses:
    the script with GAMECORE_PATH set, and the package the backend imports.
    """
    import subprocess
    import sys as _sys

    root = tmp_path / "gamecore"
    (root / "emu").mkdir(parents=True)
    env = {**os.environ, "GAMECORE_PATH": str(root),
           "PYTHONDONTWRITEBYTECODE": "1"}

    def run(code: str) -> str:
        r = subprocess.run([_sys.executable, "-c", code], capture_output=True,
                           text=True, env=env, cwd=str(REPO), timeout=60)
        assert r.returncode == 0, r.stderr
        return r.stdout.strip()

    # The script, resolving its index the way main() does — the real function,
    # not a copy of its rule.
    # Mirrors main()'s two lines exactly, None-guard included — so a regression
    # reports WHICH two paths disagree rather than crashing on a None.
    from_cli = run(
        "import sys; sys.path.insert(0, 'backend/services/gamemedia'); "
        "import gamescrape as gs; "
        "chosen = gs.resolve_index_dir(None)\n"
        "if chosen is not None: gs.set_index_dir(chosen)\n"
        "print(gs.DB_PATH)")

    # The package, as the backend imports it.
    from_backend = run(
        "from backend.services.gamemedia import gamescrape as gs; print(gs.DB_PATH)")

    assert from_cli == from_backend, (
        f"the CLI would build the index at {from_cli}\n"
        f"the backend would read it from  {from_backend}")


def test_a_standalone_gamescrape_still_caches_in_the_home(tmp_path):
    """The other half: away from a GameCore install, nothing changes.

    gamescrape is usable on its own — its module docstring documents
    ~/.cache/gamescrape — and this fix must not relocate a developer's index
    just because they have the variable exported for something else.
    """
    import subprocess
    import sys as _sys

    env = {k: v for k, v in os.environ.items() if k != "GAMECORE_PATH"}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    r = subprocess.run(
        [_sys.executable, "-c",
         "import sys; sys.path.insert(0, 'backend/services/gamemedia'); "
         "import gamescrape as gs; print(gs.resolve_index_dir(None))"],
        capture_output=True, text=True, env=env, cwd=str(REPO), timeout=60)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "None", (
        "with no GAMECORE_PATH the default must be left alone")
