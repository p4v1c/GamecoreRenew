#!/usr/bin/env python3
"""Azahar layout toggle — L3 switches between
   A = native 3DS display (both screens)
   B = top screen only

Azahar's "Toggle Screen Layout" hotkey (F10) cycles `layouts_to_cycle`;
reduced to "0, 1" it is exactly Default <-> SingleScreen. Azahar can bind
hotkeys to keys only, never to a pad button, so this daemon reads L3 on
/dev/input/event* and sends F10 through a uinput keyboard, only while Azahar
runs. No memory writes, no offsets: an Azahar update cannot break it.
Independent of the melonDS daemon and gamepad-tv-bridge (each acts only when
its own emulator runs).

Usage:
  azahar_layout_toggle.py          daemon
  azahar_layout_toggle.py --test   diagnosis: shows what is seen, injects nothing

Needs: `input` group, write access to /dev/uinput (session ACL),
and layouts_to_cycle = 0, 1 in Azahar (apply_azahar_config.py sets it).
"""

import os
import glob
import time
import fcntl
import struct
import select
import argparse

# ===========================================================================
# CONFIG
# ===========================================================================
PROC_NAME  = "azahar"       # the emulator's /proc/<pid>/comm

KEY_NAMES = {              # evdev codes, /usr/include/linux/input-event-codes.h
    "L3": 0x13d,           # BTN_THUMBL - left stick click
    "R3": 0x13e,           # BTN_THUMBR
    "L1": 0x136,
    "R1": 0x137,
    "PS": 0x13c,
}
TRIGGER_KEYCODES = {KEY_NAMES["L3"]}

SEND_KEY   = 68            # KEY_F10 = Azahar's "Toggle Screen Layout" hotkey
DEBOUNCE_S = 0.35
RESCAN_S   = 2.0           # Bluetooth pads come and go (hotplug)

# ===========================================================================
IEV     = struct.Struct("llHHi")    # struct input_event (x86-64), 24 bytes
EV_SYN, EV_KEY = 0x00, 0x01
SYN_REPORT = 0

def log(*a): print(time.strftime("%H:%M:%S"), *a, flush=True)


# ---------- process ------------------------------------------------------
# A full /proc scan every second costs more than the rest of the daemon (~300
# opens/s): while the known pid answers only its /proc/<pid>/comm is read.
SCAN_IDLE_S = 3.0
SCAN_FULL_S = 10.0       # "has a newer instance appeared?" check
_pid_cache = {"pid": None, "next_scan": 0.0, "next_full": 0.0, "warned": None}


def _starttime(pid):
    """Field 22 of /proc/<pid>/stat: start time, in ticks since boot."""
    try:
        d = open("/proc/%d/stat" % pid).read()
        return int(d[d.rindex(")") + 2:].split()[19])
    except (OSError, ValueError, IndexError):
        return 0


def _all_pids(name=PROC_NAME):
    out = []
    for p in glob.glob("/proc/[0-9]*"):
        try:
            if open(p + "/comm").read().strip() == name:
                out.append(int(os.path.basename(p)))
        except OSError:
            pass
    return out


def find_pid(name=PROC_NAME, force=False):
    """The emulator's pid — the NEWEST when several run (the synthetic key
    goes to the foreground window). Full scan every SCAN_FULL_S only."""
    c = _pid_cache
    now = time.time()

    fast = None
    if c["pid"] is not None:
        try:
            if open("/proc/%d/comm" % c["pid"]).read().strip() == name:
                fast = c["pid"]
            else:
                c["pid"] = None
        except OSError:
            c["pid"] = None

    if fast is not None and not force and now < c["next_full"]:
        return fast
    if fast is None and not force and now < c["next_scan"]:
        return None

    c["next_scan"] = now + SCAN_IDLE_S
    c["next_full"] = now + SCAN_FULL_S
    pids = _all_pids(name)
    if not pids:
        c["pid"] = None
        return None
    best = max(pids, key=_starttime)
    if len(pids) > 1 and c["warned"] != best:
        c["warned"] = best
        log("%d instances of %s (%s) -> using the newest: %d"
            % (len(pids), name, ",".join(str(x) for x in sorted(pids)), best))
    elif len(pids) == 1:
        c["warned"] = None
    c["pid"] = best
    return best


# ---------- virtual keyboard (uinput, raw ioctls) ------------------------
UI_SET_EVBIT   = 0x40045564         # _IOW('U', 100, int)
UI_SET_KEYBIT  = 0x40045565         # _IOW('U', 101, int)
UI_DEV_CREATE  = 0x00005501         # _IO ('U', 1)
UI_DEV_DESTROY = 0x00005502         # _IO ('U', 2)

class VirtualKeyboard:
    """Minimal virtual keyboard declaring one key. Uses the legacy setup
    (write struct uinput_user_dev, then UI_DEV_CREATE): still supported and
    simpler than UI_DEV_SETUP."""

    def __init__(self, keycode, name=b"azahar-layout-toggle"):
        self.fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
        fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_KEY)
        fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_SYN)
        fcntl.ioctl(self.fd, UI_SET_KEYBIT, keycode)
        # struct uinput_user_dev: name[80] + input_id(4x u16) + ff_effects_max
        #                         + 4 abs* arrays of 64 s32
        dev = (name[:79].ljust(80, b"\0")
               + struct.pack("<HHHH", 0x03, 0x1209, 0x0001, 1)   # BUS_USB, vid, pid, ver
               + struct.pack("<I", 0)
               + b"\0" * (4 * 64 * 4))
        os.write(self.fd, dev)
        fcntl.ioctl(self.fd, UI_DEV_CREATE)
        self.keycode = keycode
        time.sleep(0.3)          # let the compositor open the device

    def _ev(self, etype, code, value):
        os.write(self.fd, IEV.pack(0, 0, etype, code, value))

    def tap(self):
        self._ev(EV_KEY, self.keycode, 1)
        self._ev(EV_SYN, SYN_REPORT, 0)
        time.sleep(0.02)
        self._ev(EV_KEY, self.keycode, 0)
        self._ev(EV_SYN, SYN_REPORT, 0)

    def close(self):
        try:
            fcntl.ioctl(self.fd, UI_DEV_DESTROY)
        except OSError:
            pass
        try:
            os.close(self.fd)
        except OSError:
            pass


def open_keyboard(keycode):
    """Create the virtual keyboard, waiting for /dev/uinput access.

    /dev/uinput is root:root 0660 with the `uaccess` udev tag: access comes
    ONLY from logind's ACL once the session is active, and the (lingering)
    user service may start before that. Wait instead of failing."""
    t0, warned = time.time(), 0
    while True:
        try:
            return VirtualKeyboard(keycode)
        except OSError as e:
            if warned == 0:
                log("/dev/uinput not accessible yet (%s) - waiting for the session ACL…" % e)
                warned = 1
            elif warned == 1 and time.time() - t0 > 60:
                log("still nothing after 60 s. Check: getfacl /dev/uinput "
                    "(needs a user:<you>:rw- line)")
                warned = 2
            time.sleep(3)


# ---------- capabilities: keep only the useful devices -------------------
def EVIOCGBIT(ev, length):
    """_IOC(_IOC_READ, 'E', 0x20 + ev, length)"""
    return (2 << 30) | (length << 16) | (ord("E") << 8) | (0x20 + ev)

KEYBITS_LEN = 96        # KEY_CNT / 8: covers every code up to 767

def declares_trigger(fd):
    """True when this device declares at least one trigger button.

    Without it the DS4 motion sensors wake `select` constantly (~1 % CPU)."""
    buf = bytearray(KEYBITS_LEN)
    try:
        fcntl.ioctl(fd, EVIOCGBIT(EV_KEY, KEYBITS_LEN), buf)
    except OSError:
        return False
    return any(buf[c // 8] >> (c % 8) & 1 for c in TRIGGER_KEYCODES)


# ---------- pad inputs ---------------------------------------------------
class Inputs:
    """Readable /dev/input/event* declaring the trigger, rescanned
    periodically: a Bluetooth pad connects late and vanishes when it switches
    off (select() would spin on a dead fd)."""

    def __init__(self):
        self.fds = {}
        self.readable = 0            # openable inputs, filter included
        self.last_scan = 0.0
        self.rescan(force=True)

    def rescan(self, force=False):
        now = time.time()
        if not force and now - self.last_scan < RESCAN_S:
            return
        self.last_scan = now
        present = set(glob.glob("/dev/input/event*"))
        known = set(self.fds.values())
        self.readable = 0
        for path in sorted(present):
            if path in known:
                self.readable += 1
                continue
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            except OSError:
                continue
            self.readable += 1
            if not declares_trigger(fd):
                os.close(fd)          # keyboard, mouse, sensors…: nothing for us
                continue
            self.fds[fd] = path
            log("input + %s" % path)
        for fd, path in list(self.fds.items()):
            if path not in present:
                self.drop(fd)

    def drop(self, fd):
        self.fds.pop(fd, None)
        try:
            os.close(fd)
        except OSError:
            pass

    def pressed(self, ready):
        hit = False
        for fd in ready:
            if fd not in self.fds:
                continue
            try:
                buf = os.read(fd, IEV.size * 64)
            except BlockingIOError:
                continue
            except OSError:
                self.drop(fd)          # ENODEV: pad switched off
                continue
            for off in range(0, len(buf) - IEV.size + 1, IEV.size):
                _, _, et, code, val = IEV.unpack_from(buf, off)
                if et == EV_KEY and val == 1 and code in TRIGGER_KEYCODES:
                    hit = True
        return hit


# ---------- loop ----------------------------------------------------------
def loop(test=False):
    from apply_azahar_config import INI, apply, azahar_running

    def configure():
        if not test and os.path.isfile(INI) and not azahar_running():
            try:
                changes = apply(INI)
                if changes:
                    log("Azahar configuration:", "; ".join(changes))
            except OSError as e:
                log("Azahar configuration unavailable:", e)

    configure()
    devs = Inputs()
    if not devs.readable:
        print("No readable /dev/input/event*. The 'input' group is required "
              "(sudo usermod -aG input $USER, then log in again).")
        return 1

    kbd = open_keyboard(SEND_KEY) if not test else None

    names = ",".join(sorted(k for k, v in KEY_NAMES.items() if v in TRIGGER_KEYCODES))
    log("daemon ready%s. %d device(s) with the button, of %d read. %s -> KEY_%d, target '%s'"
        % (" [TEST, no injection]" if test else "",
           len(devs.fds), devs.readable, names or sorted(TRIGGER_KEYCODES),
           SEND_KEY, PROC_NAME))
    if not devs.fds:
        log("no pad with this button yet - waiting for one (hotplug)")

    seen_pid = None
    last_press = last_check = 0.0
    try:
        while True:
            ready, _, _ = select.select(list(devs.fds), [], [], 1.0)
            now = time.time()

            if now - last_check > 1.0:
                last_check = now
                devs.rescan()
                pid = find_pid()
                if pid != seen_pid:
                    seen_pid = pid
                    log("Azahar %s" % ("running (pid %d)" % pid if pid else "closed"))
                    if pid is None:
                        configure()

            if not devs.pressed(ready):
                continue
            if now - last_press < DEBOUNCE_S:
                continue
            last_press = now

            if seen_pid is None:
                seen_pid = find_pid(force=True)     # Azahar may have just started
            if seen_pid is None:
                log("button received, but Azahar is not running -> nothing sent")
                continue
            if test:
                log("button received, Azahar pid=%d -> would send KEY_%d" % (seen_pid, SEND_KEY))
                continue
            kbd.tap()
            log("button received -> KEY_%d sent (layout toggle)" % SEND_KEY)
    except KeyboardInterrupt:
        pass
    finally:
        if kbd:
            kbd.close()
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="L3 toggles Azahar's screen layout (through its F10 hotkey)")
    ap.add_argument("--key", action="append",
                    help="trigger button: L3 (default), R3, L1, R1, PS, or an evdev code")
    ap.add_argument("--send-key", type=int, metavar="CODE",
                    help="code of the key sent (default 68 = KEY_F10)")
    ap.add_argument("--test", action="store_true",
                    help="diagnosis: show what is seen, inject nothing")
    a = ap.parse_args()

    if a.key:
        codes = set()
        for v in a.key:
            k = KEY_NAMES.get(v.strip().upper())
            if k is None:
                try:
                    k = int(v, 0)
                except ValueError:
                    ap.error("unknown key %r (names: %s, or an evdev code)"
                             % (v, ", ".join(KEY_NAMES)))
            codes.add(k)
        TRIGGER_KEYCODES.clear(); TRIGGER_KEYCODES.update(codes)
    if a.send_key:
        global SEND_KEY
        SEND_KEY = a.send_key
    raise SystemExit(loop(a.test))


if __name__ == "__main__":
    main()
