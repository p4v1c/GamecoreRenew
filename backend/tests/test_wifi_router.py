"""/api/settings/wifi — the endpoints that hold the box's own connection.

**No test here may reach the real network.** `nmcli` is stubbed in every one of
them, and that is not tidiness: `nmcli dev wifi rescan` run for real on the
machine running this suite drops its Wi-Fi for several seconds, and
`nmcli dev disconnect` takes it down outright. A test suite that can disconnect
the developer is a test suite people stop running.

What is asserted is what a hostile or merely unusual SSID does. The name of a
Wi-Fi network is attacker-controlled input in the most literal sense — anyone
within radio range chooses it, and it arrives here through a scan the box did
itself.
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


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def nmcli(monkeypatch):
    """Every subprocess this router spawns, captured and answered.

    `calls` is the argv of each spawn — the assertion surface for "what
    actually reached the system". `stdin` records what was fed to it, which is
    where the Wi-Fi password is supposed to travel.
    """
    state = {"calls": [], "stdin": [], "stdout": "", "returncode": 0}

    class _Proc:
        returncode = 0

        async def communicate(self, data=None):
            state["stdin"].append(data)
            self.returncode = state["returncode"]
            return state["stdout"].encode(), b""

        async def wait(self):
            return 0

    async def fake_exec(*argv, **kw):
        state["calls"].append(list(argv))
        proc = _Proc()
        proc.returncode = state["returncode"]
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    return state


# ── the SSID never reaches a shell ─────────────────────────────────────────

@pytest.mark.parametrize("ssid", [
    'Cafe "Central"',
    "Bob's Phone",
    "guest; rm -rf /",
    "net && reboot",
    "wifi | tee /etc/passwd",
    "Le Café $(whoami)",
    "back\\slash",
    "两个 世界",
])
def test_a_hostile_ssid_travels_as_one_argument_and_no_further(client, nmcli, ssid):
    """The whole defence, and the reason there is no escaping code anywhere.

    `create_subprocess_exec` takes an argv list — there is no shell to quote
    for, so a semicolon, a backtick or a quote in a network name is just a
    character in one string. This test exists to keep it that way: the day
    someone reaches for `shell=True` or an f-string command line, the SSID
    stops being one element of this list and starts being syntax.
    """
    r = client.post("/api/settings/wifi/connect",
                    json={"ssid": ssid, "password": "hunter2"})
    assert r.status_code == 200, r.text

    argv = nmcli["calls"][0]
    assert argv[0] == "nmcli"
    assert argv.count(ssid) == 1, argv
    # Whole and unaltered: not split on the space, not stripped of its quotes.
    assert argv[-1] == ssid, argv
    assert all(isinstance(a, str) for a in argv)
    # And nothing was handed to a shell along the way.
    assert not any("sh" == Path(a).name for a in argv), argv


def test_the_password_goes_to_stdin_and_never_into_the_argv(client, nmcli):
    """/proc/<pid>/cmdline is world-readable.

    The password used to sit in argv, where every local user could read the
    box's Wi-Fi key for as long as the connect took. `--ask` makes nmcli read
    it from stdin instead.
    """
    secret = "correct horse battery staple"
    client.post("/api/settings/wifi/connect",
                json={"ssid": "Home", "password": secret})

    argv = nmcli["calls"][0]
    assert secret not in argv, argv
    assert "--ask" in argv
    assert nmcli["stdin"][0] == (secret + "\n").encode()


def test_an_ssid_that_looks_like_an_option_is_refused_rather_than_guessed(client,
                                                                          nmcli):
    """The SSID is positional and nmcli marks no end of options, so a name
    starting with '-' would be read as one. Refused, not escaped: guessing at
    another program's option parser is not a thing to be clever about."""
    r = client.post("/api/settings/wifi/connect",
                    json={"ssid": "-rf", "password": ""})
    assert r.status_code == 200
    assert r.json()["ok"] is False
    assert nmcli["calls"] == [], "a refused SSID still spawned nmcli"


def test_a_connect_with_no_password_sends_no_stdin_at_all(client, nmcli):
    """An open network. `--ask` with nothing to answer would hang until the
    timeout with the UI showing a spinner."""
    client.post("/api/settings/wifi/connect", json={"ssid": "OpenNet"})
    assert "--ask" not in nmcli["calls"][0]
    assert nmcli["stdin"][0] is None


# ── a scan that fails is an empty list ─────────────────────────────────────

def test_a_scan_that_returns_nothing_is_an_empty_list(client, nmcli):
    """No adapter, nmcli not installed, NetworkManager not running.

    An exception here is a settings screen that cannot open — and this is the
    screen someone opens precisely because the network is not working.
    """
    nmcli["stdout"] = ""
    nmcli["returncode"] = 1
    r = client.get("/api/settings/wifi/networks")
    assert r.status_code == 200
    assert r.json() == []


def test_a_scan_full_of_garbage_yields_no_network_rather_than_raising(client, nmcli):
    """Half a line, a missing field, a signal that is not a number: whatever
    nmcli emits, the parse must degrade to "nothing found"."""
    nmcli["stdout"] = "\n".join([
        "not a record at all",
        "OnlyOneField",
        ":::",
        "Net:notanumber:WPA2:no",     # signal unparsable -> 0, still a network
    ])
    networks = client.get("/api/settings/wifi/networks").json()
    assert isinstance(networks, list)
    assert [n["ssid"] for n in networks] == ["Net"]
    assert networks[0]["signal"] == 0


def test_a_scanned_ssid_is_returned_verbatim(client, nmcli):
    """What comes back is rendered in the list and posted back to /connect, so
    a name mangled on the way in is a network the owner cannot join."""
    nmcli["stdout"] = "Bob's \"Cafe\":70:WPA2:no"
    networks = client.get("/api/settings/wifi/networks").json()
    assert [n["ssid"] for n in networks] == ["Bob's \"Cafe\""]


def test_an_ssid_containing_a_colon_survives_the_parse(client, nmcli):
    """nmcli -t escapes a colon inside a field as '\\:' — the four fixed fields
    are split from the right for exactly this reason."""
    nmcli["stdout"] = "Floor 2\\: Guest:55:WPA2:no"
    networks = client.get("/api/settings/wifi/networks").json()
    assert [n["ssid"] for n in networks] == ["Floor 2: Guest"]


def test_the_connected_entry_wins_over_a_stronger_duplicate(client, nmcli):
    """One SSID on two access points. The list must show the one the box is
    actually on, however weak, or "connected" contradicts the status bar."""
    nmcli["stdout"] = "\n".join([
        "Home:80:WPA2:no",
        "Home:20:WPA2:yes",
    ])
    networks = client.get("/api/settings/wifi/networks").json()
    assert len(networks) == 1
    assert networks[0]["connected"] is True
    assert networks[0]["signal"] == 20


def test_an_open_network_is_reported_as_unsecured(client, nmcli):
    """nmcli writes '--' for no security, and a padlock on an open network is
    the wrong way round for a mistake to go."""
    nmcli["stdout"] = "\n".join([
        "OpenNet:60:--:no",
        "LockedNet:60:WPA2:no",
    ])
    secured = {n["ssid"]: n["secured"]
               for n in client.get("/api/settings/wifi/networks").json()}
    assert secured == {"OpenNet": False, "LockedNet": True}


# ── status, with nothing connected ─────────────────────────────────────────

def test_the_status_of_a_box_connected_to_nothing_is_well_formed(client, nmcli):
    nmcli["stdout"] = ""
    body = client.get("/api/settings/wifi/status").json()
    assert body["connected"] is False
    assert body["ssid"] == ""
    assert body["ethernet"] == {"connected": False, "iface": "", "ip": ""}


def test_a_wired_box_reports_its_ethernet_and_skips_the_wifi_list(client, nmcli):
    """The UI hides the Wi-Fi picker when the box is plugged in."""
    nmcli["stdout"] = "802-3-ethernet:activated:enp1s0"
    body = client.get("/api/settings/wifi/status").json()
    assert body["ethernet"]["connected"] is True
    assert body["ethernet"]["iface"] == "enp1s0"


def test_a_failed_disconnect_reports_instead_of_raising(client, nmcli):
    """`nmcli dev disconnect` on an interface that is already down.

    The stub is what keeps this test honest AND harmless: run for real, this is
    the call that takes the network off the machine running the suite.
    """
    nmcli["returncode"] = 1
    nmcli["stdout"] = ""
    body = client.request("DELETE", "/api/settings/wifi/connect").json()
    assert body["ok"] is False
    assert [c[:3] for c in nmcli["calls"]][-1] == ["nmcli", "dev", "disconnect"]
