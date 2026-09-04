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
    state = {"calls": [], "stdin": [], "stdout": "", "returncode": 0,
             # Optional argv -> stdout router, for the tests that need nmcli to
             # answer `con show` with something other than the canned stdout.
             "reply": None,
             # Optional argv predicate: a spawn it matches never returns, which
             # is how a test reaches the timeout path without waiting for one.
             "hang": None}

    class _Proc:
        returncode = 0
        killed = False
        spawned: list = state.setdefault("procs", [])

        async def communicate(self, data=None):
            state["stdin"].append(data)
            if state["hang"] and state["hang"](self.argv):
                await asyncio.Event().wait()
            self.returncode = state["returncode"]
            return self.out.encode(), b""

        async def wait(self):
            return 0

        def kill(self):
            self.killed = True

    async def fake_exec(*argv, **kw):
        argv = list(argv)
        state["calls"].append(argv)
        proc = _Proc()
        proc.argv = argv
        proc.spawned.append(proc)
        proc.returncode = state["returncode"]
        proc.out = state["reply"](argv) if state["reply"] else state["stdout"]
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    return state


def connect_call(nmcli):
    """The argv that actually joined a network.

    A connect carrying a password clears the saved profiles for that SSID
    first, so the join is no longer the first thing nmcli is asked to do.
    """
    for argv in nmcli["calls"]:
        if "connect" in argv:
            return argv
    raise AssertionError(f"no connect among {nmcli['calls']}")


def sent_stdin(nmcli):
    """What was fed to a spawn that was actually given something."""
    return [d for d in nmcli["stdin"] if d is not None]

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

    argv = connect_call(nmcli)
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

    argv = connect_call(nmcli)
    assert secret not in argv, argv
    assert "--ask" in argv
    assert sent_stdin(nmcli) == [(secret + "\n").encode()]
    # And it reached nothing else on the way — a profile lookup must not be
    # handed the password just because it runs in the same request.
    for call, data in zip(nmcli["calls"], nmcli["stdin"]):
        assert secret not in call, call


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


# ── a saved profile must never outlive the password that made it ───────────
#
# The failure these come from, in order: the box had a profile for the network
# from before its key was changed. Joining it again created `<SSID> 1` rather
# than replacing the first, NetworkManager answered its own secret request from
# the stale profile ("secrets exist. No new secrets needed") and never asked
# for the key that had just been typed, and every retry re-used the wrong one.
# What reached the screen minutes later was the desktop's own password dialog,
# which reads as the system asking for administrator rights.

def _saved(**profiles):
    """An nmcli that answers `con show` with the given profiles.

    `_saved(abc="Home", def_="Home")` is two profiles for one SSID — the shape
    that matters, because nmcli made the second one itself and called it
    `Home 1`.
    """
    def reply(argv):
        if argv[:5] == ["nmcli", "-t", "-f", "UUID,TYPE", "con"]:
            return "".join(f"{u}:802-11-wireless\n" for u in profiles)
        if argv[:4] == ["nmcli", "-t", "-f", "802-11-wireless.ssid"]:
            return f"802-11-wireless.ssid:{profiles[argv[-1]]}\n"
        return ""
    return reply


def _deleted(nmcli):
    return [c[-1] for c in nmcli["calls"] if c[1:4] == ["con", "delete", "uuid"]]


def test_a_password_attempt_clears_what_was_saved_for_that_ssid_first(client, nmcli):
    """Both profiles go, and they go before the join.

    Order is the whole assertion. Deleting afterwards would leave the stale key
    in place for the one attempt that mattered, which is precisely the bug.
    """
    nmcli["reply"] = _saved(aaa="CrackMe", bbb="CrackMe")
    client.post("/api/settings/wifi/connect",
                json={"ssid": "CrackMe", "password": "aaaaaaaa"})

    assert sorted(_deleted(nmcli)) == ["aaa", "bbb"]
    names = ["/".join(c) for c in nmcli["calls"]]
    assert max(i for i, n in enumerate(names) if "con/delete" in n) \
        < min(i for i, n in enumerate(names) if "connect" in n)


def test_a_profile_is_matched_on_its_ssid_not_on_its_name(client, nmcli):
    """`nmcli` names its own second profile for a network `<SSID> 1`.

    Matching on the name would walk straight past the duplicate it just made —
    and past the one profile guaranteed to hold a key the player has replaced.
    """
    nmcli["reply"] = _saved(dup="CrackMe", other="Neighbour")
    client.post("/api/settings/wifi/connect",
                json={"ssid": "CrackMe", "password": "aaaaaaaa"})

    assert _deleted(nmcli) == ["dup"], "a profile for another network was deleted"


def test_a_connect_with_no_password_leaves_saved_profiles_alone(client, nmcli):
    """Nothing was supplied, so nothing is out of date.

    Rejoining an open network, or one the box already knows, must not cost the
    player the profile they had.
    """
    nmcli["reply"] = _saved(aaa="OpenNet")
    client.post("/api/settings/wifi/connect", json={"ssid": "OpenNet"})

    assert _deleted(nmcli) == []


def test_a_refused_password_is_not_left_saved_for_the_next_attempt(client, nmcli):
    """The profile nmcli just wrote holds the key that was refused.

    Left there it shadows the next attempt exactly as the previous one shadowed
    this — the player retypes, correctly this time, and the box tries the wrong
    key again without ever asking.
    """
    nmcli["returncode"] = 1
    nmcli["stdout"] = "Error: Secrets were required, but not provided."
    calls = {"n": 0}

    def reply(argv):
        # Nothing saved going in; one profile saved by the failed join.
        if argv[:5] == ["nmcli", "-t", "-f", "UUID,TYPE", "con"]:
            calls["n"] += 1
            return "made-by-nmcli:802-11-wireless\n" if calls["n"] > 1 else ""
        if argv[:4] == ["nmcli", "-t", "-f", "802-11-wireless.ssid"]:
            return "802-11-wireless.ssid:CrackMe\n"
        return nmcli["stdout"]

    nmcli["reply"] = reply
    r = client.post("/api/settings/wifi/connect",
                    json={"ssid": "CrackMe", "password": "wrong"})

    assert r.json()["wrong_password"] is True
    assert _deleted(nmcli) == ["made-by-nmcli"]


def test_a_connect_that_times_out_kills_nmcli_rather_than_orphaning_it(
        client, nmcli, monkeypatch):
    """A cancelled await is not a stopped process.

    The abandoned nmcli keeps the secret agent it registered, NetworkManager
    keeps asking it for a password nobody is left to type, and when it gives up
    the request falls to the desktop's agent — which puts a Wi-Fi password
    dialog on screen minutes after GameCore said the attempt had failed.
    """
    from backend.routers.settings import wifi as mod
    monkeypatch.setattr(mod, "CONNECT_TIMEOUT", 0.05)
    nmcli["reply"] = _saved()
    nmcli["hang"] = lambda argv: "connect" in argv

    r = client.post("/api/settings/wifi/connect",
                    json={"ssid": "CrackMe", "password": "aaaaaaaa"})

    assert r.json() == {"ok": False, "wrong_password": False,
                        "error": "Connection timed out"}
    hung = [p for p in nmcli["procs"] if "connect" in p.argv]
    assert hung and all(p.killed for p in hung), "nmcli was left running"

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


# ── the radio detail behind a network ───────────────────────────────────────
#
# Parsed as pure functions wherever possible. The `nmcli` fixture answers every
# spawn with one canned stdout, so a test that needs `dev wifi` and `dev show`
# to say different things cannot be written against it — and widening the
# fixture would change what every test above is standing on.

from backend.routers.settings.wifi import (            # noqa: E402
    _band, _parse_dev_show, _parse_wifi_details,
)


def test_a_mac_address_survives_the_colon_split():
    """`GENERAL.HWADDR` is a value made entirely of the delimiter.

    Splitting on the last colon — which is right for a scan line, where the
    SSID leads — truncates it to `04` here. The key is what is fixed in this
    file, so the split goes on the first colon instead.
    """
    parsed = _parse_dev_show("GENERAL.HWADDR:DC\\:A6\\:32\\:11\\:8F\\:04")
    assert parsed["mac"] == "DC:A6:32:11:8F:04"


def test_every_dns_server_is_kept_not_only_the_first():
    parsed = _parse_dev_show("\n".join([
        "IP4.GATEWAY:192.168.1.1",
        "IP4.DNS[1]:9.9.9.9",
        "IP4.DNS[2]:149.112.112.112",
    ]))
    assert parsed["gateway"] == "192.168.1.1"
    assert parsed["dns"] == ["9.9.9.9", "149.112.112.112"]


def test_a_field_nmcli_cannot_answer_is_absent_rather_than_blank():
    """nmcli prints the key with an empty value, or '--', for what it does not
    know. A row rendered from that reads as "this network has no gateway",
    which is a different and wrong statement."""
    parsed = _parse_dev_show("IP4.GATEWAY:\nIP4.DNS[1]:--\nGENERAL.HWADDR:")
    assert parsed == {"gateway": "", "dns": [], "mac": ""}


@pytest.mark.parametrize("freq,expected", [
    ("2412 MHz", "2.4 GHz"),
    ("5180 MHz", "5 GHz"),
    ("5955 MHz", "6 GHz"),
    ("", ""),
    ("not a frequency", ""),
])
def test_the_band_is_named_from_the_frequency(freq, expected):
    assert _band(freq) == expected


def test_an_ssid_with_a_colon_keeps_its_detail_row():
    """Same hazard as the scan: the SSID leads and is attacker-chosen, so the
    four fixed fields are taken off the end."""
    rows = _parse_wifi_details("Cafe\\:Central:WPA2:44:5180 MHz:866 Mbit/s")
    assert rows[0]["ssid"] == "Cafe:Central"
    assert rows[0]["channel"] == 44
    assert rows[0]["band"] == "5 GHz"
    assert rows[0]["rate"] == "866 Mb/s"


def test_an_open_network_is_labelled_rather_than_left_as_two_dashes():
    rows = _parse_wifi_details("Hotspot:--:36:5180 MHz:200 Mbit/s")
    assert rows[0]["security"] == "Open"


def test_one_row_per_ssid_however_many_access_points_answer():
    """A mesh lists one line per BSSID. Three rows for one name would draw the
    same network three times in the picker."""
    rows = _parse_wifi_details("\n".join([
        "Home:WPA2:44:5180 MHz:866 Mbit/s",
        "Home:WPA2:1:2412 MHz:144 Mbit/s",
    ]))
    assert [r["ssid"] for r in rows] == ["Home"]
    assert rows[0]["channel"] == 44          # nmcli orders strongest first


def test_a_detail_line_that_is_short_or_junk_is_skipped_not_fatal():
    rows = _parse_wifi_details("\n".join(["garbage", "", "A:B", ":WPA2:1:2412 MHz:1"]))
    assert rows == []


def test_the_details_endpoint_asks_nmcli_for_the_fields_it_parses(client, nmcli):
    nmcli["stdout"] = "Livebox:WPA3:44:5180 MHz:866 Mbit/s"
    body = client.get("/api/settings/wifi/details").json()
    assert body == [{"ssid": "Livebox", "security": "WPA3", "channel": 44,
                     "band": "5 GHz", "rate": "866 Mb/s"}]
    assert nmcli["calls"][-1] == [
        "nmcli", "-t", "-f", "SSID,SECURITY,CHAN,FREQ,RATE", "dev", "wifi"]


def test_a_disconnected_box_still_reports_gateway_dns_and_mac(client, nmcli):
    """The same keys either way. A screen reading `body.gateway` must not have
    to know whether the box was connected when it asked — a missing key renders
    as `undefined` into a table row."""
    nmcli["stdout"] = ""
    body = client.get("/api/settings/wifi/status").json()
    assert body["gateway"] == ""
    assert body["dns"] == []
    assert body["mac"] == ""
