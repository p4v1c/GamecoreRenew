"""A game added after boot gets its images, without a restart.

The prefetch used to run exactly once, `_START_DELAY` seconds into the
backend's life. Everything after that was invisible to it: a ROM dropped into a
directory while the box was on had no cover and no `box-back` until somebody
opened its detail panel or restarted. Measured on six PSP games added during
one session — none of them had a `box-back` until the next boot.

What these tests pin down is not only that it now happens, but that it happens
*politely*. The old pass had three properties that kept it from ever being felt,
and a queue is exactly the kind of change that quietly drops one of them:

  · the start delay, so the home screen boots without competition
  · a concurrency of 3, so the uplink is not saturated
  · covers for every game before extra media for any game

Plus the one the queue makes necessary: a ROM appearing must not set off a
burst of downloads while somebody is playing.
"""
import asyncio
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import pytest

from backend.services import prefetch

SYSTEM = {"id": "ppsspp", "kind": "emulator", "romsPath": "emu/ppsspp/"}


class _Log(list):
    """The event log, with room for the concurrency high-water mark."""
    inflight: dict


@pytest.fixture
def wired(monkeypatch):
    """A prefetch worker with no disk, no network and no clock.

    Returns the event log: `("cover", name)`, `("meta", name)`, `("media", name)`
    in the order the worker did them.
    """
    prefetch._seen.clear()
    prefetch._pending.clear()
    prefetch._wake = None
    prefetch._loop = None

    events = _Log()
    inflight = {"now": 0, "peak": 0}

    async def cover(system, filename):
        inflight["now"] += 1
        inflight["peak"] = max(inflight["peak"], inflight["now"])
        await asyncio.sleep(0)          # let the others pile up if they can
        events.append(("cover", filename))
        inflight["now"] -= 1

    async def meta(system, filename):
        events.append(("meta", filename))

    async def warm(sid, target, types=None):
        events.append(("media", Path(target).name))
        return 1

    monkeypatch.setattr(prefetch, "_START_DELAY", 0)
    monkeypatch.setattr(prefetch, "_IDLE_POLL", 0.01)
    monkeypatch.setattr(prefetch, "resolve_cover", cover)
    monkeypatch.setattr(prefetch, "resolve_metadata", meta)
    monkeypatch.setattr(prefetch, "_startup_jobs", lambda: [])
    monkeypatch.setattr(prefetch.gamemedia, "available", lambda: True)
    monkeypatch.setattr(prefetch.gamemedia, "WARM_MEDIA", {"box-back"})
    monkeypatch.setattr(prefetch.gamemedia, "warm", warm)
    monkeypatch.setattr(prefetch, "rom_in_root", lambda system, name: None)
    # The migration is a separate concern with its own tests; here it must only
    # not get in the way.
    monkeypatch.setattr(prefetch, "_migrate_covers", lambda: asyncio.sleep(0))

    events.inflight = inflight
    return events


async def _settle(events, count, timeout=2.0):
    """Wait until `count` events have been recorded, or give up."""
    deadline = asyncio.get_running_loop().time() + timeout
    while len(events) < count:
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"only {len(events)} event(s): {events}")
        await asyncio.sleep(0.01)


# ── The defect this fixes ────────────────────────────────────────────────────

def test_a_game_noticed_after_boot_gets_its_cover_and_its_extra_media(wired):
    """The whole point. Both passes, for a game the startup sweep never saw."""
    async def scenario():
        worker = asyncio.create_task(prefetch.run())
        await asyncio.sleep(0.05)                 # the startup sweep finds nothing

        prefetch.note_scan(SYSTEM, ["Newcomer.iso"])
        await _settle(wired, 3)

        worker.cancel()
        return list(wired)

    events = asyncio.run(scenario())
    assert ("cover", "Newcomer.iso") in events
    assert ("media", "Newcomer.iso") in events, \
        "the second pass never ran — this is the box-back that used to need a reboot"
    assert events.index(("cover", "Newcomer.iso")) < events.index(("media", "Newcomer.iso"))


def test_a_library_that_has_not_changed_queues_nothing(wired):
    """`list_games` runs every time the grid opens — it must stay free."""
    assert prefetch.note_scan(SYSTEM, ["A.iso", "B.iso"]) == 2
    assert prefetch.note_scan(SYSTEM, ["A.iso", "B.iso"]) == 0
    assert prefetch.note_scan(SYSTEM, ["A.iso", "B.iso", "C.iso"]) == 1


def test_an_app_tile_is_not_a_library(wired):
    """Apps have no ROMs and no covers to scrape."""
    assert prefetch.note_scan({"id": "stremio", "kind": "app"}, ["x"]) == 0


# ── The properties that must survive the change ──────────────────────────────

def test_covers_come_before_extra_media_for_the_whole_batch(wired):
    """Every game has a cover before any game has six images.

    Someone opening the library thirty seconds in cares about the grid being
    full, not about one title's detail panel being complete.
    """
    async def scenario():
        worker = asyncio.create_task(prefetch.run())
        await asyncio.sleep(0.05)
        prefetch.note_scan(SYSTEM, [f"Game{i}.iso" for i in range(6)])
        await _settle(wired, 18)
        worker.cancel()
        return list(wired)

    events = asyncio.run(scenario())
    last_cover = max(i for i, (k, _) in enumerate(events) if k == "cover")
    first_media = min(i for i, (k, _) in enumerate(events) if k == "media")
    assert last_cover < first_media, f"a media fetch overtook a cover: {events}"


def test_no_more_than_three_at_a_time(wired):
    """The uplink politeness the old pass had, and the queue must keep."""
    async def scenario():
        worker = asyncio.create_task(prefetch.run())
        await asyncio.sleep(0.05)
        prefetch.note_scan(SYSTEM, [f"Game{i}.iso" for i in range(20)])
        await _settle(wired, 60)
        worker.cancel()

    asyncio.run(scenario())
    assert wired.inflight["peak"] <= 3, \
        f"{wired.inflight['peak']} covers were resolving at once"


def test_the_home_screen_boots_without_competition(monkeypatch, wired):
    """The delay is not bypassed by queueing something before it elapses."""
    monkeypatch.setattr(prefetch, "_START_DELAY", 0.3)

    async def scenario():
        worker = asyncio.create_task(prefetch.run())
        prefetch.note_scan(SYSTEM, ["Early.iso"])   # queued immediately
        await asyncio.sleep(0.1)
        early = list(wired)
        await _settle(wired, 1)
        worker.cancel()
        return early

    assert asyncio.run(scenario()) == [], \
        "the worker started fetching before the splash was out of the way"


# ── The one the queue makes necessary ────────────────────────────────────────

def test_nothing_is_fetched_while_a_game_is_running(monkeypatch, wired):
    """Adding a ROM must not set off a download burst under someone's session.

    Deferred rather than throttled: nobody is looking at the library while a
    game is on screen, so the work has no deadline — and the box plays over the
    same uplink a scrape would be using.
    """
    playing = {"yes": True}

    class FakePM:
        @property
        def is_running(self):
            return playing["yes"]

    monkeypatch.setattr(prefetch, "process_manager", FakePM())

    async def scenario():
        worker = asyncio.create_task(prefetch.run())
        await asyncio.sleep(0.05)
        prefetch.note_scan(SYSTEM, ["Added mid-session.iso"])
        await asyncio.sleep(0.1)
        during = list(wired)

        playing["yes"] = False          # the player quits
        await _settle(wired, 3)

        worker.cancel()
        return during, list(wired)

    during, after = asyncio.run(scenario())
    assert during == [], f"fetched while a game was running: {during}"
    assert ("cover", "Added mid-session.iso") in after, \
        "the deferred batch was dropped instead of resumed"
    assert ("media", "Added mid-session.iso") in after


# ── The wiring ───────────────────────────────────────────────────────────────

def test_the_rom_listing_is_what_notices(monkeypatch):
    """`list_games` is the box's only ROM scan, so it is the hook.

    Asserted at the router rather than trusted: a listing that stopped calling
    this would put the old defect back with no other symptom.
    """
    from backend.routers import games

    seen = []
    monkeypatch.setattr(games.prefetch, "note_scan",
                        lambda system, names: seen.append((system["id"], names)))
    monkeypatch.setattr(games, "list_all", lambda: [
        {"id": "ppsspp", "kind": "emulator", "romsPath": "emu/ppsspp/",
         "extensions": ["*.iso"]}])
    monkeypatch.setattr(games, "resolve_path", lambda p: Path("/nonexistent"))
    monkeypatch.setattr(games, "scan_roms",
                        lambda *a, **k: [{"filename": "Nine.iso"}])

    games.list_games("ppsspp")
    assert seen == [("ppsspp", ["Nine.iso"])]


def test_a_broken_prefetch_never_breaks_the_library(monkeypatch):
    """The grid must render even if the queue blows up."""
    from backend.routers import games

    def boom(system, names):
        raise RuntimeError("queue is on fire")

    monkeypatch.setattr(games.prefetch, "note_scan", boom)
    monkeypatch.setattr(games, "list_all", lambda: [
        {"id": "ppsspp", "kind": "emulator", "romsPath": "emu/ppsspp/",
         "extensions": ["*.iso"]}])
    monkeypatch.setattr(games, "resolve_path", lambda p: Path("/nonexistent"))
    monkeypatch.setattr(games, "scan_roms",
                        lambda *a, **k: [{"filename": "Nine.iso"}])

    assert games.list_games("ppsspp") == [{"filename": "Nine.iso"}]
