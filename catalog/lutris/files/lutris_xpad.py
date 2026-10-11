"""Mirror each non-Xbox pad as a virtual Xbox 360 pad for the length of a game.

Windows games that only read XInput ignore a DualShock or a DualSense under
Proton: Proton hands Sony pads to the game as raw HID (hidraw), not as an
XInput device. Steam fixes this with Steam Input; this is the same idea:
one virtual "Microsoft X-Box 360 pad" (045e:028e, the xpad driver's layout)
per real pad, fed from the real pad's evdev node, while the real pad is
hidden from Wine (`hide_env`) so the game sees each player once.

The real pad is never grabbed: GameCore keeps reading it (PS button, wake).
Our pads carry `VIRTUAL_PHYS` so GameCore does not give them a player slot.
Stdlib only: runs inside lutris_session.py on the system python3.
"""
from __future__ import annotations

import fcntl
import os
import re
import select
import struct
import threading
import time
from pathlib import Path
from typing import Callable, NamedTuple

EV_SYN, EV_KEY, EV_ABS = 0, 1, 3
SYN_REPORT = 0
ABS_X, ABS_Y, ABS_Z, ABS_RX, ABS_RY, ABS_RZ = 0x00, 0x01, 0x02, 0x03, 0x04, 0x05
ABS_HAT0X, ABS_HAT0Y = 0x10, 0x11
BTN_SOUTH, BTN_EAST, BTN_NORTH, BTN_WEST = 0x130, 0x131, 0x133, 0x134
BTN_TL, BTN_TR, BTN_TL2, BTN_TR2 = 0x136, 0x137, 0x138, 0x139
BTN_SELECT, BTN_START, BTN_MODE, BTN_THUMBL, BTN_THUMBR = 0x13A, 0x13B, 0x13C, 0x13D, 0x13E
BTN_DPAD_UP, BTN_DPAD_DOWN, BTN_DPAD_LEFT, BTN_DPAD_RIGHT = 0x220, 0x221, 0x222, 0x223

# Same string in backend/services/gamepad_devices.py (packs never import the core).
VIRTUAL_PHYS = "gamecore-virtual-pad"
XBOX_NAME = "Microsoft X-Box 360 pad"
XBOX_VENDOR, XBOX_PRODUCT, XBOX_VERSION, BUS_USB = 0x045E, 0x028E, 0x0110, 0x03
UINPUT = "/dev/uinput"
MAX_PLAYERS = 4
RESCAN_S = 1.0
# Already XInput under Proton (Microsoft), or Steam's own virtual pad (Valve).
SKIP_VENDORS = frozenset({0x045E, 0x28DE})
# Sony pads hidden even if they connect after launch: DS4 v1/v2, DS4 dongle,
# DualSense, DualSense Edge (the list GE-Proton itself uses for PROTON_DISABLE_HIDRAW).
SONY_PADS = ((0x054C, 0x05C4), (0x054C, 0x09CC), (0x054C, 0x0BA0),
             (0x054C, 0x0CE6), (0x054C, 0x0DF2))

STICK_MIN, STICK_MAX, TRIGGER_MAX = -32768, 32767, 255
STICKS = (ABS_X, ABS_Y, ABS_RX, ABS_RY)
TRIGGERS = (ABS_Z, ABS_RZ)
# The xpad driver reports X (left face button) as 0x133 and Y (top) as 0x134,
# while the kernel names those codes NORTH and WEST: swap, or square acts as Y.
KEY_MAP = {BTN_SOUTH: BTN_SOUTH, BTN_EAST: BTN_EAST, BTN_WEST: BTN_NORTH, BTN_NORTH: BTN_WEST,
           BTN_TL: BTN_TL, BTN_TR: BTN_TR, BTN_SELECT: BTN_SELECT, BTN_START: BTN_START,
           BTN_THUMBL: BTN_THUMBL, BTN_THUMBR: BTN_THUMBR}
# Declared so SDL numbers the buttons like a real xpad, never sent: the real
# pad already brings PS to GameCore, a copy would read as a double press.
XBOX_KEYS = sorted({*KEY_MAP.values(), BTN_MODE})
DPAD = {BTN_DPAD_UP: (ABS_HAT0Y, -1), BTN_DPAD_DOWN: (ABS_HAT0Y, 1),
        BTN_DPAD_LEFT: (ABS_HAT0X, -1), BTN_DPAD_RIGHT: (ABS_HAT0X, 1)}
DIGITAL_TRIGGERS = {BTN_TL2: ABS_Z, BTN_TR2: ABS_RZ}

EVENT = struct.Struct("llHHi")           # struct input_event
ABSINFO = struct.Struct("6i")            # struct input_absinfo
UI_SET_EVBIT, UI_SET_KEYBIT, UI_SET_ABSBIT = 0x40045564, 0x40045565, 0x40045567
UI_SET_PHYS = 0x4008556C                 # _IOW('U', 108, char *)
UI_DEV_CREATE, UI_DEV_DESTROY = 0x5501, 0x5502
ABS_CNT = 64


def eviocgabs(code: int) -> int:
    return (2 << 30) | (ABSINFO.size << 16) | (ord("E") << 8) | (0x40 + code)


class Pad(NamedTuple):
    order: int          # input number: grows at each plug, so connection order
    path: str           # /dev/input/eventN
    name: str
    vendor: int
    product: int


def _bits(text: str) -> set[int]:
    """A sysfs capability bitmap: 64-bit hex words, most significant first."""
    bits: set[int] = set()
    for i, word in enumerate(reversed(text.split())):
        value = int(word, 16)
        bits.update(i * 64 + b for b in range(64) if value >> b & 1)
    return bits


def _read(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def find_pads(sys_root: Path = Path("/sys")) -> list[Pad]:
    """Pads to mirror, in connection order.

    A pad with the standard layout (south button, two sticks on X/Y and
    RX/RY): DualShock, DualSense, Switch Pro, most XInput-less pads. A pad
    putting its right stick elsewhere would be mirrored wrong, so it is left
    to Wine. Xbox pads, Steam's and our own virtual pads are skipped.
    """
    found = []
    for node in (sys_root / "class/input").glob("event*"):
        dev = node / "device"
        try:
            vendor, product = int(_read(dev / "id/vendor"), 16), int(_read(dev / "id/product"), 16)
            keys, axes = _bits(_read(dev / "capabilities/key") or "0"), _bits(_read(dev / "capabilities/abs") or "0")
        except ValueError:
            continue                    # vanished while we looked
        if (vendor in SKIP_VENDORS or _read(dev / "phys").startswith(VIRTUAL_PHYS)
                or BTN_SOUTH not in keys or not set(STICKS) <= axes):
            continue
        m = re.search(r"input(\d+)$", os.path.realpath(dev))
        found.append(Pad(int(m.group(1)) if m else 0, f"/dev/input/{node.name}",
                         _read(dev / "name"), vendor, product))
    return sorted(found)


def hidden_ids(pads: list[Pad]) -> list[tuple[int, int]]:
    """Sony pads plus the pads present now, without duplicates, in order."""
    return list(dict.fromkeys([*SONY_PADS, *((p.vendor, p.product) for p in pads)]))


def hide_env(ids: list[tuple[int, int]], env: dict[str, str]) -> dict[str, str]:
    """Variables that hide `ids` from Wine: SDL's ignore list (GE-Proton's
    winebus honours it) and PROTON_DISABLE_HIDRAW (winebus.sys, per device).
    An ignore list already set (by Steam) is kept."""
    listed = ",".join(f"0x{v:04x}/0x{p:04x}" for v, p in ids)
    ignore = ",".join(x for x in (env.get("SDL_GAMECONTROLLER_IGNORE_DEVICES", ""), listed) if x)
    return {"SDL_GAMECONTROLLER_IGNORE_DEVICES": ignore, "PROTON_DISABLE_HIDRAW": listed}


def scale(value: int, lo: int, hi: int, out_lo: int, out_hi: int) -> int:
    """`value` from [lo, hi] to [out_lo, out_hi], clamped."""
    if hi <= lo:
        return out_lo
    value = min(max(value, lo), hi)
    return out_lo + (value - lo) * (out_hi - out_lo) // (hi - lo)


def translate(etype: int, code: int, value: int,
              ranges: dict[int, tuple[int, int]]) -> list[tuple[int, int, int]]:
    """One real-pad event as the virtual pad's events. `ranges` is the real
    pad's {axis: (min, max)}."""
    if etype == EV_SYN:
        return [(EV_SYN, SYN_REPORT, 0)] if code == SYN_REPORT else []
    if etype == EV_KEY:
        if code in KEY_MAP:
            return [(EV_KEY, KEY_MAP[code], value)]
        if code in DPAD:
            axis, direction = DPAD[code]
            return [(EV_ABS, axis, direction if value else 0)]
        trigger = DIGITAL_TRIGGERS.get(code)
        if trigger is not None and trigger not in ranges:
            return [(EV_ABS, trigger, TRIGGER_MAX if value else 0)]
        return []
    if etype != EV_ABS or code not in ranges:
        return []
    lo, hi = ranges[code]
    if code in STICKS:
        return [(EV_ABS, code, scale(value, lo, hi, STICK_MIN, STICK_MAX))]
    if code in TRIGGERS:
        return [(EV_ABS, code, scale(value, lo, hi, 0, TRIGGER_MAX))]
    if code in (ABS_HAT0X, ABS_HAT0Y):
        return [(EV_ABS, code, max(-1, min(1, value)))]
    return []


NEUTRAL = [(EV_KEY, k, 0) for k in XBOX_KEYS] + [
    (EV_ABS, a, 0) for a in (*STICKS, *TRIGGERS, ABS_HAT0X, ABS_HAT0Y)] + [(EV_SYN, SYN_REPORT, 0)]


class VirtualPad:
    """One Xbox 360 pad on /dev/uinput. The kernel removes it when the fd
    closes, so a killed session cannot leave it behind."""

    def __init__(self, player: int):
        self.fd = os.open(UINPUT, os.O_WRONLY | os.O_NONBLOCK)
        try:
            for ev in (EV_KEY, EV_ABS):
                fcntl.ioctl(self.fd, UI_SET_EVBIT, ev)
            for key in XBOX_KEYS:
                fcntl.ioctl(self.fd, UI_SET_KEYBIT, key)
            fcntl.ioctl(self.fd, UI_SET_PHYS, f"{VIRTUAL_PHYS}/{player}\0".encode())
            absmin, absmax, fuzz, flat = ([0] * ABS_CNT for _ in range(4))
            for axis in STICKS:
                absmin[axis], absmax[axis], fuzz[axis], flat[axis] = STICK_MIN, STICK_MAX, 16, 128
            for axis in TRIGGERS:
                absmax[axis] = TRIGGER_MAX
            for axis in (ABS_HAT0X, ABS_HAT0Y):
                absmin[axis], absmax[axis] = -1, 1
            for axis in (*STICKS, *TRIGGERS, ABS_HAT0X, ABS_HAT0Y):
                fcntl.ioctl(self.fd, UI_SET_ABSBIT, axis)
            # struct uinput_user_dev: name, input_id, ff_effects_max, absmax/min/fuzz/flat.
            os.write(self.fd, struct.pack(f"80sHHHHi{ABS_CNT * 4}i", XBOX_NAME.encode(), BUS_USB,
                                          XBOX_VENDOR, XBOX_PRODUCT, XBOX_VERSION, 0,
                                          *absmax, *absmin, *fuzz, *flat))
            fcntl.ioctl(self.fd, UI_DEV_CREATE)
        except OSError:
            os.close(self.fd)
            raise

    def emit(self, events: list[tuple[int, int, int]]) -> None:
        if events:
            os.write(self.fd, b"".join(EVENT.pack(0, 0, *e) for e in events))

    def close(self) -> None:
        try:
            fcntl.ioctl(self.fd, UI_DEV_DESTROY)
        except OSError:
            pass
        os.close(self.fd)


class Source:
    """A real pad, read without a grab."""

    def __init__(self, pad: Pad):
        self.pad = pad
        self.fd = os.open(pad.path, os.O_RDONLY | os.O_NONBLOCK)
        self.ranges: dict[int, tuple[int, int]] = {}
        for axis in (*STICKS, *TRIGGERS, ABS_HAT0X, ABS_HAT0Y):
            try:
                info = ABSINFO.unpack(fcntl.ioctl(self.fd, eviocgabs(axis), bytes(ABSINFO.size)))
            except OSError:
                continue
            # evdev answers zeros for an axis the pad lacks (digital triggers).
            if info[2] > info[1]:
                self.ranges[axis] = (info[1], info[2])

    def read(self) -> list[tuple[int, int, int]]:
        """Waiting events; raises OSError (ENODEV) once the pad is gone."""
        try:
            data = os.read(self.fd, EVENT.size * 64)
        except BlockingIOError:
            return []
        return [EVENT.unpack_from(data, i)[2:] for i in range(0, len(data), EVENT.size)]

    def close(self) -> None:
        os.close(self.fd)


class Mirror(threading.Thread):
    """Up to four players. A player's virtual pad lives until the game ends:
    when the real pad drops it goes neutral, and the next pad to connect
    takes the first free player, so a pad that reconnects gets its slot back."""

    def __init__(self, hidden: list[tuple[int, int]], log: Callable[[str], None],
                 sys_root: Path = Path("/sys")):
        super().__init__(name="xbox-pad-mirror", daemon=True)
        self.hidden, self.log, self.sys_root = set(hidden), log, sys_root
        self.players: list[tuple[VirtualPad, Source | None]] = []
        self.stopping = threading.Event()
        self.failed: set[str] = set()

    def _attach(self) -> None:
        taken = {s.pad.path for _, s in self.players if s}
        for pad in find_pads(self.sys_root):
            if pad.path in taken:
                continue
            if (pad.vendor, pad.product) not in self.hidden:
                # Not hidden from Wine at launch: a mirror would make it two pads.
                continue
            free = next((i for i, (_, s) in enumerate(self.players) if s is None), None)
            if free is None and len(self.players) >= MAX_PLAYERS:
                return
            try:
                source = Source(pad)
            except OSError as e:
                if pad.path not in self.failed:     # once, not every second
                    self.failed.add(pad.path)
                    self.log(f"cannot read {pad.name} ({pad.path}): {e}")
                continue
            if free is None:
                try:
                    virtual = VirtualPad(len(self.players) + 1)
                except OSError as e:
                    source.close()
                    self.log(f"cannot create a virtual pad: {e}")
                    self.stopping.set()
                    return
                self.players.append((virtual, source))
                free = len(self.players) - 1
            else:
                self.players[free] = (self.players[free][0], source)
            taken.add(pad.path)
            self.log(f"player {free + 1}: {pad.name} mirrored as an Xbox 360 pad")

    def _drop(self, index: int) -> None:
        virtual, source = self.players[index]
        if source is not None:
            source.close()
            self.log(f"player {index + 1}: {source.pad.name} disconnected; virtual pad kept")
        virtual.emit(NEUTRAL)
        self.players[index] = (virtual, None)

    def _pump(self, index: int) -> None:
        virtual, source = self.players[index]
        try:
            events = source.read()
        except OSError:
            self._drop(index)
            return
        out = [e for ev in events for e in translate(*ev, source.ranges)]
        try:
            virtual.emit(out)
        except OSError as e:
            self.log(f"player {index + 1}: virtual pad write failed: {e}")

    def run(self) -> None:
        next_scan = 0.0
        while not self.stopping.is_set():
            # A sysfs scan per report would cost a few hundred scans a second.
            if time.monotonic() >= next_scan:
                self._attach()
                next_scan = time.monotonic() + RESCAN_S
            fds = {s.fd: i for i, (_, s) in enumerate(self.players) if s}
            try:
                ready, _, _ = select.select(list(fds), [], [], RESCAN_S)
            except OSError:
                ready = []
            for fd in ready:
                self._pump(fds[fd])

    def stop(self) -> None:
        self.stopping.set()
        if self.is_alive():
            self.join(timeout=RESCAN_S * 2)
        for virtual, source in self.players:
            if source is not None:
                source.close()
            virtual.close()
        self.players = []
