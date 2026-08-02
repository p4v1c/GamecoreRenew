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
# plugged in to charge maps two /dev/input/event* paths to a single registry
# key. These used to assert on a dict literal that mirrored the monitor's own
# condition, so deleting that condition would have left them all green. They
# now go through pads_by_key() and _reconcile(), which is where the decision
# actually lives.

import asyncio

from backend.services import controller_profiles as cp
from backend.services import controller_registry as reg


def _node(path, mac, vendor="054c", product="09cc", name="Wireless Controller"):
    return {path: (name, mac, True, vendor, product)}


class _FakeWS:
    async def broadcast(self, *_a, **_k):
        pass


def _make_roster(monkeypatch):
    """A recorder around the profiling calls, with the registry reset.

    Split out of the fixture so the `python backend/tests/…` runner at the
    bottom can use it too."""
    calls: list[tuple] = []
    reg._slots.clear(); reg._labels.clear()
    monkeypatch.setattr(cp, "resolve_name", lambda v, p, n: {
        "054c:09cc": "PS4 Controller", "045e:02fd": "Xbox One Controller",
    }.get(f"{v}:{p}", n))
    monkeypatch.setattr(cp, "apply_profile",
                        lambda pl, v, p, n, d: calls.append(("apply", pl, v, d)) or ["ok"])
    monkeypatch.setattr(cp, "release_profile",
                        lambda pl: calls.append(("release", pl)) or ["released"])

    state: dict = {"live": {}, "applied": {}}

    def scan(devices):
        was = state["live"]
        state["live"] = gm.pads_by_key(devices)
        calls.clear()
        if was != state["live"]:
            asyncio.run(gm._reconcile(was, state["live"], state["applied"], False, _FakeWS()))
        return list(calls)

    return scan


@pytest.fixture
def roster(monkeypatch):
    try:
        yield _make_roster(monkeypatch)
    finally:
        reg._slots.clear(); reg._labels.clear()


def test_a_pad_with_several_nodes_takes_one_slot(roster):
    """A DualShock 4 exposes a touchpad and a motion node besides its buttons."""
    pad = {**_node("/dev/input/event20", "84:30:95:07:c8:1c"),
           **_node("/dev/input/event21", "84:30:95:07:c8:1c", name="Touchpad"),
           **_node("/dev/input/event22", "84:30:95:07:c8:1c", name="Motion Sensors")}

    assert roster(pad) == [("apply", 1, "054c", 0)]
    assert reg.snapshot() == [{"player": 1, "label": "Wireless Controller"}]


def test_a_pad_keeps_its_slot_while_another_node_is_alive(roster):
    """Unplugging the charging cable of a Bluetooth pad is not a disconnect."""
    bt = _node("/dev/input/event20", "84:30:95:07:c8:1c")
    roster({**bt, **_node("/dev/input/event24", "84:30:95:07:c8:1c")})

    assert roster(bt) == [], "the Bluetooth node is still there — nothing happens"
    assert reg.snapshot() == [{"player": 1, "label": "Wireless Controller"}]


def test_the_slot_is_released_once_the_last_node_goes(roster):
    roster(_node("/dev/input/event20", "84:30:95:07:c8:1c"))

    assert roster({}) == [("release", 1)]
    assert reg.snapshot() == []


def test_unplugging_one_pad_does_not_touch_another(roster):
    p1 = _node("/dev/input/event20", "84:30:95:07:c8:1c")
    p2 = _node("/dev/input/event21", "aa:bb:cc:dd:ee:ff", "045e", "02fd", "Xbox Wireless")
    roster({**p1, **p2})

    assert roster(p1) == [("release", 2)]
    assert reg.snapshot() == [{"player": 1, "label": "Wireless Controller"}]


# ── the survivors are re-profiled when the roster changes ────────────────────

def test_the_survivor_of_two_identical_pads_is_re_profiled(roster):
    """dup is relative to the roster, so a departure invalidates what is left.

    Two DualShock 4s: the second is written as `SDL/1/PS4 Controller` for
    Dolphin and `PS4 Controller 2` for RPCS3. When the first pad's battery
    dies, those strings stop describing anything — the survivor must go back
    to dup 0. Only the arriving pad used to be profiled, so it never did.
    """
    a = _node("/dev/input/event20", "84:30:95:07:c8:1c")
    b = _node("/dev/input/event21", "aa:bb:cc:dd:ee:ff")

    assert roster(a) == [("apply", 1, "054c", 0)]
    assert roster({**a, **b}) == [("apply", 2, "054c", 1)]
    assert roster(b) == [("release", 1), ("apply", 2, "054c", 0)]


def test_an_unchanged_roster_writes_nothing(roster):
    """Idempotence: the scan runs every three seconds for the whole session."""
    pad = _node("/dev/input/event20", "84:30:95:07:c8:1c")
    roster(pad)
    assert roster(pad) == []
    assert roster(pad) == []


def test_a_pad_whose_ids_are_still_zero_takes_no_slot(roster):
    """uhid can expose a Bluetooth pad before the kernel fills its ids in.

    Such a pad used to be given a player slot and then refused a config, and
    `known` blocked every later attempt — so it held that slot, unconfigured,
    until the backend restarted.
    """
    ghost = {"/dev/input/event9": ("uhid pad", "", True, "0000", "0000")}

    assert roster(ghost) == []
    assert reg.snapshot() == []

    real = {"/dev/input/event9": ("8BitDo Pro 2", "", True, "2dc8", "6003")}
    assert roster(real) == [("apply", 1, "2dc8", 0)]


def test_dup_counts_by_resolved_name_not_by_vendor_product():
    """Every consumer of dup counts by name: Dolphin writes SDL/<dup>/<name>
    and RPCS3 `<name> <dup+1>`. SDL3_FALLBACK_NAMES alone maps 054c:05c4,
    054c:09cc and 054c:0ba0 onto "PS4 Controller", so counting by
    vendor:product gave two different DualShock 4 revisions dup 0 each — one
    pad drove two ports and the other was dead.
    """
    assert gm.dup_indexes({
        "a": (1, "PS4 Controller"),
        "b": (2, "PS4 Controller"),
        "c": (3, "Xbox One Controller"),
    }) == {"a": 0, "b": 1, "c": 0}


def test_event_nodes_sort_by_number_not_lexicographically():
    """Slots are handed out in this order on the first scan, so `event10`
    sorting before `event2` made the numbering depend on how many input
    devices the box happens to have."""
    paths = ["/dev/input/event10", "/dev/input/event2", "/dev/input/event20"]
    assert sorted(paths, key=gm._event_sort_key) == [
        "/dev/input/event2", "/dev/input/event10", "/dev/input/event20"]


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

    class _Monkeypatch:
        """Enough of pytest's monkeypatch for the roster fixture."""
        def __init__(self):
            self._undo = []

        def setattr(self, obj, name, value):
            self._undo.append((obj, name, getattr(obj, name)))
            setattr(obj, name, value)

        def undo(self):
            for obj, name, old in reversed(self._undo):
                setattr(obj, name, old)
            self._undo.clear()

    for fn in (test_a_pad_with_several_nodes_takes_one_slot,
               test_a_pad_keeps_its_slot_while_another_node_is_alive,
               test_the_slot_is_released_once_the_last_node_goes,
               test_unplugging_one_pad_does_not_touch_another,
               test_the_survivor_of_two_identical_pads_is_re_profiled,
               test_an_unchanged_roster_writes_nothing,
               test_a_pad_whose_ids_are_still_zero_takes_no_slot):
        mp = _Monkeypatch()
        try:
            fn(_make_roster(mp))
        finally:
            mp.undo()
            reg._slots.clear(); reg._labels.clear()
        print(f"[OK ] {fn.__name__}")

    for fn in (test_dup_counts_by_resolved_name_not_by_vendor_product,
               test_event_nodes_sort_by_number_not_lexicographically):
        fn()
        print(f"[OK ] {fn.__name__}")
    print("\nAll tests passed.")


# ── a failed profiling pass must be retried ──────────────────────────────────
# apply_profile logged its give-ups and returned only the successes, so the
# monitor could not tell a transient failure from a clean pass — and it marked
# the pad done *before* the attempt. A DualShock 4's Ryujinx slot went missing
# for good that way: SDL had not yet caught up with a fresh Bluetooth
# connection, _ryujinx refused to invent an id, and the pad was never revisited.

def _one_pad():
    return {**_node("/dev/input/event20", "aa:bb:cc:dd:ee:ff")}


def _run_reconcile(applied, live, ws):
    asyncio.run(gm._reconcile({}, live, applied, False, ws))


def test_an_incomplete_pass_is_retried(monkeypatch):
    reg._slots.clear(); reg._labels.clear()
    monkeypatch.setattr(cp, "resolve_name", lambda v, p, n: "PS4 Controller")
    attempts = []

    def flaky(pl, v, p, n, d):
        attempts.append(pl)
        # Fails while SDL has not caught up, then succeeds — the real case.
        if len(attempts) < 3:
            return cp.ProfileResult([], ["ryujinx: SDL2 would not report a GUID"])
        return cp.ProfileResult(["ryujinx: Player 1 created"])

    monkeypatch.setattr(cp, "apply_profile", flaky)
    live = gm.pads_by_key(_one_pad())
    applied: dict = {}
    for _ in range(5):
        _run_reconcile(applied, live, _FakeWS())

    assert len(attempts) == 3, "a give-up was remembered as a success"
    # Settled once it worked: no further attempts, however many scans go by.
    _run_reconcile(applied, live, _FakeWS())
    assert len(attempts) == 3


def test_a_clean_pass_is_not_repeated(monkeypatch):
    """The whole point of `applied` — one write per pad, not one every 3 s."""
    reg._slots.clear(); reg._labels.clear()
    monkeypatch.setattr(cp, "resolve_name", lambda v, p, n: "PS4 Controller")
    attempts = []
    monkeypatch.setattr(cp, "apply_profile",
                        lambda pl, v, p, n, d: attempts.append(pl) or cp.ProfileResult(["ok"]))
    live = gm.pads_by_key(_one_pad())
    applied: dict = {}
    for _ in range(4):
        _run_reconcile(applied, live, _FakeWS())
    assert len(attempts) == 1


def test_retrying_stops_instead_of_spinning_forever(monkeypatch):
    """Some give-ups are permanent, and each retry pays for SDL probes with an
    8 s timeout. The budget has to run out."""
    reg._slots.clear(); reg._labels.clear()
    monkeypatch.setattr(cp, "resolve_name", lambda v, p, n: "PS4 Controller")
    attempts = []
    monkeypatch.setattr(cp, "apply_profile",
                        lambda pl, v, p, n, d: attempts.append(pl) or
                        cp.ProfileResult([], ["rpcs3: nothing to clone from"]))
    live = gm.pads_by_key(_one_pad())
    applied: dict = {}
    for _ in range(20):
        _run_reconcile(applied, live, _FakeWS())
    assert len(attempts) == gm.PROFILE_RETRIES


def test_a_reconnection_gives_a_fresh_budget(monkeypatch):
    """Unplugging and replugging is what an owner does when something is wrong;
    it must actually mean something."""
    reg._slots.clear(); reg._labels.clear()
    monkeypatch.setattr(cp, "resolve_name", lambda v, p, n: "PS4 Controller")
    attempts = []
    monkeypatch.setattr(cp, "apply_profile",
                        lambda pl, v, p, n, d: attempts.append(pl) or
                        cp.ProfileResult([], ["ryujinx: no GUID"]))
    live = gm.pads_by_key(_one_pad())
    applied: dict = {}
    for _ in range(10):
        _run_reconcile(applied, live, _FakeWS())
    assert len(attempts) == gm.PROFILE_RETRIES

    applied.clear()          # what a disconnect/reconnect amounts to
    reg._slots.clear(); reg._labels.clear()
    for _ in range(10):
        _run_reconcile(applied, live, _FakeWS())
    assert len(attempts) == gm.PROFILE_RETRIES * 2
