"""/api/settings/display — the mode, and the way back from a bad one.

**No test here may change the developer's screen.** `xrandr` is stubbed in
every one of them: run for real, this is the module that puts a machine into a
mode its monitor may refuse, and a test suite that can blank the screen is a
test suite nobody runs twice.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.main import app                                    # noqa: E402
from backend.routers.settings import display                    # noqa: E402

QUERY = """Screen 0: minimum 320 x 200, current 1920 x 1080, maximum 16384 x 16384
HDMI-A-1 connected primary 1920x1080+0+0 (normal left inverted right x axis y axis) 700mm x 390mm
   1920x1080     60.00*+  50.00    59.94
   1680x1050     59.95
   1280x720      60.00    50.00
DP-1 disconnected (normal left inverted right x axis y axis)
"""


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clean():
    """No test inherits another's armed timer — it would revert a mode the next
    test never set."""
    display._cancel_pending()
    yield
    display._cancel_pending()


@pytest.fixture
def xrandr(monkeypatch):
    """Every xrandr call, captured and answered."""
    state = {"calls": [], "query": QUERY, "code": 0}

    async def fake_run(*args):
        state["calls"].append(list(args))
        if "--query" in args:
            return 0, state["query"]
        return state["code"], "" if state["code"] == 0 else "xrandr: cannot find mode"

    monkeypatch.setattr(display, "_run", fake_run)
    # `current_game` is a read-only property, so it is replaced on the class
    # rather than on the instance — patching the instance raises, and patching
    # it away entirely would stop this suite from testing the refusal at all.
    monkeypatch.setattr(type(display.process_manager), "current_game",
                        property(lambda self: state.get("playing")))
    return state


# ── reading what the output offers ──────────────────────────────────────────

def test_the_live_mode_is_the_one_marked_with_a_star():
    data = display.parse_modes(QUERY)
    assert data["output"] == "HDMI-A-1"
    assert data["current"] == {"width": 1920, "height": 1080, "rate": 60.00}


def test_a_rate_can_be_both_current_and_preferred():
    """xrandr writes `60.00*+` for a mode that is live AND the monitor's
    preferred one. Testing the marker for equality instead of membership loses
    the current mode on every well-behaved monitor."""
    data = display.parse_modes(QUERY)
    rates = [m["rate"] for m in data["modes"] if m["height"] == 1080 and m["width"] == 1920]
    assert rates == [60.00, 50.00, 59.94]


def test_a_second_connected_output_is_left_alone():
    """Two screens need a layout, not a mode. Picking one at random moves a
    picture the owner cannot see, so the first connected output is the only one
    this serves."""
    two = QUERY.replace("DP-1 disconnected", "DP-1 connected 1280x1024+1920+0")
    two += "   1280x1024     75.00*\n"
    data = display.parse_modes(two)
    assert data["output"] == "HDMI-A-1"
    assert all(m["width"] != 1280 or m["height"] != 1024 for m in data["modes"])


def test_a_box_with_no_display_answers_an_empty_list_not_an_error(client, xrandr, monkeypatch):
    async def no_x(*args):
        return 1, "Can't open display"
    monkeypatch.setattr(display, "_run", no_x)
    body = client.get("/api/settings/display").json()
    assert body["modes"] == [] and body["current"] is None


# ── what it refuses ─────────────────────────────────────────────────────────

def test_a_mode_the_output_never_advertised_is_refused(client, xrandr):
    """xrandr accepts any geometry. Handing it one the monitor does not know is
    walking into the black screen this module exists to make survivable."""
    r = client.post("/api/settings/display/mode",
                    json={"width": 3840, "height": 2160, "rate": 60.0})
    assert r.status_code == 400
    assert not any("--mode" in c for c in xrandr["calls"])


def test_the_mode_cannot_change_while_a_game_is_running(client, xrandr):
    """Changing the mode under an emulator is the shortest way to crash it, and
    nobody is reading this screen then."""
    xrandr["playing"] = {"system_id": "rpcs3"}
    r = client.post("/api/settings/display/mode",
                    json={"width": 1280, "height": 720, "rate": 60.0})
    assert r.status_code == 409
    assert not any("--mode" in c for c in xrandr["calls"])


def test_asking_for_the_mode_already_on_screen_arms_nothing(client, xrandr):
    """No change, so nothing to revert — and arming a timer would make the box
    ask "can you see this?" about a screen that never moved."""
    r = client.post("/api/settings/display/mode",
                    json={"width": 1920, "height": 1080, "rate": 60.0})
    assert r.status_code == 200 and r.json()["changed"] is False
    assert display._pending is None


# ── the way back ────────────────────────────────────────────────────────────

def test_applying_a_mode_arms_the_revert(client, xrandr):
    r = client.post("/api/settings/display/mode",
                    json={"width": 1280, "height": 720, "rate": 60.0})
    assert r.status_code == 200 and r.json()["changed"] is True
    applied = [c for c in xrandr["calls"] if "--mode" in c][-1]
    assert "1280x720" in applied and "60" in applied
    assert display._pending is not None, "nothing would bring the old mode back"


def test_confirming_disarms_it(client, xrandr):
    client.post("/api/settings/display/mode",
                json={"width": 1280, "height": 720, "rate": 60.0})
    assert client.post("/api/settings/display/confirm").json()["confirmed"] is True
    assert display._pending is None


def test_confirming_twice_is_not_an_error(client, xrandr):
    """A second press, or a reload after the timer already fired, means the same
    thing as the first — and the player pressing again is not a bug report."""
    assert client.post("/api/settings/display/confirm").status_code == 200


def test_the_old_mode_comes_back_when_nobody_confirms(xrandr):
    """The one that matters, and the one nobody can test on a real television
    from here: silence means the screen is unreadable, so the previous mode is
    put back without being asked.

    Driven directly rather than through the client: the timer outlives the
    request that armed it, which is the whole point, and a request-scoped test
    would be asserting the opposite of the design.
    """
    previous = {"output": "HDMI-A-1", "width": 1920, "height": 1080, "rate": 60.0}

    async def scenario():
        await display._revert_after(0.01, previous)

    asyncio.run(scenario())
    applied = [c for c in xrandr["calls"] if "--mode" in c]
    assert applied, "the screen was left in a mode nobody could see"
    assert "1920x1080" in applied[-1]


def test_a_confirmation_stops_the_revert_before_it_fires(xrandr):
    """Cancellation is the success path: /confirm cancels the task, and a
    cancelled timer must put nothing back — otherwise confirming a mode would
    undo it a few seconds later."""
    previous = {"output": "HDMI-A-1", "width": 1920, "height": 1080, "rate": 60.0}

    async def scenario():
        task = asyncio.create_task(display._revert_after(5, previous))
        await asyncio.sleep(0)          # let it reach the sleep
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())
    assert not [c for c in xrandr["calls"] if "--mode" in c]
