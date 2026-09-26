"""configgen.detect_pads: which devices get a player slot in emulator configs."""
from __future__ import annotations

import sys
import types

import pytest

from backend.services.configgen import controllers

BTN_SOUTH = 0x130


class FakeDevice:
    def __init__(self, name, keys, vendor, product, uniq=""):
        self.name, self._keys, self.uniq = name, keys, uniq
        self.info = types.SimpleNamespace(vendor=vendor, product=product)

    def capabilities(self):
        return {1: self._keys}

    def close(self):
        pass


@pytest.fixture
def devices(monkeypatch):
    found: dict[str, FakeDevice] = {}
    module = types.ModuleType("evdev")
    module.InputDevice = lambda path: found[path]
    monkeypatch.setitem(sys.modules, "evdev", module)
    monkeypatch.setattr(controllers.glob, "glob", lambda pattern: list(found))
    return found


def test_a_virtual_keyboard_does_not_push_pad_two_to_player_three(devices):
    """Sunshine's "libvirtualhid Keyboard" declares every key, BTN_SOUTH
    included. Sorted between two real pads, it took player 2 and moved the
    second pad to player 3 in every emulator config."""
    devices["/dev/input/event10"] = FakeDevice("Wireless Controller", [BTN_SOUTH], 0x054C, 0x09CC)
    devices["/dev/input/event11"] = FakeDevice("libvirtualhid Keyboard", list(range(1, 0x2FF)),
                                               0x1209, 0x0002)
    devices["/dev/input/event12"] = FakeDevice("Xbox Wireless Controller", [BTN_SOUTH],
                                               0x045E, 0x0B13)

    assert controllers.detect_pads() == [
        ("054c", "09cc", "Wireless Controller"),
        ("045e", "0b13", "Xbox Wireless Controller"),
    ]
