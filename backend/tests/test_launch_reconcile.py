"""Launching a game frees the slots the hotplug events missed.

Launch is the one moment where the inventory is certainly complete and the
emulator is about to re-read its input config. Everything the three-second scan
loop missed — a pad that died between two passes, a scan that came back empty
because evdev was briefly unreadable, a box that came up before the pads did —
is still there at that instant and still fixable.

The whole value of doing it here rests on one property: **it must never cost a
launch.** A config left slightly stale is a playable game. An exception, or a
pass that hangs on a stalled home directory, is a game that does not start —
which is worse than the defect being fixed. So the tests that matter are not
"does it clean up", they are "what happens when it goes wrong".
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend import main                                      # noqa: E402
from backend.routers import games as games_router             # noqa: E402
from backend.services import controller_registry as reg       # noqa: E402
from backend.services import gamepad_monitor as gm            # noqa: E402
from backend.services import process_manager as pm            # noqa: E402

GHOST = {"id": "ghost", "label": "Ghost", "kind": "emulator",
         "path": "/usr/bin/definitely-not-installed", "args": "", "romsPath": ""}


@pytest.fixture
def launcher(monkeypatch):
    """A client whose launch always fails at the exec step.

    Deliberate: the cleanup runs BEFORE `process_manager.launch`, so a launch
    that cannot succeed still exercises it in full, and no emulator is started
    from a test.

    **The monitor is blinded, and that is not tidiness.** `TestClient` runs the
    app lifespan, which starts the real gamepad monitor, which scans the real
    /dev/input every three seconds — so on a developer's box with a pad plugged
    in, a second caller was reaching the same monkeypatched `release_profile`
    while the launch ran. Two tests here failed on that machine and only that
    machine, reporting `[None, None, ('ghost',), …]`: half those calls were the
    monitor's. An empty device list gives every box the same one.

    `PROFILE_BUDGET` goes to zero for the same reason. The wait it governs is
    the subject of its own tests below; in the ones about the release sweep it
    would only add up to eight seconds of real time whenever a pad happened to
    be connected.
    """
    monkeypatch.setattr(games_router, "list_all", lambda: [GHOST])
    monkeypatch.setattr(games_router, "PROFILE_BUDGET", 0.0)
    monkeypatch.setattr(gm, "_find_gamepad_devices", dict)
    reg._slots.clear(); reg._labels.clear()
    try:
        with TestClient(main.app) as c:
            yield c
    finally:
        reg._slots.clear(); reg._labels.clear()


def _launch(client):
    return client.post("/api/games/launch", json={"system_id": "ghost"})


# ── the guarantee: never at the cost of a launch ─────────────────────────────

def test_a_cleanup_that_raises_does_not_stop_the_launch(launcher, monkeypatch):
    """The failure mode that would make this change a net loss.

    Reaching the emulator means the 503 below comes from the exec step, which
    is where it came from before this hook existed.
    """
    def boom(*_a, **_k):
        raise OSError("the flatpak config directory went away")

    monkeypatch.setattr(games_router.controller_profiles, "release_profile", boom)

    r = _launch(launcher)
    assert r.status_code == 503, (
        f"the slot cleanup swallowed the launch — got {r.status_code}. A config "
        f"that cannot be cleaned is a playable game; this is a dead box.")
    assert "ghost" in r.json()["detail"]


def test_a_cleanup_that_hangs_does_not_hold_the_launch(launcher, monkeypatch):
    """A stalled home directory must cost a stale config, not a launch.

    The sweep is file I/O in a worker thread, so it cannot be cancelled — the
    budget abandons WAITING on it. What this asserts is the launch moving on,
    which is the property the player experiences.
    """
    monkeypatch.setattr(games_router, "RECONCILE_BUDGET", 0.05)
    monkeypatch.setattr(games_router.controller_profiles, "release_profile",
                        lambda *a, **k: time.sleep(1.0) or [])

    start = time.monotonic()
    r = _launch(launcher)
    elapsed = time.monotonic() - start

    assert r.status_code == 503, r.text
    assert elapsed < 1.0, (
        f"the launch waited {elapsed:.2f}s on a hung cleanup — the budget did "
        f"not cut it off")


def test_the_cleanup_runs_before_the_emulator_starts(launcher, monkeypatch):
    """Order is the whole point: an emulator reads its input config at startup,
    so a slot freed a moment later is a slot the running game still sees."""
    order: list[str] = []
    monkeypatch.setattr(games_router.controller_profiles, "release_profile",
                        lambda *a, **k: order.append("release") or [])

    async def launch(**_kw):
        order.append("launch")
        raise FileNotFoundError("not installed")

    monkeypatch.setattr(games_router.process_manager, "launch", launch)

    _launch(launcher)
    assert order and order[0] == "release", (
        f"the emulator started before its config was cleaned: {order}")
    assert "launch" in order


# ── what it actually does ────────────────────────────────────────────────────

def test_only_the_slots_nobody_holds_are_freed(launcher, monkeypatch):
    """A connected pad's slot is not a stale slot. Freeing everything and
    letting the monitor rewrite it would pass a "no ghosts" test while
    unbinding the pad in the player's hands for up to three seconds."""
    calls: list[tuple] = []
    monkeypatch.setattr(games_router.controller_profiles, "release_profile",
                        lambda slot, occupied=(), pack_ids=None:
                        calls.append((slot, tuple(sorted(occupied)))) or [])
    # The roster is stated, not built with reg.connect(): TestClient runs the
    # app lifespan, which starts the gamepad monitor, which scans the REAL
    # /dev/input — so a developer with a pad plugged in had a third slot taken
    # under the test's feet and this assertion failed on their machine only.
    monkeypatch.setattr(games_router.controller_registry, "snapshot",
                        lambda: [{"player": 1, "label": "pad one"},
                                 {"player": 2, "label": "pad two"}])

    _launch(launcher)

    freed = [slot for slot, _ in calls]
    assert 1 not in freed and 2 not in freed, (
        f"slots held by a connected pad were freed: {freed}")
    assert set(freed) == {3, 4}, freed
    assert all(occ == (1, 2) for _, occ in calls), (
        f"the remaining roster was not passed on: {calls}. Without it a "
        f"release cannot decide anything the roster owns — the multitap.")


def test_only_the_emulator_being_launched_is_touched(launcher, monkeypatch):
    """Rewriting Cemu because someone started PCSX2 is a side effect nobody
    asked for, and it is also what would put this over its time budget."""
    seen: list = []
    monkeypatch.setattr(games_router.controller_profiles, "release_profile",
                        lambda slot, occupied=(), pack_ids=None:
                        seen.append(pack_ids) or [])

    _launch(launcher)

    assert seen, "the cleanup did not run at all"
    assert all(p == ("ghost",) for p in seen), (
        f"the pass was not scoped to the launched emulator: {seen}")


def test_a_launch_with_no_pad_connected_still_works(launcher):
    """Nothing connected is a legitimate state — a mouse-and-keyboard box, or
    a pad that has not woken up yet. It must not turn a launch into a 500."""
    r = _launch(launcher)
    assert r.status_code == 503, r.text
    assert not pm.process_manager.is_running


# ── the other half: a pad that IS there and has not been written yet ─────────
#
# Freeing a slot no pad holds was only ever half the job, and the half that was
# missing is the one the reference box measured: RPCS3 started six seconds
# before its config was written, Dolphin two, and both were dead in game until
# the next launch. An emulator reads its input config once, at startup.


@pytest.fixture
def waiting(monkeypatch):
    """`launcher`, with the profiling wait live and the monitor state stated.

    The state is set by hand rather than by running the monitor: the point of
    these tests is what the LAUNCH does with each answer, and driving them
    through a real 3 s scan loop would test the loop's timing instead.
    """
    monkeypatch.setattr(gm, "_running", True)
    monkeypatch.setattr(gm, "_scanned", True)
    monkeypatch.setattr(gm, "_roster", {})
    monkeypatch.setattr(gm, "_applied", {})
    yield monkeypatch


def _pad_is_connected(unprofiled: bool) -> None:
    """One pad in the monitor's roster, profiled or not."""
    gm._roster["40:1b:5f:b9:ea:8d"] = ("054c", "09cc", "PS4 Controller", 3)
    if not unprofiled:
        gm._applied["40:1b:5f:b9:ea:8d"] = (("footprint",), 0)


def test_the_launch_waits_for_a_pad_that_is_not_profiled_yet(launcher, waiting):
    """The defect itself: an emulator that starts before its config is written
    is an emulator with a dead pad, and it will never re-read the file."""
    waiting.setattr(games_router, "PROFILE_BUDGET", 0.6)
    _pad_is_connected(unprofiled=True)

    start = time.monotonic()
    r = _launch(launcher)
    elapsed = time.monotonic() - start

    assert r.status_code == 503, r.text
    assert elapsed >= 0.5, (
        f"the launch went ahead after {elapsed:.2f}s with a pad that had no "
        f"config written — this is the race D1 measured")


def test_a_settled_roster_costs_the_launch_nothing(launcher, waiting):
    """The normal case, and it must be free: one scan period after boot every
    pad is written, and a console that paused before every game would have
    traded one fault for a worse one."""
    waiting.setattr(games_router, "PROFILE_BUDGET", 5.0)
    _pad_is_connected(unprofiled=False)

    start = time.monotonic()
    r = _launch(launcher)
    elapsed = time.monotonic() - start

    assert r.status_code == 503, r.text
    assert elapsed < 0.5, (
        f"a launch with every pad already profiled waited {elapsed:.2f}s")


def test_the_wait_ends_as_soon_as_the_pad_is_written(launcher, waiting):
    """It waits for the event, not for the budget. The budget is only the
    point at which it gives up."""
    waiting.setattr(games_router, "PROFILE_BUDGET", 5.0)
    _pad_is_connected(unprofiled=True)

    async def profiled_shortly() -> None:
        await asyncio.sleep(0.3)
        gm._applied["40:1b:5f:b9:ea:8d"] = (("footprint",), 0)

    original = games_router._await_controller_profiles

    async def wrapped(*a, **k):
        task = asyncio.create_task(profiled_shortly())
        try:
            await original(*a, **k)
        finally:
            await task

    waiting.setattr(games_router, "_await_controller_profiles", wrapped)

    start = time.monotonic()
    r = _launch(launcher)
    elapsed = time.monotonic() - start

    assert r.status_code == 503, r.text
    assert 0.25 <= elapsed < 2.0, (
        f"the launch took {elapsed:.2f}s — it should have moved on the moment "
        f"the pad was written, not sat out the budget")


def test_giving_up_launches_the_game_anyway(launcher, waiting):
    """A budget that expires must cost a possibly-stale config, never a game.

    The pad here never becomes profiled, which is what a pad SDL cannot name
    looks like from this side. Reaching the exec step (503) is the proof the
    launch was not blocked.
    """
    waiting.setattr(games_router, "PROFILE_BUDGET", 0.2)
    _pad_is_connected(unprofiled=True)

    r = _launch(launcher)

    assert r.status_code == 503, (
        f"the profiling wait swallowed the launch — got {r.status_code}. A late "
        f"config is a playable game; this is a dead box.")


def test_a_monitor_that_never_started_is_not_waited_for(launcher, monkeypatch):
    """No monitor means nothing will ever profile anything. Waiting the full
    budget before every single launch, for a pass that is not coming, is how a
    fix for a cold-boot race becomes a permanent tax."""
    monkeypatch.setattr(games_router, "PROFILE_BUDGET", 5.0)
    monkeypatch.setattr(gm, "_running", False)

    start = time.monotonic()
    r = _launch(launcher)
    elapsed = time.monotonic() - start

    assert r.status_code == 503, r.text
    assert elapsed < 0.5, f"waited {elapsed:.2f}s on a monitor that is not running"


def test_the_wait_comes_before_the_emulator_starts(launcher, waiting):
    """Same reason the release sweep does: a config that lands after startup is
    a config the running emulator will never read."""
    waiting.setattr(games_router, "PROFILE_BUDGET", 0.3)
    _pad_is_connected(unprofiled=True)
    order: list[str] = []

    original = games_router._await_controller_profiles

    async def watched(*a, **k):
        await original(*a, **k)
        order.append("profiled")

    async def launch(**_kw):
        order.append("launch")
        raise FileNotFoundError("not installed")

    waiting.setattr(games_router, "_await_controller_profiles", watched)
    waiting.setattr(games_router.process_manager, "launch", launch)

    _launch(launcher)

    assert order == ["profiled", "launch"], order
