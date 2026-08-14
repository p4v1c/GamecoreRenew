"""The standby switch, and the two things it forgot.

Neither was reported. Both were found reading `run()` next to the report, and
both are reachable from Settings → Standby with nothing unusual going on.

  · the idle clock kept running while standby was OFF. The loop skipped the
    tick without touching `_last_input`, so the counter went on accumulating
    against a threshold nobody was measuring. Turn standby off, use the box for
    an afternoon, turn it back on — and it sleeps within one poll, straight
    past the screensaver, because it believes nobody has touched it since
    lunchtime.

  · turning standby off while the box was ASLEEP left it asleep. The loop's
    first line is `if not enabled: continue`, so nothing ever undid what the
    last tick had done. From the web UI on a phone — which is where somebody
    would reach for that switch with the television dark — the box answered
    "standby disabled" and stayed exactly as it was.

`run()`'s body is a function now, so a tick can be asked for directly instead of
waiting fifteen real seconds for the loop to come round.
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from backend.services import standby


@pytest.fixture(autouse=True)
def quiet_screen(monkeypatch):
    """xset and cpupower are not this file's business."""
    async def fake_run_cmd(*argv):
        return True
    monkeypatch.setattr(standby, "_run_cmd", fake_run_cmd)


@pytest.fixture(autouse=True)
def awake():
    standby._state = "active"
    standby._last_input = time.monotonic()
    yield
    standby._state = "active"


@pytest.fixture
def not_playing(monkeypatch):
    from backend.services import process_manager as pm
    monkeypatch.setattr(type(pm.process_manager), "is_running", property(lambda self: False))


def idle_for(minutes: float) -> None:
    standby._last_input = time.monotonic() - minutes * 60


CFG_ON = {"enabled": True, "screensaver_mins": 10, "sleep_mins": 20}
CFG_OFF = {**CFG_ON, "enabled": False}


def tick(cfg):
    asyncio.run(standby._tick(cfg))


# ── the clock must not run while nobody is counting ──────────────────────────

def test_a_tick_with_standby_off_restarts_the_idle_clock(not_playing):
    idle_for(180)
    tick(CFG_OFF)
    assert (time.monotonic() - standby._last_input) < 5


def test_turning_standby_back_on_does_not_sleep_the_box_at_once(not_playing):
    # The whole point. An afternoon with standby off, then the switch goes on.
    idle_for(180)
    for _ in range(3):
        tick(CFG_OFF)
    tick(CFG_ON)
    assert standby.get_state() == "active"


def test_the_screensaver_still_comes_up_on_its_own_schedule(not_playing):
    # And the guard on that fix: the clock restarting must not mean standby
    # never happens.
    idle_for(11)
    tick(CFG_ON)
    assert standby.get_state() == "screensaver"


def test_sleep_still_follows(not_playing):
    idle_for(21)
    tick(CFG_ON)
    assert standby.get_state() == "sleep"


def test_a_running_game_still_holds_everything_off(monkeypatch):
    from backend.services import process_manager as pm
    monkeypatch.setattr(type(pm.process_manager), "is_running", property(lambda self: True))
    idle_for(180)
    tick(CFG_ON)
    assert standby.get_state() == "active"
    assert (time.monotonic() - standby._last_input) < 5


# ── the switch must be able to end a standby it is switching off ─────────────

def test_switching_standby_off_wakes_a_sleeping_box(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from backend import main

    monkeypatch.setattr(standby, "CONFIG_FILE", tmp_path / "standby.json")
    with TestClient(main.app) as c:
        # After the client starts, not before: the lifespan calls
        # resume_after_restart(), which sets the state to active by design. A
        # test that arranged the state first would be testing that.
        standby._state = "sleep"
        r = c.post("/api/standby/config", json={"enabled": False})
    assert r.status_code == 200, r.text
    assert standby.get_state() == "active"


def test_switching_standby_on_leaves_the_box_where_it_is(monkeypatch, tmp_path):
    # Only switching OFF wakes. Turning it on is not a reason to light the
    # screen, and a box that woke on any config write would never settle while
    # somebody was adjusting the timings.
    from fastapi.testclient import TestClient
    from backend import main

    monkeypatch.setattr(standby, "CONFIG_FILE", tmp_path / "standby.json")
    with TestClient(main.app) as c:
        standby._state = "screensaver"
        r = c.post("/api/standby/config", json={"enabled": True})
    assert r.status_code == 200, r.text
    assert standby.get_state() == "screensaver"


def test_changing_only_the_timings_does_not_wake(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from backend import main

    monkeypatch.setattr(standby, "CONFIG_FILE", tmp_path / "standby.json")
    with TestClient(main.app) as c:
        standby._state = "screensaver"
        r = c.post("/api/standby/config", json={"screensaver_mins": 5})
    assert r.status_code == 200, r.text
    assert standby.get_state() == "screensaver"
