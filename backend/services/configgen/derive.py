"""Building a GUID-bound emulator's config from a captured mapping.

`snapshots.py` opens by saying nothing here can be synthesised, and when it was
written that was exactly right:

    azahar (3DS), mgba (GBA), Cemu (Wii U) … bind by a device GUID plus RAW
    BUTTON INDICES, and neither can be derived from a vendor:product.

**The wizard changes the premise, and only that one.** A vendor:product still
says nothing about raw indices — but a pad the owner has just mapped button by
button has had those indices MEASURED. `azahar wrote button_up = 11` is no
longer a number nobody could have predicted; it is a number the capture holds.

What has NOT changed is everything else that paragraph is defending, so the
rules here are narrow on purpose:

  1. **A hand-made snapshot always wins.** If the owner configured the pad
     inside the emulator and pressed "Scan mapping", that is their work and a
     derivation must not touch it. Derivation only fills the case where there
     is nothing.
  2. **Only emulators whose format is known from a REAL file.** azahar and mgba
     are derived because this box carries captured blocks for both, hats and
     analogue axes included, so every line emitted below has a measured
     original. Cemu is refused — see `cemu_is_not_derivable` at the bottom.
  3. **Only pads SDL drives through evdev.** This is the sharp one, and it is
     what `evdev_driven()` exists for.

## Why rule 3 decides everything

The wizard's indices come from SDL's LINUX JOYSTICK driver, because that is
what reads /dev/input. But SDL does not use that driver for every pad: it has
HIDAPI drivers for the Sony, Microsoft and Nintendo families, and those report
a completely different button order for the same physical controller.

That is not a theory, it is the measurement already in `snapshots.py`:

    azahar wrote  button_up = 11        for a DualShock 4
    …while SDL's own GameController mapping calls that pad's D-pad a hat and
    button 11 the touchpad.

Both are true at once because they come from two different drivers. So writing
evdev-derived indices into azahar's config for a HIDAPI-driven pad produces
exactly the failure this module is trying to avoid — a config full of plausible
numbers that binds the wrong things.

For the pads the wizard is FOR, the question does not arise: a controller SDL
has no HIDAPI driver for is a controller SDL reads through evdev, which is the
same source the capture came from. `evdev_driven()` asks SDL rather than
assuming, and a pad it cannot answer for is refused.
"""
from __future__ import annotations

import logging
import subprocess
import sys

from . import mapping_db
from .controllers import sdl2_probe
from .inputs import Input, parse_token

log = logging.getLogger(__name__)

# `Input` and `parse_token` live in `inputs.py` and are re-exported here.
#
# They were defined in this file, and a second copy grew in the abstract model
# next door — same dataclass, same regex, same hat bitmask. Two parsers for one
# grammar is two places for `h0.8` to stop meaning left, and only one of them
# would have a test. The model is the lower layer: this module is one SOURCE of
# it, the wizard's, and SDL's own mapping is the other.
__all__ = ["Input", "parse_token", "captured", "evdev_driven", "bindings_for",
           "azahar_binding", "azahar_compound", "cemu_is_not_derivable"]


# ── the captured bindings ────────────────────────────────────────────────────

def captured(guid: str) -> dict[str, Input] | None:
    """The wizard's bindings for one GUID, or None when it never mapped it.

    Keyed by GUID and not by vendor:product, deliberately: the wizard writes one
    line per SDL identity the pad has, and the caller knows which identity ITS
    emulator computes. Matching on vendor:product would hand azahar the line
    written for the host's SDL3 GUID, whose indices are a different driver's.
    """
    if not guid:
        return None
    wanted = guid.lower()
    for line in mapping_db.read_user():
        parsed = mapping_db.parse(line)
        if not parsed or parsed[0] != wanted:
            continue
        out: dict[str, Input] = {}
        for token in parsed[2].split(","):
            field, _, value = token.partition(":")
            got = parse_token(value)
            if got:
                out[field.strip()] = got
        return out or None
    return None


# ── is this pad read through evdev? ──────────────────────────────────────────

# Asks the same SDL2 twice, once with HIDAPI off. If a HIDAPI driver claims the
# pad the two GUIDs differ — SDL stamps the driver into the GUID's last two
# bytes and the bus byte changes with it — and that difference IS the answer:
# two drivers, two button orders, and the capture only describes one of them.
_HIDAPI_PROBE = (
    "import ctypes,os,sys\n"
    "os.environ['SDL_VIDEODRIVER']='dummy'\n"
    "os.environ['SDL_JOYSTICK_HIDAPI']=sys.argv[3]\n"
    "v=int(sys.argv[1],16);p=int(sys.argv[2],16)\n"
    "try: s=ctypes.CDLL('libSDL2-2.0.so.0')\n"
    "except OSError: sys.exit(1)\n"
    "class G(ctypes.Structure): _fields_=[('data',ctypes.c_uint8*16)]\n"
    "s.SDL_JoystickGetDeviceGUID.restype=G\n"
    "s.SDL_JoystickGetDeviceGUID.argtypes=[ctypes.c_int]\n"
    "s.SDL_JoystickGetDeviceVendor.restype=ctypes.c_uint16\n"
    "s.SDL_JoystickGetDeviceProduct.restype=ctypes.c_uint16\n"
    "s.SDL_JoystickGetDeviceVendor.argtypes=[ctypes.c_int]\n"
    "s.SDL_JoystickGetDeviceProduct.argtypes=[ctypes.c_int]\n"
    "if s.SDL_Init(0x200)!=0: sys.exit(1)\n"
    "for i in range(s.SDL_NumJoysticks()):\n"
    " if s.SDL_JoystickGetDeviceVendor(i)==v and s.SDL_JoystickGetDeviceProduct(i)==p:\n"
    "  print(bytes(s.SDL_JoystickGetDeviceGUID(i).data).hex());break\n"
    "s.SDL_Quit()\n"
)


def _guid_with_hidapi(vendor: str, product: str, enabled: str) -> str:
    try:
        r = subprocess.run(
            [sys.executable, "-c", _HIDAPI_PROBE, vendor, product, enabled],
            capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout.strip()


def evdev_driven(vendor: str, product: str) -> bool | None:
    """True when SDL reads this pad through the same driver the capture did.

    None when it cannot be established — SDL unavailable, pad gone — and the
    caller must treat that as a refusal, not as a yes. An untouched config is
    recoverable; a config full of another driver's indices looks correct and is
    not.
    """
    with_hidapi = _guid_with_hidapi(vendor, product, "1")
    without = _guid_with_hidapi(vendor, product, "0")
    if not with_hidapi or not without:
        return None
    return with_hidapi == without


# ── what a generator asks for ────────────────────────────────────────────────

def bindings_for(vendor: str, product: str, app_id: str = "") -> tuple[str, dict[str, Input]] | None:
    """(guid, bindings) this emulator can be written from, or None.

    The GUID is the one THAT EMULATOR's SDL computes — the whole reason
    `Pad.guid_for()` exists — so a mapping is only handed over when the wizard
    filed a line under that exact identity.

    **The cheap question is asked first, and that ordering is the point.** This
    runs on the hotplug path, once per generator, every time a pad connects —
    and `sdl2_probe` is a SUBPROCESS with an eight-second timeout. On a box that
    has never run the wizard there is nothing to derive from, and finding that
    out has to cost a stat of one absent file rather than an SDL launch per
    emulator. Which is every box, until the day it is not.
    """
    if not mapping_db.read_user():
        return None
    raw = sdl2_probe(vendor, product).get("guid", "")
    if not raw:
        return None
    bindings = captured(raw)
    if not bindings:
        return None
    if evdev_driven(vendor, product) is not True:
        log.info("configgen: not deriving a config for %s:%s — SDL does not "
                 "read it through the driver the mapping was captured with, so "
                 "the button indices would be another driver's",
                 vendor, product)
        return None
    return raw, bindings


# ── azahar's binding syntax ──────────────────────────────────────────────────
# Every shape below has a measured original in the snapshots this box already
# carries: a button and a trigger axis in azahar/054c_09cc.snap, a hat D-pad in
# azahar/045e_02fd.snap, and the compound stick in both. Qt serialises the keys
# alphabetically, which is why they are emitted sorted rather than in a natural
# reading order — a differently ordered line is not wrong for azahar, but it
# would make every diff against a captured snapshot noise.

def azahar_binding(inp: Input, guid: str, threshold: float = 0.5) -> str:
    fields: dict[str, str] = {"engine": "sdl", "guid": guid, "port": "0"}
    if inp.kind == "button":
        fields["button"] = str(inp.index)
    elif inp.kind == "hat":
        fields["hat"] = str(inp.index)
        fields["direction"] = inp.direction
    else:
        fields["axis"] = str(inp.index)
        fields["direction"] = inp.direction
        fields["threshold"] = f"{threshold}"
    return ",".join(f"{k}:{fields[k]}" for k in sorted(fields))


def azahar_compound(part: str) -> str:
    """A binding nested inside another one: `:` becomes `$0`, `,` becomes `$1`.

    azahar's own escaping, and the reason `snapshots.guid_scannable()` exists —
    the `0` of `$0` is a hex digit, which hid every stick binding from the
    GUID check until it was measured.
    """
    return part.replace(":", "$0").replace(",", "$1")


# ── why Cemu is not here ─────────────────────────────────────────────────────

cemu_is_not_derivable = """Cemu's <uuid> is not an identity anything else on this box can compute.

Measured, same physical DualShock 4, same instant:

    Cemu wrote            05009b514c050000cc09000000810000
    the host's SDL3 says  05008fe54c050000cc09000000006800

The name CRC (bytes 2-3) and the driver tail (bytes 14-15) both differ, so the
GUID cannot be derived from any SDL this process can ask — which is precisely
the reason `snapshots.py` made Cemu a snapshot rather than a GUID rewrite in
the first place, and the wizard does not change it: the capture supplies BUTTON
INDICES, not a Cemu-computed device id.

Its <button> values are the second problem. controller0.xml on this box uses
0-15 for buttons and 38-47 for axis and trigger pseudo-buttons, an encoding
internal to Cemu's SDLController that no file here documents and that cannot be
checked without running Cemu and watching what it binds.

Two unknowns, both of which produce a config that looks right. "Scan mapping"
remains the way to teach Cemu a pad, and that path still works.
"""
