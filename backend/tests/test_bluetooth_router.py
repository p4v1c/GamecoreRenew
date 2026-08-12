"""/api/settings/bluetooth — the paired list, and how long it takes to arrive.

**No test here may reach the real adapter.** `bluetoothctl` is stubbed in every
one of them, for the same reason the Wi-Fi suite stubs `nmcli`: a real
`scan on` puts the developer's adapter into discovery for ten seconds, and a
real `disconnect` drops whatever they are listening to.
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
def btctl(monkeypatch):
    """Every `bluetoothctl` this router spawns, answered by argv.

    `answers` maps a fragment of the command to its stdout, so one test can make
    `devices Paired` and `info <mac>` say different things — which the single
    canned stdout the Wi-Fi fixture uses cannot express, and which is the whole
    subject here.
    """
    state = {"calls": [], "answers": {}, "events": []}

    class _Proc:
        returncode = 0

        def __init__(self, argv):
            self.argv = argv

        async def communicate(self, data=None):
            # One yield to the loop before answering. That is what makes the
            # ordering below meaningful: concurrent callers all reach this
            # point before any of them resumes, a sequential one cannot.
            await asyncio.sleep(0)
            if "info" in self.argv:
                state["events"].append(("answered", self.argv[-1]))
            joined = " ".join(self.argv)
            for needle, out in state["answers"].items():
                if needle in joined:
                    return out.encode(), b""
            return b"", b""

        async def wait(self):
            return 0

    async def fake_exec(*argv, **kw):
        state["calls"].append(list(argv))
        if "info" in argv:
            state["events"].append(("spawned", argv[-1]))
        return _Proc(list(argv))

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    return state


PAIRED = "\n".join([
    "Device E4:17:D8:2A:9C:03 8BitDo Ultimate 2C",
    "Device 5C:BA:11:60:7F:AA DualSense Wireless",
    "Device A0:9E:1B:44:D2:18 Marshall Major IV",
])


def test_the_paired_list_carries_each_device_and_its_connected_state(client, btctl):
    btctl["answers"] = {
        "devices Paired": PAIRED,
        "info E4:17:D8:2A:9C:03": "Connected: yes",
        "info 5C:BA:11:60:7F:AA": "Connected: yes",
        "info A0:9E:1B:44:D2:18": "Connected: no",
    }
    body = client.get("/api/settings/bluetooth/devices").json()
    assert [(d["name"], d["connected"]) for d in body] == [
        ("8BitDo Ultimate 2C", True),
        ("DualSense Wireless", True),
        ("Marshall Major IV", False),
    ]
    assert all(d["paired"] for d in body)


def test_every_info_call_goes_out_before_any_of_them_answers(client, btctl):
    """The paired list used to be a sequential loop — one `bluetoothctl info`
    per device, each awaited before the next was spawned. Three paired devices
    therefore cost three round trips end to end, and the settings screen drew
    its empty state in the meantime: "nothing is paired yet", to somebody
    holding a paired pad.

    Asserted on the ORDER of spawn and answer rather than on a clock. Every
    `info` yields to the loop once before answering, so a concurrent
    implementation spawns all three before the first one comes back and a
    sequential one interleaves them strictly. A stopwatch would have been
    flaky; a gate that blocks until all three arrive would hang the suite on
    the very regression it is meant to catch, which is worse than no test.
    """
    btctl["answers"] = {"devices Paired": PAIRED, "info": "Connected: yes"}

    body = client.get("/api/settings/bluetooth/devices").json()
    assert len(body) == 3

    kinds = [kind for kind, _ in btctl["events"]]
    assert kinds == ["spawned"] * 3 + ["answered"] * 3, (
        "the info calls are serialised — each one is being awaited before the "
        f"next is spawned: {btctl['events']}"
    )


def test_a_box_with_nothing_paired_answers_an_empty_list_not_an_error(client, btctl):
    """The screen distinguishes "nothing paired" from "not loaded yet", so this
    has to be a clean empty list rather than a failure it would render as the
    same thing."""
    btctl["answers"] = {"devices Paired": ""}
    assert client.get("/api/settings/bluetooth/devices").json() == []
