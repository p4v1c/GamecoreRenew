"""Game metadata (description, year, genres, players, rating) via TheGamesDB.

Same key as the cover scraper (THEGAMESDB_API_KEY). Results are cached on
disk under emu/metadata/<system>/<stem>.json — one network hit per game,
survives OTA updates (emu/ is excluded from the update rsync). Misses are
cached too (found:false + TTL) so the library stays fast without a key.

The search name prefers the title embedded in the game (PARAM.SFO for
PS3/PS4/PSP) over the filename — exact titles give exact matches.
"""
import json
import logging
import time
from pathlib import Path

import httpx

from ..config import GAMECORE_ROOT, THEGAMESDB_API_KEY, resolve_path
from . import local_media
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
    # Same confinement as cover_pipeline._rom_in_root: `filename` comes from a
    # {filename:path} route parameter, so it can carry slashes and '..'. Nothing
    # here leaks a file's contents, but the invariant is "a ROM path is checked
    # against its root", and it should hold everywhere rather than case by case.
    roms_root = resolve_path(system.get("romsPath", ""))
    if roms_root:
        try:
            rom = (roms_root / filename).resolve()
            rom.relative_to(roms_root.resolve())
        except (ValueError, OSError):
            rom = None
        if rom is not None and rom.exists():
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
