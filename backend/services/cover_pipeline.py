"""Cover resolution pipeline — local-first, then exact ID lookup, then the
legacy name scrapers. Order:

  1. cache (emu/covers/<system>/<stem>.png|.jpg — drop a file there to force a cover)
  2. icon embedded in the game itself (PS3/PS4 folders, PSP ISO) — offline, exact
  3. gamemedia: ScreenScraper by file hash, then the offline LaunchBox index
  4. disc-ID lookup: GameTDB (GC/Wii/PS3), xlenore repos (PS1/PS2) — exact
  5. libretro thumbnails by name, then TheGamesDB (services.scraper)

Step 3 is the one that is certain on a cartridge: there is no icon to extract
and no serial to read, so everything below it guesses from the filename, while
a CRC32 the ScreenScraper database recognises identifies the game outright. It
sits *below* the embedded icon because that one is exact too and costs no
network at all, and *above* the name scrapers for the same reason it exists.

It is also inert unless configured: with no ScreenScraper credentials and no
LaunchBox index, `gamemedia.available()` is False and this pipeline is byte for
byte the one that ran before it was added.

Misses are remembered (<stem>.miss, TTL) so the library UI doesn't re-hit
the network for every unmatched game on every visit.
"""
import logging
import shutil
import time
from pathlib import Path

import httpx

from ..config import COVERS_DIR
from ..utils import rom_in_root
from . import gamemedia, local_media
from .scraper import Unreachable, _is_transient, fetch_cover

log = logging.getLogger(__name__)

_MISS_TTL = 7 * 24 * 3600  # retry failed lookups after a week

# GameTDB region folder from the region letter of a disc ID / serial
_GAMETDB_REGION = {
    "E": "US", "P": "EN", "J": "JA", "K": "KO", "W": "ZH", "D": "DE",
    "F": "FR", "I": "IT", "S": "ES", "H": "NL", "U": "AU", "R": "RU",
    "T": "ZH", "A": "EN",
}

_XLENORE = "https://raw.githubusercontent.com/xlenore/{repo}/main/covers/default/{serial}.jpg"


def _regions(letter: str) -> list[str]:
    first = _GAMETDB_REGION.get(letter, "EN")
    out = [first]
    for r in ("US", "EN", "JA"):
        if r not in out:
            out.append(r)
    return out


def _id_urls(kind: str, value: str) -> list[tuple[str, str]]:
    """Candidate (url, extension) pairs for a disc ID, best first."""
    if kind == "wii":  # GameTDB hosts GameCube and Wii together
        return [(f"https://art.gametdb.com/wii/cover/{r}/{value}.png", ".png")
                for r in _regions(value[3])]
    if kind == "ps3":
        return [(f"https://art.gametdb.com/ps3/cover/{r}/{value}.jpg", ".jpg")
                for r in _regions(value[2])]
    if kind == "psx":
        return [(_XLENORE.format(repo="psx-covers", serial=value), ".jpg")]
    if kind == "ps2":
        return [(_XLENORE.format(repo="ps2-covers", serial=value), ".jpg")]
    return []


async def _fetch_by_id(kind: str, value: str, base: Path) -> Path | None:
    """Raises Unreachable if none of the candidate URLs actually answered."""
    urls = _id_urls(kind, value)
    if not urls:
        return None
    reached = False
    transient = False
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        for url, ext in urls:
            try:
                r = await client.get(url)
            except httpx.RequestError:
                continue
            reached = True
            if _is_transient(r.status_code):
                transient = True
                continue
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image/"):
                dest = base.with_suffix(ext)
                dest.write_bytes(r.content)
                return dest
    if not reached or transient:
        raise Unreachable(f"no disc-ID lookup completed for {kind}/{value}")
    return None


async def _from_gamemedia(sid: str, target: str, base: Path,
                          refresh: bool = False) -> tuple[Path | None, bool]:
    """(cover, unreachable) from the ScreenScraper / LaunchBox tier.

    Copied into emu/covers/ rather than served from the gamemedia cache: this
    directory is what `/covers` mounts statically, what the screensaver reads,
    and what a user drops a file into to override a cover. One image per game
    duplicated is worth keeping that one place.

    The type asked for is a flat jacket (COVER_ORDER), so what lands here is
    the same *kind* of picture the pipeline has always produced — no theme sees
    a different shape. The 3D box, the logo and the screenshots are reachable
    through /api/media, which is what a theme built on them would use.
    """
    manifest = await gamemedia.resolve(sid, target, refresh=refresh)
    if manifest is None:
        return None, False          # tier not configured — not a verdict
    if not manifest.get("found"):
        # `unreachable` is the whole point of asking: a spent quota must not be
        # written down as "nobody has a cover for this game" for a week.
        return None, bool(manifest.get("unreachable"))

    available = manifest.get("media") or {}
    for slug in gamemedia.COVER_ORDER:
        if slug not in available:
            continue
        src = await gamemedia.media_file(sid, target, slug)
        if not src:
            continue
        dest = base.with_suffix(src.suffix if src.suffix in (".png", ".jpg") else ".png")
        dest.write_bytes(src.read_bytes())
        return dest, False
    # Found the game, but it has no box art at all. That is an answer.
    return None, False


# The confinement moved to utils.rom_in_root when the media router became the
# third caller. Kept under its old name here: it is the guard the covers tests
# assert on directly, and the invariant is easier to check where it is used.
_rom_in_root = rom_in_root


async def resolve(system: dict, filename: str, refresh: bool = False) -> Path | None:
    """Return a local path to the cover for one game, or None."""
    sid = system["id"].lower()
    cache_dir = COVERS_DIR / sid
    cache_dir.mkdir(parents=True, exist_ok=True)

    stem = Path(filename).stem
    base = cache_dir / stem
    png, jpg = base.with_suffix(".png"), base.with_suffix(".jpg")
    miss = base.with_suffix(".miss")

    if refresh:
        for p in (png, jpg, miss):
            p.unlink(missing_ok=True)

    for p in (png, jpg):
        if p.is_file():
            return p

    # Migrate from the old flat cache layout (emu/covers/<stem>.png)
    legacy = COVERS_DIR / f"{stem}.png"
    if legacy.is_file():
        shutil.move(str(legacy), png)
        return png

    if miss.exists() and time.time() - miss.stat().st_mtime < _MISS_TTL:
        return None

    rom: Path | None = _rom_in_root(system, filename)

    # Set as soon as any step could not get an answer. A .miss is a claim that
    # nobody has this cover; nothing may claim that on the strength of a request
    # that never left the box.
    unreachable = False

    if rom:
        # 1. Icon embedded in the game (offline, always right)
        if local_media.extract_icon(sid, rom, png):
            return png

    # 2. gamemedia — the hash when the ROM is a file, the PARAM.SFO title when
    #    it is a directory, the name otherwise. Passing the full path is what
    #    makes the first two possible; without it the tier still works, by name.
    if gamemedia.available():
        try:
            found, gm_unreachable = await _from_gamemedia(
                sid, str(rom or filename), base, refresh=refresh)
        except Exception:
            log.warning("gamemedia lookup failed for %s/%s", sid, filename, exc_info=True)
            found, gm_unreachable = None, True
        if found:
            return found
        unreachable = unreachable or gm_unreachable

    if rom:
        # 3. Exact lookup by the ID read from the game itself
        did = local_media.disc_id(sid, rom)
        if did:
            try:
                found = await _fetch_by_id(did[0], did[1], base)
            except Unreachable:
                unreachable, found = True, None
            if found:
                return found

    # 4./5. Name-based scraping (libretro CDN, then TheGamesDB)
    try:
        scraped = await fetch_cover(filename, sid, dest=png)
    except Unreachable as e:
        log.info("cover lookup for %s/%s did not complete (%s)", sid, filename, e)
        unreachable, scraped = True, None
    except Exception:
        log.warning("cover scrape failed for %s/%s", sid, filename, exc_info=True)
        # An unexpected error says nothing about whether the cover exists.
        unreachable, scraped = True, None
    if scraped:
        return Path(scraped)

    if unreachable:
        # No marker. This is the case that mattered most: prefetch starts 15 s
        # after boot, and on a brand-new box there is no Wi-Fi yet — the owner
        # configures it from this very interface. The first run used to write a
        # .miss for every game in the library, and _MISS_TTL is seven days, so
        # the box stayed blank for a week with no message and no way to force a
        # retry short of ?refresh=1 on each game. Rebooting did not help; the
        # markers are on disk.
        return None

    miss.touch()
    return None
