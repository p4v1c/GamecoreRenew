"""Input side: the uinput key sent to melonDS, and the pads read over evdev."""

import errno
import fcntl
import glob
import os
import select
import struct
import time

from melonds_common import EV_KEY, EV_SYN, IEV, RESCAN_S, TRIGGER_KEYCODES, log

# The trigger sent to melonDS is a synthetic KEYBOARD key: melonDS remembers an
# SDL joystick index, which changes whenever pads are reordered.
UI_SET_EVBIT   = 0x40045564      # _IOW('U', 100, int)
UI_SET_KEYBIT  = 0x40045565      # _IOW('U', 101, int)
UI_DEV_CREATE  = 0x5501          # _IO('U', 1)
UI_DEV_DESTROY = 0x5502          # _IO('U', 2)


class KeyEmitter:
    """A one-key virtual keyboard on /dev/uinput."""

    def __init__(self, code):
        self.code = code
        self.fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
        try:
            fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_KEY)
            fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_SYN)
            fcntl.ioctl(self.fd, UI_SET_KEYBIT, code)
            # struct uinput_user_dev:
            #   char name[80]; struct input_id id (8); __u32 ff_effects_max;
            #   __s32 absmax/absmin/absfuzz/absflat [ABS_CNT=64]
            dev = (b"melonds-layout-toggle".ljust(80, b"\x00")
                   + struct.pack("<HHHH", 0x03, 0x1209, 0x0001, 0x0001)
                   + struct.pack("<I", 0)
                   + b"\x00" * (4 * 64 * 4))
            os.write(self.fd, dev)
            fcntl.ioctl(self.fd, UI_DEV_CREATE)
        except OSError:
            os.close(self.fd)
            raise
        time.sleep(0.15)          # let udev create the node

    def _ev(self, t, c, v):
        os.write(self.fd, IEV.pack(0, 0, t, c, v))

    def tap(self):
        self._ev(EV_KEY, self.code, 1); self._ev(EV_SYN, 0, 0)
        time.sleep(0.02)
        self._ev(EV_KEY, self.code, 0); self._ev(EV_SYN, 0, 0)

    def close(self):
        try: fcntl.ioctl(self.fd, UI_DEV_DESTROY)
        except OSError: pass
        try: os.close(self.fd)
        except OSError: pass


def uinput_status():
    """(available, explanation)"""
    if not os.path.exists("/dev/uinput"):
        return False, "missing (sudo modprobe uinput)"
    if not os.access("/dev/uinput", os.W_OK):
        return False, "present but not writable (udev rule, see README)"
    return True, "OK"


# Devices are tracked by (path, st_rdev), not path: unplug pad 1 and plug pad 2
# and the kernel often reuses the same /dev/input/eventN.
def EVIOCGBIT(ev, length):  return (2 << 30) | (length << 16) | (ord("E") << 8) | (0x20 + ev)
def EVIOCGNAME(length):     return (2 << 30) | (length << 16) | (ord("E") << 8) | 0x06

KEYBITS_LEN = 96        # KEY_CNT / 8: covers codes up to 767


def dev_name(fd):
    buf = bytearray(128)
    try:
        fcntl.ioctl(fd, EVIOCGNAME(len(buf)), buf)
    except OSError:
        return "?"
    return buf.split(b"\x00", 1)[0].decode("utf-8", "replace") or "?"


def dev_keybits(fd):
    buf = bytearray(KEYBITS_LEN)
    try:
        fcntl.ioctl(fd, EVIOCGBIT(EV_KEY, KEYBITS_LEN), buf)
    except OSError:
        return None
    return buf


def declares(keybits, codes):
    return any(keybits[c // 8] >> (c % 8) & 1 for c in codes if c // 8 < len(keybits))


class Inputs:
    """Every /dev/input/event* declaring the trigger button, tracked by
    identity and rescanned periodically (Bluetooth pad = hotplug)."""

    def __init__(self):
        self.devs = {}        # fd -> {"path", "rdev", "name"}
        self.skip = {}        # path -> rdev already rejected (avoid reopening)
        self.poller = select.poll()
        self.last_scan = 0.0
        self.readable = 0
        self.rescan(force=True)

    def _present(self):
        out = {}
        for path in glob.glob("/dev/input/event*"):
            try:
                out[path] = os.stat(path).st_rdev
            except OSError:
                pass
        return out

    def rescan(self, force=False):
        now = time.time()
        if not force and now - self.last_scan < RESCAN_S:
            return
        self.last_scan = now
        present = self._present()

        # drop what vanished OR whose device number changed
        for fd, d in list(self.devs.items()):
            if present.get(d["path"]) != d["rdev"]:
                self.drop(fd, "removed/replaced")
        for path, rdev in list(self.skip.items()):
            if present.get(path) != rdev:
                del self.skip[path]

        open_paths = {d["path"] for d in self.devs.values()}
        self.readable = 0
        for path, rdev in sorted(present.items()):
            if path in open_paths or self.skip.get(path) == rdev:
                self.readable += 1
                continue
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            except OSError:
                continue
            self.readable += 1
            bits = dev_keybits(fd)
            if bits is None or not declares(bits, TRIGGER_KEYCODES):
                # keyboard, mouse, DS4 motion sensors...: nothing for us.
                self.skip[path] = rdev
                os.close(fd)
                continue
            self.devs[fd] = {"path": path, "rdev": rdev, "name": dev_name(fd)}
            self.poller.register(fd, select.POLLIN)
            log("input + %s  [%s]" % (path, self.devs[fd]["name"]))

    def drop(self, fd, why="closed"):
        d = self.devs.pop(fd, None)
        try: self.poller.unregister(fd)
        except (OSError, KeyError): pass
        try: os.close(fd)
        except OSError: pass
        if d:
            log("input - %s  [%s] (%s)" % (d["path"], d["name"], why))

    def wait(self, timeout_ms):
        return self.poller.poll(timeout_ms)

    def pressed(self, events):
        """Name of the device that sent a trigger press, else None.
        POLLHUP/POLLERR handled explicitly: a dead fd otherwise stays 'ready'
        forever → 100 % CPU when a pad switches off."""
        hit = None
        for fd, ev in events:
            if fd not in self.devs:
                continue
            if ev & (select.POLLHUP | select.POLLERR | select.POLLNVAL):
                self.drop(fd, "disconnected")
                continue
            try:
                buf = os.read(fd, IEV.size * 64)
            except BlockingIOError:
                continue
            except OSError as e:
                self.drop(fd, "error %s" % errno.errorcode.get(e.errno, e.errno))
                continue
            for off in range(0, len(buf) - IEV.size + 1, IEV.size):
                _, _, et, code, val = IEV.unpack_from(buf, off)
                if et == EV_KEY and val == 1 and code in TRIGGER_KEYCODES:
                    hit = self.devs[fd]["name"]
        return hit

    def close(self):
        for fd in list(self.devs):
            self.drop(fd)
