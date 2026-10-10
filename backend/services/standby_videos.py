"""Game videos for the standby TV: which to download, how much, which to drop.

The CRT standby plays each game's ScreenScraper clip on the TV in the room.
Clips are 5 to 20 MB, so they are never part of the warming pass
(`gamemedia.WARM_MEDIA` leaves them out on purpose); this worker fetches them
on its own terms:

- **Order**: the games people play most and most recently first
  (`standby_picks.rank`), then the rest.
- **Source**: `video-normalized`, else `video`, through
  `gamemedia.media_file`: the same lock and ScreenScraper pacing as every other
  media. It never scrapes; a game without a manifest yet is skipped until the
  cover pass has made one.
- **Never during a game**: it waits on `prefetch.wait_until_nobody_is_playing`
  before every download.
- **Disk cap**: `GAMECORE_STANDBY_VIDEO_CAP_GB` (default 5). Over it, the least
  valuable clips go first; orphans (ROM deleted) before anything. 0 removes
  every clip and fetches none.
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
from pathlib import Path
from urllib.parse import quote

from . import gamemedia, prefetch, standby_picks

log = logging.getLogger(__name__)

CAP_ENV = "GAMECORE_STANDBY_VIDEO_CAP_GB"
DEFAULT_CAP_GB = 5.0
VIDEO_TYPES = ("video-normalized", "video")
STILL_TYPES = ("screenshot-gameplay", "screenshot-game-title")

_START_DELAY = 180          # after the cover sweep has had its turn
_RESWEEP_SECS = 3 * 3600    # playtime moves; the ranking with it
_MAX_STILLS = 40            # enough for an evening without repeats


def cap_bytes() -> int:
    """The disk budget for clips, from the environment. Bad values → default."""
    raw = os.environ.get(CAP_ENV, "").strip()
    try:
        gb = float(raw) if raw else DEFAULT_CAP_GB
    except ValueError:
        log.warning("standby videos: %s=%r is not a number, using %s GB",
                    CAP_ENV, raw, DEFAULT_CAP_GB)
        gb = DEFAULT_CAP_GB
    return max(0, int(gb * 1024 ** 3))


# ── What is on disk ─────────────────────────────────────────────────────────

def _file_of(manifest: dict | None, slugs: tuple[str, ...], entry: Path) -> tuple[str, Path] | None:
    """The first of `slugs` downloaded for this game, as (slug, path)."""
    media = (manifest or {}).get("media") or {}
    for slug in slugs:
        info = media.get(slug) or {}
        if info.get("file") and not info.get("blank"):
            path = entry / Path(info["file"]).name
            if path.is_file():
                return slug, path
    return None


def _offered(manifest: dict | None) -> str | None:
    """The video type this game's manifest lists, preferred first."""
    media = (manifest or {}).get("media") or {}
    for slug in VIDEO_TYPES:
        info = media.get(slug)
        if info and not info.get("blank") and (info.get("url") or info.get("file")):
            return slug
    return None


def _entry(game: dict) -> Path:
    return gamemedia.gm.entry_dir(game["system_id"], game["target"])


def clips_on_disk() -> dict[Path, int]:
    """Every downloaded clip in the media cache, path → bytes, orphans included."""
    root = Path(gamemedia.gm.CACHE_ROOT)
    found: dict[Path, int] = {}
    for slug in VIDEO_TYPES:
        for path in root.glob(f"*/*/{slug}.*"):
            if path.suffix in (".tmp", ".part"):
                continue
            try:
                found[path.resolve()] = path.stat().st_size
            except OSError:
                continue
    return found


# ── The cap ─────────────────────────────────────────────────────────────────

def plan_eviction(clips: dict[Path, int], rank_of_dir: dict[Path, int], cap: int) -> list[Path]:
    """Which clips to delete so the rest fit in `cap`. Pure.

    `rank_of_dir` maps a game's cache directory to its rank (0 = most
    valuable). A clip whose game is not in it (ROM deleted, disk unplugged)
    ranks last: kept while there is room, dropped first when there is not.
    """
    last = len(rank_of_dir)
    by_value = sorted(clips, key=lambda p: (rank_of_dir.get(p.parent, last), str(p)))
    kept, evict = 0, []
    for path in by_value:
        if kept + clips[path] <= cap:
            kept += clips[path]
        else:
            evict.append(path)
    return evict


async def _evict(paths: list[Path]) -> int:
    freed = 0
    for path in paths:
        try:
            freed += await gamemedia.drop_file(path)
        except Exception:  # noqa: BLE001 — one stuck file must not stop the rest
            log.warning("standby videos: could not drop %s", path, exc_info=True)
    return freed


# ── The sweep ───────────────────────────────────────────────────────────────

async def _ranked() -> list[dict]:
    games = await asyncio.to_thread(standby_picks.library)
    return standby_picks.rank(games, await standby_picks.played_rows())


def _todo(games: list[dict]) -> list[tuple[dict, str, int]]:
    """Games with a clip to fetch, in value order: (game, type, known size or 0).

    The size is known when the clip was downloaded once and evicted since.
    """
    todo = []
    for g in games:
        manifest = gamemedia.cached(g["system_id"], g["target"])
        if not _file_of(manifest, VIDEO_TYPES, _entry(g)) and (slug := _offered(manifest)):
            todo.append((g, slug, int(manifest["media"][slug].get("bytes") or 0)))
    return todo


async def sweep() -> dict:
    """One pass: trim to the cap, then download in value order until it is full."""
    cap = cap_bytes()
    games = await _ranked()
    rank_of_dir = {_entry(g): i for i, g in enumerate(games)}
    clips = clips_on_disk()
    evicted = plan_eviction(clips, rank_of_dir, cap)
    await _evict(evicted)
    for p in evicted:
        clips.pop(p, None)
    fetched = 0

    for game, slug, known in (_todo(games) if gamemedia.available() else []):
        used = sum(clips.values())
        if used >= cap:
            break
        if used + known > cap:
            continue    # evicted earlier for being too big; a smaller one may fit
        await prefetch.wait_until_nobody_is_playing()
        path = await gamemedia.media_file(game["system_id"], game["target"], slug)
        if not path:
            continue
        path = path.resolve()
        fetched += 1
        clips[path] = path.stat().st_size
        over = plan_eviction(clips, rank_of_dir, cap)
        if over:
            await _evict(over)
            for p in over:
                clips.pop(p, None)
            evicted += over
            if path in over:
                break   # the most valuable game left does not fit
    used = sum(clips.values())
    log.info("standby videos: %d fetched, %d evicted, %.2f of %.2f GB",
             fetched, len(evicted), used / 1024 ** 3, cap / 1024 ** 3)
    return {"cap": cap, "used": used, "fetched": fetched, "evicted": len(evicted)}


async def run() -> None:
    """The worker: one sweep after boot, then one every few hours."""
    await asyncio.sleep(_START_DELAY)
    while True:
        try:
            await prefetch.wait_until_nobody_is_playing()
            await sweep()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("standby videos: sweep failed")
        await asyncio.sleep(_RESWEEP_SECS)


# ── The playlist ────────────────────────────────────────────────────────────

def _entry_json(game: dict, slug: str) -> dict:
    return {
        "system_id": game["system_id"],
        "filename": game["filename"],
        "display_name": game["display_name"],
        "system_name": game["system_name"],
        "last_played": game.get("last_played"),
        "media_type": slug,
        "url": f"/api/media/{quote(game['system_id'])}/{quote(game['filename'])}/media/{slug}",
    }


async def playlist(favourites: set[tuple[str, str]] = frozenset(),
                   rng: random.Random | None = None) -> dict:
    """Clips already on disk, valuable ones tending first; stills for the rest.

    `stills` are screenshots of games without a clip, so a box with no video
    source still has something on the TV. Nothing here touches the network.
    """
    rng = rng or random.Random()
    videos, stills = [], []
    for g in await _ranked():
        manifest = gamemedia.cached(g["system_id"], g["target"])
        if not manifest:
            continue
        entry = _entry(g)
        if have := _file_of(manifest, VIDEO_TYPES, entry):
            videos.append({**g, "slug": have[0]})
        elif len(stills) < _MAX_STILLS and (have := _file_of(manifest, STILL_TYPES, entry)):
            stills.append({**g, "slug": have[0]})
    return {
        "videos": [_entry_json(g, g["slug"]) for g in standby_picks.weighted_shuffle(videos, rng, favourites)],
        "stills": [_entry_json(g, g["slug"]) for g in standby_picks.weighted_shuffle(stills, rng, favourites)],
    }
