#!/usr/bin/env python3
"""gamemedia — one endpoint that returns EVERYTHING known about a game.

    python3 gamemedia.py --serve 8899
    curl 'http://127.0.0.1:8899/api/games/nds/Mario%20Kart%20DS%20(USA).nds' | jq

The idea: the frontend does not scrape and does not pick a source. It asks for a
game, it gets the metadata and the list of EVERY available media with a local URL
for each, and it decides what to display — 3D box, cover, screenshot, logo,
video, mix. The service handles the rest.

Three tiers, in this order:

  1. CACHE      ~/.cache/gamemedia/<system>/<key>/ — if game.json is there,
                nothing hits the network. The normal case after the first call.
  2. SCREENSCRAPER  by file hash when the ROM exists (CRC/MD5/SHA1: the match is
                certain even if the file is misnamed), by name otherwise. The
                only source that gives description, developer, publisher,
                genres, player count and rating.
  3. LAUNCHBOX  official dump indexed into SQLite, offline, no credentials. The
                net when ScreenScraper is absent, out of quota or silent. Also
                gives description, developer, publisher, genres, players and
                rating: 172,550 synopses over 185,201 games, no account, no
                network.

Name parsing, the LaunchBox index and downloading all come from gamescrape.py,
imported as a library — there are no two copies to maintain.

The rules for being a good ScreenScraper citizen (1.2 s between requests,
errors classified on the raw bytes, thread count dictated by the account,
repairing invalid JSON) are taken from Skyscraper (muldjord), the reference CLI
scraper, which learned them in production. See the "ScreenScraper client" block.

No dependencies: standard library only, HTTP server included. The server only
exists for development and testing — once integrated into GameCore, its backend
will call resolve() directly from its own router.

    --serve PORT      HTTP API on 127.0.0.1
    --cache-stats     what is in the cache
    <rom>             resolve a game and write the manifest on stdout

Endpoints:

    GET /api/health
    GET /api/cache
    GET /api/games/{system}/{file}              → metadata + every media
    GET /api/games/{system}/{file}/media/{type} → one media
        ?refresh=1    ignore the cache and rescrape
        ?download=0   resolve without downloading

Credentials: ~/.config/gamescrape/credentials (see gamescrape.py). Without them
only tier 3 works, and the service says so in `notes`.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

# GameCore: vendored as backend.services.gamemedia.gamemedia, so the sibling is
# a package module. The fallback keeps `python3 gamemedia.py` working from the
# folder itself, which is how the two files are debugged.
try:
    from . import gamescrape as gs
except ImportError:  # pragma: no cover — standalone use
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import gamescrape as gs  # noqa: E402  — parsing, LaunchBox index, SS calls

try:
    from . import paths
except ImportError:                                    # plain-script CLI
    import paths




# ── The façade ──────────────────────────────────────────────────────────────
#
# This file was 1 605 lines. Four of its section headers were already the
# seams, and they are now four modules, plus one for the location they share:
#
#     helpers.py     what is a game, what is junk, where its entry goes
#     registry.py    which ScreenScraper system a ROM belongs to
#     identity.py    the dumps that are directories, and what they call themselves
#     ss_client.py   the ScreenScraper client: rate limit, retries, hashes, scoring
#     paths.py       the cache root, which MOVES (see paths.set_cache_root)
#
# What stayed is the two scraping tiers, the resolution-and-cache logic they
# feed, the HTTP API and the CLI — the parts that orchestrate rather than
# answer one question.
#
# Everything the modules define is re-exported HERE, under the names it had
# before: services/gamemedia/__init__.py reaches into this module as `gm.<name>`
# and so do the tests. A split that changed one import outside this package
# would not be a split.
# `ss_client` is also imported as a MODULE: `ss_remaining` is rebound on every
# API answer that reports the quota, and a from-import would pin it to the
# value it had at startup — the health endpoint would report a full quota for
# ever, including after the account was closed for exceeding it.
try:
    from . import ss_client
    from .helpers import (                                     # noqa: F401
        entry_dir,
        game_key,
        looks_like_game,
        write_json,
    )
    from .identity import local_identity, read_sfo             # noqa: F401
    from .registry import (                                    # noqa: F401
        EMULATOR_ALIASES,
        _alias_names,
        _catalog_aliases,
        detect_system,
        fetch_systems,
        registry,
        system_candidates,
    )
    from .ss_client import (                                   # noqa: F401
        HASH_MAX_BYTES,
        NAME_ACCEPT,
        SS_MAX_THREADS,
        ScreenScraperClosed,
        ScreenScraperUnreachable,
        _hash_confirmed,
        _ss_limiter,
        _matched_by,
        _rating_01,
        _title_score,
        _year_of,
        hashes_for,
        ss_request,
        ss_threads,
    )
except ImportError:                                            # plain-script CLI
    import ss_client
    from helpers import entry_dir, game_key, looks_like_game, write_json  # noqa: F401
    from identity import local_identity, read_sfo              # noqa: F401
    from registry import (                                     # noqa: F401
        EMULATOR_ALIASES, _alias_names, _catalog_aliases, detect_system,
        fetch_systems, registry, system_candidates,
    )
    from ss_client import (                                    # noqa: F401
        HASH_MAX_BYTES, NAME_ACCEPT, SS_MAX_THREADS, ScreenScraperClosed,
        ScreenScraperUnreachable, _hash_confirmed, _matched_by, _rating_01, _ss_limiter,
        _title_score, _year_of, hashes_for, ss_request, ss_threads,
    )


def set_cache_root(directory) -> None:
    """Move the media cache. The ONLY supported way to move it.

    Assigning `gm.CACHE_ROOT` used to work because there was one module; there
    are five now, and an assignment here would leave helpers.entry_dir writing
    covers under ~/.cache while everything else reported them inside the
    installation — where the OTA rsync never sees them and a cleaner does.
    """
    global CACHE_ROOT, SYSTEMS_CACHE
    paths.set_cache_root(directory)
    CACHE_ROOT, SYSTEMS_CACHE = paths.CACHE_ROOT, paths.SYSTEMS_CACHE


# Re-exported so `gm.CACHE_ROOT` and `gm.SYSTEMS_CACHE` keep answering, and kept
# in step by set_cache_root() above.
CACHE_ROOT = paths.CACHE_ROOT
SYSTEMS_CACHE = paths.SYSTEMS_CACHE
MANIFEST = paths.MANIFEST

def safe_url(url: str) -> str:
    """Re-normalise a URL handed over by a third-party API.

    ScreenScraper returns media URLs whose query contains unescaped spaces —
    for instance `…&media=maps(Complete Graphical Map)`. urllib flatly refuses
    ("URL can't contain control characters") and the exception travelled up to
    kill the whole HTTP request: one malformed media and the game became
    unrecoverable. So the query is re-encoded properly.
    """
    import urllib.parse
    parts = urllib.parse.urlsplit(url.strip())
    if not parts.query:
        return url.strip()
    pairs = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    return urllib.parse.urlunsplit(parts._replace(
        path=urllib.parse.quote(parts.path, safe="/%"),
        query=urllib.parse.urlencode(pairs)))


# GameCore: a media URL is kept in the manifest so it can be fetched later
# (see `only=` in resolve), and a manifest is a file on disk. ScreenScraper puts
# devid/devpassword/ssid/sspassword in the query of every mediaJeu.php URL, so
# storing one as received would write the developer account into
# emu/gamemedia/<system>/<game>/game.json — world-readable, and carried into
# every bug report that attaches a manifest. The four parameters are dropped on
# write and put back from the live credentials on read; nothing else in the URL
# identifies the account, and the LaunchBox CDN carries none at all.
def strip_creds(url: str) -> str:
    """URL without the credential parameters — safe to write to disk."""
    import urllib.parse
    parts = urllib.parse.urlsplit(url)
    if not parts.query:
        return url
    kept = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
            if k.lower() not in gs._SECRET_PARAMS]
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(kept)))


def with_creds(url: str) -> str:
    """The stored URL, credentials restored. Unchanged for a non-SS host."""
    import urllib.parse
    parts = urllib.parse.urlsplit(url)
    if "screenscraper" not in parts.netloc:
        return url
    creds = gs.ss_credentials()
    if not creds:
        return url
    pairs = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
             if k.lower() not in gs._SECRET_PARAMS]
    pairs += [(k, creds[k]) for k in ("devid", "devpassword", "ssid", "sspassword")
              if creds.get(k)]
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(pairs)))


# GameCore: which language wins, most preferred first. Upstream hardcoded
# French then English; GameCore's whole interface is in English, so a library
# where the buttons read "PLAY TIME" and the synopses are in French is not a
# choice anyone made. Set by the adapter from GAMECORE_SCRAPER_LANG.
#
# It applies to the synopsis AND to the genre names — ScreenScraper localises
# both, which is why a French install shows "Course, Conduite" where an English
# one shows "Racing, Driving".
LANG_PREF: list[str] = ["fr", "en"]


def _pick_lang(items: list[dict], key: str = "text") -> str:
    """Value from a multilingual ScreenScraper list, per LANG_PREF."""
    if not items:
        return ""
    by = {i.get("langue"): i.get(key, "") for i in items if isinstance(i, dict)}
    for lang in LANG_PREF:
        if by.get(lang):
            return by[lang]
    return next((i.get(key, "") for i in items if isinstance(i, dict)), "")


def _pick_region(items: list[dict], order: list[str]) -> str:
    """Regionalised value, per the preference order derived from the ROM tag."""
    if not items:
        return ""
    by = {i.get("region"): i.get("text", "") for i in items if isinstance(i, dict)}
    for r in order:
        if by.get(r):
            return by[r]
    return next((i.get("text", "") for i in items if isinstance(i, dict)), "")




# ── Tier 2: ScreenScraper, metadata AND media in one call ───────────────────

def ss_everything(parsed: dict, rom_path: Path | None,
                  verbose: bool) -> dict | None:
    """{meta, media, source…} from a single jeuInfos, or None.

    gamescrape.ss_lookup only returns the images — it lacks the description, the
    developer, the genres. The call is made here to capture everything at once
    rather than paying two requests out of a 20,000/day quota.

    Returns None when ScreenScraper clearly answers "not this game" (a final,
    cacheable result). Lets ScreenScraperClosed / ScreenScraperUnreachable
    propagate otherwise, so the caller does not write a "nothing found" manifest
    on a spent quota or a network outage.
    """
    creds = gs.ss_credentials()
    if not creds:
        return None

    # `romnom`: the title the game gives itself (PARAM.SFO) when known, the
    # filename otherwise. For a PS3 directory that is the difference between a
    # 404 and 152 media — see local_identity().
    params = dict(creds, romtype="rom",
                  romnom=parsed.get("romnom") or Path(parsed["source"]).name)
    hashes = hashes_for(rom_path) if rom_path else None
    if hashes:
        params.update(hashes)
    # systemeid comes from the registry built off the API (250 systems), not
    # from a frozen table. Candidates are tried in order: an emulator can cover
    # several consoles, and the hash, when we have it, decides on its own —
    # hence the attempt without systemeid first in that case.
    cands = parsed.get("ss_candidates") or [parsed.get("ss_systemeid")]
    # (systemeid, with_hash) — the hash first, then one LAST attempt without it.
    # A CRC absent from the database (private dump, romhack, trimmed ROM, bad
    # dump, re-encode) made all five attempts fail and carved a final negative,
    # while searching by NAME would have found the game. The hash is a shortcut,
    # not the only route — that is what ES-DE does, logging its fallback to the
    # name (ScreenScraper.cpp:787-793).
    attempts: list[tuple[int | None, bool]] = []
    if hashes:
        attempts.append((None, True))
    attempts += [(sid, True) for sid in cands]
    if hashes:
        attempts.append((cands[0] if cands else None, False))
    # With no systemeid AND no hash, the API answers "Champ systemeid
    # obligatoire si aucun CRC": the request is lost before it leaves. It went
    # out anyway — 3 attempts at 1.2 s, 3 quota requests — for every entry whose
    # console stays undetermined (a `metadata/` directory, a DLC pack).
    # `use_hash` means "send the hash if we have one", not "we have one": it is
    # `hashes` that must be interrogated.
    attempts = [(sid, uh) for sid, uh in attempts if sid or (uh and hashes)]
    if not attempts:
        # "I could not ask", not "the game does not exist". Returning None here
        # would carve a final negative on an entry never submitted — the day the
        # console becomes detectable, the cache would still serve that refusal.
        raise ScreenScraperUnreachable(
            "console undetermined and no usable hash")

    # GameCore: the best candidate wins, not the first one to answer.
    #
    # An emulator can cover several consoles, and the search is fuzzy, so the
    # first console asked will happily return its nearest title — which is how
    # a Wii game came back as a GameCube one. Candidates are compared instead.
    #
    # The quota cost is paid only where there is doubt: a title that comes back
    # nearly exact is accepted on the spot, so a game found on the first try
    # still costs one request. Only an unconvincing answer makes us ask the next
    # console, which is precisely when it is worth it.
    best: tuple[float, dict, bool] | None = None
    for sid, use_hash in attempts:
        p = dict(params)
        if sid:
            p["systemeid"] = sid
        else:
            p.pop("systemeid", None)
        if not use_hash:
            for k in ("crc", "md5", "sha1"):
                p.pop(k, None)          # romtaille stays: it helps the server
        data = ss_request("jeuInfos.php", p, verbose)
        if data is None:
            continue
        jeu = (data.get("response") or {}).get("jeu")
        if not jeu:
            continue

        # A digest the server echoed back is proof, not a guess. Nothing about
        # a title can improve on it, and nothing may override it.
        if use_hash and hashes and _hash_confirmed(jeu, hashes):
            best = (1.0, jeu, use_hash)
            break

        score = _title_score(parsed, jeu)
        if best is None or score > best[0]:
            best = (score, jeu, use_hash)
        if score >= NAME_ACCEPT:
            break

    if best is None:
        return None
    # Kept even when nothing was convincing: a weak match is still far more
    # useful than a blank card, and `matched_by` carries the doubt so it can be
    # seen rather than guessed at.
    name_score, jeu, hash_used = best

    order = gs.SS_REGION_PREF.get(parsed["region"], gs.SS_REGION_PREF[None])
    genres = [_pick_lang(g.get("noms", [])) for g in (jeu.get("genres") or [])]
    meta = {
        "title": _pick_region(jeu.get("noms", []), order),
        "description": _pick_lang(jeu.get("synopsis", [])),
        "developer": (jeu.get("developpeur") or {}).get("text", ""),
        "publisher": (jeu.get("editeur") or {}).get("text", ""),
        "released": _pick_region(jeu.get("dates", []), order),
        "genres": [g for g in genres if g],
        "players": (jeu.get("joueurs") or {}).get("text", ""),
        "rating": (jeu.get("note") or {}).get("text", ""),
        "platform": (jeu.get("systeme") or {}).get("text", ""),
    }
    # ScreenScraper rates out of 20 and dates in assorted formats
    # ("1993-11-01", "1993", "11/1993"). Serving that raw forced every theme to
    # become a parser again — and "rating: 16" on an unstated scale means
    # nothing.
    meta["year"] = _year_of(meta["released"])
    meta["rating_20"] = meta["rating"]
    meta["rating"] = _rating_01(meta["rating"])
    # A given field must exist whatever the source, otherwise the frontend has
    # to know which tier its record came from — exactly what this service is
    # meant to spare it. `classifications` carries everything the source knows
    # (ScreenScraper: USK, PEGI, ESRB, CERO, JV), `esrb` is its shortcut;
    # `rating_count` and `coop` only exist on LaunchBox.
    meta["classifications"] = {c["type"]: c.get("text", "")
                               for c in (jeu.get("classifications") or [])
                               if c.get("type")}
    meta["esrb"] = meta["classifications"].get("ESRB", "")
    meta["rating_count"] = None
    meta["coop"] = None

    # A media type exists in several regions: keep the best per the order above,
    # and record the region so the frontend can ask for a specific one some day.
    #
    # `category` and `kind` travel with every media: without them the frontend
    # had to recognise 54 type names by hand to tell which one is a box, which
    # is a video, which is only a pinball cabinet bezel.
    media: dict[str, dict] = {}
    for m in jeu.get("medias") or []:
        short, category, kind = gs.ss_media_info(m.get("type") or "")
        if not short or not m.get("url"):
            continue
        region = m.get("region") or ""
        rank = order.index(region) if region in order else len(order)
        prev = media.get(short)
        if prev is None or rank < prev["_rank"]:
            media[short] = {"_rank": rank, "url": safe_url(m["url"]), "region": region,
                            "format": (m.get("format") or "").lower(),
                            "category": category, "kind": kind,
                            "ss_type": m.get("type") or ""}
    for v in media.values():
        v.pop("_rank", None)

    how = _matched_by(jeu, hashes if hash_used else None)
    # GameCore: a name match nobody is confident about says so. It is the same
    # honesty `_matched_by` already applies to hashes — describe what actually
    # happened, so a wrong cover can be recognised as a weak match rather than
    # looked at as a mystery.
    if how.startswith("name") and name_score < NAME_ACCEPT:
        how = f"{how} (weak, {name_score:.0%})"
    return {"source": "screenscraper", "game_id": jeu.get("id"),
            "matched_by": how, "meta": meta, "media": media}


# ── Tier 3: LaunchBox ───────────────────────────────────────────────────────

def lb_everything(parsed: dict, cutoff: float) -> dict | None:
    """Same through the local LaunchBox index — description included, offline.

    The index only returned name + platform + year, and the manifest came out
    with `description`, `developer`, `publisher`, `genres` and `rating` empty.
    All of it is in Metadata.xml; only the indexing was throwing it away:
    172,550 synopses over 185,201 games, available with no account and no
    network.
    """
    # auto=False: build_index() (106 MB, 1 to 2 min) must NEVER start from an
    # HTTP handler. resolve() already checks the index is usable before getting
    # here; this guard covers direct calls.
    if not gs.lb_index_ready():
        return None
    try:
        db = gs.open_db(auto=False)
    except Exception:
        return None
    try:
        game, score = gs.find_game(db, parsed, parsed["systems"], cutoff)
        if not game:
            return None
        images = gs.game_images(db, game["id"], parsed, None, False)
    finally:
        db.close()
    media = {}
    for typ, urls in images.items():
        if not urls:
            continue
        category, kind = gs.lb_media_info(typ)
        media[typ] = {"url": urls[0], "region": "", "format": "",
                      "category": category, "kind": kind, "ss_type": ""}
    # `released` carries an ISO date when LaunchBox has one (15 % of games), the
    # year otherwise: the field keeps the same meaning as on the ScreenScraper
    # side.
    released = game.get("released") or game.get("year", "")
    meta = {"title": game["name"],
            "description": game.get("overview", ""),
            "developer": game.get("developer", ""),
            "publisher": game.get("publisher", ""),
            "released": released,
            "genres": game.get("genres") or [],
            "players": game.get("players", ""),
            # LaunchBox rates out of 5, ScreenScraper out of 20: `rating` is
            # already brought to 0–1 at indexing time, the only common scale.
            "rating": game.get("rating"),
            "rating_20": "",
            "rating_count": game.get("rating_count"),
            "esrb": game.get("esrb", ""),
            "classifications": ({"ESRB": game["esrb"]} if game.get("esrb")
                                else {}),
            "coop": game.get("coop", False),
            "platform": game.get("platform", ""),
            "year": _year_of(released)}
    for extra in ("video_url", "wiki_url"):
        if game.get(extra):
            meta[extra] = game[extra]
    return {"source": "launchbox", "game_id": game["id"],
            "matched_by": f"name ({score:.0%})", "meta": meta, "media": media}


# ── Resolution + cache ──────────────────────────────────────────────────────

def _manifest_complete(d: Path, manifest: dict) -> bool:
    """Is the manifest servable as it stands?

    The presence of an ENTRY is not its COMPLETENESS — that confusion is what
    made a `?download=0` write `{"pending": true}` per type, and the next call
    serve that manifest as final: no download was ever attempted again and
    /media answered 404 forever. Same for a media whose download failed, and for
    a file deleted from the cache by hand. So completeness is judged per
    resource, the way Skyscraper's dedup key does (src/cache.cpp:1464-1486).
    """
    if not manifest.get("found"):
        # A negative written while a tier was missing deserves another try.
        tried = set(manifest.get("tiers_tried") or [])
        if gs.ss_credentials() and "screenscraper" not in tried:
            return False
        if gs.lb_index_ready() and "launchbox" not in tried:
            return False
        return True
    # GameCore: the synopsis and the genre names are stored in the language that
    # was preferred when the game was scraped, so an entry scraped under another
    # one is not servable — it would pin a library to whatever language it
    # happened to be first swept in. Re-scraping costs one jeuInfos; the media
    # already downloaded are kept (see `have` in resolve()), so no file moves.
    if manifest.get("found") and manifest.get("lang") != LANG_PREF[0]:
        return False

    for info in (manifest.get("media") or {}).values():
        # GameCore: `deferred` is a fourth state, and the only one that does not
        # make the entry incomplete. `pending` means "a download=0 wrote this and
        # nobody ever came back", which is the bug this function exists to catch;
        # `deferred` means "resolve() was told not to fetch this type, its URL is
        # right here, fetch_media() will get it when something asks". Treating
        # the two alike would rescrape the whole game — one jeuInfos out of the
        # daily quota — every single time a theme displayed a cover.
        if info.get("deferred") and info.get("url"):
            continue
        # `blank` is a FIFTH state, and it is settled rather than incomplete:
        # the source served a chroma-key plate, the other tier was asked, and
        # this is the answer. Reading it as a hole would rescrape the game — one
        # jeuInfos out of the daily quota — every single time a theme drew a
        # cover, to be handed the same plate again.
        if info.get("blank"):
            continue
        if info.get("pending") or info.get("failed") or not info.get("file"):
            return False
        path = d / Path(info["file"]).name
        if not path.is_file():
            return False
        # A plate filed BEFORE this was recognised. Nine of them are on the
        # reference box, recorded as ordinary scans, and nothing would ever
        # revisit them: the manifest is complete, the file is there, and the
        # greenness is only visible to something that reads pixels. Calling it
        # incomplete costs one rescrape, once — the download path then records
        # it `blank`, `_top_up_blanks` asks the other tier, and the next check
        # takes the `blank` branch above and settles. It cannot loop.
        #
        # Gated on the size the manifest already stores, so this stays an
        # integer comparison for every real media: the plates run 1 996 to
        # 3 082 bytes, the smallest real scan on that box is over 100 KB. Only
        # a genuinely tiny file is ever opened, and an icon — which IS tiny —
        # fails the bytes-per-pixel test rather than the size one.
        if info.get("bytes", 0) < _PLATE_SUSPECT_BYTES and gs.looks_like_flat_plate(path):
            return False
    return True


def load_cached(system: str, filename: str) -> dict | None:
    try:
        return json.loads((entry_dir(system, filename) / MANIFEST).read_text("utf-8"))
    except (OSError, ValueError):
        return None


def resolve(system: str, filename: str, *, refresh: bool = False,
            download: bool = True, only: set[str] | None = None,
            cutoff: float = 0.72, verbose: bool = False) -> dict:
    """A game's manifest. Cache first, network only when necessary.

    GameCore: `only` restricts what is downloaded NOW to that set of slugs.
    Everything else is recorded as `deferred` with its URL, and fetch_media()
    gets it the day something asks. Without it, one game costs ~28 downloads at
    1.2 s each — over half a minute per title, times the whole library, on a
    prefetch that runs 15 s after boot. The default theme shows one image per
    game, so it must pay for one.
    """
    if why := looks_like_game(filename):
        return {"system": system, "filename": filename, "found": False,
                "skipped": why, "notes": [f"skipped: {why}"],
                "meta": {}, "media": {}, "cached": False}

    d = entry_dir(system, filename)
    cached = None if refresh else load_cached(system, filename)
    # `refresh` destroys NOTHING up front. An rmtree before the first network
    # call deleted a PS3 game's 152 media, then the quota ran out, then nothing
    # was rewritten: the entry was lost and the next call rescraped into the
    # void. Skyscraper replaces resource by resource and never razes the entry
    # (src/cache.cpp:1464-1486) — same principle here.
    if cached and _manifest_complete(d, cached):
        cached["cached"] = True
        return cached

    parsed = gs.parse_rom(filename)
    if system and system not in parsed["systems"]:
        parsed["systems"] = [system] + parsed["systems"]

    # The system, resolved once for both sources. `system` can be an emulator id
    # (rpcs3), a console slug (ps3), a full name (PlayStation 3) or an alias from
    # another frontend — the registry knows them all. Failing that, the parent
    # directory is the hint, then the extension.
    sid, sinfo = detect_system(filename, system)
    parsed["ss_candidates"] = system_candidates(filename, system)
    if sid:
        parsed["ss_systemeid"] = sid
        parsed["system_name"] = sinfo.get("name", "")
        # The matching LaunchBox name, so tier 3 searches in the right place.
        if lb := sinfo.get("launchbox"):
            parsed["systems"] = [lb] + [s for s in parsed["systems"] if s != lb]

    rom = Path(filename)
    # A game that is a directory (PS3, PS4, PSP dump) carries its real title in
    # its PARAM.SFO. It is used for BOTH sources: ScreenScraper accepts only
    # that one, and LaunchBox matches better on it than on a directory name.
    if ident := local_identity(rom):
        parsed["romnom"] = ident["title"]
        parsed["title"] = ident["title"]
        parsed["serial"] = ident["serial"]
        parsed["identified_by"] = "PARAM.SFO"
    hit, unreachable, notes = None, False, []
    tiers_tried: list[str] = []
    if not gs.ss_credentials():
        # "I did not even try" is a THIRD state, distinct from "not found" and
        # from "unreachable". Without this unreachable, sweeping a library before
        # configuring credentials carved a final "this game does not exist" over
        # everything LaunchBox could not find — and adding the credentials
        # changed nothing afterwards.
        unreachable = True
        notes.append("screenscraper: no credentials — LaunchBox tier only")
    else:
        tiers_tried.append("screenscraper")
        try:
            hit = ss_everything(parsed, rom if rom.is_file() else None, verbose)
            if hit is None:
                notes.append("screenscraper: game not in the database")
        except (ScreenScraperClosed, ScreenScraperUnreachable) as e:
            # The distinction that matters: neither case says ANYTHING about
            # the game. We fall through to LaunchBox for this response, but
            # nothing is cached if LaunchBox does not find it either.
            unreachable = True
            notes.append(f"screenscraper : {type(e).__name__} — {e}")

    if hit is None:
        if gs.lb_index_ready():
            tiers_tried.append("launchbox")
            hit = lb_everything(parsed, cutoff)
            if hit is None:
                notes.append("launchbox: no match")
        else:
            # build_index() downloads 106 MB and indexes for 1 to 2 minutes.
            # Never inside an HTTP handler: say so and hand back control.
            #
            # The path is named, and the command is one that WORKS. This note
            # used to read "run `gamescrape.py --refresh`", and following it to
            # the letter rebuilt 234 MB in ~/.cache/gamescrape — not here.
            # A remedy that changes nothing is worse than no remedy: it spends
            # a quarter of an hour and leaves the reader certain they fixed it.
            unreachable = True
            notes.append(
                f"launchbox: index missing at {gs.DB_PATH} — run "
                f"`gamescrape.py --refresh --index-dir {gs.CACHE_DIR}`")

    if hit is None:
        # Nothing found. A negative manifest is only written when the tiers
        # REALLY answered — otherwise a network outage, a spent quota or missing
        # credentials would carve "this game does not exist" onto the disk, and
        # the cache would serve that lie indefinitely.
        result = {"system": system, "filename": filename, "key": game_key(filename),
                  "found": False, "notes": notes, "parsed": parsed,
                  "meta": {}, "media": {}, "cached": False,
                  # Timestamped and traced: a negative written while a tier was
                  # missing can be retried once that tier comes back.
                  "negative_at": datetime.now(timezone.utc).isoformat(),
                  # The frontend must be able to tell "this game is not in the
                  # database" (show a neutral placeholder, final) from "I could
                  # not ask" (offer a retry). Without this field the two looked
                  # alike: found=False in both cases.
                  "unreachable": unreachable,
                  "tiers_tried": tiers_tried}
        if not unreachable:
            write_json(d / MANIFEST, result)
        elif cached:
            # We had an entry and could rebuild nothing: return it as is rather
            # than letting anyone believe the game vanished.
            cached["cached"] = True
            cached["notes"] = list(cached.get("notes") or []) + notes
            return cached
        return result

    manifest = {
        "system": system, "filename": filename, "key": game_key(filename),
        "found": True, "source": hit["source"], "matched_by": hit["matched_by"],
        "game_id": hit["game_id"], "scraped_at": datetime.now(timezone.utc).isoformat(),
        # GameCore: the language the text in `meta` is in. Without it, changing
        # the preference would leave every already-scraped game in the old one.
        "lang": LANG_PREF[0],
        "parsed": parsed, "meta": hit["meta"], "notes": notes,
        "media": {}, "cached": False,
    }

    if download:
        # The LaunchBox CDN limits nothing; ScreenScraper grants threads per
        # account and penalises going over, so it is the one that decides.
        is_ss = hit["source"] == "screenscraper"
        workers = ss_threads() if is_ss else 8
        # Keep what is already there and valid: re-downloading 152 media
        # because one was missing wastes both quota and time.
        # "Keep what is already there and VALID" — and a chroma-key plate filed
        # before it could be recognised is not valid. Left in `have` it would be
        # kept rather than re-fetched, so the rescrape `_manifest_complete` just
        # asked for would preserve the very file it asked about.
        have = {k: v for k, v in ((cached or {}).get("media") or {}).items()
                if v.get("file") and not v.get("failed") and not v.get("pending")
                and (d / Path(v["file"]).name).is_file()
                and not (v.get("bytes", 0) < _PLATE_SUSPECT_BYTES
                         and gs.looks_like_flat_plate(d / Path(v["file"]).name))}
        todo = {k: v for k, v in hit["media"].items() if k not in have
                and (only is None or k in only)}
        fresh = _download_media(d, todo, workers, verbose, throttle=is_ss)
        # GameCore: everything neither cached nor just fetched keeps its URL and
        # waits. Credentials are stripped before the manifest is written.
        later = {k: {"deferred": True, "url": strip_creds(v["url"]), **_descriptors(v)}
                 for k, v in hit["media"].items()
                 if k not in have and k not in fresh}
        manifest["media"] = {**have, **fresh, **later}
        _top_up_blanks(d, manifest, hit, parsed, cutoff, notes, verbose)
        if have:
            notes.append(f"{len(have)} media already cached, {len(todo)} fetched")
        if later:
            notes.append(f"{len(later)} media deferred (fetched on demand)")
    else:
        # `download=0` does NOT claim to deliver a complete game: the manifest
        # states explicitly that every media is still to be fetched, and
        # _manifest_complete() will refuse to serve it as is.
        manifest["media"] = {k: {"pending": True, **_descriptors(v)}
                             for k, v in hit["media"].items()}
        manifest["partial"] = True

    write_json(d / MANIFEST, manifest)
    return manifest


# Below this, a recorded media is small enough to be worth opening. The plates
# measured run 1 996 to 3 082 bytes; the smallest real scan on the reference box
# is over 100 KB. See `_manifest_complete`.
_PLATE_SUSPECT_BYTES = 8192


def _top_up_blanks(d: Path, manifest: dict, hit: dict, parsed: dict,
                   cutoff: float, notes: list[str], verbose: bool) -> None:
    """Ask the OTHER tier for the media this one had nothing real for.

    The tier fallback was per GAME and all-or-nothing: `lb_everything` is
    reached only when ScreenScraper does not find the title at all, is
    unreachable, or has no credentials. So a game ScreenScraper knows keeps
    every gap ScreenScraper has, however complete LaunchBox's record is — and
    for `box-2D-back` the gap is not even empty, it is a chroma-key plate that
    every consumer has to recognise for itself.

    Measured on the reference box, on the LaunchBox index already sitting there
    (234 MB, no network, no quota): of the nine titles whose ScreenScraper back
    is a plate, **seven have a real `Box - Back`** — Pokémon Y, Inazuma Eleven,
    Mario Party DS, Mario & Sonic, Cars, Mario Party Superstars, Mario Party
    Jamboree. Only FIFA 19 and Breath of the Wild do not resolve.

    Deliberately narrow. It runs only for slugs that came back BLANK, never for
    ones that are merely deferred or that failed — a deferred media has a URL
    that works and a failure deserves a retry, neither is a hole in the record.
    It costs one index lookup, local, and one download per slug actually
    replaced; a game with nothing blank costs nothing at all. And it never
    touches `meta`: the text stays the tier's that answered, in one language,
    which is what `lang` in the manifest is a promise about.
    """
    blanks = [k for k, v in manifest["media"].items() if v.get("blank")]
    if not blanks or hit["source"] == "launchbox" or not gs.lb_index_ready():
        return
    other = lb_everything(parsed, cutoff)
    if not other:
        notes.append(f"launchbox: no match to replace {len(blanks)} blank media")
        return
    offered = {k: v for k, v in (other.get("media") or {}).items() if k in blanks}
    if not offered:
        notes.append(f"launchbox: nothing for {', '.join(sorted(blanks))}")
        return
    # LaunchBox's CDN limits nothing and this is never ScreenScraper's quota.
    got = _download_media(d, offered, 8, verbose, throttle=False)
    took = {k: v for k, v in got.items() if v.get("file")}
    manifest["media"] = {**manifest["media"], **took}
    if took:
        notes.append(f"launchbox: {', '.join(sorted(took))} taken from the "
                     f"second tier (screenscraper served a blank plate)")


def _download_media(d: Path, wanted: dict[str, dict], workers: int,
                    verbose: bool, throttle: bool = False) -> dict[str, dict]:
    """Download every media into the game's directory.

    The extension comes from the CONTENT (gamescrape.sniff_ext): ScreenScraper
    serves everything through mediaJeu.php, so trusting the URL produced
    unreadable .php files.

    `throttle` applies the 1.2 s limiter to downloads TOO. It only covered API
    calls: 25 media went out back to back with no wait on a 1-thread account.
    Skyscraper calls its limiter before every network request, media and videos
    included (src/screenscraper.cpp:76,334,357,380,403). The devid is shared —
    getting blacklisted takes down everyone using the same softname.
    """
    from concurrent.futures import ThreadPoolExecutor
    d.mkdir(parents=True, exist_ok=True)
    got: dict[str, dict] = {}

    def grab(url: str, dest: Path):
        if throttle:
            _ss_limiter.wait()
        return gs.fetch(url, dest, verbose)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(grab, info["url"], d / kind): (kind, info)
                   for kind, info in wanted.items()}
        for fut, (kind, info) in futures.items():
            # A media that fails must never take the other 24 with it.
            # gamescrape.fetch only catches URLError/OSError; an invalid URL
            # raises http.client.InvalidURL (a ValueError), which slipped past.
            try:
                written = fut.result()
            except Exception as e:                      # noqa: BLE001 — volontaire
                written, why = None, f"{type(e).__name__}: {e}"
            else:
                why = "empty or non-media response"
            if written and gs.looks_like_flat_plate(written):
                # A chroma-key plate is a valid file and a picture of nothing —
                # see `looks_like_flat_plate`. Recorded as `blank` rather than
                # kept: `failed` would mean "retry me", and this one will come
                # back identical every time. The URL stays so the state is
                # explicable, and `resolve()` reads this to know which slugs are
                # worth asking the other tier for.
                if verbose:
                    print(f"    · {kind} : flat plate, not a scan", file=sys.stderr)
                written.unlink(missing_ok=True)
                got[kind] = {"blank": True, "url": strip_creds(info["url"]),
                             **_descriptors(info)}
            elif written:
                # If sniff_ext changed the extension, the old file would be
                # orphaned and inflate cache_stats — remove it.
                for old in d.glob(f"{kind}.*"):
                    if old != written:
                        old.unlink(missing_ok=True)
                got[kind] = {"file": written.name,
                             "bytes": written.stat().st_size,
                             # GameCore: kept credential-free, so a file deleted
                             # from the cache costs one download to restore
                             # rather than a rescrape of the whole game.
                             "url": strip_creds(info["url"]),
                             **_descriptors(info)}
            else:
                # A failure is RECORDED, not hushed: without this the type
                # vanished from the manifest silently and was never retried.
                if verbose:
                    print(f"    · {kind} : {why}", file=sys.stderr)
                got[kind] = {"failed": why,
                             "at": datetime.now(timezone.utc).isoformat(),
                             **_descriptors(info)}
    return got


# GameCore: fetch one deferred media, on demand.
def fetch_media(system: str, filename: str, slug: str,
                verbose: bool = False) -> Path | None:
    """Local path to one media, downloading it if it was deferred.

    Returns None when the game has no such type, or when the download failed.
    The manifest is rewritten so the next call is a stat(), and a failure is
    recorded WITHOUT clearing the URL: a media that could not be fetched today
    must not force a full rescrape of the game tomorrow, it must simply be
    retried. That is the difference from the `failed` state written during a
    bulk download, which does mean "this entry is incomplete".
    """
    d = entry_dir(system, filename)
    manifest = load_cached(system, filename)
    info = ((manifest or {}).get("media") or {}).get(slug)
    if not info:
        return None

    # A blank is a decision already taken, not a media waiting to be fetched.
    # Its URL still works and still serves the same chroma-key plate, so going
    # back for it would download a picture of nothing on every call and hand it
    # over as a scan.
    if info.get("blank"):
        return None

    if info.get("file"):
        on_disk = d / Path(info["file"]).name
        if on_disk.is_file():
            return on_disk

    url = info.get("url")
    if not url:
        return None

    if "screenscraper" in url:
        _ss_limiter.wait()
    try:
        written = gs.fetch(with_creds(url), d / slug, verbose)
    except Exception as e:                      # noqa: BLE001 — same reason as
        written, why = None, f"{type(e).__name__}: {e}"   # in _download_media
    else:
        why = "empty or non-media response"

    media = dict(manifest["media"])
    if written:
        for old in d.glob(f"{slug}.*"):
            if old != written:
                old.unlink(missing_ok=True)
        media[slug] = {"file": written.name, "bytes": written.stat().st_size,
                       # The URL stays (credential-free): if the file is later
                       # deleted from the cache, this is what re-fetches it for
                       # one HTTP request instead of a whole rescrape.
                       "url": strip_creds(url), **_descriptors(info)}
    else:
        media[slug] = {**info, "last_error": why,
                       "at": datetime.now(timezone.utc).isoformat()}
    write_json(d / MANIFEST, {**manifest, "media": media})
    return written


def _descriptors(info: dict) -> dict:
    """What describes a media independently of the file obtained.

    These fields were computed then thrown away: the written manifest only kept
    `file`, `bytes` and `region`, so the category died on write and the frontend
    received 27 media with no way to tell which one is a box.
    """
    return {"region": info.get("region", ""),
            "category": info.get("category", "unknown"),
            "kind": info.get("kind", "image"),
            "ss_type": info.get("ss_type", "")}


# ── API HTTP ─────────────────────────────────────────────────────────────────

# Standard library, no framework: this server only exists for development and
# testing. Once integrated into GameCore, its backend will call resolve()
# directly from its own router — this HTTP layer goes away. And with no
# dependency, the script runs on a fresh box as is.

_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
         ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
         ".mp4": "video/mp4", ".webm": "video/webm", ".pdf": "application/pdf"}

# The `meta` keys the frontend can read without an existence check, whatever the
# source and however old the cached entry is.
META_DEFAULTS = {"title": "", "description": "", "developer": "", "publisher": "",
                 "released": "", "year": "", "genres": [], "players": "",
                 "rating": None, "rating_20": "", "rating_count": None,
                 "esrb": "", "classifications": {}, "coop": None, "platform": ""}

# slug → (category, kind), the reverse of gs.SS_MEDIA. Lets an entry cached before
# those fields existed be completed on read instead of rescraped.
SLUG_INFO = {slug: (cat, kind) for slug, cat, kind in gs.SS_MEDIA.values()}

# Values `matched_by` used to take. Kept only to normalise old cached entries —
# the manifest must not speak two languages depending on when it was written.
_MATCHED_BY_LEGACY = {
    "empreinte": "hash",
    "nom": "name",
    "empreinte (non vérifiable)": "hash (unverifiable)",
    "nom (empreinte envoyée, non confirmée)": "name (hash sent, not confirmed)",
}


def _normalise_media(slug: str, info: dict) -> dict:
    """Fill in the descriptors a manifest written earlier does not have."""
    if info.get("category") and info.get("kind"):
        return info
    category, kind = SLUG_INFO.get(slug) or gs.lb_media_info(slug)
    return {**info, "category": info.get("category") or category,
            "kind": info.get("kind") or kind,
            "ss_type": info.get("ss_type", "")}


def _public(manifest: dict, base_url: str) -> dict:
    """The manifest as the frontend sees it.

    ScreenScraper URLs NEVER leave here: they carry devid, devpassword, ssid
    and sspassword in their query. Every media is re-exposed through a URL of
    THIS service, which serves the already cached file.
    """
    import urllib.parse
    sysid = urllib.parse.quote(manifest["system"], safe="")
    fname = urllib.parse.quote(manifest["filename"], safe="")
    out = dict(manifest)
    # Constant shape, even for an entry written by an earlier version of the
    # service: a field added since must not force the frontend to tell old
    # manifests from recent ones, nor force a library rescrape just to make them
    # uniform (that would be quota burned on padding).
    if manifest.get("meta"):
        out["meta"] = {**META_DEFAULTS, **manifest["meta"]}
    if legacy := _MATCHED_BY_LEGACY.get(manifest.get("matched_by") or ""):
        out["matched_by"] = legacy
    out["media"] = {
        slug: {**{k: v for k, v in _normalise_media(slug, info).items()
                  if k != "url"},
               "url": f"{base_url}/api/games/{sysid}/{fname}/media/"
                      f"{urllib.parse.quote(slug, safe='')}"}
        for slug, info in (manifest.get("media") or {}).items()
    }
    return out


def serve(port: int, verbose: bool = False) -> None:
    import urllib.parse
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
        server_version = "gamemedia/1.0"

        def log_message(self, fmt, *a):
            if verbose:
                sys.stderr.write("  %s\n" % (fmt % a))

        def _json(self, code: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False, indent=2).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _file(self, path: Path) -> None:
            data = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type",
                             _MIME.get(path.suffix.lower(), "application/octet-stream"))
            self.send_header("Content-Length", str(len(data)))
            # A media's content never changes under a given key.
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:            # noqa: N802
            u = urllib.parse.urlsplit(self.path)
            parts = [urllib.parse.unquote(p) for p in u.path.strip("/").split("/")]
            q = urllib.parse.parse_qs(u.query)
            base = f"http://{self.headers.get('Host', f'127.0.0.1:{port}')}"

            if parts == ["api", "health"]:
                return self._json(200, {
                    "ok": True, "cache": str(CACHE_ROOT),
                    "screenscraper": bool(gs.ss_credentials()),
                    "ss_requests_left": ss_client.ss_remaining,
                    "launchbox_index": gs.lb_index_ready()})

            if parts == ["api", "cache"]:
                return self._json(200, cache_stats())

            # /api/games/<system>/<file…>            → manifest
            # /api/games/<system>/<file…>/media/<t>   → the media
            if len(parts) >= 4 and parts[:2] == ["api", "games"]:
                system = parts[2]
                if len(parts) >= 6 and parts[-2] == "media":
                    kind, filename = parts[-1], "/".join(parts[3:-2])
                    return self._serve_media(system, filename, kind)
                filename = "/".join(parts[3:])
                try:
                    m = resolve(system, filename,
                                refresh=q.get("refresh", ["0"])[0] not in ("0", "false"),
                                download=q.get("download", ["1"])[0] not in ("0", "false"),
                                verbose=verbose)
                except ValueError as e:
                    return self._json(400, {"error": str(e)})
                if not m.get("found"):
                    return self._json(404, {"error": "game not found",
                                            "notes": m.get("notes", [])})
                return self._json(200, _public(m, base))

            self._json(404, {"error": "route inconnue",
                             "routes": ["/api/health", "/api/cache",
                                        "/api/games/{system}/{file}",
                                        "/api/games/{system}/{file}/media/{type}"]})

        def _serve_media(self, system: str, filename: str, kind: str) -> None:
            try:
                d = entry_dir(system, filename)
            except ValueError as e:
                return self._json(400, {"error": str(e)})
            m = load_cached(system, filename)
            if not m:
                return self._json(404, {"error": "game not resolved yet — "
                                                 "call /api/games/… first"})
            info = (m.get("media") or {}).get(kind)
            if not info or not info.get("file"):
                return self._json(404, {"error": f"media '{kind}' missing",
                                        "available": sorted(m.get("media") or {})})
            # `kind` comes from the URL: never build a path with it. Re-read the
            # filename we wrote into the manifest ourselves, and re-check the
            # confinement before opening.
            path = (d / Path(info["file"]).name).resolve()
            if d.resolve() not in path.parents or not path.is_file():
                return self._json(404, {"error": "file missing from the cache"})
            self._file(path)

    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"gamemedia on http://127.0.0.1:{port}  (cache: {CACHE_ROOT})")
    print(f"  ScreenScraper: {'configured' if gs.ss_credentials() else 'absent'}"
          f"   LaunchBox: {'indexed' if gs.lb_index_ready() else 'absent'}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


def cache_stats() -> dict:
    entries, files, total = 0, 0, 0
    for m in CACHE_ROOT.glob(f"*/*/{MANIFEST}"):
        entries += 1
        for f in m.parent.iterdir():
            if f.is_file() and f.name != MANIFEST:
                files += 1
                total += f.stat().st_size
    return {"games": entries, "media_files": files, "bytes": total,
            "human": f"{total / 1048576:.1f} Mo"}


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(
        description="Every image and every piece of metadata for a game, "
                    "cached, served by an API — the frontend chooses.")
    p.add_argument("rom", nargs="?", help="ROM name or path")
    p.add_argument("-s", "--system", default="", help="console key (nds, psx…)")
    p.add_argument("--serve", type=int, metavar="PORT",
                   help="start the API on 127.0.0.1:PORT")
    p.add_argument("--refresh", action="store_true", help="ignore the cache")
    p.add_argument("--no-download", action="store_true",
                   help="resolve without downloading the media")
    p.add_argument("--cache-stats", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    if args.serve:
        serve(args.serve, args.verbose)
        return 0

    if args.cache_stats:
        st = cache_stats()
        print(f"  {st['games']} game(s), {st['media_files']} files, "
              f"{st['human']} under {CACHE_ROOT}")
        for m in sorted(CACHE_ROOT.glob(f"*/*/{MANIFEST}"))[:20]:
            d = json.loads(m.read_text("utf-8"))
            print(f"    {d.get('system','?'):10} {d.get('meta',{}).get('title','?')[:38]:38} "
                  f"{len(d.get('media',{})):2} media  [{d.get('source','?')}]")
        return 0

    if not args.rom:
        p.error("a ROM name is required, or --serve PORT, or --cache-stats")

    m = resolve(args.system, args.rom, refresh=args.refresh,
                download=not args.no_download, verbose=args.verbose)
    print(json.dumps(m, ensure_ascii=False, indent=2))
    return 0 if m.get("found") else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
