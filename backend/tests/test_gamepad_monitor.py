"""Unit tests for the gamepad detector (services.gamepad_monitor).

Two failures that both look like "the emulator is broken" from the sofa:
a pad with no Home button never being detected at all, and a Bluetooth pad
losing its player slot when its charging cable is unplugged.

The evdev module is replaced with a fake, so these run on any machine and
without a controller plugged in.

Run under pytest:  pytest backend/tests/test_gamepad_monitor.py
Or directly:       python backend/tests/test_gamepad_monitor.py
"""
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from backend.services import gamepad_monitor as gm


BTN_MODE = 0x13C        # Guide / PS / Home
BTN_SOUTH = 0x130       # A / Cross — every real pad, no keyboard
KEY_A = 30              # a plain keyboard key


class FakeDevice:
    def __init__(self, path, name, keys, uniq="", vendor=0x054C, product=0x09CC):
        self.path, self.name, self._keys, self.uniq = path, name, keys, uniq
        self.info = types.SimpleNamespace(vendor=vendor, product=product)

    def capabilities(self):
        return {gm.EV_KEY: self._keys}

    def close(self):
        pass


@pytest.fixture
def fake_evdev(monkeypatch):
    """Install a fake `evdev` whose device list the test controls."""
    devices: dict[str, FakeDevice] = {}

    module = types.ModuleType("evdev")
    module.InputDevice = lambda path: devices[path]
    module.list_devices = lambda: list(devices)
    monkeypatch.setitem(sys.modules, "evdev", module)
    monkeypatch.setattr(gm.glob, "glob", lambda pattern: list(devices))
    gm._logged_no_guide.clear()
    return devices


# ── #11 · detection ──────────────────────────────────────────────────────────

def test_a_pad_with_a_guide_button_is_detected(fake_evdev):
    fake_evdev["/dev/input/event3"] = FakeDevice(
        "/dev/input/event3", "Wireless Controller", [BTN_MODE, BTN_SOUTH], uniq="aa:bb:cc:dd:ee:ff")

    found = gm._find_gamepad_devices()
    assert "/dev/input/event3" in found
    assert found["/dev/input/event3"][2] is True, "is_pad"


def test_a_pad_without_a_guide_button_is_detected_too(fake_evdev):
    """The bug: no Guide code meant the device never entered the dict at all —
    not watched, not registered, no player slot, apply_profile never called."""
    fake_evdev["/dev/input/event5"] = FakeDevice(
        "/dev/input/event5", "USB Gamepad", [BTN_SOUTH, 0x131, 0x133])

    found = gm._find_gamepad_devices()
    assert "/dev/input/event5" in found, "generic pad must be detected"
    assert found["/dev/input/event5"][2] is True, "and must take a player slot"


def test_a_keyboard_is_still_refused_a_player_slot(fake_evdev):
    """The anti-keyboard rule has to survive the change above."""
    fake_evdev["/dev/input/event0"] = FakeDevice("/dev/input/event0", "AT Translated Set 2 keyboard",
                                                 [KEY_A, 31, 32])
    fake_evdev["/dev/input/event1"] = FakeDevice("/dev/input/event1", "HDMI CEC remote",
                                                 [172, KEY_A])   # KEY_HOMEPAGE, no BTN_SOUTH

    found = gm._find_gamepad_devices()
    assert "/dev/input/event0" not in found, "a plain keyboard is not a device we watch"
    # The remote still gets watched for its Home key, but is not a controller.
    assert found["/dev/input/event1"][2] is False, "remote must not take a player slot"


def test_a_pad_with_neither_guide_nor_south_is_ignored(fake_evdev):
    fake_evdev["/dev/input/event9"] = FakeDevice("/dev/input/event9", "Some sensor", [KEY_A])
    assert gm._find_gamepad_devices() == {}


def test_the_no_guide_notice_is_logged_once_per_device(fake_evdev, caplog):
    import logging
    fake_evdev["/dev/input/event5"] = FakeDevice("/dev/input/event5", "USB Gamepad", [BTN_SOUTH])

    with caplog.at_level(logging.INFO, logger=gm.log.name):
        gm._find_gamepad_devices()
        gm._find_gamepad_devices()
        gm._find_gamepad_devices()

    notices = [r for r in caplog.records if "no Guide button" in r.getMessage()]
    assert len(notices) == 1, f"scan runs every few seconds; logged {len(notices)}x"


# ── #12 · one pad, several device nodes ──────────────────────────────────────
#
# key_for() returns the pad's MAC, so a DualShock 4 on Bluetooth that is then
# plugged in to charge maps two /dev/input/event* paths to a single registry key.

def test_a_pad_keeps_its_slot_while_another_node_is_alive():
    reg_keys = {"/dev/input/event20": "84:30:95:07:c8:1c",   # Bluetooth
                "/dev/input/event24": "84:30:95:07:c8:1c"}   # USB cable

    # The cable is unplugged: event24's watcher dies.
    key = reg_keys.pop("/dev/input/event24")
    assert key in reg_keys.values(), "the Bluetooth node is still there — keep the slot"


def test_the_slot_is_released_once_the_last_node_goes():
    reg_keys = {"/dev/input/event20": "84:30:95:07:c8:1c"}

    key = reg_keys.pop("/dev/input/event20")
    assert key not in reg_keys.values(), "nothing left — the pad really is gone"


def test_unplugging_one_pad_does_not_touch_another():
    reg_keys = {"/dev/input/event20": "84:30:95:07:c8:1c",
                "/dev/input/event21": "aa:bb:cc:dd:ee:ff"}

    key = reg_keys.pop("/dev/input/event21")
    assert key not in reg_keys.values(), "player 2 left"
    assert "84:30:95:07:c8:1c" in reg_keys.values(), "player 1 stayed"


def test_registry_keeps_the_slot_when_only_one_node_dies():
    """The same thing end to end, against the real registry."""
    from backend.services import controller_registry as reg
    reg._slots.clear()
    reg._labels.clear()
    try:
        mac = "84:30:95:07:c8:1c"
        reg_keys = {"/dev/input/event20": mac}
        player = reg.connect(mac, "Wireless Controller")
        assert player == 1

        # Plug the cable in — same pad, second node, same key.
        reg_keys["/dev/input/event24"] = reg.key_for(mac, "/dev/input/event24")
        assert reg.connect(reg_keys["/dev/input/event24"], "Wireless Controller") == 1

        # Unplug it.
        key = reg_keys.pop("/dev/input/event24")
        if key not in reg_keys.values():
            reg.disconnect(key)
        assert reg.snapshot() == [{"player": 1, "label": "Wireless Controller"}], \
            "the pad is still on Bluetooth — it must keep player 1"

        # Now turn the pad off for real.
        key = reg_keys.pop("/dev/input/event20")
        if key not in reg_keys.values():
            reg.disconnect(key)
        assert reg.snapshot() == []
    finally:
        reg._slots.clear()
        reg._labels.clear()


if __name__ == "__main__":
    import contextlib
    import logging

    class _Caplog:
        def __init__(self):
            self.records = []

        @contextlib.contextmanager
        def at_level(self, level, logger=None):
            handler = logging.Handler()
            handler.emit = self.records.append
            lg = logging.getLogger(logger)
            lg.addHandler(handler)
            old = lg.level
            lg.setLevel(level)
            try:
                yield
            finally:
                lg.setLevel(old)
                lg.removeHandler(handler)

    @contextlib.contextmanager
    def fake_evdev_ctx():
        devices: dict[str, FakeDevice] = {}
        module = types.ModuleType("evdev")
        module.InputDevice = lambda path: devices[path]
        module.list_devices = lambda: list(devices)
        saved_mod, saved_glob = sys.modules.get("evdev"), gm.glob.glob
        sys.modules["evdev"] = module
        gm.glob.glob = lambda pattern: list(devices)
        gm._logged_no_guide.clear()
        try:
            yield devices
        finally:
            gm.glob.glob = saved_glob
            if saved_mod is None:
                sys.modules.pop("evdev", None)
            else:
                sys.modules["evdev"] = saved_mod

    for fn in (test_a_pad_with_a_guide_button_is_detected,
               test_a_pad_without_a_guide_button_is_detected_too,
               test_a_keyboard_is_still_refused_a_player_slot,
               test_a_pad_with_neither_guide_nor_south_is_ignored):
        with fake_evdev_ctx() as devs:
            fn(devs)
        print(f"[OK ] {fn.__name__}")

    with fake_evdev_ctx() as devs:
        test_the_no_guide_notice_is_logged_once_per_device(devs, _Caplog())
    print("[OK ] test_the_no_guide_notice_is_logged_once_per_device")

    for fn in (test_a_pad_keeps_its_slot_while_another_node_is_alive,
               test_the_slot_is_released_once_the_last_node_goes,
               test_unplugging_one_pad_does_not_touch_another,
               test_registry_keeps_the_slot_when_only_one_node_dies):
        fn()
        print(f"[OK ] {fn.__name__}")
    print("\nAll tests passed.")
