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

import glob
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from ...config import GAMECORE_ROOT

log = logging.getLogger(__name__)

DB_FILE = GAMECORE_ROOT / "backend" / "data" / "gamecontrollerdb.txt"
SDL_INIT_GAMEPAD = 0x2000


# ── GUID <-> vendor:product ───────────────────────────────────────────────

def vidpid_of(guid: str) -> tuple[str, str]:
    """SDL packs vendor/product as little-endian 16-bit words at a fixed hex
    offset, stable across every GUID format revision seen on this box (03..
    and 05.. bus-type prefixes both use it)."""
    vendor = (guid[10:12] + guid[8:10]).lower()
    product = (guid[18:20] + guid[16:18]).lower()
    return vendor, product


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


def _sdl3_live_names() -> dict[tuple[str, str], str]:
    """vendor:product → device name for every currently-connected gamepad, as
    reported by the system's libSDL3 — the same library family RPCS3 and
    Dolphin bundle, so the name written to their configs is byte-for-byte the
    name they will enumerate at boot."""
    import ctypes

    os.environ.setdefault("SDL_NO_SIGNAL_HANDLERS", "1")
    if DB_FILE.is_file():
        os.environ.setdefault("SDL_GAMECONTROLLERCONFIG_FILE", str(DB_FILE))
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
_flatpak_loc_cache: dict[str, str] = {}


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


def bundled_sdl2(app_id: str) -> str:
    """Absolute path of the SDL2 a flatpak'd emulator ships, or "".

    Measured on the reference box, same physical DualShock 4, same instant:

        host libSDL2-2.0.so.0 (sdl2-compat over SDL3)
            05008fe54c050000cc09000000006800   bus 0x0005, Bluetooth
        Ryujinx's bundled libSDL2.so (real SDL 2.30.0)
            03008fe54c050000cc09000000006800   bus 0x0003, USB

    One byte, the bus type: SDL3 reports the transport, SDL2 2.30 reports USB
    for anything HIDAPI drives, Bluetooth included. That one byte is the
    difference between Ryujinx binding the pad and its
    `_gamepadsIds.IndexOf(id)` returning -1 and disposing the slot in silence.
    """
    if app_id in _bundled_sdl_cache:
        return _bundled_sdl_cache[app_id]
    loc = flatpak_location(app_id)
    lib = Path(loc) / "files" / "bin" / "libSDL2.so" if loc else None
    path = str(lib) if lib and lib.is_file() else ""
    _bundled_sdl_cache[app_id] = path
    return path


def sdl2_probe(vendor: str, product: str, lib: str = "") -> dict[str, str]:
    """What SDL2 itself says about a connected pad: its raw 32-hex GUID and its
    GameController mapping. `{}` when SDL2 cannot be asked.

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
                           capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.SubprocessError):
        log.warning("configgen: SDL2 probe failed for %s:%s", vendor, product)
        return {}
    out: dict[str, str] = {}
    for line in r.stdout.splitlines():
        tag, _, value = line.partition(" ")
        if tag in ("GUID", "MAP") and value:
            out[tag.lower()] = value.strip()
    if out:
        _sdl2_cache[key] = (time.monotonic(), out)
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

    def guid_for(self, app_id: str) -> str | None:
        """The dashed GUID *that emulator's own SDL2* computes.

        None when it cannot be asked — an invented id is worse than an
        untouched slot, and the caller turns None into a `Skip`.

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
                return None
        raw = sdl2_probe(self.vendor, self.product, bundled_sdl2(app_id)).get("guid", "")
        return ryu_guid_from_sdl2(raw) if raw else None

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
