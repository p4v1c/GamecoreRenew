"""The common controller abstraction — one `Pad`, resolved per consumer.

Batocera's `Controller` carries one `guid` and one `real_name`, and that works
because Batocera owns its SDL: EmulationStation and every emulator link the
same library, and it even regenerates gamecontrollerdb.txt per session to make
sure of it.

GameCore does not own its SDL. Each Flatpak brings its own, and the same pad
therefore has SEVERAL simultaneous identities. Measured on the reference box,
one DualShock 4:

    host libSDL3 / sdl2-compat        05008fe54c050000cc09000000006800
    libSDL2 bundled by Ryujinx        03008fe54c050000cc09000000006800
    what azahar wrote for itself      03008fe54c050000cc09000000006800
    what Cemu wrote for itself        05009b514c050000cc09000000810000

The first two were read at the same instant, from the same pad: bus 0x05
against bus 0x03. That alone is why a single `guid` field cannot carry the
truth here, and why this class exposes `guid_for(app_id)` rather than `.guid`.

Generators never touch evdev or SDL: they receive a `Pad` and ask it. That is
the part of Batocera's structure worth taking — the flattening is not.
"""
from __future__ import annotations

import contextlib
import glob
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from ..paths import backend_data_dir

log = logging.getLogger(__name__)

DB_FILE = backend_data_dir() / "gamecontrollerdb.txt"
SDL_INIT_GAMEPAD = 0x2000


# ── GUID <-> vendor:product ───────────────────────────────────────────────

def vidpid_of(guid: str) -> tuple[str, str]:
    """SDL packs vendor/product as little-endian 16-bit words at a fixed hex
    offset, stable across every GUID format revision seen on this box (03..
    and 05.. bus-type prefixes both use it)."""
    vendor = (guid[10:12] + guid[8:10]).lower()
    product = (guid[18:20] + guid[16:18]).lower()
    return vendor, product


# SDL stamps the driver that read a pad into byte 14 of its GUID — `h` (0x68)
# for one of the HIDAPI drivers, zero for the linux joystick driver that reads
# /dev/input. Measured on this box, one DualShock 4, the two probes an instant
# apart:
#
#     SDL_JOYSTICK_HIDAPI=1   05008fe54c050000cc09000000006800
#     SDL_JOYSTICK_HIDAPI=0   05009b514c050000cc09000000810000
#
# `derive.evdev_driven()` reaches the same fact by asking SDL twice and
# comparing, which needs the pad present. This reads it off a saved GUID alone,
# which is what a caller holding a stored line and no connected pad can do.
_GUID_DRIVER_BYTE = slice(28, 30)


def guid_read_through_evdev(guid: str) -> bool:
    """Whether the identity in `guid` was read by the driver that reads
    /dev/input — and therefore whether indices captured from /dev/input are in
    its numbering.

    False for anything malformed: this answers a question whose wrong answer
    publishes one driver's button order under another driver's name, so an
    unreadable GUID is a no.
    """
    guid = guid.strip().lower()
    if len(guid) != 32:
        return False
    try:
        int(guid, 16)
    except ValueError:
        return False
    return guid[_GUID_DRIVER_BYTE] == "00"


def db_name_for(vendor: str, product: str) -> str | None:
    """Canonical SDL product name for a vendor:product, from the vendored
    gamecontrollerdb.txt — a LAST resort: it is the SDL2-era community name and
    is wrong for SDL3 on some pads."""
    try:
        text = DB_FILE.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        fields = line.split(",")
        if len(fields) < 2 or len(fields[0]) < 20:
            continue
        v, p = vidpid_of(fields[0])
        if v == vendor and p == product:
            return fields[1].strip()
    return None


# SDL3 HIDAPI names for pads we know, used when live SDL3 enumeration is
# unavailable (library missing, or the pad went back to sleep between the
# evdev scan and this call). These differ from the SDL2 community-DB names.
SDL3_FALLBACK_NAMES = {
    ("054c", "05c4"): "PS4 Controller",
    ("054c", "09cc"): "PS4 Controller",
    ("054c", "0ba0"): "PS4 Controller",          # DS4 USB dongle
    ("054c", "0ce6"): "DualSense Wireless Controller",
    ("054c", "0df2"): "DualSense Edge Wireless Controller",
}

_sdl3_cache: tuple[float, dict[tuple[str, str], str]] = (0.0, {})

# The two variables SDL reads a mapping table from. Named once because two
# places care about them for opposite reasons: this file's name lookup wants
# the served table, and every SUBPROCESS PROBE wants none of it — see
# `probe_env` below.
_MAPPING_ENV = ("SDL_GAMECONTROLLERCONFIG_FILE", "SDL_GAMECONTROLLERCONFIG")


@contextlib.contextmanager
def _served_db_in_env():
    """Point SDL at the served database for the duration of ONE in-process init.

    It used to be an `os.environ.setdefault`, which is a permanent mutation of
    the backend's own environment — and the environment is what every
    `subprocess.run` below inherits. Measured on the reference box, one
    DualShock 4, after the owner ran the wizard:

        a fresh process asks azahar's SDL2 for its mapping
            start:b6  back:b4  leftshoulder:b9  rightshoulder:b10  dpup:b11
        the same call inside a backend that had enumerated a pad once
            start:b9  back:b8  leftshoulder:b4  rightshoulder:b5  dpup:h0.1

    The second is the owner's own capture, read back out of the served file and
    returned as though SDL had said it. `inputs.py` is built on those two
    sources never mixing, and this leak mixed them without passing the guard
    that exists to stop exactly that — `evdev_driven()` was never asked,
    because the capture no longer arrived by the wizard's road. What reached
    the box was azahar bound to a hat its SDL calls buttons 11-14, `start` on
    that driver's L1, and nothing at all on R1.

    Restored on the way out, so the leak cannot outlive the call.
    """
    from . import mapping_db
    db = mapping_db.served()
    if not db:
        yield
        return
    before = os.environ.get("SDL_GAMECONTROLLERCONFIG_FILE")
    os.environ["SDL_GAMECONTROLLERCONFIG_FILE"] = str(db)
    try:
        yield
    finally:
        if before is None:
            os.environ.pop("SDL_GAMECONTROLLERCONFIG_FILE", None)
        else:
            os.environ["SDL_GAMECONTROLLERCONFIG_FILE"] = before


def probe_env() -> dict[str, str]:
    """The environment an SDL probe subprocess runs in: this one, minus any
    mapping table.

    A probe asks SDL what IT knows about a pad. A mapping file on the way in
    makes it answer with what the file knows instead — and SDL keeps the LAST
    line it reads for a GUID, so a table containing the owner's capture wins
    over SDL's built-in every time. The answer is then evdev indices wearing
    the name of the driver's.

    Scrubbed here rather than trusted to be absent: the backend is not the only
    thing that can put it there, and a probe whose answer depends on who
    started the process is a probe that gives one box two configs.
    """
    env = dict(os.environ)
    for name in _MAPPING_ENV:
        env.pop(name, None)
    return env


def _sdl3_live_names() -> dict[tuple[str, str], str]:
    """vendor:product → device name for every currently-connected gamepad, as
    reported by the system's libSDL3 — the same library family RPCS3 and
    Dolphin bundle, so the name written to their configs is byte-for-byte the
    name they will enumerate at boot."""
    import ctypes

    os.environ.setdefault("SDL_NO_SIGNAL_HANDLERS", "1")
    lib = ctypes.CDLL("libSDL3.so.0")
    lib.SDL_InitSubSystem.restype = ctypes.c_bool
    lib.SDL_InitSubSystem.argtypes = [ctypes.c_uint32]
    lib.SDL_QuitSubSystem.argtypes = [ctypes.c_uint32]
    lib.SDL_GetGamepads.restype = ctypes.POINTER(ctypes.c_uint32)
    lib.SDL_GetGamepads.argtypes = [ctypes.POINTER(ctypes.c_int)]
    lib.SDL_GetGamepadNameForID.restype = ctypes.c_char_p
    lib.SDL_GetGamepadNameForID.argtypes = [ctypes.c_uint32]
    lib.SDL_GetGamepadVendorForID.restype = ctypes.c_uint16
    lib.SDL_GetGamepadVendorForID.argtypes = [ctypes.c_uint32]
    lib.SDL_GetGamepadProductForID.restype = ctypes.c_uint16
    lib.SDL_GetGamepadProductForID.argtypes = [ctypes.c_uint32]
    lib.SDL_free.argtypes = [ctypes.c_void_p]

    names: dict[tuple[str, str], str] = {}
    # The SERVED database, not the vendored one: a pad the owner has just
    # mapped by hand must be enumerated here exactly as the emulators will
    # enumerate it, or the name we write into their configs comes from a
    # different table than the one they read. A NAME is safe to take from the
    # owner's table; an INDEX is not, which is the whole distinction
    # `probe_env` draws.
    with _served_db_in_env():
        if not lib.SDL_InitSubSystem(SDL_INIT_GAMEPAD):
            return names
        try:
            count = ctypes.c_int(0)
            pads = lib.SDL_GetGamepads(ctypes.byref(count))
            if pads:
                for k in range(count.value):
                    jid = pads[k]
                    raw = lib.SDL_GetGamepadNameForID(jid)
                    vendor = lib.SDL_GetGamepadVendorForID(jid)
                    product = lib.SDL_GetGamepadProductForID(jid)
                    if raw and vendor:
                        names[(f"{vendor:04x}", f"{product:04x}")] = raw.decode()
                lib.SDL_free(pads)
        finally:
            lib.SDL_QuitSubSystem(SDL_INIT_GAMEPAD)
    return names


def sdl3_names(want: tuple[str, str] | None = None) -> dict[tuple[str, str], str]:
    """_sdl3_live_names() behind a short cache, degrading to {} rather than
    raising when libSDL3 is unavailable.

    `want` is the pad the caller is asking about. A 5 s cache with a 3 s scan
    period meant a pad that had just arrived was answered from a snapshot taken
    before it existed, and the name fell through to the static table or the
    community DB — right for a DualShock 4 by luck, wrong for anything less
    common. A cached miss on the pad we are asking about is therefore worth one
    re-enumeration, rate-limited so an unplugged pad cannot spin SDL up on
    every pass.
    """
    global _sdl3_cache
    ts, cached = _sdl3_cache
    stale = time.monotonic() - ts > 5.0 or not cached
    missing = want is not None and want not in cached and time.monotonic() - ts > 1.0
    if stale or missing:
        try:
            cached = _sdl3_live_names()
        except Exception:
            log.warning("configgen: SDL3 enumeration failed — falling back to "
                        "static names", exc_info=True)
            cached = {}
        _sdl3_cache = (time.monotonic(), cached)
    return cached


class ResolvedName(str):
    """A device name, plus WHERE it came from.

    A bare string could not tell a reliable answer from a guess, and the
    guesses were being written into configs. `source` is one of:

        sdl3_live       libSDL3 named this pad, with it connected. The truth.
        fallback_table  SDL3_FALLBACK_NAMES — measured SDL3 names. Reliable.
        unknown         neither answered. The VALUE is still the pad's kernel
                        name, so a log line or a toast reads sensibly, but it
                        is not what an SDL3 emulator enumerates and a consumer
                        that matches by name must refuse to write it.

    Only three, and deliberately: the community DB and the raw kernel name are
    not rungs of this chain any more. They are `display_name()`'s business,
    where being approximately right is the whole job. Keeping them here as
    "sources" would have preserved exactly the confusion this class exists to
    remove — a value that reads like an answer and is a guess.

    A `str` subclass, like `Skip`, so every existing consumer — the f-strings
    in the generators, the dup counter, the JSON the router returns — keeps
    working unchanged and only the callers that must care, care.
    """
    __slots__ = ("source",)

    def __new__(cls, value: str, source: str):
        obj = super().__new__(cls, value)
        obj.source = source
        return obj


# Which rungs are a real answer to "what will an SDL3 emulator enumerate".
SDL3_TRUSTED = frozenset({"sdl3_live", "fallback_table"})

# vendor:product → the rung it last came back on. `Pad.name` is a property, so
# one profiling pass resolves the same pad about ten times, and the monitor
# retries an incomplete pass five times: an unconditional line here would be
# fifty copies of the same warning per pad. Said once, and again whenever the
# answer CHANGES — which is the interesting event, because a pad that moves
# from sdl3_live to unknown is a pad that went to sleep.
_logged_resolution: dict[tuple[str, str], str] = {}


def _say_once(vendor: str, product: str, source: str, level: int,
              message: str, *args) -> None:
    if _logged_resolution.get((vendor, product)) == source:
        return
    _logged_resolution[(vendor, product)] = source
    log.log(level, message, *args)


def resolve_name(vendor: str, product: str, evdev_name: str) -> ResolvedName:
    """The device-name string SDL3-based emulators (RPCS3, Dolphin) will see.

    **The community DB is no longer in this chain.** It is an SDL2-era name and
    is wrong for SDL3 on several pads, which showed up live in RPCS3.log as
    "SDL: Adding empty device" and a dead pad in game. It survives in
    `display_name()`, where being approximately right is exactly what is wanted.

    **The failure this exists to stop being silent is an ABSENCE, not an
    exception.** `sdl3_names()` warns when libSDL3 raises — but the common case
    is that SDL3 answers perfectly well and simply does not know this pad,
    which is what the comment on SDL3_FALLBACK_NAMES describes ("the pad went
    back to sleep between the evdev scan and this call"). No exception, a valid
    dict without the entry, and the chain used to walk quietly down to the raw
    kernel name and write it. The only trace was in the EMULATOR's log, not
    ours. So every rung below the first says so.
    """
    live = sdl3_names((vendor, product)).get((vendor, product))
    if live:
        _say_once(vendor, product, "sdl3_live", logging.DEBUG,
                  "configgen: libSDL3 names %s:%s %r", vendor, product, live)
        return ResolvedName(live, "sdl3_live")

    table = SDL3_FALLBACK_NAMES.get((vendor, product))
    if table:
        # Not a failure — these were measured against SDL3 — but it does mean
        # the pad was not enumerated live, which is worth knowing when a config
        # written now turns out not to match at boot.
        _say_once(vendor, product, "fallback_table", logging.INFO,
                  "configgen: libSDL3 did not enumerate %s:%s — falling back "
                  "to the known-pads table (%r)", vendor, product, table)
        return ResolvedName(table, "fallback_table")

    _say_once(vendor, product, "unknown", logging.WARNING,
              "configgen: no SDL3 name for %s:%s — libSDL3 does not enumerate "
              "it and it is not in the known-pads table. Its kernel name is "
              "%r, which is NOT what an SDL3 emulator calls a device: written "
              "into a config it produces \"SDL: Adding empty device\" and a "
              "pad that is dead in game. The emulators that match by name are "
              "left untouched.", vendor, product, evdev_name)
    return ResolvedName(evdev_name, "unknown")


def display_name(vendor: str, product: str, evdev_name: str) -> str:
    """A name for a HUMAN — a toast, a log line, the Power menu.

    Where `resolve_name` must refuse a guess because the string has to match
    what an emulator enumerates, this one only has to be recognisable, so the
    community DB earns its place: "Horipad Mini 4" tells the owner which pad is
    in their hands, and no config is written from it.
    """
    resolved = resolve_name(vendor, product, evdev_name)
    if resolved.source in SDL3_TRUSTED:
        return str(resolved)
    return db_name_for(vendor, product) or evdev_name


# ── Ryujinx GUID ──────────────────────────────────────────────────────────

def ryu_guid_vidpid(dashed_guid: str) -> tuple[str, str] | None:
    """(vendor, product) from a Ryujinx dashed SDL GUID.

    Kept for READING a Config.json, never for deciding what to write: two pads
    can share a vendor:product and still have different GUIDs (a DualShock 4
    over USB and the same pad over Bluetooth differ in their bus and driver
    bytes). Treating this as an identity is what broke Ryujinx.
    """
    g = dashed_guid.replace("-", "")
    if len(g) != 32:
        return None
    return g[8:12].lower(), (g[18:20] + g[16:18]).lower()


def ryu_guid_from_sdl2(sdl_hex: str) -> str | None:
    """Ryujinx's dashed GUID from SDL2's raw 32-hex one.

    Ryujinx hands SDL2's 16 GUID bytes straight to .NET's `System.Guid`, whose
    string form reverses the first three fields and leaves the last eight bytes
    alone. So the whole thing is a byte reordering, not a lossy summary.

    **Bytes 2-3 are zeroed first.** SDL 2.26 started packing a CRC16 of the
    device name there to tell apart pads that share a vendor:product; Ryujinx
    clears it before building its id, so the CRC must not survive into what we
    write. Bus byte and CRC are two independent corrections and both are
    required — zeroing the CRC on the host's answer still yields bus 0x05, an
    id Ryujinx never computes.
    """
    try:
        b = bytearray.fromhex(sdl_hex)
    except ValueError:
        return None
    if len(b) != 16:
        return None
    b[2] = b[3] = 0
    return "-".join((bytes(b[0:4])[::-1].hex(), bytes(b[4:6])[::-1].hex(),
                     bytes(b[6:8])[::-1].hex(), bytes(b[8:10]).hex(),
                     bytes(b[10:16]).hex()))


# ── asking a specific SDL2 ────────────────────────────────────────────────

_SDL2_PROBE = (
    "import ctypes,os,sys\n"
    "os.environ['SDL_VIDEODRIVER']='dummy'\n"
    "v=int(sys.argv[1],16);p=int(sys.argv[2],16)\n"
    "lib=sys.argv[3] if len(sys.argv)>3 and sys.argv[3] else 'libSDL2-2.0.so.0'\n"
    "try: s=ctypes.CDLL(lib)\n"
    "except OSError: sys.exit(0)\n"
    "class G(ctypes.Structure): _fields_=[('data',ctypes.c_uint8*16)]\n"
    "s.SDL_GameControllerMappingForDeviceIndex.restype=ctypes.c_char_p\n"
    "s.SDL_GameControllerMappingForDeviceIndex.argtypes=[ctypes.c_int]\n"
    "s.SDL_JoystickGetDeviceGUID.restype=G\n"
    "s.SDL_JoystickGetDeviceGUID.argtypes=[ctypes.c_int]\n"
    "s.SDL_JoystickGetDeviceVendor.restype=ctypes.c_uint16\n"
    "s.SDL_JoystickGetDeviceProduct.restype=ctypes.c_uint16\n"
    "s.SDL_JoystickGetDeviceVendor.argtypes=[ctypes.c_int]\n"
    "s.SDL_JoystickGetDeviceProduct.argtypes=[ctypes.c_int]\n"
    "if s.SDL_Init(0x2000)!=0: sys.exit(0)\n"
    "for i in range(s.SDL_NumJoysticks()):\n"
    " if s.SDL_JoystickGetDeviceVendor(i)==v and s.SDL_JoystickGetDeviceProduct(i)==p:\n"
    "  print('GUID '+bytes(s.SDL_JoystickGetDeviceGUID(i).data).hex())\n"
    "  m=s.SDL_GameControllerMappingForDeviceIndex(i)\n"
    "  print('MAP '+m.decode()) if m else None\n"
    "  break\n"
    "s.SDL_Quit()\n"
)

_sdl2_cache: dict[tuple[str, str, str], tuple[float, dict[str, str]]] = {}
_bundled_sdl_cache: dict[str, str] = {}
_bundled_sdl3_cache: dict[str, str] = {}
_flatpak_loc_cache: dict[str, str] = {}
_runtime_loc_cache: dict[str, str] = {}


def flatpak_location(app_id: str) -> str:
    """Deploy directory of an installed flatpak, or "". Cached per process."""
    if app_id in _flatpak_loc_cache:
        return _flatpak_loc_cache[app_id]
    out = ""
    try:
        r = subprocess.run(["flatpak", "info", "--show-location", app_id],
                           capture_output=True, text=True, timeout=8)
        if r.returncode == 0:
            out = r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    _flatpak_loc_cache[app_id] = out
    return out


def flatpak_runtime_location(app_id: str) -> str:
    """Deploy directory of the RUNTIME an installed flatpak links against.

    An app that ships no SDL of its own is not an app with no SDL: it links its
    runtime's, and that library is on this filesystem and can be asked.
    """
    if app_id in _runtime_loc_cache:
        return _runtime_loc_cache[app_id]
    out = ""
    try:
        r = subprocess.run(["flatpak", "info", "--show-runtime", app_id],
                           capture_output=True, text=True, timeout=8)
        runtime = r.stdout.strip() if r.returncode == 0 else ""
        if runtime:
            r = subprocess.run(
                ["flatpak", "info", "--show-location", f"runtime/{runtime}"],
                capture_output=True, text=True, timeout=8)
            if r.returncode == 0:
                out = r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    _runtime_loc_cache[app_id] = out
    return out


# Where a flatpak runtime keeps its shared libraries. One entry today, and a
# list rather than a constant because the path is the runtime's convention and
# not ours.
_RUNTIME_LIB_DIRS = ("files/lib/x86_64-linux-gnu", "files/lib")


def bundled_sdl2(app_id: str) -> str:
    """Absolute path of the SDL2 a flatpak'd emulator really uses, or "".

    Measured on the reference box, same physical DualShock 4, same instant:

        host libSDL2-2.0.so.0 (sdl2-compat over SDL3)
            05008fe54c050000cc09000000006800   bus 0x0005, Bluetooth
        Ryujinx's bundled libSDL2.so (real SDL 2.30.0)
            03008fe54c050000cc09000000006800   bus 0x0003, USB

    One byte, the bus type: SDL3 reports the transport, SDL2 2.30 reports USB
    for anything HIDAPI drives, Bluetooth included. That one byte is the
    difference between Ryujinx binding the pad and its
    `_gamepadsIds.IndexOf(id)` returning -1 and disposing the slot in silence.

    **The runtime is checked when the app ships nothing, and it is not a
    nicety.** Ryujinx bundles `files/bin/libSDL2.so`; azahar, melonDS and RMG
    ship none and link `org.kde.Platform`'s. Returning "" for those meant "ask
    the host", and the host is sdl2-compat over SDL3 — a different library that
    answers differently. Measured, one DualShock 4, same instant:

        host sdl2-compat 2.32.70    dpup:h0.1  dpdown:h0.4  …  touchpad:b11
        org.kde.Platform 6.9's
        real SDL 2.32.10            dpup:b11   dpdown:b12  …  touchpad:b15

    That second line is not a curiosity: `snapshots.py` records azahar writing
    `button_up = 11` for this exact pad and calls it unexplainable next to SDL's
    own mapping "which claims a hat and calls button 11 the touchpad". Both are
    true, and this is why — two SDL2 builds, two answers, and azahar's is the
    one in the runtime. Asking the host for an azahar binding produces a hat
    where azahar wants button 11: a config full of plausible numbers binding the
    wrong things, which is the failure the whole package is arranged to avoid.

    App first, runtime second, host never: the order is the specificity order,
    and an app that bundles its own SDL is not affected by any of this.
    """
    if app_id in _bundled_sdl_cache:
        return _bundled_sdl_cache[app_id]
    path = ""
    loc = flatpak_location(app_id)
    if loc:
        lib = Path(loc) / "files" / "bin" / "libSDL2.so"
        if lib.is_file():
            path = str(lib)
    if not path:
        runtime = flatpak_runtime_location(app_id)
        for rel in _RUNTIME_LIB_DIRS if runtime else ():
            lib = Path(runtime) / rel / "libSDL2-2.0.so.0"
            if lib.is_file():
                path = str(lib)
                break
    _bundled_sdl_cache[app_id] = path
    return path


def sdl2_probe(vendor: str, product: str, lib: str = "") -> dict[str, str]:
    """What SDL2 itself says about a connected pad: its raw 32-hex GUID and its
    GameController mapping. `{}` when SDL2 cannot be asked.

    **Itself** is the load-bearing word, and `probe_env` is what enforces it:
    the probe runs with no mapping table in its environment, so the mapping
    that comes back is SDL's own built-in one for the driver it really uses.
    Handed the served database instead, it returns the owner's capture — evdev
    indices for a pad SDL reads through HIDAPI — and the caller has no way to
    tell the two apart.

    `lib` picks WHICH SDL2 answers. Empty means the host's. Pass an emulator's
    bundled one whenever the answer is going into that emulator's config.

    Run in a SUBPROCESS because the backend has already loaded SDL3 into its
    own address space, and because these answers must come from the same SDL2
    the emulators use.
    """
    key = (vendor.lower(), product.lower(), lib)
    ts, cached = _sdl2_cache.get(key, (0.0, {}))
    if cached and time.monotonic() - ts <= 5.0:
        return cached
    try:
        r = subprocess.run([sys.executable, "-c", _SDL2_PROBE, vendor, product, lib],
                           capture_output=True, text=True, timeout=8,
                           env=probe_env())
    except (OSError, subprocess.SubprocessError) as e:
        # Two different facts used to leave here as the same empty dict: "SDL
        # ran, and this pad is not among its joysticks" and "SDL was never
        # asked". Only the first is an answer about the pad.
        #
        # The second is what the reference box hit — three times over several
        # days, each at the instant a Bluetooth pad connected — and it reached
        # the player as "SDL2 would not report a GUID": a claim about SDL's
        # answer, for a probe that never produced one. It sent the diagnosis
        # to gamecontrollerdb and to /dev/input permissions, neither of which
        # was involved; measured afterwards, that same SDL2 returned the GUID
        # ten times out of ten in 0.85 s.
        #
        # The exception was discarded as well, so the journal could not tell a
        # timeout from a failure to spawn — which is why the errno behind those
        # three lines is now unrecoverable. `error` carries the class to the
        # caller, the log line carries the detail to whoever reads it.
        log.warning("configgen: SDL2 probe for %s:%s could not be run (%s: %s)",
                    vendor, product, e.__class__.__name__, e)
        # Deliberately not cached: a probe that never ran is not a finding
        # about this pad, and the monitor's retry must be free to ask again.
        return {"error": e.__class__.__name__}
    out: dict[str, str] = {}
    for line in r.stdout.splitlines():
        tag, _, value = line.partition(" ")
        if tag in ("GUID", "MAP") and value:
            out[tag.lower()] = value.strip()
    if out:
        _sdl2_cache[key] = (time.monotonic(), out)
    return out


# ── asking a specific SDL3 who a pad IS ───────────────────────────────────

# RMG-Input identifies a pad by three strings at once and compares them by
# equality (Source/RMG-Input/main.cpp:647):
#
#     deviceName == profile->DeviceName && devicePath == profile->DevicePath
#                                       && deviceSerial == profile->DeviceSerial
#
# read from SDL_GetGamepadName / Path / Serial. One field wrong and the profile
# does not attach — silently, the way a wrong GUID silently disposes Ryujinx's
# slot. The name has a source of its own (`resolve_name`, which is already what
# every SDL3-name consumer uses); the other two are what this probe is for.
#
# **They are not derivable from the pad's ids, and not interchangeable.**
# Measured on the reference box, same instant:
#
#     054c:09cc DualShock 4    path /dev/hidraw0     serial 40:1b:5f:b9:ea:8d
#     045e:02fd Xbox Wireless  path /dev/input/event14   serial ""
#
# SDL names the node of whichever driver it reads the pad through — hidraw for
# the HIDAPI families, the evdev node otherwise — and only a HIDAPI-driven pad
# has a serial at all. So `_hidraw_for(serial)` can answer for the first pad
# and can never answer for the second, and inventing an empty path for it
# writes a profile RMG will not match.
_SDL3_IDENTITY_PROBE = (
    "import ctypes,os,sys\n"
    "os.environ['SDL_VIDEODRIVER']='dummy'\n"
    "os.environ.setdefault('SDL_NO_SIGNAL_HANDLERS','1')\n"
    "v=int(sys.argv[1],16);p=int(sys.argv[2],16)\n"
    "lib=sys.argv[3] if len(sys.argv)>3 and sys.argv[3] else 'libSDL3.so.0'\n"
    "try: s=ctypes.CDLL(lib)\n"
    "except OSError: sys.exit(0)\n"
    "s.SDL_InitSubSystem.restype=ctypes.c_bool\n"
    "s.SDL_InitSubSystem.argtypes=[ctypes.c_uint32]\n"
    "s.SDL_GetGamepads.restype=ctypes.POINTER(ctypes.c_uint32)\n"
    "s.SDL_GetGamepads.argtypes=[ctypes.POINTER(ctypes.c_int)]\n"
    "s.SDL_GetGamepadVendorForID.restype=ctypes.c_uint16\n"
    "s.SDL_GetGamepadProductForID.restype=ctypes.c_uint16\n"
    "s.SDL_GetGamepadVendorForID.argtypes=[ctypes.c_uint32]\n"
    "s.SDL_GetGamepadProductForID.argtypes=[ctypes.c_uint32]\n"
    "s.SDL_GetGamepadPathForID.restype=ctypes.c_char_p\n"
    "s.SDL_GetGamepadPathForID.argtypes=[ctypes.c_uint32]\n"
    "s.SDL_OpenGamepad.restype=ctypes.c_void_p\n"
    "s.SDL_OpenGamepad.argtypes=[ctypes.c_uint32]\n"
    "s.SDL_GetGamepadSerial.restype=ctypes.c_char_p\n"
    "s.SDL_GetGamepadSerial.argtypes=[ctypes.c_void_p]\n"
    "s.SDL_CloseGamepad.argtypes=[ctypes.c_void_p]\n"
    "if not s.SDL_InitSubSystem(0x2000): sys.exit(0)\n"
    "n=ctypes.c_int(0)\n"
    "ids=s.SDL_GetGamepads(ctypes.byref(n))\n"
    "for i in range(n.value):\n"
    " j=ids[i]\n"
    " if s.SDL_GetGamepadVendorForID(j)!=v: continue\n"
    " if s.SDL_GetGamepadProductForID(j)!=p: continue\n"
    " q=s.SDL_GetGamepadPathForID(j)\n"
    " print('PATH '+(q.decode() if q else ''))\n"
    " g=s.SDL_OpenGamepad(j)\n"
    " if g:\n"
    "  r=s.SDL_GetGamepadSerial(g)\n"
    "  print('SERIAL '+(r.decode() if r else ''))\n"
    "  s.SDL_CloseGamepad(g)\n"
    " break\n"
    "s.SDL_Quit()\n"
)

_sdl3_identity_cache: dict[tuple[str, str, str], tuple[float, dict[str, str]]] = {}


def bundled_sdl3(app_id: str) -> str:
    """Absolute path of the libSDL3 a flatpak'd emulator really uses, or "".

    `bundled_sdl2`'s twin, and same order — app first, runtime second — for the
    same reason: an app that ships its own library is not answered by anybody
    else's. RMG ships none and links `org.kde.Platform`'s.

    **Where it differs from its twin: the host is an acceptable last resort
    here, and it is measured rather than assumed.** `bundled_sdl2` says "host
    never" because a GUID encodes the bus byte and two SDL builds disagree
    about it. These three strings are properties of the DEVICE and the driver
    reading it, not of the enumerating build. Measured, one DualShock 4, same
    instant, on the reference box:

        host libSDL3 3.4.12               PS4 Controller  /dev/hidraw0
                                          40:1b:5f:b9:ea:8d
        org.kde.Platform 6.10's
        libSDL3 3.2.30 — RMG's own        PS4 Controller  /dev/hidraw0
                                          40:1b:5f:b9:ea:8d

    Byte-identical across two SDL3 generations. So the caller may fall back to
    the host, and this returning "" is not a refusal to answer.
    """
    if app_id in _bundled_sdl3_cache:
        return _bundled_sdl3_cache[app_id]
    path = ""
    loc = flatpak_location(app_id)
    if loc:
        lib = Path(loc) / "files" / "lib" / "libSDL3.so.0"
        if lib.is_file():
            path = str(lib)
    if not path:
        runtime = flatpak_runtime_location(app_id)
        for rel in _RUNTIME_LIB_DIRS if runtime else ():
            lib = Path(runtime) / rel / "libSDL3.so.0"
            if lib.is_file():
                path = str(lib)
                break
    _bundled_sdl3_cache[app_id] = path
    return path


def sdl3_identity(vendor: str, product: str, lib: str = "") -> dict[str, str]:
    """`{"path": …, "serial": …}` for a connected pad, or `{}`.

    A present key with an empty value is an ANSWER — "SDL read this pad through
    a driver that gives it no serial" — and `{}` is the absence of one. The
    caller must be able to tell those apart: writing `DeviceSerial = ""` is
    correct for an Xbox pad and is a guess for a pad SDL never reported.

    Run in a SUBPROCESS, like `sdl2_probe` and for one more reason besides. The
    backend has libSDL3 loaded in its own address space already, so a second
    build cannot be dlopen'd next to it; and reading a serial means OPENING the
    gamepad, which hands the pad to SDL's HIDAPI driver for the duration. Doing
    that inside the process that is also enumerating pads on a three-second
    loop is a side effect nobody asked for.

    `probe_env()` rather than the served mapping table, and the distinction is
    the one `inputs.py` draws: a mapping table can rename a pad, so a NAME is
    taken from `resolve_name`, which enumerates WITH the table exactly as the
    emulators will. A path and a serial come from the device and no table can
    speak into them.
    """
    key = (vendor.lower(), product.lower(), lib)
    ts, cached = _sdl3_identity_cache.get(key, (0.0, {}))
    if cached and time.monotonic() - ts <= 5.0:
        return cached
    try:
        r = subprocess.run(
            [sys.executable, "-c", _SDL3_IDENTITY_PROBE, vendor, product, lib],
            capture_output=True, text=True, timeout=8, env=probe_env())
    except (OSError, subprocess.SubprocessError) as e:
        # Same distinction `sdl2_probe` makes, and not cached for the same
        # reason: a probe that never ran said nothing about this pad.
        log.warning("configgen: SDL3 identity probe for %s:%s could not be run "
                    "(%s: %s)", vendor, product, e.__class__.__name__, e)
        return {}
    out: dict[str, str] = {}
    for line in r.stdout.splitlines():
        tag, _sep, value = line.partition(" ")
        if tag in ("PATH", "SERIAL"):
            out[tag.lower()] = value.strip()
    if out:
        _sdl3_identity_cache[key] = (time.monotonic(), out)
    return out


def pad_has_hat(vendor: str, product: str) -> bool | None:
    """Whether the pad exposes its D-pad as an evdev hat (ABS_HAT0X) rather
    than buttons — the D-pad-only fallback. None when the pad can't be found."""
    try:
        import evdev
    except ImportError:
        return None
    for path in glob.glob("/dev/input/event*"):
        try:
            dev = evdev.InputDevice(path)
            info = dev.info
            if f"{info.vendor:04x}" == vendor and f"{info.product:04x}" == product:
                abs_codes = [a[0] if isinstance(a, tuple) else a
                             for a in dev.capabilities().get(3, [])]
                dev.close()
                return 0x10 in abs_codes
            dev.close()
        except (OSError, PermissionError):
            continue
    return None


# ── why a GUID could not be produced ──────────────────────────────────────
# Returned by `Pad.guid_for`, and named rather than spelled out at each call
# site so a generator's message and a test's assertion cannot drift apart.

# SDL answered, and this pad is not one of its joysticks. Permanent for a pad
# SDL has no driver for; this is the one the mapping wizard exists for.
GUID_NO_GUID = "no-guid"
# `flatpak info` could not locate the emulator, so its own SDL2 is out of
# reach and the host's must not be substituted (they disagree on the bus byte).
GUID_UNREACHABLE = "unreachable"
# The probe subprocess never ran to completion, so SDL was never asked.
# Transient — gamepad_monitor's PROFILE_RETRIES budget is what clears it.
GUID_PROBE_FAILED = "probe-failed"


# ── the object generators actually receive ────────────────────────────────

@dataclass
class Pad:
    """One physical controller, as a generator sees it.

    `dup_index` is how many pads with the same RESOLVED NAME occupy a LOWER
    player slot. It is the value every per-name and per-GUID counter needs, and
    it is NOT the player number: RPCS3 suffixes a 1-based counter per name
    (sdl_pad_handler.cpp), Dolphin a 0-based one (SDL/<k>/<name>), Ryujinx
    counts per GUID. A lone DualSense is "DualSense Wireless Controller 1" and
    SDL/0/... even as Player 2.

    It counts by name, not by vendor:product: every consumer counts by name,
    and SDL3_FALLBACK_NAMES alone maps three Sony product ids onto
    "PS4 Controller".
    """
    vendor: str
    product: str
    evdev_name: str = ""
    dup_index: int = 0

    @property
    def name(self) -> ResolvedName:
        """What an SDL3-based emulator will call it — and how sure we are.

        Carries `.source`; a generator whose emulator matches this string
        against its own SDL3 enumeration must check it before writing.
        """
        return resolve_name(self.vendor, self.product, self.evdev_name)

    def guid_for(self, app_id: str) -> tuple[str | None, str]:
        """`(guid, why_not)` — the dashed GUID *that emulator's own SDL2*
        computes, or None and one of the `GUID_*` reasons above.

        None when it cannot be asked — an invented id is worse than an
        untouched slot, and the caller turns None into a `Skip`.

        **Why the reason is returned rather than only logged.** All three
        failures used to arrive at the caller as a bare None, so the `Skip`
        could only name the commonest of them. On the reference box the one
        that actually fired was `GUID_PROBE_FAILED`, and the player was told
        `SDL2 would not report a GUID` — which is a statement about an answer
        SDL never gave. The three call for different things: NO_GUID is
        permanent and wants the mapping wizard, UNREACHABLE means the flatpak
        moved, PROBE_FAILED is transient and the monitor's retry is what
        clears it. A caller that cannot tell them apart cannot say any of it.

        **The silent fallback this used to have.** The code asked
        `sdl2_probe(vendor, product, bundled_sdl2(app_id))`, and `sdl2_probe`
        with an empty `lib` asks the HOST's SDL2. So whenever the flatpak
        lookup failed for any reason, the answer quietly became the host's —
        and the host disagrees with Ryujinx's own SDL2 on the bus byte
        (`0x05` against `0x03` for a Bluetooth DualShock 4, measured).
        Ryujinx resolves ids with `IndexOf`, so `-1`, so the slot is disposed
        in silence. Exactly the failure this whole path exists to prevent,
        reached by a different road: not an invented GUID, a GUID read from
        the wrong source.

        Found by running the backend with a redirected HOME, where
        `flatpak info` cannot see the user installation. That is a test
        artefact — but a busy flatpak, a timeout, or a system-vs-user install
        mismatch produce it on a real box.

        The three cases are now distinct:

          no app_id                the emulator is a native install; the
                                   host's SDL2 IS its SDL2. Ask it.
          app_id, not locatable    we cannot reach the emulator's own SDL2.
                                   Refuse rather than answer with the host's.
          app_id, located          use its bundled libSDL2.so when it ships
                                   one; when it does not, it links the
                                   runtime's and the host's is a fair proxy.
        """
        if app_id:
            if not flatpak_location(app_id):
                log.warning("configgen: cannot locate %s — refusing to answer "
                            "with the host's SDL2, which disagrees on the bus byte",
                            app_id)
                return None, GUID_UNREACHABLE
        answer = sdl2_probe(self.vendor, self.product, bundled_sdl2(app_id))
        raw = answer.get("guid", "")
        if not raw:
            return None, (GUID_PROBE_FAILED if answer.get("error")
                          else GUID_NO_GUID)
        return ryu_guid_from_sdl2(raw), ""

    def sdl2_mapping(self) -> dict[str, str] | None:
        """Live SDL2 GameController mapping (SDL name → raw token like 'b6' or
        'h0.1'). melonDS binds by raw SDL2 joystick index, and those indices
        differ per controller AND per driver version — the vendored
        gamecontrollerdb even ships conflicting Linux entries for one pad."""
        line = sdl2_probe(self.vendor, self.product).get("map", "")
        if "," not in line:
            return None
        out = {k: v for tok in line.split(",")[2:]
               if ":" in tok for k, _, v in (tok.partition(":"),)}
        return out or None

    def has_hat(self) -> bool | None:
        return pad_has_hat(self.vendor, self.product)

    @property
    def vidpid(self) -> tuple[str, str]:
        return self.vendor.lower(), self.product.lower()


def detect_pads(max_n: int = 4) -> list[tuple[str, str, str]]:
    """[(vendor, product, evdev_name), …], one per physical device (deduped by
    uniq/MAC), in the same order controller_registry.py would assign slots."""
    try:
        import evdev
    except ImportError:
        return []
    seen: set[str] = set()
    pads: list[tuple[str, str, str]] = []
    for path in sorted(glob.glob("/dev/input/event*")):
        try:
            dev = evdev.InputDevice(path)
            caps = dev.capabilities()
            if 0x130 not in caps.get(1, []):  # BTN_SOUTH
                dev.close()
                continue
            info = dev.info
            vendor, product, name = f"{info.vendor:04x}", f"{info.product:04x}", dev.name
            key = dev.uniq or path
            dev.close()
        except (PermissionError, OSError):
            continue
        if key in seen:
            continue
        seen.add(key)
        pads.append((vendor, product, name))
        if len(pads) >= max_n:
            break
    return pads
