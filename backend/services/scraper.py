"""Async cover scraper — libretro thumbnails CDN with TheGamesDB fallback."""
import logging
import re
import time
from pathlib import Path
from urllib.parse import quote, unquote

import httpx

from ..config import THEGAMESDB_API_KEY
from ..utils import TAG_RE
from .paths import covers_dir

COVERS_DIR = covers_dir()

log = logging.getLogger(__name__)


class Unreachable(Exception):
    """No lookup actually completed — nothing answered, or what answered was
    not an answer about this game (429, 403, 5xx).

    The distinction exists because callers cache the negative result. "Nobody
    has a cover for this game" is worth remembering for a week; "the Wi-Fi was
    not configured yet" is not. Collapsing the two is what left a brand-new box
    with no artwork at all: prefetch starts 15 s after boot, before the owner
    has been able to join a network from the very interface it is filling, so
    the first run wrote a miss marker for every single game.
    """


# Statuses that say "ask again later", not "no such thing". Anything >= 500 is
# treated the same way.
_TRANSIENT_STATUS = frozenset({403, 408, 425, 429})


def _is_transient(status: int) -> bool:
    return status in _TRANSIENT_STATUS or status >= 500

# ── platform ids, from the catalogue ────────────────────────────────────────
# These two maps were hand-written here, and they had already drifted from the
# rest of the project: `melonds` listed two libretro systems where
# systems.json.dist listed one, and `xenia` was missing from PLATFORM_MAP
# entirely — so the libretro cover fallback never fired for the Xbox 360 even
# though systems.json declared its system. One source now: catalog/<id>/pack.json.
#
# The extras below are ids with no pack: other emulators gamescrape can be
# pointed at by hand. They are kept, and kept separate, so it stays obvious
# which entries are catalogue-backed and which are not.
_EXTRA_LIBRETRO: dict[str, list[str]] = {
    "retroarch": ["Nintendo - Super Nintendo Entertainment System"],
    "snes9x":    ["Nintendo - Super Nintendo Entertainment System"],
    "nestopia":  ["Nintendo - Nintendo Entertainment System"],
    "mame":      ["MAME"],
}


def _catalog_scraper_maps() -> tuple[dict[str, int], dict[str, list[str]]]:
    """(tgdb ids, libretro systems) declared by the packs.

    Never fatal: a backend that cannot read the catalogue must still scrape
    with whatever it knows, not fail to import.
    """
    tgdb: dict[str, int] = {}
    libretro: dict[str, list[str]] = {}
    try:
        from .catalog import load_catalog
        for pack in load_catalog().values():
            sc = pack.data.get("scraper") or {}
            if (tid := sc.get("tgdbId")) is not None:
                tgdb[pack.id] = tid
            if names := sc.get("libretro"):
                libretro[pack.id] = list(names)
    except Exception:
        log.warning("scraper: catalogue unreadable — platform ids limited to "
                    "the built-in extras", exc_info=True)
    return tgdb, libretro


TGDB_PLATFORM_MAP, _CATALOG_LIBRETRO = _catalog_scraper_maps()

_TGDB_SEARCH  = "https://api.thegamesdb.net/v1/Games/ByGameName"
_TGDB_IMAGES  = "https://api.thegamesdb.net/v1/Games/Images"
_TGDB_IMG_CDN = "https://cdn.thegamesdb.net/images/medium/"

PLATFORM_MAP: dict[str, list[str]] = {**_EXTRA_LIBRETRO, **_CATALOG_LIBRETRO}

_LIBRETRO_BASE = "https://thumbnails.libretro.com/{system}/Named_Boxarts/{name}.png"
_LIBRETRO_INDEX = "https://thumbnails.libretro.com/{system}/Named_Boxarts/"
_LANG_RE = re.compile(r"\(((?:En|Fr|De|Es|It|Ja|Ko|Ru|Pt){2,})\)")
_INDEX_HREF_RE = re.compile(r'href="([^"]+\.png)"')

# Cache for directory listings: { "Nintendo - Nintendo 3DS": (fetched_at, ["Game (USA).png", ...]) }
# TTL so a long-lived backend eventually sees new CDN entries.
_INDEX_CACHE: dict[str, tuple[float, list[str]]] = {}
_INDEX_TTL = 24 * 3600


def _normalize(name: str) -> str:
    """Lowercase alphanumeric only for fuzzy matching."""
    return re.sub(r'[^a-z0-9]', '', name.lower())


def _name_variants(base: str) -> list[str]:
    variants = [base]
    # Try underscore to space (common for sanitized files)
    if "_" in base:
        variants.append(base.replace("_", " "))

    clean = TAG_RE.sub("", base).strip()
    if clean and clean != base:
        variants.append(clean)

    m = _LANG_RE.search(base)
    if m:
        parts = [m.group(1)[i:i+2] for i in range(0, len(m.group(1)), 2)]
        normalized = base.replace(m.group(0), f"({','.join(parts)})")
        if normalized not in variants:
            variants.append(normalized)
    return variants


async def _get_index(client: httpx.AsyncClient, system_name: str) -> tuple[list[str], bool, bool]:
    """Fetch and cache the Libretro directory listing.

    Returns (files, reached, transient). The two flags are what let the caller
    tell "this game is not in the index" from "the index never loaded" — an
    empty list means both, and only the first may be cached as a miss.
    """
    cached = _INDEX_CACHE.get(system_name)
    if cached and time.time() - cached[0] < _INDEX_TTL:
        return cached[1], True, False

    url = _LIBRETRO_INDEX.format(system=quote(system_name))
    try:
        r = await client.get(url)
        if r.status_code == 200:
            # Extract filenames from hrefs, unquoting them
            files = [unquote(f) for f in _INDEX_HREF_RE.findall(r.text)]
            _INDEX_CACHE[system_name] = (time.time(), files)
            return files, True, False
        # Refresh failed — keep serving the stale listing rather than nothing
        return (cached[1] if cached else []), True, _is_transient(r.status_code)
    except Exception:
        return (cached[1] if cached else []), False, False


async def fetch_cover(rom_path: str, system_id: str, dest: Path | None = None) -> str | None:
    """Return local path to cover image, downloading if necessary.

    None means the lookups completed and nobody has this cover. Raises
    Unreachable when they did not complete — see that class. dest overrides the
    target file (used by cover_pipeline's per-system cache).
    """
    base = Path(rom_path).stem
    if dest is None:
        COVERS_DIR.mkdir(parents=True, exist_ok=True)
        dest = COVERS_DIR / f"{base}.png"
    cached = dest
    if cached.exists():
        return str(cached)

    platforms = PLATFORM_MAP.get(system_id.lower(), [])
    if not platforms:
        return None

    variants = _name_variants(base)
    norm_base = _normalize(base)
    # Normalized clean name (no region/language tags) for cross-region fallback
    clean_base = TAG_RE.sub("", base).strip()
    norm_clean = _normalize(clean_base) if clean_base != base else None

    # Did anything answer at all, and did anything answer "later"? Together they
    # decide whether a None from this function may be cached as a real miss.
    reached = False
    transient = False

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        for platform in platforms:
            # 1. Try heuristics first (fast, no index fetch needed if match)
            for name in variants:
                url = _LIBRETRO_BASE.format(
                    system=quote(platform, safe=""),
                    name=quote(name, safe=""),
                )
                try:
                    r = await client.head(url)
                    reached = True
                    if _is_transient(r.status_code):
                        transient = True
                        continue
                    if r.status_code == 200:
                        r = await client.get(url)
                        cached.write_bytes(r.content)
                        return str(cached)
                except httpx.RequestError:
                    continue

            # 2. Index-based fuzzy matching — exact norm match, then prefix, then cross-region
            index, idx_reached, idx_transient = await _get_index(client, platform)
            reached = reached or idx_reached
            transient = transient or idx_transient
            if not index:
                continue

            best_match = None
            prefix_matches: list[str] = []
            cross_region_matches: list[str] = []

            for remote_file in index:
                remote_name = Path(remote_file).stem
                norm_remote = _normalize(remote_name)

                if norm_remote == norm_base:
                    best_match = remote_name
                    break
                if norm_remote.startswith(norm_base):
                    prefix_matches.append(remote_name)
                # Cross-region: ROM stripped of tags matches the CDN entry stripped of tags
                elif norm_clean and _normalize(TAG_RE.sub("", remote_name).strip()) == norm_clean:
                    cross_region_matches.append(remote_name)

            if not best_match and prefix_matches:
                prefix_matches.sort(key=len)
                best_match = prefix_matches[0]

            if not best_match and cross_region_matches:
                # Prefer entries with recognisable region order: USA > Europe > Japan > others
                def _region_rank(n: str) -> int:
                    nl = n.lower()
                    if "usa" in nl or "world" in nl: return 0
                    if "europe" in nl or "eur" in nl: return 1
                    if "japan" in nl or "jpn" in nl: return 2
                    return 3
                cross_region_matches.sort(key=_region_rank)
                best_match = cross_region_matches[0]

            if best_match:
                url = _LIBRETRO_BASE.format(
                    system=quote(platform, safe=""),
                    name=quote(best_match, safe=""),
                )
                try:
                    r = await client.get(url)
                    reached = True
                    if _is_transient(r.status_code):
                        transient = True
                    elif r.status_code == 200:
                        cached.write_bytes(r.content)
                        return str(cached)
                except httpx.RequestError:
                    continue

    # ── Fallback: TheGamesDB ──────────────────────────────────────────────────
    if THEGAMESDB_API_KEY:
        # Raises Unreachable itself if it could not get an answer.
        result = await _fetch_tgdb_cover(base, system_id, cached)
        if result:
            return result
        reached = True

    if not reached or transient:
        raise Unreachable(
            f"no cover lookup completed for {base!r} "
            f"(reached={reached}, transient={transient})")
    return None


async def _fetch_tgdb_cover(name: str, system_id: str, dest: Path) -> str | None:
    """Try TheGamesDB — local path on success, None if it has no cover for this game.

    Raises Unreachable if the API did not answer, or answered with a quota or
    server error. That used to be swallowed by a bare `except Exception: return
    None`, which the caller could not tell from a genuine "not found" — so a
    day of exhausted quota was recorded as "this game has no cover" for a week.
    """
    platform_id = TGDB_PLATFORM_MAP.get(system_id.lower())
    if not platform_id:
        return None

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        try:
            r = await client.get(_TGDB_SEARCH, params={
                "apikey": THEGAMESDB_API_KEY,
                "name": name,
                "filter[platform]": platform_id,
                "fields": "game_title",
            })
            if r.status_code != 200:
                raise Unreachable(f"TheGamesDB search answered {r.status_code}")
            games = r.json().get("data", {}).get("games", [])
            if not games:
                return None
            game_id = games[0]["id"]

            r = await client.get(_TGDB_IMAGES, params={
                "apikey": THEGAMESDB_API_KEY,
                "games_id": game_id,
                "filter[type]": "boxart",
            })
            if r.status_code != 200:
                raise Unreachable(f"TheGamesDB images answered {r.status_code}")
            data = r.json().get("data", {})
            images = data.get("images", {}).get(str(game_id), [])
            front = next((img for img in images if img.get("side") == "front"), None)
            if not front and images:
                front = images[0]
            if not front:
                return None

            img_url = _TGDB_IMG_CDN + front["filename"]
            r = await client.get(img_url)
            if r.status_code == 200:
                dest.write_bytes(r.content)
                return str(dest)
            if _is_transient(r.status_code):
                raise Unreachable(f"TheGamesDB CDN answered {r.status_code}")
        except Unreachable:
            raise
        except httpx.RequestError as e:
            raise Unreachable(f"TheGamesDB unreachable: {e}") from e
        except Exception:
            # A malformed payload is not evidence about this game either.
            raise Unreachable("TheGamesDB returned something unusable")

    return None
