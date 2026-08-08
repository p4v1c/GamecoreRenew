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

import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend import main                                      # noqa: E402
from backend.routers import games as games_router             # noqa: E402
from backend.services import controller_registry as reg       # noqa: E402
from backend.services import process_manager as pm            # noqa: E402

GHOST = {"id": "ghost", "label": "Ghost", "kind": "emulator",
         "path": "/usr/bin/definitely-not-installed", "args": "", "romsPath": ""}


@pytest.fixture
def launcher(monkeypatch):
    """A client whose launch always fails at the exec step.

    Deliberate: the cleanup runs BEFORE `process_manager.launch`, so a launch
    that cannot succeed still exercises it in full, and no emulator is started
    from a test.
    """
    monkeypatch.setattr(games_router, "list_all", lambda: [GHOST])
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
