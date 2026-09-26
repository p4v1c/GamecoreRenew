"""Which /dev/input nodes are gamepads, and one entry per physical pad."""
import glob
import logging

from . import controller_registry

log = logging.getLogger(__name__)

# Button codes for PS/Guide/Home across common Linux drivers:
#   BTN_MODE    = 0x13c (316) — hid-sony (DualShock 3/4/5), xpad, most modern drivers
#   KEY_HOMEPAGE = 172        — some older or generic HID mappings
GUIDE_CODES = frozenset({0x13C, 172})

# BTN_SOUTH (A/Cross) — declared by every real gamepad, by no keyboard/remote.
# Used to decide which guide-capable devices deserve a player slot.
BTN_SOUTH = 0x130

# KEY_ESC (1) through KEY_S (31): udev's own keyboard test (input_id's
# test_key). A virtual keyboard that declares every code declares BTN_SOUTH
# too — Sunshine's "libvirtualhid Keyboard" (1209:0002) does, and it took
# player 2 and a "not configured" toast on every box running Sunshine.
KEYBOARD_KEYS = frozenset(range(1, 32))

EV_KEY = 1   # evdev event type for key/button events

# Paths already reported as "kept, but has no Guide button" — the scan runs
# every few seconds and this should be said once per device, not per pass.
_logged_no_guide: set[str] = set()

# Both evdev failure modes return the SAME empty dict a box with nothing
# plugged in returns, and the scan loop below runs every three seconds forever.
# So each one gets a WARNING the first time and on every change after that,
# never once per pass — a line repeated 1200 times an hour is how the one line
# that names the cause gets buried. The unconditional debug line underneath
# stays available when someone is actually looking.
_logged_no_evdev = False
_last_denied: tuple[int, int] | None = None


def _report_denied(denied: int, total: int) -> None:
    """Say that input devices are being refused, without saying it every pass.

    A box with no controller plugged in is a legitimate state and MUST stay
    silent. That is the whole difficulty: it produces the same `{}` as a box
    whose every device was refused. `denied` is the only thing that tells the
    two apart, so nothing is written unless something was actually refused.
    """
    global _last_denied
    if not denied:
        _last_denied = None          # cleared, so a later failure reports again
        return
    log.debug("gamepad_monitor: %d/%d input devices refused", denied, total)
    if _last_denied == (denied, total):
        return
    _last_denied = (denied, total)
    log.warning(
        "gamepad_monitor: %d of %d input devices refused (permission denied) — "
        "is the account running the backend outside the `input` group? A pad "
        "refused here is invisible everywhere: no player slot, no emulator "
        "config, and no guide shortcut, in the menu as well as in games.",
        denied, total)

def _find_gamepad_devices() -> dict[str, tuple[str, str, bool, str, str, int]]:
    """
    Map path → (name, uniq, is_pad, vendor, product) for event devices that
    declare the guide button. Scans /dev/input/event* directly instead of
    relying on evdev.list_devices(), which reads /proc/bus/input/devices and
    may be inaccessible without input group.

    `bustype` is the transport (0x03 USB, 0x05 Bluetooth). It is part of what
    a config is written FOR, not just how the pad is reached: an SDL GUID
    encodes the bus, so the same Xbox pad is 0x05... over Bluetooth and
    0x03... over USB, and Ryujinx binds by that GUID. Without it in the
    footprint, moving a pad from Bluetooth to a cable left every GUID-bound
    emulator pointing at a device that no longer exists — silently, because
    the MAC, the vendor and the product are all unchanged.

    `uniq` is the pad's MAC address — the controller registry keys on it, and
    battery.py joins sysfs power supplies back to a player slot through it.
    `vendor`/`product` (4-hex USB IDs) drive controller_profiles.apply_profile
    — whichever controller TYPE takes a slot gets that slot's emulator
    configs written for it, live (docs/CONTROLLER_MODELS.md).

    `is_pad` tells actual gamepads apart: KEY_HOMEPAGE (172) is also a plain
    multimedia key, so keyboards and remotes land here too — they must keep
    being watched for the guide/home behavior but must NOT take a player
    slot. Every real pad declares BTN_SOUTH; a real keyboard does not, and a
    virtual one that declares every code is told apart by its letter keys.
    """
    global _logged_no_evdev
    try:
        import evdev
    except ImportError:
        # Not a crash: the rest of the box works without a pad. But it is not
        # the absence of a controller either — it is the guarantee that no
        # controller will EVER be seen, which the empty dict below cannot say.
        log.debug("gamepad_monitor: python-evdev is not importable")
        if not _logged_no_evdev:
            _logged_no_evdev = True
            log.error("gamepad_monitor: python-evdev is not importable — no "
                      "controller can be detected on this box at all. Install "
                      "python-evdev in the backend's environment.")
        return {}

    candidate_paths: set[str] = set(glob.glob("/dev/input/event*"))
    try:
        candidate_paths |= set(evdev.list_devices())
    except Exception:
        pass

    found: dict[str, tuple[str, str, bool, str, str, int]] = {}
    denied = 0
    for path in sorted(candidate_paths):
        try:
            dev = evdev.InputDevice(path)
            caps = dev.capabilities()
            keys = caps.get(EV_KEY, [])
            name, uniq = dev.name, (dev.uniq or "")
            info = dev.info
            vendor, product = f"{info.vendor:04x}", f"{info.product:04x}"
            bustype = getattr(info, "bustype", 0)
            dev.close()
            has_guide = any(code in GUIDE_CODES for code in keys)
            is_pad = BTN_SOUTH in keys and not KEYBOARD_KEYS <= set(keys)
            # `or is_pad` is the second half of this test, and it was missing:
            # a device had to declare a Guide/Home code to be seen at all. A pad
            # without a Home button — a generic USB pad, an arcade stick, a SNES
            # or N64 clone, an 8BitDo in DInput — never entered this dict, so it
            # was never watched, never registered, never given a player slot, and
            # apply_profile was never called for it. PCSX2 and DuckStation got no
            # [Pad2], Dolphin left Wiimote1 on the virtual pointer, RPCS3 and
            # Ryujinx were never retargeted. It still worked in emulators that
            # read SDL directly, which is what made it look like something else.
            #
            # These pads simply never reach _on_guide_pressed, which is correct.
            # A keyboard cannot arrive this way: is_pad is BTN_SOUTH, which no
            # keyboard declares, so the anti-keyboard rule below is unchanged.
            if has_guide or is_pad:
                found[path] = (name, uniq, is_pad, vendor, product, bustype)
                if is_pad and not has_guide and path not in _logged_no_guide:
                    _logged_no_guide.add(path)
                    log.info("gamepad_monitor: %s (%s) has no Guide button — taking a "
                             "player slot, but it cannot trigger the guide shortcut",
                             name, path)
        except PermissionError:
            # Counted, not reported here: one line per device would be four
            # lines a pass on a box that simply lacks the group. Must come
            # before OSError — it is a subclass, so the wide clause would
            # swallow it and the count would always be zero.
            denied += 1
        except OSError:
            # A device that vanished between the glob and the open — a pad
            # being unplugged right now. Routine, and not a permission problem.
            pass
    _report_denied(denied, len(candidate_paths))
    _logged_no_guide.intersection_update(found)
    return found

def _event_sort_key(path: str) -> tuple[str, int]:
    """Sort /dev/input/event10 after event2, not before it. Player slots are
    handed out in this order on the first scan, so a lexicographic sort quietly
    made the numbering depend on how many input devices the box happens to
    have."""
    head = path.rstrip("0123456789")
    tail = path[len(head):]
    return head, int(tail) if tail else -1

def pads_by_key(devices: dict[str, tuple[str, str, bool, str, str, int]]
                ) -> dict[str, tuple[str, str, str, int]]:
    """registry key → (vendor, product, evdev name, bustype), one entry per
    PHYSICAL controller.

    A pad owns several event nodes (a DualShock 4 adds a touchpad and a motion
    node) and key_for() collapses them onto its MAC, so the same controller
    must not be counted — or slotted — twice. Pads whose ids are still zero are
    left out entirely: uhid can expose a Bluetooth pad before the kernel fills
    them in, and a slot handed out then used to be held for ever by a pad we
    refused to profile, because `known` blocked every later attempt.
    """
    out: dict[str, tuple[str, str, str, int]] = {}
    for path in sorted(devices, key=_event_sort_key):
        name, uniq, is_pad, vendor, product, bustype = devices[path]
        if not is_pad or vendor == "0000" or product == "0000":
            continue
        key = controller_registry.key_for(uniq, path)
        out.setdefault(key, (vendor, product, name, bustype))
    return out

def dup_indexes(roster: dict[str, tuple[int, str]]) -> dict[str, int]:
    """key → how many pads sharing the same RESOLVED NAME hold a lower slot.

    It used to count by vendor:product, but every consumer counts by name:
    Dolphin writes `SDL/<dup>/<name>` and RPCS3 `<name> <dup+1>`, both per-name
    counters. SDL3_FALLBACK_NAMES alone collapses 054c:05c4, 054c:09cc and
    054c:0ba0 onto "PS4 Controller", so a DualShock 4 v1 and a v2 both got
    dup 0 — GCPad1 and GCPad2 pointed at `SDL/0/PS4 Controller`, one pad drove
    two ports and the other was dead. Ryujinx counts by GUID, where the name is
    at least as fine-grained, so counting by name is safe for it too.
    """
    return {key: sum(1 for k2, (slot2, name2) in roster.items()
                     if k2 != key and name2 == name and slot2 < slot)
            for key, (slot, name) in roster.items()}

def _can_read(path: str) -> bool:
    try:
        import os
        return os.access(path, os.R_OK)
    except Exception:
        return False
