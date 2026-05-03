"""Async cover scraper — libretro thumbnails CDN."""
import re
from pathlib import Path
from urllib.parse import quote, unquote

import httpx

from ..config import COVERS_DIR
from ..utils import TAG_RE

PLATFORM_MAP: dict[str, list[str]] = {
    "melonds":     ["Nintendo - Nintendo DS", "Nintendo - Nintendo DS (Download Play)"],
    "azahar":      ["Nintendo - Nintendo 3DS"],
    "mgba":        ["Nintendo - Game Boy Advance", "Nintendo - Game Boy Color", "Nintendo - Game Boy"],
    "dolphin":     ["Nintendo - GameCube", "Nintendo - Wii"],
    "cemu":        ["Nintendo - Wii U"],
    "ryujinx":     ["Nintendo - Switch"],
    "gopher64":    ["Nintendo - Nintendo 64"],
    "duckstation": ["Sony - PlayStation"],
    "pcsx2":       ["Sony - PlayStation 2"],
    "ppsspp":      ["Sony - PlayStation Portable"],
    "rpcs3":       ["Sony - PlayStation 3"],
    "retroarch":   ["Nintendo - Super Nintendo Entertainment System"],
    "snes9x":      ["Nintendo - Super Nintendo Entertainment System"],
    "nestopia":    ["Nintendo - Nintendo Entertainment System"],
    "mame":        ["MAME"],
}

_LIBRETRO_BASE = "https://thumbnails.libretro.com/{system}/Named_Boxarts/{name}.png"
_LIBRETRO_INDEX = "https://thumbnails.libretro.com/{system}/Named_Boxarts/"
_LANG_RE = re.compile(r"\(((?:En|Fr|De|Es|It|Ja|Ko|Ru|Pt){2,})\)")
_INDEX_HREF_RE = re.compile(r'href="([^"]+\.png)"')

# Cache for directory listings: { "Nintendo - Nintendo 3DS": ["Game (USA).png", ...] }
_INDEX_CACHE: dict[str, list[str]] = {}


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


async def _get_index(client: httpx.AsyncClient, system_name: str) -> list[str]:
    """Fetch and cache directory listing from Libretro."""
    if system_name in _INDEX_CACHE:
        return _INDEX_CACHE[system_name]
    
    url = _LIBRETRO_INDEX.format(system=quote(system_name))
    try:
        r = await client.get(url)
        if r.status_code == 200:
            # Extract filenames from hrefs, unquoting them
            files = [unquote(f) for f in _INDEX_HREF_RE.findall(r.text)]
            _INDEX_CACHE[system_name] = files
            return files
    except Exception:
        pass
    return []


async def fetch_cover(rom_path: str, system_id: str) -> str | None:
    """Return local path to cover image, downloading if necessary. None if not found."""
    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    base = Path(rom_path).stem
    cached = COVERS_DIR / f"{base}.png"
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
                    if r.status_code == 200:
                        r = await client.get(url)
                        cached.write_bytes(r.content)
                        return str(cached)
                except httpx.RequestError:
                    continue

            # 2. Index-based fuzzy matching — exact norm match, then prefix, then cross-region
            index = await _get_index(client, platform)
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
                    if r.status_code == 200:
                        cached.write_bytes(r.content)
                        return str(cached)
                except httpx.RequestError:
                    continue

    return None
