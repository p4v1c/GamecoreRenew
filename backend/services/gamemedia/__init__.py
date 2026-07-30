"""gamemedia — everything known about a game, from one call.

`gamescrape.py` and `gamemedia.py` are vendored here as they are (see
VENDORED.md). This module is the only thing the rest of the backend imports:
it points their caches at the box's own directories, adapts the synchronous
API to the async one the routers use, and translates a manifest into the
shapes GameCore already speaks.

Two sources sit behind it, in this order:

  1. ScreenScraper — by file hash (certain even for a misnamed ROM), by the
     PARAM.SFO title for PS3/PS4/PSP directories. Needs a developer account
     AND a member account; without them this tier is simply absent.
  2. LaunchBox — the official dump indexed into SQLite, offline, no account.
     Needs `gamescrape.py --refresh` to have been run once (234 MB).

With neither configured, `available()` is False and every entry point here is
a no-op — the cover and metadata pipelines then behave exactly as they did
before this service existed. That is deliberate: an install that never
configures a ScreenScraper account must not notice the difference.

What it adds over the existing pipeline: 54 media types per game instead of
one cover — 3D box, gameplay screenshot, clear logo, video, ready-made mixes —
so a theme can be built on something other than a flat jacket.
"""
import asyncio
import logging
import re
from pathlib import Path

from ...config import GAMECORE_ROOT
from . import gamemedia as gm
from . import gamescrape as gs

log = logging.getLogger(__name__)

# ── Where the caches live ────────────────────────────────────────────────────
# Under emu/, with the covers and the ROMs: that directory is excluded from the
# OTA rsync (update/linux.sh) and from git, so a manifest, a 234 MB index and
# 40 MB of artwork survive every update and never reach a commit. Upstream
# defaults to ~/.cache, which the backend's systemd unit would resolve against
# whichever HOME it happens to have.
CACHE_DIR = GAMECORE_ROOT / "emu" / "gamemedia"
INDEX_DIR = GAMECORE_ROOT / "emu" / "gamescrape"

gm.CACHE_ROOT = CACHE_DIR
gm.SYSTEMS_CACHE = CACHE_DIR / "systems.json"        # derived at import time
gs.CACHE_DIR = INDEX_DIR
gs.DB_PATH = INDEX_DIR / "launchbox.sqlite"          # idem

# The softname identifies this software to ScreenScraper. It is tied to the
# devid granted on their forum, so it belongs to GameCore, not to the script.
gs.SS_SOFTNAME = "gamecore"

# ── Media policy ─────────────────────────────────────────────────────────────
# What is downloaded during a scrape. Everything else the game has is recorded
# with its URL and fetched the first time something asks for it (see
# gamemedia.fetch_media).
#
# One image per game is what the default theme displays and what the previous
# pipeline downloaded, so that is what a scrape costs. Fetching all 28 media a
# PS3 game carries would be ~34 s per title at the 1.2 s ScreenScraper demands
# — for artwork no shipped theme reads.
EAGER_MEDIA = {"box-front"}

# The cover pipeline asks for these in order. box-front is the jacket every
# current theme draws; the rest are there so a system that has no flat box art
# still yields something rectangular rather than nothing.
COVER_ORDER = ("box-front", "box-scan", "box-3d", "mix-rbv2", "mix-rbv1",
               "screenshot-gameplay")

# A slug arrives from a URL and becomes a filename inside the cache directory,
# so it is checked before anything opens it — the same rule as romsPath
# confinement in cover_pipeline. A real slug is what gamescrape.slug() produces:
# lowercase, digits, dashes. That leaves no room for a separator or a '..'.
#
# It is deliberately not checked against the SS table: LaunchBox names its own
# types (`cart-3d`, `advertisement-flyer-front`), and a 55th ScreenScraper type
# would be rejected on the day it appears. The real gate is the manifest —
# fetch_media only serves a slug the scrape actually recorded for this game.
_SLUG_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")

# ── Concurrency ──────────────────────────────────────────────────────────────
# gamemedia is synchronous (urllib + a thread pool), the backend is async, so
# every call runs in a worker thread. The lock is not about thread safety —
# gamescrape's rate limiter already holds one — it is about the quota: prefetch
# warms three games at a time, and three concurrent scrapes means three
# jeuInfos in flight ignoring each other's 1.2 s. One scrape at a time, and the
# limiter's spacing is the real spacing.
_scrape_lock = asyncio.Lock()


def available() -> bool:
    """True when at least one source can answer. Cheap: no network."""
    try:
        return bool(gs.ss_credentials()) or gs.lb_index_ready()
    except Exception:  # noqa: BLE001 — a broken index must not break a request
        log.debug("gamemedia: availability check failed", exc_info=True)
        return False


def status() -> dict:
    """What is configured, for /api/sysinfo and the installer's own checks."""
    return {
        "available": available(),
        "screenscraper": bool(gs.ss_credentials()),
        "launchbox_index": gs.lb_index_ready(),
        "cache": str(CACHE_DIR),
    }


def cached(system_id: str, filename: str) -> dict | None:
    """The manifest already on disk, or None. No network, no thread."""
    try:
        return gm.load_cached(system_id, filename)
    except Exception:  # noqa: BLE001
        return None


async def resolve(system_id: str, target: Path | str, *,
                  only: set[str] | None = None,
                  refresh: bool = False) -> dict | None:
    """Scrape (or read back) one game's manifest.

    `target` should be the ROM's absolute path when it exists on disk: that is
    what lets the hash and the PARAM.SFO be read, and a hash match is certain
    where a name match is a guess.

    None means *this tier could not be asked at all* — nothing configured, not
    a game, or the scraper raised. A manifest with `found: false` means it was
    asked and answered; the caller still has to read `unreachable` before
    concluding the game does not exist, because a spent quota and an empty
    database both arrive as `found: false`.
    """
    if not available():
        return None

    name = str(target)
    if gm.looks_like_game(Path(name).name):
        return None  # .gitkeep, saves, covers/ — not a game, don't ask about it

    if only is None:
        only = EAGER_MEDIA

    def work() -> dict:
        return gm.resolve(system_id, name, refresh=refresh, only=only)

    async with _scrape_lock:
        try:
            return await asyncio.to_thread(work)
        except Exception:  # noqa: BLE001 — a scraper must never 500 a request
            log.warning("gamemedia: resolve failed for %s/%s", system_id, name,
                        exc_info=True)
            return None


async def media_file(system_id: str, filename: str, slug: str) -> Path | None:
    """Local path to one media type, fetching it if it was deferred."""
    if not _SLUG_RE.match(slug or ""):
        return None

    def work() -> Path | None:
        return gm.fetch_media(system_id, filename, slug)

    async with _scrape_lock:
        try:
            return await asyncio.to_thread(work)
        except Exception:  # noqa: BLE001
            log.warning("gamemedia: fetching %s for %s/%s failed", slug,
                        system_id, filename, exc_info=True)
            return None


def media_index(manifest: dict) -> dict[str, dict]:
    """`media` as the API exposes it: descriptors only, never the URL.

    The stored URL is credential-free but still points at ScreenScraper; the
    frontend has no business calling it directly, and re-exposing it would
    hand the box's quota to any page that can reach the backend.
    """
    out: dict[str, dict] = {}
    for slug, info in (manifest.get("media") or {}).items():
        info = gm._normalise_media(slug, info)
        out[slug] = {
            "category": info.get("category", "unknown"),
            "kind": info.get("kind", "image"),
            "region": info.get("region", ""),
            # Downloaded already, or waiting for the first request. A theme can
            # use this to prefer what is instant over what costs a round trip.
            "cached": bool(info.get("file")),
        }
    return out


def _players_count(raw) -> int:
    """"1-3" → 3, "4" → 4, "" → 0.

    GameCore's GameMeta.players is a number and the panel renders "N players"
    from it. ScreenScraper writes a range, LaunchBox a maximum; the useful
    number in both is the largest one.
    """
    digits = [int(n) for n in str(raw or "").replace("+", " ").split() if n.isdigit()]
    if digits:
        return max(digits)
    parts = [p for p in str(raw or "").replace("-", " ").split() if p.isdigit()]
    return max((int(p) for p in parts), default=0)


def to_game_meta(manifest: dict) -> dict:
    """A manifest as `GameMeta`, the shape /api/metadata has always returned.

    The seven original keys keep their exact meaning and type, because
    GameMetaPanel and every theme already read them. `rating` is the age
    rating, a string, as TheGamesDB returned it — the 0–1 score arrives beside
    it as `score`, on a new key, rather than changing what `rating` means.
    """
    meta = manifest.get("meta") or {}
    classifications = meta.get("classifications") or {}
    return {
        "found": True,
        "title": meta.get("title") or "",
        "description": meta.get("description") or "",
        "year": meta.get("year") or "",
        "genres": list(meta.get("genres") or []),
        "players": _players_count(meta.get("players")),
        "rating": meta.get("esrb") or classifications.get("PEGI") or "",
        # ── added by gamemedia, absent from the TheGamesDB path ──
        "source": manifest.get("source") or "",
        "developer": meta.get("developer") or "",
        "publisher": meta.get("publisher") or "",
        "released": meta.get("released") or "",
        "players_label": str(meta.get("players") or ""),
        "score": meta.get("rating"),
        "score_count": meta.get("rating_count"),
        "classifications": classifications,
        "platform": meta.get("platform") or "",
    }
