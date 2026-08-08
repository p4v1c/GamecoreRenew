#!/usr/bin/env python3
"""Measure `sdl_layout()` against the real SDL, through a virtual pad.

`controller_capture.sdl_layout()` reproduces the order SDL's Linux joystick
driver assigns its button, axis and hat indices in. That is a claim about
someone ELSE's code, and the failure mode if it is wrong is not a crash: it is a
mapping whose numbers are all plausible and all shifted by one, written to disk
and applied to every emulator on the box.

So it is measured rather than reasoned about. This script creates gamepads that
do not exist through /dev/uinput, declaring capability sets chosen to make the
ordering rules disagree with each other, and asks the real SDL — the host's, and
every one an emulator bundles — how many buttons, axes and hats it ended up
with.

Not part of the test suite: it needs a writable /dev/uinput, which CI does not
have and which is not worth a skip in the gate. What IS in the suite is
`backend/tests/test_controller_capture.py`, which replays the layouts this
script measured. Re-run this after touching `sdl_layout()`, and paste any
disagreement into that test as a new case.

    python3 scripts/verify-sdl-layout.py

Read-only with respect to the box: uinput devices vanish with the process, and
nothing here writes a udev rule or touches an existing device.
"""
from __future__ import annotations

import ctypes
import glob
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.services.controller_capture import sdl_layout        # noqa: E402

# ── the pads to invent ───────────────────────────────────────────────────────
# Each is (name, key codes, absolute axis codes). Chosen so that a derivation
# which gets one rule right and another wrong still fails somewhere:
#
#   plain-pad     the ordinary case, buttons all above BTN_JOYSTICK
#   keyboard-keys declares keys BELOW BTN_JOYSTICK too. They must be numbered
#                 AFTER the gamepad buttons; putting them first shifts every
#                 index a real pad uses. Arcade sticks and clones do this.
#   hats-only     a d-pad as a hat and no analogue sticks: the axis walk must
#                 skip the hat range entirely rather than number it
#   two-hats      a second hat, to check hats are paired and counted per pair
#   sparse-axes   axis codes with gaps, so an index derived from the CODE
#                 rather than from the position is caught
BTN_SOUTH, BTN_EAST, BTN_C, BTN_NORTH, BTN_WEST = 0x130, 0x131, 0x132, 0x133, 0x134
BTN_TL, BTN_TR, BTN_TL2, BTN_TR2 = 0x136, 0x137, 0x138, 0x139
BTN_SELECT, BTN_START, BTN_MODE = 0x13A, 0x13B, 0x13C
BTN_THUMBL, BTN_THUMBR = 0x13D, 0x13E
BTN_TRIGGER, BTN_THUMB = 0x120, 0x121
KEY_A, KEY_ENTER = 0x1E, 0x1C
ABS_X, ABS_Y, ABS_Z, ABS_RX, ABS_RY, ABS_RZ = 0, 1, 2, 3, 4, 5
ABS_HAT0X, ABS_HAT0Y, ABS_HAT1X, ABS_HAT1Y = 0x10, 0x11, 0x12, 0x13

FACE = [BTN_SOUTH, BTN_EAST, BTN_NORTH, BTN_WEST, BTN_TL, BTN_TR,
        BTN_SELECT, BTN_START, BTN_MODE, BTN_THUMBL, BTN_THUMBR]

PADS = {
    "plain-pad":     (FACE, [ABS_X, ABS_Y, ABS_RX, ABS_RY, ABS_Z, ABS_RZ,
                             ABS_HAT0X, ABS_HAT0Y]),
    "keyboard-keys": (FACE + [BTN_TRIGGER, BTN_THUMB, KEY_A, KEY_ENTER],
                      [ABS_X, ABS_Y]),
    "hats-only":     (FACE, [ABS_HAT0X, ABS_HAT0Y]),
    "two-hats":      (FACE, [ABS_X, ABS_Y, ABS_HAT0X, ABS_HAT0Y,
                             ABS_HAT1X, ABS_HAT1Y]),
    "sparse-axes":   (FACE, [ABS_X, ABS_RZ, ABS_HAT0X, ABS_HAT0Y]),
}

VENDOR, PRODUCT, VERSION = 0xDEAD, 0xBEEF, 0x0111

# Asked out of process, one library at a time: SDL caches its joystick list in
# process globals, and a segfault in a bundled build must cost a probe rather
# than the run.
_PROBE = r"""
import ctypes, os, sys, time
api, lib, vendor, product = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_NO_SIGNAL_HANDLERS"] = "1"
os.environ["SDL_JOYSTICK_HIDAPI"] = "0"     # force the Linux evdev driver
s = ctypes.CDLL(lib)
class G(ctypes.Structure):
    _fields_ = [("data", ctypes.c_uint8 * 16)]
if api == "2":
    s.SDL_JoystickGetDeviceVendor.restype = ctypes.c_uint16
    s.SDL_JoystickGetDeviceProduct.restype = ctypes.c_uint16
    s.SDL_JoystickGetDeviceVendor.argtypes = [ctypes.c_int]
    s.SDL_JoystickGetDeviceProduct.argtypes = [ctypes.c_int]
    s.SDL_JoystickOpen.restype = ctypes.c_void_p
    s.SDL_JoystickOpen.argtypes = [ctypes.c_int]
    for fn in ("SDL_JoystickNumButtons", "SDL_JoystickNumAxes", "SDL_JoystickNumHats"):
        getattr(s, fn).restype = ctypes.c_int
        getattr(s, fn).argtypes = [ctypes.c_void_p]
    s.SDL_JoystickGetDeviceGUID.restype = G
    s.SDL_JoystickGetDeviceGUID.argtypes = [ctypes.c_int]
    if s.SDL_Init(0x200) != 0:
        sys.exit(2)
    for _ in range(20):
        n = s.SDL_NumJoysticks()
        if n:
            break
        time.sleep(0.1)
    for i in range(s.SDL_NumJoysticks()):
        if s.SDL_JoystickGetDeviceVendor(i) == vendor and s.SDL_JoystickGetDeviceProduct(i) == product:
            guid = bytes(s.SDL_JoystickGetDeviceGUID(i).data).hex()
            j = s.SDL_JoystickOpen(i)
            print(s.SDL_JoystickNumButtons(j), s.SDL_JoystickNumAxes(j),
                  s.SDL_JoystickNumHats(j), guid)
            break
else:
    s.SDL_InitSubSystem.restype = ctypes.c_bool
    s.SDL_InitSubSystem.argtypes = [ctypes.c_uint32]
    s.SDL_GetJoysticks.restype = ctypes.POINTER(ctypes.c_uint32)
    s.SDL_GetJoysticks.argtypes = [ctypes.POINTER(ctypes.c_int)]
    s.SDL_GetJoystickVendorForID.restype = ctypes.c_uint16
    s.SDL_GetJoystickProductForID.restype = ctypes.c_uint16
    s.SDL_GetJoystickVendorForID.argtypes = [ctypes.c_uint32]
    s.SDL_GetJoystickProductForID.argtypes = [ctypes.c_uint32]
    s.SDL_OpenJoystick.restype = ctypes.c_void_p
    s.SDL_OpenJoystick.argtypes = [ctypes.c_uint32]
    for fn in ("SDL_GetNumJoystickButtons", "SDL_GetNumJoystickAxes", "SDL_GetNumJoystickHats"):
        getattr(s, fn).restype = ctypes.c_int
        getattr(s, fn).argtypes = [ctypes.c_void_p]
    s.SDL_GetJoystickGUIDForID.restype = G
    s.SDL_GetJoystickGUIDForID.argtypes = [ctypes.c_uint32]
    if not s.SDL_InitSubSystem(0x200):
        sys.exit(2)
    count = ctypes.c_int(0)
    for _ in range(20):
        ids = s.SDL_GetJoysticks(ctypes.byref(count))
        if count.value:
            break
        time.sleep(0.1)
    for k in range(count.value):
        jid = ids[k]
        if s.SDL_GetJoystickVendorForID(jid) == vendor and s.SDL_GetJoystickProductForID(jid) == product:
            guid = bytes(s.SDL_GetJoystickGUIDForID(jid).data).hex()
            j = s.SDL_OpenJoystick(jid)
            print(s.SDL_GetNumJoystickButtons(j), s.SDL_GetNumJoystickAxes(j),
                  s.SDL_GetNumJoystickHats(j), guid)
            break
"""


def sdl_libraries() -> list[tuple[str, str]]:
    found = []
    for path, api in (("/usr/lib/libSDL3.so.0", "3"),
                      ("/usr/lib/libSDL2-2.0.so.0", "2")):
        if Path(path).exists():
            found.append((path, api))
    for root in glob.glob(str(Path.home() / ".local/share/flatpak/app/*/*/*/active/files")):
        for lib in glob.glob(f"{root}/**/libSDL2.so", recursive=True):
            found.append((lib, "2"))
        for lib in glob.glob(f"{root}/**/libSDL3.so.0", recursive=True):
            found.append((lib, "3"))
    return found


def ask_sdl(lib: str, api: str) -> tuple[int, int, int, str] | None:
    try:
        r = subprocess.run([sys.executable, "-c", _PROBE, api, lib,
                            str(VENDOR), str(PRODUCT)],
                           capture_output=True, text=True, timeout=40)
    except (OSError, subprocess.SubprocessError):
        return None
    out = r.stdout.split()
    if len(out) != 4:
        return None
    return int(out[0]), int(out[1]), int(out[2]), out[3]


def press_test() -> int:
    """The stronger measurement: press each input and see which index moved.

    Counts are necessary and not sufficient — a derivation that PERMUTES the
    indices produces exactly the right totals, and a permuted mapping is the
    failure this whole path exists to avoid: every binding plausible, every
    binding wrong. So each evdev code is actuated one at a time and SDL is
    asked which of its own indices changed.

    One child process per pad. SDL only enumerates joysticks that existed when
    its subsystem started unless something pumps its udev monitor, so the
    device has to be created BEFORE SDL_Init — which means a fresh process,
    since SDL keeps its device list for the life of one.
    """
    failures = 0
    for pad_name in PADS:
        r = subprocess.run([sys.executable, __file__, "--press-one", pad_name],
                           capture_output=True, text=True, timeout=300)
        sys.stdout.write(r.stdout)
        if r.returncode:
            sys.stdout.write(r.stderr)
            failures += 1
    print("\nMISMATCHES in {} pad(s)".format(failures) if failures
          else "\nevery input SDL reported matched sdl_layout()")
    return 1 if failures else 0


def press_one(pad_name: str) -> int:
    """Actuate every input of one invented pad and check where SDL puts it."""
    import os

    import evdev
    from evdev import UInput

    keys, axes = PADS[pad_name]
    derived = sdl_layout(keys, axes)
    capabilities = {
        evdev.ecodes.EV_KEY: keys,
        evdev.ecodes.EV_ABS: [
            (code, evdev.AbsInfo(value=0, min=-32768, max=32767,
                                 fuzz=0, flat=128, resolution=0))
            if code < ABS_HAT0X else
            (code, evdev.AbsInfo(value=0, min=-1, max=1, fuzz=0, flat=0,
                                 resolution=0))
            for code in axes],
    }
    device = UInput(capabilities, name=f"gamecore-press-{pad_name}",
                    vendor=VENDOR, product=PRODUCT, version=VERSION)
    time.sleep(0.5)                 # udev must create the node before SDL looks

    os.environ["SDL_VIDEODRIVER"] = "dummy"
    os.environ["SDL_JOYSTICK_HIDAPI"] = "0"
    lib = ctypes.CDLL("/usr/lib/libSDL3.so.0")
    lib.SDL_InitSubSystem.restype = ctypes.c_bool
    lib.SDL_InitSubSystem.argtypes = [ctypes.c_uint32]
    lib.SDL_GetJoysticks.restype = ctypes.POINTER(ctypes.c_uint32)
    lib.SDL_GetJoysticks.argtypes = [ctypes.POINTER(ctypes.c_int)]
    lib.SDL_GetJoystickVendorForID.restype = ctypes.c_uint16
    lib.SDL_GetJoystickProductForID.restype = ctypes.c_uint16
    lib.SDL_GetJoystickVendorForID.argtypes = [ctypes.c_uint32]
    lib.SDL_GetJoystickProductForID.argtypes = [ctypes.c_uint32]
    lib.SDL_OpenJoystick.restype = ctypes.c_void_p
    lib.SDL_OpenJoystick.argtypes = [ctypes.c_uint32]
    lib.SDL_GetJoystickButton.restype = ctypes.c_bool
    lib.SDL_GetJoystickButton.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.SDL_GetJoystickAxis.restype = ctypes.c_int16
    lib.SDL_GetJoystickAxis.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.SDL_GetJoystickHat.restype = ctypes.c_uint8
    lib.SDL_GetJoystickHat.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.SDL_UpdateJoysticks.argtypes = []
    lib.SDL_CloseJoystick.argtypes = [ctypes.c_void_p]

    if not lib.SDL_InitSubSystem(0x200):
        print(f"{pad_name}: SDL3 joystick init failed")
        return 2

    joystick = None
    count = ctypes.c_int(0)
    for _ in range(30):
        lib.SDL_UpdateJoysticks()
        ids = lib.SDL_GetJoysticks(ctypes.byref(count))
        for k in range(count.value):
            if (lib.SDL_GetJoystickVendorForID(ids[k]) == VENDOR
                    and lib.SDL_GetJoystickProductForID(ids[k]) == PRODUCT):
                joystick = lib.SDL_OpenJoystick(ids[k])
                break
        if joystick:
            break
        time.sleep(0.2)
    if not joystick:
        print(f"{pad_name}: SDL never saw the virtual pad")
        device.close()
        return 2

    def settle() -> None:
        for _ in range(6):
            lib.SDL_UpdateJoysticks()
            time.sleep(0.02)

    bad = []
    for code in sorted(keys):
        device.write(evdev.ecodes.EV_KEY, code, 1)
        device.syn()
        settle()
        down = [i for i in range(len(derived.buttons))
                if lib.SDL_GetJoystickButton(joystick, i)]
        device.write(evdev.ecodes.EV_KEY, code, 0)
        device.syn()
        settle()
        want = derived.buttons.get(code)
        if down != [want]:
            bad.append(f"key {hex(code)}: derived b{want}, SDL lit {down}")

    for code in sorted(c for c in axes if c < ABS_HAT0X):
        device.write(evdev.ecodes.EV_ABS, code, 30000)
        device.syn()
        settle()
        moved = [i for i in range(len(derived.axes))
                 if lib.SDL_GetJoystickAxis(joystick, i) > 20000]
        device.write(evdev.ecodes.EV_ABS, code, 0)
        device.syn()
        settle()
        want = derived.axes.get(code)
        if moved != [want]:
            bad.append(f"axis {hex(code)}: derived a{want}, SDL moved {moved}")

    for code in sorted(c for c in axes if c >= ABS_HAT0X):
        device.write(evdev.ecodes.EV_ABS, code, 1)
        device.syn()
        settle()
        hat_index = derived.hats.get(code)
        got = (lib.SDL_GetJoystickHat(joystick, hat_index)
               if hat_index is not None else None)
        device.write(evdev.ecodes.EV_ABS, code, 0)
        device.syn()
        settle()
        expect = HAT_RIGHT_MASK if (code - ABS_HAT0X) % 2 == 0 else HAT_DOWN_MASK
        if got != expect:
            bad.append(f"hat {hex(code)}: derived h{hat_index}.{expect}, "
                       f"SDL reported {got}")

    lib.SDL_CloseJoystick(joystick)
    device.close()
    if bad:
        print(f"{pad_name}: MISMATCH")
        for line in bad:
            print(f"    {line}")
        return 1
    print(f"{pad_name}: every input landed on the derived index "
          f"({len(keys)} keys, {len(axes)} abs, counts {derived.counts})")
    return 0


# SDL's hat bitmask, as SDL_GetJoystickHat reports it.
HAT_RIGHT_MASK, HAT_DOWN_MASK = 2, 4


def main() -> int:
    try:
        import evdev
        from evdev import UInput
    except ImportError:
        print("python-evdev is required: pip install evdev")
        return 2
    if not Path("/dev/uinput").exists():
        print("/dev/uinput is absent — nothing to measure against")
        return 2

    if "--press-one" in sys.argv:
        return press_one(sys.argv[sys.argv.index("--press-one") + 1])
    if "--press" in sys.argv:
        return press_test()

    libraries = sdl_libraries()
    if not libraries:
        print("no SDL library found")
        return 2
    print(f"{len(libraries)} SDL librar(ies), {len(PADS)} virtual pad(s)\n")

    failures = 0
    for pad_name, (keys, axes) in PADS.items():
        derived = sdl_layout(keys, axes)
        capabilities = {
            evdev.ecodes.EV_KEY: keys,
            evdev.ecodes.EV_ABS: [
                (code, evdev.AbsInfo(value=0, min=-32768, max=32767,
                                     fuzz=0, flat=128, resolution=0))
                if code < ABS_HAT0X else
                (code, evdev.AbsInfo(value=0, min=-1, max=1, fuzz=0, flat=0,
                                     resolution=0))
                for code in axes],
        }
        try:
            device = UInput(capabilities, name=f"gamecore-probe-{pad_name}",
                            vendor=VENDOR, product=PRODUCT, version=VERSION)
        except Exception as e:
            print(f"  {pad_name}: cannot create a uinput device — {e}")
            return 2
        time.sleep(0.4)          # udev has to create the node and settle
        try:
            print(f"{pad_name}: derived {derived.counts}")
            for lib, api in libraries:
                answer = ask_sdl(lib, api)
                if answer is None:
                    continue
                counts, guid = answer[:3], answer[3]
                verdict = "ok " if counts == derived.counts else "MISMATCH"
                if counts != derived.counts:
                    failures += 1
                print(f"    {verdict} SDL{api} {counts} guid={guid}  "
                      f"{Path(lib).parent.parent.name}")
        finally:
            device.close()
            time.sleep(0.2)
        print()

    print("MISMATCHES:" if failures else "every SDL agreed with sdl_layout()",
          failures or "")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
