"""Kernel side of the per-player mouse: find mice, read and grab them (evdev),
and drive one virtual touchscreen per player (uinput). Stdlib only.

Codes and ioctl numbers are the kernel's (linux/input-event-codes.h,
linux/input.h, linux/uinput.h).
"""
from __future__ import annotations

import fcntl
import os
import re
import struct
from pathlib import Path

EV_SYN, EV_KEY, EV_REL, EV_ABS = 0, 1, 2, 3
REL_X, REL_Y = 0, 1
BTN_LEFT, BTN_TOUCH = 0x110, 0x14A
KEY_A = 30
ABS_X, ABS_Y = 0, 1
ABS_MT_SLOT, ABS_MT_POSITION_X, ABS_MT_POSITION_Y, ABS_MT_TRACKING_ID = 0x2F, 0x35, 0x36, 0x39
INPUT_PROP_DIRECT = 1
ABS_CNT = 64

EVIOCGRAB = 0x40044590
UI_SET_EVBIT, UI_SET_KEYBIT, UI_SET_ABSBIT, UI_SET_PROPBIT = 0x40045564, 0x40045565, 0x40045567, 0x4004556E
UI_DEV_CREATE, UI_DEV_DESTROY = 0x5501, 0x5502
BUS_USB = 0x03

EVENT = struct.Struct("llHHi")           # struct input_event: timeval, type, code, value
# Our own devices; never taken for a player's mouse.
OWN_PREFIX = "gc-"
TOUCH_NAME = "gc-touch-p{}"


def _bits(text: str) -> set[int]:
    """A sysfs capability bitmap: hex words of 64 bits (x86_64's long), most
    significant first, e.g. "1f0000 0 3"."""
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


def find_mice(sys_root: Path = Path("/sys")) -> list[tuple[int, str, str]]:
    """[(input number, /dev/input/eventN, name)] for every mouse, oldest
    first: the input number grows at each plug, the event number is reused.

    A mouse moves (REL_X, REL_Y) and clicks (BTN_LEFT). A node that also has
    letter keys is a keyboard with a built-in pointer: grabbing it would take
    the keyboard away for the whole game.
    """
    found = []
    for node in sorted((sys_root / "class/input").glob("event*")):
        caps = node / "device/capabilities"
        name = _read(node / "device/name")
        if name.startswith(OWN_PREFIX):
            continue
        rel, keys = _bits(_read(caps / "rel") or "0"), _bits(_read(caps / "key") or "0")
        if not {REL_X, REL_Y} <= rel or BTN_LEFT not in keys or KEY_A in keys:
            continue
        m = re.search(r"input(\d+)$", os.path.realpath(node / "device"))
        found.append((int(m.group(1)) if m else 0, f"/dev/input/{node.name}", name))
    return sorted(found)


class Mouse:
    """One evdev mouse, non-blocking; `grab()` takes it away from X."""

    def __init__(self, path: str, name: str = ""):
        self.path, self.name = path, name
        self.fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        self.grabbed = False

    def fileno(self) -> int:
        return self.fd

    def grab(self) -> None:
        if not self.grabbed:
            fcntl.ioctl(self.fd, EVIOCGRAB, 1)
            self.grabbed = True

    def read(self) -> list[tuple[int, int, int]]:
        """[(type, code, value)] waiting on the device. Raises OSError once
        the mouse is unplugged."""
        try:
            data = os.read(self.fd, EVENT.size * 64)
        except BlockingIOError:
            return []
        n = len(data) // EVENT.size
        return [EVENT.unpack_from(data, i * EVENT.size)[2:] for i in range(n)]

    def close(self) -> None:
        try:
            os.close(self.fd)                # also releases the grab
        except OSError:
            pass


class Touchscreen:
    """A virtual touchscreen covering the whole X screen, one per player.

    One device per player, not one finger each on a shared device: Qt hands
    a window every finger of the device, and melonDS reads only the first
    one, so the second player to touch lost half their strokes (8/8 against
    4/8, measured). Plain touchscreens attached to the core pointer; extra
    X pointers (MPX) crash kwin_x11 and Electron's GTK3."""

    def __init__(self, name: str, width: int, height: int, fingers: int):
        self.fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
        self.down_slots: set[int] = set()
        self.tracking = 0
        for ev in (EV_KEY, EV_ABS):
            fcntl.ioctl(self.fd, UI_SET_EVBIT, ev)
        fcntl.ioctl(self.fd, UI_SET_KEYBIT, BTN_TOUCH)
        fcntl.ioctl(self.fd, UI_SET_PROPBIT, INPUT_PROP_DIRECT)
        absmax = [0] * ABS_CNT
        for code, top in ((ABS_X, width - 1), (ABS_Y, height - 1), (ABS_MT_SLOT, fingers - 1),
                          (ABS_MT_POSITION_X, width - 1), (ABS_MT_POSITION_Y, height - 1),
                          (ABS_MT_TRACKING_ID, 65535)):
            fcntl.ioctl(self.fd, UI_SET_ABSBIT, code)
            absmax[code] = top
        # struct uinput_user_dev: name, input_id, ff_effects_max, absmax/min/fuzz/flat.
        setup = struct.pack(f"80sHHHHi{ABS_CNT}i{ABS_CNT * 3}i", name.encode()[:79],
                            BUS_USB, 0x1209, 0x5D50, 1, 0, *absmax, *([0] * ABS_CNT * 3))
        os.write(self.fd, setup)
        fcntl.ioctl(self.fd, UI_DEV_CREATE)

    def _emit(self, *events: tuple[int, int, int]) -> None:
        touching = 1 if self.down_slots else 0
        tail = ((EV_KEY, BTN_TOUCH, touching), (EV_SYN, 0, 0))
        os.write(self.fd, b"".join(EVENT.pack(0, 0, t, c, v) for t, c, v in (*events, *tail)))

    def down(self, slot: int, x: int, y: int) -> None:
        self.tracking = self.tracking % 65000 + 1
        self.down_slots.add(slot)
        self._emit((EV_ABS, ABS_MT_SLOT, slot), (EV_ABS, ABS_MT_TRACKING_ID, self.tracking),
                   (EV_ABS, ABS_MT_POSITION_X, x), (EV_ABS, ABS_MT_POSITION_Y, y))

    def move(self, slot: int, x: int, y: int) -> None:
        self._emit((EV_ABS, ABS_MT_SLOT, slot),
                   (EV_ABS, ABS_MT_POSITION_X, x), (EV_ABS, ABS_MT_POSITION_Y, y))

    def up(self, slot: int) -> None:
        self.down_slots.discard(slot)
        self._emit((EV_ABS, ABS_MT_SLOT, slot), (EV_ABS, ABS_MT_TRACKING_ID, -1))

    def close(self) -> None:
        try:
            fcntl.ioctl(self.fd, UI_DEV_DESTROY)
        except OSError:
            pass
        try:
            os.close(self.fd)
        except OSError:
            pass
