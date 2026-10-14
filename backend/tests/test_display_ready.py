"""After a wake: wait for a lit connector, bounded, before the UI is told.

A fake /sys/class/drm tree; nothing reads the real one.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from backend.services import display_ready, standby


def _conn(root, name, status="connected", enabled="enabled", dpms="On"):
    d = root / name
    d.mkdir(parents=True)
    (d / "status").write_text(status + "\n")
    (d / "enabled").write_text(enabled + "\n")
    if dpms is not None:
        (d / "dpms").write_text(dpms + "\n")
    return d


@pytest.mark.parametrize("status, enabled, dpms, ready", [
    ("connected", "enabled", "On", True),
    ("connected", "enabled", "", True),           # no dpms file
    ("connected", "disabled", "On", False),       # link up, no mode yet
    ("connected", "enabled", "Off", False),       # still blanked
    ("disconnected", "disabled", "Off", False),   # TV not re-sensed yet
])
def test_a_connector_is_ready_when_connected_with_a_lit_mode(status, enabled, dpms, ready):
    assert display_ready.connector_ready(status, enabled, dpms) is ready


def test_any_lit_connector_will_do(tmp_path):
    _conn(tmp_path, "card1-DP-1", "disconnected", "disabled", "Off")
    assert not display_ready.display_ready(tmp_path)
    _conn(tmp_path, "card1-HDMI-A-1")
    assert display_ready.display_ready(tmp_path)


def test_it_waits_for_the_link_to_come_back(tmp_path, monkeypatch):
    monkeypatch.setattr(display_ready, "POLL_SECS", 0.01)
    hdmi = _conn(tmp_path, "card1-HDMI-A-1", "disconnected", "disabled", "Off")

    async def scenario():
        async def tv_resyncs():
            await asyncio.sleep(0.1)
            (hdmi / "status").write_text("connected\n")
            (hdmi / "enabled").write_text("enabled\n")
            (hdmi / "dpms").write_text("On\n")
        asyncio.create_task(tv_resyncs())
        start = time.monotonic()
        ok = await display_ready.wait_for_display(0, tmp_path, max_wait=2)
        return ok, time.monotonic() - start

    ok, took = asyncio.run(scenario())
    assert ok and 0.09 <= took < 1.0


def test_no_screen_gives_up_after_the_bound_and_wakes_anyway(tmp_path, monkeypatch):
    monkeypatch.setattr(display_ready, "POLL_SECS", 0.01)
    _conn(tmp_path, "card1-HDMI-A-1", "disconnected", "disabled", "Off")
    start = time.monotonic()
    assert asyncio.run(display_ready.wait_for_display(0, tmp_path, max_wait=0.1)) is False
    assert time.monotonic() - start < 0.5


def test_no_drm_at_all_is_not_waited_for(tmp_path):
    start = time.monotonic()
    assert asyncio.run(display_ready.wait_for_display(0, tmp_path, max_wait=5)) is True
    assert time.monotonic() - start < 0.5


def test_the_settle_delay_is_a_setting_clamped_to_0_8(monkeypatch, tmp_path):
    monkeypatch.setattr(standby, "CONFIG_FILE", tmp_path / "standby.json")
    assert standby.load_config()["wake_settle_secs"] == 2.5
    assert standby.save_config({"wake_settle_secs": 4})["wake_settle_secs"] == 4.0
    assert standby.save_config({"wake_settle_secs": 30})["wake_settle_secs"] == 8.0
    assert standby.save_config({"wake_settle_secs": -1})["wake_settle_secs"] == 0.0
    assert standby.load_config()["wake_settle_secs"] == 0.0
