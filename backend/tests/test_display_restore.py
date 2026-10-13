"""After a wake, the confirmed display mode comes back if the TV handed X another.

xrandr is stubbed in every test: nothing here may change a real screen.
"""
from __future__ import annotations

import asyncio

import pytest

from backend.services import display

QUERY = """Screen 0: minimum 320 x 200, current 1280 x 720, maximum 16384 x 16384
HDMI-A-1 connected primary 1280x720+0+0 (normal left inverted right x axis y axis) 700mm x 390mm
   1920x1080     60.00 +  50.00    59.94
   1280x720      60.00*   50.00
"""


@pytest.fixture
def xrandr(monkeypatch, tmp_path):
    state = {"calls": [], "query": QUERY, "playing": False}

    async def fake_run(*args):
        state["calls"].append(list(args))
        return 0, state["query"] if "--query" in args else ""

    monkeypatch.setattr(display, "_run", fake_run)
    monkeypatch.setattr(display, "_kscreen_available", lambda: False)
    monkeypatch.setattr(type(display.process_manager), "is_running",
                        property(lambda self: state["playing"]))
    monkeypatch.setattr(display, "config_dir", lambda: tmp_path)
    display._cancel_pending()
    return state


def _prefer(tmp_path, **mode):
    (tmp_path / display.PREFERENCE_FILE).write_text(
        '{"width": %(width)d, "height": %(height)d, "rate": %(rate)s, "output": "%(output)s"}' % mode)


def _applied(state):
    return [c for c in state["calls"] if "--mode" in c]


def test_the_confirmed_mode_is_put_back(xrandr, tmp_path):
    _prefer(tmp_path, width=1920, height=1080, rate=60.0, output="HDMI-A-1")
    assert asyncio.run(display.restore_preferred()) is True
    assert _applied(xrandr) == [["xrandr", "--output", "HDMI-A-1", "--mode", "1920x1080",
                                 "--rate", "60"]]


def test_the_mode_already_on_screen_is_left_alone(xrandr, tmp_path):
    _prefer(tmp_path, width=1280, height=720, rate=60.0, output="HDMI-A-1")
    assert asyncio.run(display.restore_preferred()) is False
    assert _applied(xrandr) == []


def test_no_confirmed_mode_means_nothing_to_restore(xrandr):
    assert asyncio.run(display.restore_preferred()) is False
    assert xrandr["calls"] == []


def test_another_output_or_an_unadvertised_mode_is_not_forced(xrandr, tmp_path):
    _prefer(tmp_path, width=1920, height=1080, rate=60.0, output="DP-1")
    assert asyncio.run(display.restore_preferred()) is False
    _prefer(tmp_path, width=3840, height=2160, rate=60.0, output="HDMI-A-1")
    assert asyncio.run(display.restore_preferred()) is False
    assert _applied(xrandr) == []
