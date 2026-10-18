"""Which paired Bluetooth devices may wake the box: pads, never keyboards or mice.

`busctl` is faked; the GetManagedObjects reply below is the shape busctl
prints with `--json=short`.
"""
from __future__ import annotations

import asyncio
import json

from backend.services import bt_wake


def _dev(mac, icon, paired=True, wake=False, connected=False):
    props = {"Address": {"type": "s", "data": mac},
             "Paired": {"type": "b", "data": paired},
             "Connected": {"type": "b", "data": connected}}
    if icon:
        props["Icon"] = {"type": "s", "data": icon}
    if wake is not None:
        props["WakeAllowed"] = {"type": "b", "data": wake}
    return {"org.bluez.Device1": props}


OBJECTS = {
    "/org/bluez/hci0": {"org.bluez.Adapter1": {}},
    "/org/bluez/hci0/dev_AA_00_00_00_00_01": _dev("AA:00:00:00:00:01", "input-gaming"),
    "/org/bluez/hci0/dev_AA_00_00_00_00_02": _dev("AA:00:00:00:00:02", "input-keyboard"),
    "/org/bluez/hci0/dev_AA_00_00_00_00_03": _dev("AA:00:00:00:00:03", "input-mouse"),
    "/org/bluez/hci0/dev_AA_00_00_00_00_04": _dev("AA:00:00:00:00:04", "input-gaming", paired=False),
    "/org/bluez/hci0/dev_AA_00_00_00_00_05": _dev("AA:00:00:00:00:05", "input-gaming", wake=True),
    "/org/bluez/hci0/dev_AA_00_00_00_00_06": _dev("AA:00:00:00:00:06", "input-gaming", wake=None),
    "/org/bluez/hci0/dev_AA_00_00_00_00_07": _dev("AA:00:00:00:00:07", ""),
    "/org/bluez/hci0/dev_AA_00_00_00_00_08": _dev("AA:00:00:00:00:08", "audio-headset"),
}


def test_only_paired_pads_still_refused_wake_are_armed():
    assert bt_wake.pads_to_arm(OBJECTS, set()) == ["/org/bluez/hci0/dev_AA_00_00_00_00_01"]


def test_a_pad_on_gamecores_roster_counts_even_without_the_gaming_icon():
    """A pad BlueZ draws with no icon is still a pad if the evdev scan says so."""
    armed = bt_wake.pads_to_arm(OBJECTS, {"aa:00:00:00:00:07"})
    assert "/org/bluez/hci0/dev_AA_00_00_00_00_07" in armed
    assert "/org/bluez/hci0/dev_AA_00_00_00_00_08" not in armed


def test_a_keyboard_is_never_armed_even_if_the_roster_names_it():
    armed = bt_wake.pads_to_arm(OBJECTS, {"aa:00:00:00:00:02", "aa:00:00:00:00:03"})
    assert not any(p.endswith(("_02", "_03")) for p in armed)


def test_roster_keys_that_are_device_paths_are_not_macs(monkeypatch):
    monkeypatch.setattr(bt_wake.gamepad_monitor, "roster", lambda: {
        "84:30:95:07:c8:1c": ("054c", "09cc", "DS4", 5), "/dev/input/event7": ("2dc8", "6001", "8BitDo", 3)})
    assert bt_wake.roster_macs() == {"84:30:95:07:c8:1c"}


def test_a_pass_sets_wake_allowed_through_busctl(monkeypatch):
    calls = []

    async def busctl(*args):
        calls.append(args)
        if "GetManagedObjects" in args:
            return 0, json.dumps({"type": "a{oa{sa{sv}}}", "data": [OBJECTS]})
        return 0, ""

    monkeypatch.setattr(bt_wake, "_busctl", busctl)
    monkeypatch.setattr(bt_wake.gamepad_monitor, "roster", lambda: {})
    assert asyncio.run(bt_wake.set_wake_permissions()) is True
    assert calls[1] == ("set-property", "org.bluez", "/org/bluez/hci0/dev_AA_00_00_00_00_01",
                        "org.bluez.Device1", "WakeAllowed", "b", "true")
    assert len(calls) == 2


def test_bluez_not_answering_is_reported_as_unknown(monkeypatch):
    async def busctl(*args):
        return 1, "Failed to connect to bus"
    monkeypatch.setattr(bt_wake, "_busctl", busctl)
    assert asyncio.run(bt_wake.set_wake_permissions()) is None


def test_the_loop_passes_again_when_a_new_pad_connects(monkeypatch):
    passes = []
    roster = {}

    async def one_pass():
        passes.append(set(roster))
        return True

    monkeypatch.setattr(bt_wake, "set_wake_permissions", one_pass)
    monkeypatch.setattr(bt_wake.gamepad_monitor, "roster", lambda: dict(roster))
    monkeypatch.setattr(bt_wake, "ROSTER_POLL_SECS", 0.01)

    async def scenario():
        task = asyncio.create_task(bt_wake.run())
        await asyncio.sleep(0.05)
        roster["84:30:95:07:c8:1c"] = ("054c", "09cc", "DS4", 5)
        await asyncio.sleep(0.05)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())
    assert len(passes) == 2, "one pass at start, one for the new pad, none in between"


# What the box had on 16/10: an Xbox pad and a DS4 on, the JBL speaker, a mouse.
AT_SLEEP = {
    "/org/bluez/hci0/dev_5C_BA_37_63_EE_62": _dev("5C:BA:37:63:EE:62", "input-gaming", wake=True, connected=True),
    "/org/bluez/hci0/dev_40_1B_5F_B9_EA_8D": _dev("40:1B:5F:B9:EA:8D", "", wake=True, connected=True),
    "/org/bluez/hci0/dev_AA_00_00_00_00_09": _dev("AA:00:00:00:00:09", "input-gaming", wake=True),
    "/org/bluez/hci0/dev_AA_00_00_00_00_0A": _dev("AA:00:00:00:00:0A", "audio-card", wake=None, connected=True),
    "/org/bluez/hci0/dev_00_00_13_08_05_04": _dev("00:00:13:08:05:04", "input-mouse", wake=True, connected=True),
    "/org/bluez/hci0/dev_AA_00_00_00_00_0B": _dev("AA:00:00:00:00:0B", "input-keyboard", wake=True),
}


def _fake_bus(monkeypatch, objects):
    calls = []

    async def busctl(*args):
        calls.append(args)
        if "GetManagedObjects" in args:
            return 0, json.dumps({"type": "a{oa{sa{sv}}}", "data": [objects]})
        return 0, ""

    monkeypatch.setattr(bt_wake, "_busctl", busctl)
    return calls


def test_only_connected_pads_are_turned_off_never_the_speaker_or_the_mouse():
    off = bt_wake.pads_to_turn_off(AT_SLEEP, {"40:1b:5f:b9:ea:8d"})
    assert off == ["/org/bluez/hci0/dev_40_1B_5F_B9_EA_8D", "/org/bluez/hci0/dev_5C_BA_37_63_EE_62"]


def test_turning_pads_off_disconnects_them_over_bluez_and_leaves_their_wake(monkeypatch):
    calls = _fake_bus(monkeypatch, AT_SLEEP)
    monkeypatch.setattr(bt_wake.gamepad_monitor, "roster", lambda: {"40:1b:5f:b9:ea:8d": ()})
    assert asyncio.run(bt_wake.turn_off_pads()) == 2
    sent = sorted(c for c in calls if "GetManagedObjects" not in c)
    assert sent == [
        ("call", "org.bluez", "/org/bluez/hci0/dev_40_1B_5F_B9_EA_8D", "org.bluez.Device1", "Disconnect"),
        ("call", "org.bluez", "/org/bluez/hci0/dev_5C_BA_37_63_EE_62", "org.bluez.Device1", "Disconnect"),
    ]


def test_no_bluez_turns_nothing_off(monkeypatch):
    async def busctl(*args):
        return 1, "Failed to connect to bus"
    monkeypatch.setattr(bt_wake, "_busctl", busctl)
    assert asyncio.run(bt_wake.turn_off_pads()) == 0


def test_mice_and_keyboards_lose_their_wake_and_pads_keep_theirs(monkeypatch):
    assert bt_wake.others_to_disarm(AT_SLEEP) == [
        "/org/bluez/hci0/dev_00_00_13_08_05_04", "/org/bluez/hci0/dev_AA_00_00_00_00_0B"]
    calls = _fake_bus(monkeypatch, AT_SLEEP)
    monkeypatch.setattr(bt_wake.gamepad_monitor, "roster", lambda: {})
    assert asyncio.run(bt_wake.set_wake_permissions()) is True
    sets = [c for c in calls if c[0] == "set-property"]
    assert sets == [
        ("set-property", "org.bluez", "/org/bluez/hci0/dev_00_00_13_08_05_04",
         "org.bluez.Device1", "WakeAllowed", "b", "false"),
        ("set-property", "org.bluez", "/org/bluez/hci0/dev_AA_00_00_00_00_0B",
         "org.bluez.Device1", "WakeAllowed", "b", "false"),
    ]
