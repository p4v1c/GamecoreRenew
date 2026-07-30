"""Warm the cover + metadata caches in the background at startup.

Without this, the first visit to each library pays one network round-trip
per game (cover, then metadata) right when the user is navigating. This
walks every system shortly after boot and resolves everything through the
same pipelines the API uses — already-cached entries cost one stat() each,
so warm boots are essentially free.
"""
import asyncio
import logging

from ..config import resolve_path
from ..routers.systems import list_all
from .cover_pipeline import resolve as resolve_cover
from .metadata import resolve as resolve_metadata
from .rom_scanner import iter_rom_files

log = logging.getLogger(__name__)

_START_DELAY = 15   # let the splash/home screen boot without competition
_CONCURRENCY = 3    # be gentle with the CDNs and the box's uplink

# Note on pacing when ScreenScraper is configured: the gamemedia tier holds its
# own lock and spaces its calls 1.2 s apart, so the three workers above do not
# multiply into three concurrent scrapes. A first sweep of a large library
# therefore takes minutes rather than seconds — deliberately. It runs once, in
# the background, and every game it resolves costs nothing on every boot after.


async def run() -> None:
    await asyncio.sleep(_START_DELAY)

    jobs: list[tuple[dict, str]] = []
    try:
        for system in list_all():
            if system.get("kind") != "emulator":
                continue
            roms = resolve_path(system.get("romsPath", ""))
            if not roms:
                continue
            for f in iter_rom_files(roms, system.get("extensions", []),
                                    scan_dirs=system.get("scanDirs", False)):
                jobs.append((system, f.name))
    except Exception:
        log.exception("prefetch: scan failed")
        return

    if not jobs:
        return
    log.info("prefetch: warming covers/metadata for %d games", len(jobs))

    sem = asyncio.Semaphore(_CONCURRENCY)

    async def warm(system: dict, filename: str) -> None:
        async with sem:
            try:
                await resolve_cover(system, filename)
            except Exception:
                log.debug("prefetch: cover failed for %s", filename, exc_info=True)
            try:
                await resolve_metadata(system, filename)
            except Exception:
                log.debug("prefetch: metadata failed for %s", filename, exc_info=True)

    await asyncio.gather(*(warm(s, f) for s, f in jobs))
    log.info("prefetch: done (%d games)", len(jobs))
