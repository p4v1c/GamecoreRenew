"""Game metadata (description, year, genres, players, rating).

Two sources, in this order:

  1. gamemedia — ScreenScraper, then the offline LaunchBox index. It answers in
     French when it can, gives the developer, the publisher, the age ratings
     and a normalised score, and needs no network at all on the LaunchBox side.
     Its manifest is already on disk when the cover pipeline has run, so this
     usually costs nothing.
  2. TheGamesDB — what was here before, unchanged, and still the only source on
     a box with no ScreenScraper account and no index.

Results are cached on disk under emu/metadata/<system>/<stem>.json — one
network hit per game, survives OTA updates (emu/ is excluded from the update
rsync). Misses are cached too (found:false + TTL) so the library stays fast
without a key.

The search name prefers the title embedded in the game (PARAM.SFO for
PS3/PS4/PSP) over the filename — exact titles give exact matches.

**The seven keys the API has always returned keep their name, type and
meaning**: `found`, `title`, `description`, `year`, `genres`, `players`
(a number), `rating` (the age rating, a string). GameMetaPanel and every theme
already read those. What gamemedia adds — developer, publisher, the 0–1 score,
the full classifications table — arrives on new keys beside them.
"""
import json
import logging
import time
from pathlib import Path

import httpx

from ..config import GAMECORE_ROOT, THEGAMESDB_API_KEY
from ..utils import rom_in_root
from . import gamemedia, local_media
from .rom_scanner import clean_name
from .scraper import TGDB_PLATFORM_MAP, Unreachable

log = logging.getLogger(__name__)

METADATA_DIR = GAMECORE_ROOT / "emu" / "metadata"
_MISS_TTL = 7 * 24 * 3600

_TGDB_SEARCH = "https://api.thegamesdb.net/v1/Games/ByGameName"
_TGDB_GENRES = "https://api.thegamesdb.net/v1/Genres"

# genre id → name, fetched once per process (the list is tiny and static)
_genres: dict[str, str] | None = None


async def _genre_names(client: httpx.AsyncClient) -> dict[str, str]:
    global _genres
    if _genres is None:
        try:
            r = await client.get(_TGDB_GENRES, params={"apikey": THEGAMESDB_API_KEY})
            data = r.json().get("data", {}).get("genres", {})
            _genres = {str(k): v.get("name", "") for k, v in data.items()}
        except Exception:
            return {}  # transient failure — retry on next call
    return _genres


def _search_name(system: dict, filename: str) -> str:
    # utils.rom_in_root does the confinement: `filename` comes from a
    # {filename:path} route parameter, so it can carry slashes and '..'. Nothing
    # here leaks a file's contents, but the invariant is "a ROM path is checked
    # against its root", and it should hold everywhere rather than case by case.
    rom = rom_in_root(system, filename)
    if rom is not None:
        title = local_media.get_title(system["id"], rom)
        if title:
            return title
    return clean_name(filename)


async def resolve(system: dict, filename: str) -> dict | None:
    """Metadata dict for one game, or None. Disk-cached, negative-cached."""
    sid = system["id"].lower()
    cache_dir = METADATA_DIR / sid
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / f"{Path(filename).stem}.json"

    if cache.is_file():
        try:
            data = json.loads(cache.read_text())
            if data.get("found"):
                return data
            if time.time() - cache.stat().st_mtime < _MISS_TTL:
                return None
        except (json.JSONDecodeError, OSError):
            pass

    # ── 1. gamemedia ─────────────────────────────────────────────────────────
    # Ahead of TheGamesDB because it identifies the game by hash rather than by
    # name, and because it is the only one of the two that answers with no key
    # at all (the LaunchBox index is offline). Inert when neither source is
    # configured — `available()` is then False and this block does nothing.
    if gamemedia.available():
        rom = rom_in_root(system, filename)
        manifest = await gamemedia.resolve(sid, str(rom) if rom else filename)
        if manifest is not None and manifest.get("found"):
            data = gamemedia.to_game_meta(manifest)
            cache.write_text(json.dumps(data, ensure_ascii=False))
            return data
        # A `found: false` here is NOT written down. gamemedia already caches
        # its own negative, and only when the tiers really answered; copying it
        # into a second cache with a 7-day TTL would outlive the retry it does
        # for free the day credentials appear or the quota resets.

    platform_id = TGDB_PLATFORM_MAP.get(sid)
    if not THEGAMESDB_API_KEY or not platform_id:
        return None  # not worth a miss file — config, not data

    data = None
    try:
        data = await _fetch_tgdb(platform_id, _search_name(system, filename))
    except Unreachable as e:
        log.info("metadata: lookup for %s/%s did not complete (%s)", sid, filename, e)
        return None  # transient — don't cache
    except Exception:
        log.warning("metadata: lookup failed for %s/%s", sid, filename, exc_info=True)
        return None  # transient — don't cache

    if data:
        cache.write_text(json.dumps(data, ensure_ascii=False))
        return data
    # Only reached when TheGamesDB answered and had nothing. _fetch_tgdb raises
    # on a non-200, so an exhausted quota is no longer written down as "this
    # game has no metadata" for the next seven days.
    cache.write_text(json.dumps({"found": False}))
    return None


async def _fetch_tgdb(platform_id: int, name: str) -> dict | None:
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        r = await client.get(_TGDB_SEARCH, params={
            "apikey": THEGAMESDB_API_KEY,
            "name": name,
            "filter[platform]": platform_id,
            "fields": "overview,players,rating,genres",
        })
        if r.status_code != 200:
            # A 429 body has no "games" key either, so without this the caller
            # saw an empty result and cached it as a definitive miss.
            raise Unreachable(f"TheGamesDB answered {r.status_code}")
        games = r.json().get("data", {}).get("games", [])
        if not games:
            return None
        g = games[0]

        genre_ids = g.get("genres") or []
        names = await _genre_names(client)
        genres = [names[str(i)] for i in genre_ids if str(i) in names]

        release = g.get("release_date") or ""
        return {
            "found": True,
            "title": g.get("game_title", ""),
            "description": g.get("overview") or "",
            "year": release[:4] if len(release) >= 4 else "",
            "genres": genres,
            "players": g.get("players") or 0,
            "rating": g.get("rating") or "",
        }
