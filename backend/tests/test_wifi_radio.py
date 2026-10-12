"""/api/settings/wifi/radio and the `radio` field of /status.

`nmcli` is stubbed in every test: `nmcli radio wifi off` run for real takes the
machine running the suite off the network, the developer's session included.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.main import app                          # noqa: E402
from backend.services.wifi_radio import parse_radio   # noqa: E402


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def nmcli(monkeypatch):
    """A fake NetworkManager: `radio` holds the state, `calls` every argv."""
    state = {"calls": [], "hw": "enabled", "wifi": "enabled",
             "set_code": 0, "set_out": "", "follow": True, "hang": False}

    class _Proc:
        returncode = 0

        def __init__(self, argv):
            self.argv = argv

        async def communicate(self, data=None):
            argv = self.argv
            if state["hang"]:
                await asyncio.Event().wait()
            if argv[1:3] == ["radio", "wifi"] and len(argv) == 4:
                self.returncode = state["set_code"]
                if self.returncode == 0 and state["follow"]:
                    state["wifi"] = "enabled" if argv[3] == "on" else "disabled"
                return b"", state["set_out"].encode()
            if "radio" in argv:
                return f"{state['hw']}:{state['wifi']}\n".encode(), b""
            return b"", b""

        async def wait(self):
            return 0

        def kill(self):
            state["killed"] = True

    async def fake_exec(*argv, **kw):
        state["calls"].append(list(argv))
        return _Proc(list(argv))

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    return state


@pytest.mark.parametrize("text, expected", [
    ("enabled:enabled\n", True),
    ("enabled:disabled", False),
    ("disabled:enabled", False),   # rfkill hard block: software "on" changes nothing
    ("missing:disabled", None),    # no Wi-Fi hardware: no switch to draw
    ("", None),
    ("garbage", None),
])
def test_parse_radio_reads_hardware_and_software_state(text, expected):
    assert parse_radio(text) is expected


def test_status_reports_the_radio(client, nmcli):
    nmcli["wifi"] = "disabled"
    body = client.get("/api/settings/wifi/status").json()
    assert body["radio"] is False
    assert body["connected"] is False


@pytest.mark.parametrize("enabled, word", [(False, "off"), (True, "on")])
def test_set_radio_runs_nmcli_and_returns_the_state_read_back(client, nmcli, enabled, word):
    nmcli["wifi"] = "disabled" if enabled else "enabled"
    r = client.post("/api/settings/wifi/radio", json={"enabled": enabled})
    assert r.status_code == 200
    assert r.json() == {"enabled": enabled}
    assert ["nmcli", "radio", "wifi", word] in nmcli["calls"]


def test_set_radio_refusal_is_reported_with_nmcli_sentence(client, nmcli):
    nmcli["set_code"] = 1
    nmcli["set_out"] = "Error: failed to disable WiFi: Not authorized to control networking."
    r = client.post("/api/settings/wifi/radio", json={"enabled": False})
    assert r.status_code == 502
    assert "Not authorized" in r.json()["detail"]


def test_turning_on_under_a_hardware_block_is_an_error_not_a_silent_success(client, nmcli):
    nmcli["hw"] = "disabled"
    nmcli["wifi"] = "disabled"
    r = client.post("/api/settings/wifi/radio", json={"enabled": True})
    assert r.status_code == 409
    assert "hardware switch" in r.json()["detail"]


def test_a_hung_nmcli_is_killed_and_answered(client, nmcli, monkeypatch):
    from backend.services import wifi_radio
    monkeypatch.setattr(wifi_radio, "NMCLI_SECS", 0.01)
    nmcli["hang"] = True
    r = client.post("/api/settings/wifi/radio", json={"enabled": False})
    assert r.status_code == 504
    assert nmcli.get("killed") is True


def test_radio_request_needs_a_boolean(client, nmcli):
    r = client.post("/api/settings/wifi/radio", json={"enabled": "maybe"})
    assert r.status_code == 422
    assert not any(c[1:3] == ["radio", "wifi"] for c in nmcli["calls"])
