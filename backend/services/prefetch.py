"""Warm the cover + metadata caches in the background — at boot, and after.

Without this, the first visit to each library pays one network round-trip
per game (cover, then metadata) right when the user is navigating. This
walks every system shortly after boot and resolves everything through the
same pipelines the API uses — already-cached entries cost one stat() each,
so warm boots are essentially free.

**It used to run exactly once, at startup**, and that was the hole: a game
added while the box was on was never prefetched. Its images arrived only if
someone opened its detail panel, or at the next reboot. Measured on six PSP
games added during a session — not one had a `box-back` until the box was
restarted.

So the sweep is no longer a single pass but a worker with a queue. The startup
scan fills it once; `note_scan` fills it again every time the library listing
discovers a filename this process has not seen. What is warmed is the same, in
the same order, with the same politeness — see below.

── The three properties that make this invisible, and are kept ───────────────

**The delay.** The home screen boots without competition. A queue changes
nothing here: the worker does not start draining until `_START_DELAY` has
passed, however early something is queued.

**The concurrency of 3.** Gentle with the CDNs and the box's uplink. Note on
pacing when ScreenScraper is configured: the gamemedia tier holds its own lock
and spaces its calls 1.2 s apart, so the three workers do not multiply into
three concurrent scrapes. A first sweep of a large library therefore takes
minutes rather than seconds — deliberately.

**The two passes.** Covers for every game first, then the rest. Every game must
have a cover before any game has six images: someone opening the library thirty
seconds after boot cares about the grid being full, not about the detail panel
of one title being complete. The order holds *within a batch*, which is what
matters — a game added on its own is a batch of one, and gets its cover before
its screenshots either way.

── And one that is new ──────────────────────────────────────────────────────

**Nothing is fetched while a game is running.** Adding a ROM must not set off a
burst of downloads under someone's session. `process_manager` knows, so it is
asked rather than guessed at.

The choice is to **defer entirely until the game exits**, not to lower the
concurrency further. Three reasons, in order of weight: nobody is looking at
the library while a game is on screen, so the work has no deadline it could
miss; the box plays and streams over the same uplink, where a scrape burst is
felt; and ScreenScraper's 1.2 s spacing means a throttled sweep would not
finish quickly anyway — it would simply spread the interference over the whole
session instead of concentrating it. Deferring costs nothing: the queue is
drained when the player comes back to the grid, which is exactly when the
images start mattering again.
"""
import asyncio
import logging
import threading

from ..config import resolve_path
from ..routers.systems import list_all
from ..utils import rom_in_root
from . import cover_encode, gamemedia
from .cover_pipeline import resolve as resolve_cover
from .metadata import resolve as resolve_metadata
from .paths import covers_dir
from .process_manager import process_manager
from .rom_scanner import iter_rom_files

log = logging.getLogger(__name__)

_START_DELAY = 15   # let the splash/home screen boot without competition
_CONCURRENCY = 3    # be gentle with the CDNs and the box's uplink
_IDLE_POLL = 5.0    # how often to look up from a deferred batch

# What has been queued this process, so a library listing that runs every time
# the grid opens does not re-queue the same library every time. Guarded by a
# plain lock rather than an asyncio one: `note_scan` is called from FastAPI's
# threadpool (`list_games` is a sync endpoint), not from the event loop.
_lock = threading.Lock()
_seen: set[tuple[str, str]] = set()
_pending: list[tuple[dict, str]] = []

# Set from the loop when there is something to drain. `_loop` is captured when
# the worker starts, because the signal has to cross a thread boundary.
_wake: asyncio.Event | None = None
_loop: asyncio.AbstractEventLoop | None = None


def _enqueue(jobs: list[tuple[dict, str]]) -> int:
    """Queue the jobs this process has not seen. Returns how many were new."""
    fresh = []
    with _lock:
        for system, filename in jobs:
            key = (system["id"].lower(), filename)
            if key in _seen:
                continue
            _seen.add(key)
            fresh.append((system, filename))
        _pending.extend(fresh)

    if fresh and _loop is not None and _wake is not None:
        # Thread-safe by construction: `note_scan` runs in a worker thread.
        _loop.call_soon_threadsafe(_wake.set)
    return len(fresh)


def _drain() -> list[tuple[dict, str]]:
    with _lock:
        batch, _pending[:] = list(_pending), []
    return batch


def note_scan(system: dict, filenames: list[str]) -> int:
    """A library listing just enumerated a system. Warm anything new.

    Called from `routers/games.list_games`, which is the box's only ROM scan
    and runs whenever the grid opens — so a game dropped into a ROMs directory
    is noticed the first time anyone looks at that system, without a restart.

    Returns how many were queued, which is 0 for the overwhelmingly common case
    of a library that has not changed. Cheap enough to call on every listing:
    one set lookup per game.
    """
    if system.get("kind") == "app":
        return 0
    queued = _enqueue([(system, name) for name in filenames])
    if queued:
        log.info("prefetch: %d new game(s) in %s — queued", queued, system["id"])
    return queued


def _startup_jobs() -> list[tuple[dict, str]]:
    jobs: list[tuple[dict, str]] = []
    for system in list_all():
        if system.get("kind") != "emulator":
            continue
        roms = resolve_path(system.get("romsPath", ""))
        if not roms:
            continue
        for f in iter_rom_files(roms, system.get("extensions", []),
                                scan_dirs=system.get("scanDirs", False)):
            jobs.append((system, f.name))
    return jobs


async def _wait_until_nobody_is_playing() -> None:
    """Hold the batch while a game is on screen — see the module docstring."""
    if not process_manager.is_running:
        return
    log.info("prefetch: a game is running — deferring until it exits")
    while process_manager.is_running:
        await asyncio.sleep(_IDLE_POLL)
    log.info("prefetch: the game exited — resuming")


async def _warm(batch: list[tuple[dict, str]]) -> None:
    """The two passes, over one batch."""
    sem = asyncio.Semaphore(_CONCURRENCY)

    async def one(system: dict, filename: str) -> None:
        async with sem:
            try:
                await resolve_cover(system, filename)
            except Exception:
                log.debug("prefetch: cover failed for %s", filename, exc_info=True)
            try:
                await resolve_metadata(system, filename)
            except Exception:
                log.debug("prefetch: metadata failed for %s", filename, exc_info=True)

    await asyncio.gather(*(one(s, f) for s, f in batch))
    log.info("prefetch: covers/metadata warmed for %d game(s)", len(batch))

    # Second pass: the artwork a theme draws beyond the cover — the faces of
    # the 3D box, the captures. Deliberately after the first, and not merged
    # into it.
    #
    # It costs no jeuInfos — the URLs are already in the manifests — so a
    # second sweep is downloads and nothing else. Games whose media are already
    # on disk cost a stat() each.
    if not gamemedia.available() or not gamemedia.WARM_MEDIA:
        return
    warmed = 0
    for system, filename in batch:
        rom = rom_in_root(system, filename)
        try:
            warmed += await gamemedia.warm(system["id"].lower(),
                                           str(rom) if rom else filename)
        except Exception:
            log.debug("prefetch: warming failed for %s", filename, exc_info=True)
    if warmed:
        log.info("prefetch: %d extra media cached", warmed)


async def _migrate_covers() -> None:
    """Re-encode the covers already on disk as lossless WebP. Once.

    Deliberately AFTER the first sweep rather than before it. The re-encode is
    CPU, and the first sweep is the moment the grid is filling — the one time
    the player is actually waiting on a cover. Running it here means the boot
    that installs the update is unimproved and every boot after it is faster,
    which is the right way round.

    `emu/` is excluded from the OTA rsync, so this is the only thing that ever
    reaches a library that was scraped before the conversion existed.
    """
    if not cover_encode.available():
        return
    try:
        await asyncio.to_thread(
            cover_encode.migrate, covers_dir(),
            should_continue=lambda: not process_manager.is_running)
    except Exception:
        log.exception("prefetch: cover migration failed")


async def run() -> None:
    """The worker. One task, for the life of the backend."""
    global _wake, _loop
    _wake = asyncio.Event()
    _loop = asyncio.get_running_loop()

    await asyncio.sleep(_START_DELAY)

    try:
        _enqueue(_startup_jobs())
    except Exception:
        log.exception("prefetch: startup scan failed")

    migrated = False
    while True:
        batch = _drain()
        if not batch:
            if not migrated:
                # The queue has run dry for the first time: the grid is as full
                # as this boot is going to make it. Now is the cheap moment.
                migrated = True
                await _migrate_covers()
                continue
            _wake.clear()
            # Re-check after clearing: something may have been queued between
            # the drain and the clear, and waiting on it would strand the batch
            # until the *next* scan came along.
            if not _pending:
                await _wake.wait()
            continue

        await _wait_until_nobody_is_playing()
        try:
            await _warm(batch)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("prefetch: warming a batch failed")
