"""Live per-slot controller profiling — the actual "any controller, any
emulator" system (docs/CONTROLLER_MODELS.md has the full rationale).

This is NOT a script you re-run by hand: gamepad_monitor.py calls
apply_profile() every time a pad takes a NEW player slot (including the
pads already connected when the backend starts). Whichever controller
connects first becomes Player 1 for every emulator; the second becomes
Player 2; and so on — the controller TYPE is irrelevant, it is detected
fresh (USB vendor/product ID via evdev) each time and the matching native
config is written for that slot, live. No slot is ever hardcoded to a
brand.

Per-emulator mechanics (ground-truthed by reading each emulator's live
config AND logs on this box, plus the relevant emulator sources):
  - PCSX2, DuckStation, gopher64 bind by SDL role name with NO device
    identity at all for slot 1 — already correct forever. Slots 2-4 still
    need an SDL-index section to exist (create it once, cloned from
    slot 1's role bindings) — after that, also correct forever regardless
    of which controller occupies that slot.
  - RPCS3, Dolphin bind by SDL role name too, but pick the physical pad by
    a literal device NAME string. Two hard-won facts about that string:
      * Both bundle SDL3, whose HIDAPI drivers name pads differently from
        the SDL2-era community DB — a DualSense is "DualSense Wireless
        Controller" to SDL3, not "PS5 Controller" (seen live in RPCS3.log:
        the DB name produced "SDL: Adding empty device" and a dead pad).
        So the name is resolved against the system's libSDL3 with the
        pads actually connected, not against gamecontrollerdb.txt.
      * The numeric part is NOT the player slot: RPCS3 suffixes a 1-based
        counter PER NAME ("DualSense Wireless Controller 1" even as
        Player 2 — sdl_pad_handler.cpp counts same-named devices), and
        Dolphin's SDL/<k>/<name> uses a 0-based PER-NAME <k> (ciface
        DeviceContainer). Hence `dup_index` below.
  - Ryujinx binds by a device GUID, and it must be the exact one its own
    SDL2 computes: bus type, version and driver signature are all in there,
    so the same pad has different GUIDs over USB and over Bluetooth. It is
    read from SDL2 and converted, never derived from a vendor:product
    (ryu_guid_from_sdl2 — Ryujinx renders SDL2's 16 raw bytes through .NET's
    System.Guid, which is a pure byte reordering). Every button assignment
    the owner validated stays where it is; only the device changes.
    The accompanying index is, again, NOT the player slot: the `id` prefix
    (`<dup>-<GUID>` in Config.json) counts pads sharing the same GUID — a lone
    DualSense is dup 0 even as Player 2, and a wrong dup binds a device that
    is not there. Ryujinx slots live as objects in the `input_config` list
    keyed by `player_index` (`Player1`..).
  - azahar (3DS), mgba (GBA), Cemu (Wii U): snapshot restore, NOT GUID
    substitution. Their bindings cannot be synthesised from a VID:PID — the
    owner maps the pad once per emulator with "Scan mapping", that config is
    saved (snapshot_save), and it is put back when the same model reconnects
    (snapshot_restore). All three are single-player here, so only slot 1 is
    ever touched whatever player index is passed in. GUID-rewriting versions
    of the mgba and Cemu profilers used to exist in this file and were never
    called by apply_profile; they have been removed.
  - melonDS (DS): single-player, slot 1 only. Face buttons are consistent
    across pads; only the D-pad differs (hat vs buttons), so just that is
    adapted to the connected controller (see _melonds / _pad_has_hat).
  - ppsspp: skipped — no existing binding on this box to clone
    from (never launched/configured yet).

`dup_index` = how many already-connected pads of the same vendor:product
occupy a LOWER player slot. It is the value all four per-name/per-GUID
counters above need (same-model pads are the only ones that can collide
in either scheme). Callers that know the full roster pass it; it defaults
to 0, which is always right for the first pad of a given model.
"""
from __future__ import annotations

import glob
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from ..config import GAMECORE_ROOT, SYSTEMS_FILE

log = logging.getLogger(__name__)

DB_FILE = GAMECORE_ROOT / "backend" / "data" / "gamecontrollerdb.txt"
GUID_RE = re.compile(r"\b([0-9a-fA-F]{32})\b")

HOME = Path.home()
RYUJINX_CFG = HOME / ".var/app/io.github.ryubing.Ryujinx/config/Ryujinx/Config.json"
AZAHAR = HOME / ".var/app/org.azahar_emu.Azahar/config/azahar-emu/qt-config.ini"
DOLPHIN_DIR = HOME / ".var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu"
CEMU_PROFILES = HOME / ".var/app/info.cemu.Cemu/config/Cemu/controllerProfiles"
DUCK_INI = HOME / ".local/share/duckstation/settings.ini"


def _sys_path(emu_id: str) -> str:
    """The `path` an emulator declares in systems.json ('' when unreadable) —
    tells flatpak installs apart from native ones."""
    try:
        systems = json.loads(SYSTEMS_FILE.read_text())
        return next((s.get("path", "") for s in systems if s.get("id") == emu_id), "")
    except (OSError, ValueError):
        return ""


def _flatpak_or_native(emu_id: str, flatpak: Path, native: Path) -> Path:
    """The config file of the install the box actually runs. systems.json
    decides — a native tree kept as a post-migration backup must not shadow
    the live flatpak. Unknown → whichever exists (native first, the
    pre-flatpak layout)."""
    declared = _sys_path(emu_id)
    if declared == "flatpak":
        return flatpak
    if declared:
        return native
    return native if native.is_file() else flatpak


def rpcs3_default() -> Path:
    return _flatpak_or_native(
        "rpcs3",
        HOME / ".var/app/net.rpcs3.RPCS3/config/rpcs3/input_configs/global/Default.yml",
        HOME / ".config/rpcs3/input_configs/global/Default.yml")


def pcsx2_ini() -> Path:
    return _flatpak_or_native(
        "pcsx2",
        HOME / ".var/app/net.pcsx2.PCSX2/config/PCSX2/inis/PCSX2.ini",
        HOME / ".config/PCSX2/inis/PCSX2.ini")


def mgba_config() -> Path:
    # install/arch.sh installs io.mgba.mGBA and flatpakify-systems.sh rewrites
    # mgba to flatpak, so a hardcoded ~/.config path silently profiled nothing
    # on a standard install. It is right on THIS box, which runs Arch's native
    # mgba-qt — an accident that hid the bug.
    return _flatpak_or_native(
        "mgba",
        HOME / ".var/app/io.mgba.mGBA/config/mgba/config.ini",
        HOME / ".config/mgba/config.ini")


def melonds_toml() -> Path:
    return _flatpak_or_native(
        "melonds",
        HOME / ".var/app/net.kuribo64.melonDS/config/melonDS/melonDS.toml",
        HOME / ".config/melonDS/melonDS.toml")


# ── VID/PID <-> GUID helpers ──────────────────────────────────────────────────

def vidpid_of(guid: str) -> tuple[str, str]:
    """SDL packs vendor/product as little-endian 16-bit words at a fixed hex
    offset, stable across every GUID format revision seen on this box (03..
    and 05.. bus-type prefixes both use it) — the same trick every web/
    native SDL_GameControllerDB consumer uses."""
    vendor = (guid[10:12] + guid[8:10]).lower()
    product = (guid[18:20] + guid[16:18]).lower()
    return vendor, product


def swap_vidpid(guid: str, vendor: str, product: str) -> str:
    """Same GUID, new vendor/product bytes — every other byte (bus type,
    driver signature, version) is preserved untouched."""
    v_le = vendor[2:4] + vendor[0:2]
    p_le = product[2:4] + product[0:2]
    return guid[:8] + v_le + guid[12:16] + p_le + guid[20:]


def db_name_for(vendor: str, product: str) -> str | None:
    """Canonical SDL product name for a vendor:product, read from the
    vendored gamecontrollerdb.txt — any platform entry works, the friendly
    name is the same string across platform variants."""
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

SDL_INIT_GAMEPAD = 0x2000

_sdl3_cache: tuple[float, dict[tuple[str, str], str]] = (0.0, {})


def _sdl3_live_names() -> dict[tuple[str, str], str]:
    """vendor:product → device name for every currently-connected gamepad,
    as reported by the system's libSDL3 — the same library family RPCS3 and
    Dolphin bundle, so the name written to their configs is byte-for-byte
    the name they will enumerate at boot."""
    import ctypes

    os.environ.setdefault("SDL_NO_SIGNAL_HANDLERS", "1")
    if DB_FILE.is_file():
        # Mirror the emulators' launch env (process_manager.py) so pads that
        # only exist as community-DB mappings enumerate here too.
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


def sdl3_names() -> dict[tuple[str, str], str]:
    """_sdl3_live_names() behind a short cache — two pads taking slots in
    the same scan pass shouldn't init SDL twice — degrading to {} instead
    of raising when libSDL3 is unavailable."""
    global _sdl3_cache
    ts, cached = _sdl3_cache
    if time.monotonic() - ts > 5.0 or not cached:
        try:
            cached = _sdl3_live_names()
        except Exception:
            log.warning("controller_profiles: SDL3 enumeration failed — "
                        "falling back to static names", exc_info=True)
            cached = {}
        _sdl3_cache = (time.monotonic(), cached)
    return cached


def resolve_name(vendor: str, product: str, evdev_name: str) -> str:
    """The device-name string SDL3-based emulators (RPCS3, Dolphin) will
    see for this pad. Live SDL3 answer first, known-pads table next, the
    SDL2 community-DB name only as a last resort (it is WRONG for SDL3 on
    some pads — 'PS5 Controller' vs 'DualSense Wireless Controller')."""
    return (sdl3_names().get((vendor, product))
            or SDL3_FALLBACK_NAMES.get((vendor, product))
            or db_name_for(vendor, product)
            or evdev_name)


class Skip(str):
    """Why a step wrote nothing — a real answer, not an absence of one.

    Every writer used to return `str | None`, and apply_profile only collected
    the truthy ones. So "I retargeted Player 2" reached the log and "there is
    no Player 1 pad to clone from" reached nobody: a give-up was byte-for-byte
    indistinguishable from a success. RPCS3's players 2-4 sat dead for a week
    that way, and `scan_mapping()` answered `{"ok": True}` on a snapshot it had
    taken of the wrong controller.

    A Skip is a str, so it logs and joins like any other message; it is a
    distinct type, so apply_profile can file it apart and log it as a warning.
    `None` keeps its old meaning and only it: nothing to do, nothing to say.
    """
    __slots__ = ()


def backup(p: Path) -> None:
    b = p.with_name(p.name + ".bak-ctrlmodel")
    if p.is_file() and not b.exists():
        shutil.copy2(p, b)


def _atomic_write(p: Path, text: str) -> None:
    """Write through a temp file in the same directory, then os.replace().

    `write_text()` truncates first and writes second. This pipeline runs at
    backend startup — the exact moment someone powers the box on, and the exact
    moment they can cut the power again with the wall switch. A Config.json
    caught between the two is invalid JSON, and Ryujinx starts over from
    defaults. os.replace() is atomic within a filesystem, so a reader sees
    either the whole old file or the whole new one.
    """
    tmp = p.with_name(p.name + ".gamecore-tmp")
    try:
        tmp.write_text(text)
        os.replace(tmp, p)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def section(text: str, header: str) -> str | None:
    m = re.search(rf"^\[{re.escape(header)}\]\n(.*?)(?=^\[|\Z)", text, re.S | re.M)
    return m.group(1) if m else None


def set_section(text: str, header: str, body: str) -> str:
    pat = rf"^\[{re.escape(header)}\]\n.*?(?=^\[|\Z)"
    if re.search(pat, text, re.S | re.M):
        return re.sub(pat, f"[{header}]\n{body}", text, count=1, flags=re.S | re.M)
    return text.rstrip() + f"\n\n[{header}]\n{body}"


# ── Ryujinx (Switch, up to 8 in principle — we honor players 1-4) ───────────

def ryu_guid_vidpid(dashed_guid: str) -> tuple[str, str] | None:
    """(vendor, product) from a Ryujinx dashed SDL GUID — the vendor sits at
    [8:12] big-endian and the product at [16:20] little-endian
    (`00000003-054c-0000-cc09-…` → 054c / 09cc).

    Kept for reading a Config.json, never for deciding what to write: two pads
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
    alone. So the whole thing is a byte reordering, not a lossy summary — which
    means the exact GUID Ryujinx will compute can be derived from the exact
    GUID SDL2 reports, with nothing guessed:

        030000004c050000cc09000000006800 -> 00000003-054c-0000-cc09-000000006800
        050000005e040000fd02000003090000 -> 00000005-045e-0000-fd02-000003090000

    Both of those are byte-for-byte what this box's Config.json holds for its
    DualShock 4 and its Xbox One pad.
    """
    try:
        b = bytes.fromhex(sdl_hex)
    except ValueError:
        return None
    if len(b) != 16:
        return None
    return "-".join((b[0:4][::-1].hex(), b[4:6][::-1].hex(), b[6:8][::-1].hex(),
                     b[8:10].hex(), b[10:16].hex()))


def _ryujinx(i: int, dup: int, vendor: str, product: str, name: str) -> str | None:
    """Ryujinx binds each slot in Config.json's `input_config` list by
    `player_index` (`Player1`..`Player8`) and an `id` `"<dup>-<SDL GUID>"`,
    where <dup> counts pads sharing that GUID (SDL2GamepadDriver.
    GenerateGamepadId walks `guidIndex` up while the id is taken) — NOT the
    player number.

    NpadManager.DriverConfigurationUpdate resolves that id with
    `_gamepadsIds.IndexOf(id)`. No match means -1, means the slot is disposed,
    silently — no log, no "already assigned" mark in Input Settings, nothing.

    So the GUID has to be exactly right, and it used to be neither read nor
    computed. It was copied from another entry that merely shared a
    vendor:product — which breaks the moment a pad changes transport, because
    the bus and driver bytes change and only vendor/product were compared — or
    else fabricated by substituting vendor/product into a reference GUID, which
    produced strings no device has ever had (a DualShock 4 GUID with Xbox
    vendor bytes keeps the DS4's bus 0x0003 and HIDAPI signature; the real Xbox
    pad is bus 0x0005 with a different tail). Worse, the fabricated GUID parsed
    back to the right vendor:product, so the next pass adopted it as "a GUID
    Ryujinx wrote" and logged a match. Once wrong, always wrong.

    Nothing needs guessing: ask SDL2 for the pad's actual GUID and convert
    (ryu_guid_from_sdl2). If SDL2 cannot be reached, say so and change nothing
    — an invented id is worse than an untouched slot.
    """
    if not RYUJINX_CFG.is_file():
        return None
    try:
        cfg = json.loads(RYUJINX_CFG.read_text())
    except (OSError, ValueError) as e:
        return Skip(f"ryujinx: Config.json unreadable ({e.__class__.__name__})")
    ic = cfg.get("input_config")
    if not isinstance(ic, list):
        return Skip("ryujinx: Config.json has no input_config list")

    sdl_hex = _sdl2_probe(vendor, product).get("guid", "")
    new_guid = ryu_guid_from_sdl2(sdl_hex) if sdl_hex else None
    if not new_guid:
        return Skip(f"ryujinx: SDL2 would not report a GUID for {vendor}:{product} "
                    f"— Player {i} left as it was")

    # A pad template to clone from, for a slot that does not exist yet or that
    # currently belongs to the keyboard. Any gamepad slot will do; the button
    # map is role-based, so it carries over between controller types.
    model = next((e for e in ic if e.get("backend") == "GamepadSDL2"), None)
    pi = f"Player{i}"
    slot = next((e for e in ic if e.get("player_index") == pi), None)
    new_id = f"{dup}-{new_guid}"

    if slot is not None and slot.get("backend") == "GamepadSDL2":
        if slot.get("id") == new_id and slot.get("name") == f"{name} ({dup})":
            return None                     # already correct — do not rewrite 11 KB
        slot["id"], slot["name"] = new_id, f"{name} ({dup})"
        action = "retargeted"
    else:
        # An existing non-gamepad slot used to have its id mutated in place,
        # which left a keyboard config claiming to be an SDL device: the pad
        # did not work and neither did the keyboard.
        if model is None:
            return Skip(f"ryujinx: no gamepad slot to clone from — Player {i} left as it was")
        clone = json.loads(json.dumps(model))
        clone["player_index"] = pi
        clone["id"], clone["name"] = new_id, f"{name} ({dup})"
        if slot is not None:
            ic[ic.index(slot)] = clone
            action = "replaced (was a keyboard slot)"
        else:
            ic.append(clone)
            action = "created"
    backup(RYUJINX_CFG)
    _atomic_write(RYUJINX_CFG, json.dumps(cfg, indent=2) + "\n")
    return f"ryujinx: Player {i} {action} (dup {dup}, {new_guid})"


# ── azahar (3DS) / mgba (GBA) — single-player hardware, slot 1 only ─────────

def _single_player_guid(path: Path, label: str, line_prefix: str,
                        i: int, vendor: str, product: str, name: str) -> str | None:
    if i != 1 or not path.is_file():
        return None
    t = path.read_text()
    old_guid = None
    for line in t.splitlines():
        if line.startswith(line_prefix):
            m = GUID_RE.search(line)
            if m:
                old_guid = m.group(1)
                break
    if not old_guid:
        return None
    new_guid = swap_vidpid(old_guid, vendor, product)
    out, n = [], 0
    for line in t.splitlines(keepends=True):
        if line.startswith(line_prefix) and old_guid in line:
            out.append(line.replace(old_guid, new_guid))
            n += 1
        else:
            out.append(line)
    if not n:
        return None
    backup(path); _atomic_write(path, "".join(out))
    return f"{label}: Player 1 retargeted ({n} keys)"


# ── capture / restore per-controller configs (GUID-based single-player emus) ──
# 3DS/azahar (and GBA/Wii U) bind by a device GUID + raw button indices we can't
# synthesize reliably — swapping vidpid bytes produces GUIDs no real pad has and
# pollutes the config. Instead we DON'T synthesize: the user auto-maps the pad
# once in the emulator (which writes a correct config), we remember that config
# PER controller, and swap it back in whenever that pad reconnects.
SNAP_DIR = HOME / ".local/share/gamecore/controller-snapshots"


def _sdl_guid_vidpid(guid: str) -> tuple[str, str] | None:
    """(vendor, product) from a 32-hex SDL GUID (vendor LE @[8:12], product
    LE @[16:20])."""
    if len(guid) != 32:
        return None
    return (guid[10:12] + guid[8:10]).lower(), (guid[18:20] + guid[16:18]).lower()


# Per-emulator adapters: extract the input-config block from the config text,
# and replace it back. The "Scan mapping" button captures the block for the
# connected controller (keyed by vidpid); connect-time restore swaps it in.
def _sect_bounds(lines: list[str], header: str):
    start = None
    for i, l in enumerate(lines):
        if l.strip() == f"[{header}]":
            start = i
        elif start is not None and l.strip().startswith("["):
            return start, i
    return (start, len(lines)) if start is not None else (None, None)


def _az_prefix(text: str) -> str:
    """The `profiles\\N\\` prefix azahar is actually using.

    Qt writes array entries 1-based (`profiles\\1\\…`) but stores the selected
    index 0-based in `profile=`. `profiles\\1\\` was hardcoded, which is right
    only while `profile=0` — true today, false the moment a second input
    profile is created and picked, at which point a snapshot restore would
    rewrite the profile the owner is not using.
    """
    m = re.search(r"^profile=(\d+)$", text, re.M)
    return f"profiles\\{int(m.group(1)) + 1 if m else 1}\\"


def _az_extract(text: str) -> str:
    prefix = _az_prefix(text)
    return "".join(l for l in text.splitlines(keepends=True) if l.startswith(prefix))


def _az_replace(text: str, block: str) -> str:
    prefix = _az_prefix(text)
    if not block.endswith("\n"):
        block += "\n"
    # A snapshot taken under a different active profile carries that profile's
    # prefix; re-key it onto the one in use rather than writing a dead index.
    block = re.sub(r"^profiles\\\d+\\", lambda _: prefix, block, flags=re.M)
    out, done = [], False
    for l in text.splitlines(keepends=True):
        if l.startswith(prefix):
            if not done:
                out.append(block); done = True
        else:
            out.append(l)
    if not done:
        out.append(block)
    return "".join(out)


def _sect_extract(header):
    def f(text: str) -> str:
        lines = text.splitlines(keepends=True)
        s, e = _sect_bounds(lines, header)
        return "".join(lines[s:e]) if s is not None else ""
    return f


def _sect_replace(header):
    def f(text: str, block: str) -> str:
        lines = text.splitlines(keepends=True)
        s, e = _sect_bounds(lines, header)
        if not block.endswith("\n"):
            block += "\n"
        if s is None:
            return text + ("" if text.endswith("\n") else "\n") + block
        return "".join(lines[:s]) + block + "".join(lines[e:])
    return f


# Cemu: one XML file per player slot; controller0.xml is Player 1's whole config.
def _whole_extract(text: str) -> str:
    return text


def _whole_replace(_text: str, block: str) -> str:
    return block


def _ini_sections(block: str) -> list[tuple[str, str]]:
    """[(header, whole section including its [header] line)] for a block of
    complete INI sections — the shape snapshots of multi-section formats take."""
    out: list[tuple[str, str]] = []
    header, body = None, []
    for line in block.splitlines(keepends=True):
        if line.strip().startswith("[") and line.strip().endswith("]"):
            if header is not None:
                out.append((header, "".join(body)))
            header, body = line.strip()[1:-1], [line]
        elif header is not None:
            body.append(line)
    if header is not None:
        out.append((header, "".join(body)))
    return out


# mgba keeps the ACTIVE binding table in [gba.input.SDLB] — every keyA/keyL/hat0
# lives there, along with `device0=`, the GUID of the pad it belongs to. The
# per-GUID [gba.input-profile.<GUID>] sections hold tilt and gyro axes and
# nothing else.
#
# The snapshot used to capture `device0=` plus that GUID section, i.e. six gyro
# keys and not one button: 180 bytes on this box, for both saved controllers.
# "Scan mapping" reported success, restore announced "restored saved mapping",
# and no button ever moved. Capture the section that actually binds buttons,
# and keep the gyro section alongside it.
def _mgba_extract(text: str) -> str:
    lines = text.splitlines(keepends=True)
    s, e = _sect_bounds(lines, "gba.input.SDLB")
    if s is None:
        return ""
    block = "".join(lines[s:e])
    guid = next((l.split("=", 1)[1].strip() for l in lines[s:e]
                 if l.startswith("device0=")), "")
    if guid:
        gs, ge = _sect_bounds(lines, f"gba.input-profile.{guid}")
        if gs is not None:
            block += "".join(lines[gs:ge])
    return block


def _mgba_replace(text: str, block: str) -> str:
    for header, body in _ini_sections(block):
        text = _sect_replace(header)(text, body)
    return text


# emu_id → (config-path getter, extract(text)→block, replace(text, block)→text)
_SNAP_EMUS = {
    "azahar":  (lambda: AZAHAR, _az_extract, _az_replace),
    "melonds": (melonds_toml, _sect_extract("Instance0.Joystick"),
                _sect_replace("Instance0.Joystick")),
    "mgba":    (mgba_config, _mgba_extract, _mgba_replace),
    "cemu":    (lambda: CEMU_PROFILES / "controller0.xml", _whole_extract, _whole_replace),
}


def _snap_path(emu_id: str, vendor: str, product: str) -> Path:
    return SNAP_DIR / emu_id / f"{vendor.lower()}_{product.lower()}.snap"


def snapshot_exists(emu_id: str, vendor: str, product: str) -> bool:
    return _snap_path(emu_id, vendor, product).is_file()


# A 32-hex SDL GUID wherever it appears — after `guid:` in azahar, after `0_`
# in Cemu's <uuid>, bare after `device0=` in mgba. GUID_RE's \b does not fire
# after an underscore, which is a word character.
_ANY_GUID_RE = re.compile(r"(?<![0-9a-fA-F])([0-9a-fA-F]{32})(?![0-9a-fA-F])")


def _block_disagrees(block: str, vendor: str, product: str) -> str | None:
    """The first GUID in `block` that belongs to another controller, if any.

    Cemu's controller0.xml carries the pad's <uuid> and azahar's profile carries
    a `guid:` per binding, so a captured block states which controller it is
    for. Nothing checked that against the pad the user said they had just
    mapped, and the box ends up with cemu/045e_02fd.snap byte-identical to
    cemu/054c_09cc.snap — both the DualShock 4's config, because "Scan mapping"
    was pressed with the Xbox pad connected while the file still held the DS4.
    Restoring it is a no-op today, but the moment the owner maps the Xbox by
    hand, the next connection overwrites their work with the DS4's config.
    """
    want = (vendor.lower(), product.lower())
    for guid in _ANY_GUID_RE.findall(block):
        if vidpid_of(guid) != want:
            return guid
    return None


def snapshot_capture(vendor: str, product: str) -> tuple[list[str], list[str]]:
    """Save each GUID-emulator's CURRENT input config for this controller — the
    'Scan mapping' action, after the user has auto-mapped the pad in-emulator.

    Returns (saved, refused): an emulator whose config plainly describes a
    different controller is refused rather than saved under this one's name."""
    saved: list[str] = []
    refused: list[str] = []
    for emu_id, (pathfn, extract, _r) in _SNAP_EMUS.items():
        path = pathfn()
        if not path.is_file():
            continue
        block = extract(path.read_text())
        if not block.strip():
            continue
        wrong = _block_disagrees(block, vendor, product)
        if wrong:
            log.warning("controller_profiles: %s config describes %s, not %s:%s "
                        "— refusing to save it as this pad's mapping",
                        emu_id, wrong, vendor, product)
            refused.append(emu_id)
            continue
        snap = _snap_path(emu_id, vendor, product)
        snap.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(snap, block)
        saved.append(emu_id)
    return saved, refused


def snapshot_restore(emu_id: str, vendor: str, product: str) -> str | None:
    """Swap this controller's saved input config into one emulator (on connect).
    None when there's no snapshot yet (caller can fall back to a live handler)."""
    entry = _SNAP_EMUS.get(emu_id)
    if not entry:
        return None
    pathfn, extract, replace = entry
    path, snap = pathfn(), _snap_path(emu_id, vendor, product)
    if not path.is_file() or not snap.is_file():
        return None
    block, text = snap.read_text(), path.read_text()
    if extract(text).strip() == block.strip():
        return None                                   # already applied
    backup(path); _atomic_write(path, replace(text, block))
    return f"{emu_id}: restored saved mapping ({vendor}:{product})"


def _pad_has_hat(vendor: str, product: str) -> bool | None:
    """Whether the connected pad exposes its D-pad as an evdev hat (ABS_HAT0X,
    code 0x10) rather than buttons — the D-pad-only fallback when the fuller
    SDL mapping is unavailable. None when the pad can't be found."""
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
                             for a in dev.capabilities().get(3, [])]  # EV_ABS
                dev.close()
                return 0x10 in abs_codes                             # ABS_HAT0X
            dev.close()
        except (OSError, PermissionError):
            continue
    return None


_SDL2_PROBE = (
    "import ctypes,os,sys\n"
    "os.environ['SDL_VIDEODRIVER']='dummy'\n"
    "v=int(sys.argv[1],16);p=int(sys.argv[2],16)\n"
    "try: s=ctypes.CDLL('libSDL2-2.0.so.0')\n"
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

_sdl2_cache: dict[tuple[str, str], tuple[float, dict[str, str]]] = {}


def _sdl2_probe(vendor: str, product: str) -> dict[str, str]:
    """What SDL2 itself says about a connected pad: its raw 32-hex GUID and its
    GameController mapping string. `{}` when SDL2 cannot be asked.

    Run in a SUBPROCESS because the backend has already loaded SDL3 into its
    own address space, and because these two answers must come from the same
    SDL2 the emulators use — melonDS binds raw joystick indices that differ per
    driver version, and Ryujinx's GUID carries bus and driver bytes that exist
    nowhere else. Cached briefly: two pads taking slots in the same scan pass
    would otherwise each pay the subprocess, and its timeout is 8 seconds.
    """
    key = (vendor.lower(), product.lower())
    ts, cached = _sdl2_cache.get(key, (0.0, {}))
    if cached and time.monotonic() - ts <= 5.0:
        return cached
    try:
        r = subprocess.run([sys.executable, "-c", _SDL2_PROBE, vendor, product],
                           capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.SubprocessError):
        log.warning("controller_profiles: SDL2 probe failed for %s:%s", vendor, product)
        return {}
    out: dict[str, str] = {}
    for line in r.stdout.splitlines():
        tag, _, value = line.partition(" ")
        if tag in ("GUID", "MAP") and value:
            out[tag.lower()] = value.strip()
    if out:
        _sdl2_cache[key] = (time.monotonic(), out)
    return out


def _sdl2_live_mapping(vendor: str, product: str) -> dict[str, str] | None:
    """Live SDL2 GameController mapping (SDL name → raw token like 'b6'/'h0.1')
    for the connected vendor:product. melonDS binds by raw SDL2 joystick index,
    and those indices differ per controller AND per driver version — the
    vendored gamecontrollerdb even ships conflicting Linux entries for one pad
    (an Xbox is b4/b5 or b6/b7). The only reliable source is the exact SDL2 the
    emulator uses. None on any failure."""
    line = _sdl2_probe(vendor, product).get("map", "")
    if "," not in line:
        return None
    out = {k: v for tok in line.split(",")[2:]
           if ":" in tok for k, _, v in (tok.partition(":"),)}
    return out or None


# melonDS [Instance0.Joystick] key → SDL GameController button name.
_MELONDS_SHOULDER_KEYS = {
    "L": "leftshoulder", "R": "rightshoulder", "Start": "start", "Select": "back",
}
_MELONDS_DPAD_KEYS = {
    "Up": "dpup", "Down": "dpdown", "Left": "dpleft", "Right": "dpright",
}
# Controllers whose D-pad melonDS's own SDL reads as BUTTONS, not the hat that
# SDL's GameController mapping reports (verified by what melonDS records when
# you bind the D-pad in-app). SDL says h0 for both a DS4 and an Xbox, but
# melonDS latches buttons 11-14 on a DualShock 4 and the hat on an Xbox — so
# the hat token can't be trusted here; list the button exceptions instead.
_MELONDS_DPAD_BUTTONS = {
    ("054c", "09cc"): {"Up": 11, "Down": 12, "Left": 13, "Right": 14},  # DualShock 4
}


def _melon_encode(token: str) -> int | None:
    """SDL raw token → melonDS joystick value. Buttons ('bN' → N) and hats
    ('hM.D' → 0x100 | M<<4 | SDL_HAT_dir). Axis tokens (triggers) return None —
    leave that key's existing binding rather than guess an axis encoding."""
    if re.fullmatch(r"b\d+", token):
        return int(token[1:])
    m = re.fullmatch(r"h(\d+)\.(\d+)", token)
    if m:
        return 0x100 | (int(m.group(1)) << 4) | int(m.group(2))
    return None


def _melonds(i: int, vendor: str, product: str, name: str) -> str | None:
    """melonDS (DS) is single-player — only slot 1. It binds raw SDL2 joystick
    inputs, whose indices differ per controller (a DS4's shoulders are b9/b10,
    an Xbox's b6/b7; its D-pad is a hat, a DS4's is buttons 11-14). Re-derive
    the shoulders / start / select / D-pad from the connected pad's live SDL2
    mapping so they land on the right physical inputs for any controller. Face
    buttons (A/B/X/Y = b0-b3) are consistent and left untouched."""
    toml = melonds_toml()
    if i != 1 or not toml.is_file():
        return None
    mapping = _sdl2_live_mapping(vendor, product)
    vals: dict[str, int] = {}
    if mapping:
        for key, sdl in _MELONDS_SHOULDER_KEYS.items():
            enc = _melon_encode(mapping.get(sdl, ""))
            if enc is not None:
                vals[key] = enc
    # D-pad: a known button-exception controller wins; otherwise trust the SDL
    # hat token (works for hat pads like the Xbox).
    override = _MELONDS_DPAD_BUTTONS.get((vendor.lower(), product.lower()))
    if override:
        vals.update(override)
    elif mapping:
        for key, sdl in _MELONDS_DPAD_KEYS.items():
            enc = _melon_encode(mapping.get(sdl, ""))
            if enc is not None:
                vals[key] = enc
    src = "SDL live"
    if not vals:                       # fallback: at least the D-pad, via evdev
        hat = _pad_has_hat(vendor, product)
        if hat is None:
            return None
        vals = ({"Up": 257, "Right": 258, "Down": 260, "Left": 264} if hat
                else {"Up": 11, "Down": 12, "Left": 13, "Right": 14})
        src = "hat fallback"
    out, insec, n = [], False, 0
    for line in toml.read_text().splitlines():
        s = line.strip()
        if s.startswith("["):
            insec = (s == "[Instance0.Joystick]")
        m = re.match(r"^(L|R|Start|Select|Up|Down|Left|Right)\s*=\s*-?\d+\s*$", s)
        if insec and m and m.group(1) in vals:
            out.append(f"{m.group(1)} = {vals[m.group(1)]}"); n += 1
        else:
            out.append(line)
    if not n:
        return None
    backup(toml)
    _atomic_write(toml, "\n".join(out) + "\n")
    return f"melonds: {n} keys mapped ({src})"


# ── mgba / Cemu / azahar: GUID substitution is NOT how these work ───────────
#
# _mgba() and _cemu() used to live here and rewrote the device GUID in place.
# Neither was ever called: apply_profile() restores a snapshot the owner
# captured with "Scan mapping" instead (snapshot_restore), because these
# emulators bind to a GUID that cannot be synthesised from a VID:PID alone.
# They were removed rather than kept as reference — dead code that looks like
# the mechanism is worse than no code, and docs/CONTROLLER_MODELS.md described
# the box on the strength of them. The snapshot model is documented in this
# module's docstring.


# ── Dolphin (GameCube/Wii, GCPad1-4) — roles semantic, index+name only ──────

# Canonical "gamepad plays Wii" mapping: Wiimote + Nunchuk on a dual-analog
# pad, using the same device-agnostic SDL role tokens Dolphin writes for GCPad
# (validated against the pad's own GCPadNew). It fits ANY controller — only the
# Device line is retargeted per pad. Left stick = Nunchuk movement, right stick
# = IR pointer (the box has no mouse, so mouse-cursor IR is useless here).
# `Source = 1` marks the slot Emulated: that's the Dolphin default for Wiimote1
# only — players 2-4 default to None and would stay dead without it.
_WIIMOTE_BODY = (
    "Source = 1\n"
    "Device = {device}\n"
    "Buttons/A = `Button S`\n"
    "Buttons/B = `Trigger R`\n"
    "Buttons/1 = `Button W`\n"
    "Buttons/2 = `Button N`\n"
    "Buttons/- = `Back`\n"
    "Buttons/+ = `Start`\n"
    "Buttons/Home = `Thumb R`\n"
    "D-Pad/Up = `Pad N`\n"
    "D-Pad/Down = `Pad S`\n"
    "D-Pad/Left = `Pad W`\n"
    "D-Pad/Right = `Pad E`\n"
    "IR/Up = `Right Y+`\n"
    "IR/Down = `Right Y-`\n"
    "IR/Left = `Right X-`\n"
    "IR/Right = `Right X+`\n"
    # Tilt (roll/pitch the remote) on the SAME right stick as IR: 2D games use
    # tilt (NSMB Wii "Tilt Lift" seesaws) but not the pointer, 3D pointer games
    # use IR but ignore tilt — so one stick serves both with no real conflict.
    "Tilt/Forward = `Right Y+`\n"
    "Tilt/Backward = `Right Y-`\n"
    "Tilt/Left = `Right X-`\n"
    "Tilt/Right = `Right X+`\n"
    "Shake/X = `Button E`\n"
    "Shake/Y = `Button E`\n"
    "Shake/Z = `Button E`\n"
    "Extension = Nunchuk\n"
    "Nunchuk/Buttons/C = `Shoulder L`\n"
    "Nunchuk/Buttons/Z = `Trigger L`\n"
    "Nunchuk/Stick/Up = `Left Y+`\n"
    "Nunchuk/Stick/Down = `Left Y-`\n"
    "Nunchuk/Stick/Left = `Left X-`\n"
    "Nunchuk/Stick/Right = `Left X+`\n"
    "Nunchuk/Stick/Calibration = 100.00 141.42 100.00 141.42 100.00 141.42 100.00 141.42\n"
    "Nunchuk/Shake/X = `Shoulder R`\n"
    "Nunchuk/Shake/Y = `Shoulder R`\n"
    "Nunchuk/Shake/Z = `Shoulder R`\n"
)


# Canonical "any gamepad plays GameCube" bindings — every value is a
# device-agnostic SDL role token, so the same body fits a DualShock, an Xbox
# pad or a generic USB stick; only the Device line is per-pad.
#
# No Calibration line: a calibration is a measurement of one physical stick,
# and Dolphin falls back to a perfect circle without it, which is right for a
# pad nobody has measured. No Modifier line either: `Main Stick/Modifier =
# `Shift`` came from the machine these configs were captured on, and it lets a
# plugged-in keyboard shrink a player's stick range.
_GCPAD_BODY = (
    "Device = {device}\n"
    "Buttons/A = `Button S`\n"
    "Buttons/B = `Button E`\n"
    "Buttons/X = `Button W`\n"
    "Buttons/Y = `Button N`\n"
    "Buttons/Z = Back\n"
    "Buttons/Start = Start\n"
    "D-Pad/Up = `Pad N`\n"
    "D-Pad/Down = `Pad S`\n"
    "D-Pad/Left = `Pad W`\n"
    "D-Pad/Right = `Pad E`\n"
    "Main Stick/Up = `Left Y+`\n"
    "Main Stick/Down = `Left Y-`\n"
    "Main Stick/Left = `Left X-`\n"
    "Main Stick/Right = `Left X+`\n"
    "C-Stick/Up = `Right Y+`\n"
    "C-Stick/Down = `Right Y-`\n"
    "C-Stick/Left = `Right X-`\n"
    "C-Stick/Right = `Right X+`\n"
    "Triggers/L = `Shoulder L`\n"
    "Triggers/R = `Shoulder R`\n"
    "Triggers/L-Analog = `Trigger L`\n"
    "Triggers/R-Analog = `Trigger R`\n"
)

# The SDL role tokens Dolphin writes for a gamepad. A value outside this set is
# a keyboard key, a mouse axis, or something else that will not follow the pad.
_GC_SDL_TOKEN = re.compile(
    r"`?(?:Button [NESW]|Pad [NESW]|Shoulder [LR]|Trigger [LR]|Thumb [LR]|"
    r"(?:Left|Right) [XY][+-]|Back|Start|Guide)`?$")

# The keys that name a physical input. Everything else in a GCPad section is a
# number or a tuning knob (Calibration, Dead Zone, Range, Modifier) and says
# nothing about which device the section follows.
#
# Presence is not required: Dolphin omits a binding the owner never made, and
# an unbound C-Stick is a choice, not a leftover. What is required is that
# every action key that IS there names an SDL role.
_GC_ACTION_KEY = re.compile(
    r"(?:Buttons/(?:A|B|X|Y|Z|Start)|D-Pad/(?:Up|Down|Left|Right)|"
    r"(?:Main Stick|C-Stick)/(?:Up|Down|Left|Right)|"
    r"Triggers/(?:L|R|L-Analog|R-Analog))$")


def _gc_values(body: str) -> dict[str, str]:
    return {k.strip(): v.strip()
            for line in body.splitlines() if "=" in line
            for k, _, v in (line.partition("="),)}


def _gcpad_is_real(body: str | None) -> bool:
    """Is this GCPad section a usable gamepad config, or a leftover?

    The old test asked "does any of the D-Pad or Z look like a bare keyboard
    key", which is a blacklist: `Buttons/Z = `D`` was caught, `Main Stick/
    Modifier = `Shift`` was not. This asks the opposite question — is every
    binding a device-agnostic SDL role token — which is what "works with any
    controller" actually means. Someone who deliberately put their D-Pad on a
    stick still passes, because a stick token is a role token; a config
    captured on a machine with a keyboard does not.
    """
    if not body or not re.search(r"Device = SDL/\d+/", body):
        return False
    values = _gc_values(body)
    if not _GC_SDL_TOKEN.match(values.get("Buttons/A", "")):
        return False        # no face buttons: a skeleton, not a config
    return all(_GC_SDL_TOKEN.match(v)
               for k, v in values.items() if _GC_ACTION_KEY.match(k))


def _dolphin(i: int, dup: int, vendor: str, product: str, name: str) -> str | None:
    """Retarget BOTH of Dolphin's input configs for player `i` onto the pad.
    Dolphin qualifies devices as SDL/<k>/<name> where <k> is a 0-based counter
    over devices SHARING THE SAME NAME (ciface DeviceContainer), not a global
    index — a lone DualSense is SDL/0/... even as Player 2. `name` must be what
    Dolphin's bundled SDL3 calls the pad.
      • GameCube (GCPadNew.ini): keep the slot's own bindings when they are
        real, else take them from another healthy slot, else from the canonical
        template above. Only the Device line varies per pad.
      • Wii (WiimoteNew.ini): write the canonical Wiimote+Nunchuk gamepad
        template with this pad's Device — the old per-pad config was a
        keyboard/mouse frankenstein and slots 2-4 were empty (Virtual pointer).
    Dolphin binds by SDL role, so `SDL/<dup>/<name>` is all that varies. Either
    file may be absent/unconfigured; we do whichever we can.

    The donor used to be GCPad1, unconditionally and untested — and on this box
    GCPad1 was itself the contaminated section (D-Pad on `T`/`G`/`F`/`H`, Z on
    `D`). So slot 1 repaired itself with itself, slots 3 and 4 cloned the
    contamination, and only slot 2 — the one section that happened to be
    correct — worked. The fix has to live in the code and not in
    emu-configs/dolphin/GCPadNew.ini, because update/linux.sh excludes
    emu-configs/ from the OTA rsync: a correction shipped there can never reach
    a box that is already installed.
    """
    device = f"SDL/{dup}/{name}"
    msgs: list[str] = []

    gcpad = DOLPHIN_DIR / "GCPadNew.ini"
    if gcpad.is_file():
        t = gcpad.read_text()
        header = f"GCPad{i}"
        body = section(t, header)
        if _gcpad_is_real(body):
            source, origin = body, "retargeted"
        else:
            # Any healthy sibling first — it may carry a remap the owner made
            # on purpose — then the template. Never an untested GCPad1.
            donor_k = _gc_donor_index(t, i)
            if donor_k:
                source, origin = section(t, f"GCPad{donor_k}"), f"rebuilt from GCPad{donor_k}"
            else:
                source, origin = _GCPAD_BODY, "rebuilt from template"
        # A plain replacement, not a regex one: an SDL device name is arbitrary
        # text and may hold backslashes that re.sub would read as escapes.
        new_body = re.sub(r"^Device = .*$", lambda _: f"Device = {device}",
                          source, count=1, flags=re.M)
        if not new_body.startswith("Device = ") and "\nDevice = " not in new_body:
            new_body = f"Device = {device}\n" + new_body
        # A calibration is a measurement of one physical stick. Cloned onto
        # another pad it is simply wrong, so it does not travel with a donor.
        new_body = re.sub(r"^.*/Calibration = .*\n", "", new_body, flags=re.M)
        # `Main Stick/Modifier = `Shift`` and `C-Stick/Modifier = `Ctrl`` are
        # keyboard leftovers that survive an otherwise healthy section: holding
        # Shift on a plugged-in keyboard shrinks the stick range of whoever
        # owns this port.
        new_body = re.sub(r"^.*/Modifier = `[^`]*`\n", "", new_body, flags=re.M)
        if new_body != body:
            t = set_section(t, header, new_body)
            msgs.append(f"GCPad{i} {origin}")
        # One physical pad cannot hold two GameCube ports. GCPad2 and GCPad3
        # both ended up on `SDL/0/Xbox One Controller`, and Mario Party moved
        # two characters at once.
        stolen = _gc_release_others(t, i, device)
        if stolen != t:
            t = stolen
            msgs.append(f"freed the duplicate {device}")
        if msgs:
            backup(gcpad); _atomic_write(gcpad, t)

    wii = DOLPHIN_DIR / "WiimoteNew.ini"
    if wii.is_file():
        t = wii.read_text()
        header = f"Wiimote{i}"
        new_body = _WIIMOTE_BODY.format(device=device)
        if section(t, header) != new_body:
            t = set_section(t, header, new_body)
            backup(wii); _atomic_write(wii, t)
            msgs.append(f"Wiimote{i} set")

    if not msgs:
        return None
    return f"dolphin: {', '.join(msgs)} (SDL/{dup}/{name})"


def _gc_donor_index(text: str, i: int) -> int:
    return next((k for k in range(1, 5)
                 if k != i and _gcpad_is_real(section(text, f"GCPad{k}"))), 0)


def _gc_release_others(text: str, i: int, device: str) -> str:
    """Blank the Device line of every other GCPad bound to the same pad."""
    for k in range(1, 5):
        if k == i:
            continue
        body = section(text, f"GCPad{k}")
        if body and re.search(rf"^Device = {re.escape(device)}$", body, re.M):
            text = set_section(text, f"GCPad{k}",
                               re.sub(r"^Device = .*$", "Device =", body, flags=re.M))
    return text


# ── RPCS3 (PS3, Player 1-4 already exist) — roles semantic, name only ───────

def _rpcs3_block(text: str, i: int) -> re.Match | None:
    return re.search(rf"^Player {i} Input:\n(.*?)(?=^Player \d+ Input:|\Z)", text, re.S | re.M)


def _rpcs3_is_bound(block: str) -> bool:
    """A slot that will actually drive a pad: the SDL handler, and bindings
    that are not all empty strings. RPCS3 writes `Handler: "Null"` with every
    binding blanked when it saves a player whose Device matched nothing."""
    if "Handler: SDL" not in block:
        return False
    return bool(re.search(r'^\s+(?:Cross|Circle|Square|Triangle|Start):\s*(?!""|$)\S',
                          block, re.M))


def _rpcs3(i: int, dup: int, vendor: str, product: str, name: str) -> str | None:
    """RPCS3's SDL handler names devices "<name> <k>" with k a 1-based
    counter over devices SHARING THE SAME NAME (sdl_pad_handler.cpp), not
    the player number — a lone DualSense is "DualSense Wireless
    Controller 1" even as Player 2. A non-matching string makes RPCS3 log
    "SDL: Adding empty device" and the pad is silently dead in game.
    `name` must be what RPCS3's bundled SDL3 calls the pad.

    Only the Device line used to be rewritten, and only if the slot already
    said `Handler: SDL`. But the state RPCS3 leaves a slot in when its Device
    matches nothing is exactly `Handler: "Null"` with every binding blanked —
    so the one case that needed repairing was the one case that returned
    early, silently, on every connection, for ever. Players 2-4 on this box
    have been in that state since 28/07 while the pre-GameCore backup still
    shows all four on `Handler: SDL`. A slot like that is now rebuilt from a
    healthy one: the bindings are role names, identical from one controller to
    the next, so the clone is correct by construction.
    """
    yml = rpcs3_default()
    if not yml.is_file():
        return Skip(f"rpcs3: no input config at {yml} — nothing to retarget")
    t = yml.read_text()
    m = _rpcs3_block(t, i)
    if not m:
        return Skip(f"rpcs3: Config has no 'Player {i} Input:' block")
    block = m.group(1)

    if _rpcs3_is_bound(block):
        source, action = block, "retargeted"
    else:
        donor = next((d.group(1) for k in range(1, 8) if k != i
                      and (d := _rpcs3_block(t, k)) and _rpcs3_is_bound(d.group(1))), None)
        if donor is None:
            return Skip(f"rpcs3: Player {i} is unbound and no other player is bound "
                        f"— nothing to clone from")
        source, action = donor, "rebuilt"
    # A device name is arbitrary text; a lambda keeps re.sub from reading a
    # backslash in it as a group reference.
    new_block = re.sub(r"^(  Device: ).*$", lambda mm: f"{mm.group(1)}{name} {dup + 1}",
                       source, count=1, flags=re.M)
    if new_block == block:
        return None
    t = t[:m.start(1)] + new_block + t[m.end(1):]
    backup(yml); _atomic_write(yml, t)
    return f"rpcs3: Player {i} {action} ({name} {dup + 1})"


# ── PCSX2 / DuckStation — Tier 0, only the SDL index needs to exist ─────────

# Per emulator: the pad type that leaves the analog sticks and the rumble
# motors alive, and where the multitap switch lives.
#
# DuckStation shipped `Type = DigitalController` while [Pad1] holds every
# analog binding it needs (LDown, RUp, L3, R3, LargeMotor, SmallMotor). The
# upstream DigitalController declares 14 digital inputs and nothing else, so
# those eleven lines are dead: sticks inert, no rumble, Ape Escape unplayable.
# It is the only Sony-side fault that hits player 1, and it could never be
# repaired because _tier0_ini returned immediately for i == 1.
#
# The multitap matters because PS1 and PS2 have two physical ports. PCSX2
# refuses slot 3+ at the SIO2 level while IsMultitapPortEnabled(port) is false,
# and DuckStation only wires Pad1/Pad2 while MultitapMode is Disabled — so
# writing [Pad3] and reporting success, as this did, promised a third player
# that could never move. Enabling the tap on port 1 gives that port slots
# 1/3/4/5, port 2 staying Pad2: four players, at the cost of a virtual
# accessory the games that ignore multitaps ignore anyway.
_TIER0 = {
    "pcsx2":       {"type": "DualShock2",
                    "tap": ("Pad", "MultitapPort1", "true")},
    "duckstation": {"type": "AnalogController",
                    "tap": ("ControllerPorts", "MultitapMode", "Port1Only")},
}


def _set_ini_key(text: str, header: str, key: str, value: str) -> tuple[str, bool]:
    """Set `key = value` in an INI section, adding the line if it is missing.
    Returns (text, changed) and never reformats anything else."""
    body = section(text, header)
    if body is None:
        return text, False
    if re.search(rf"^{re.escape(key)} = {re.escape(value)}$", body, re.M):
        return text, False
    if re.search(rf"^{re.escape(key)} = ", body, re.M):
        new = re.sub(rf"^{re.escape(key)} = .*$", lambda _: f"{key} = {value}",
                     body, count=1, flags=re.M)
    else:
        lines = body.splitlines(keepends=True)
        at = max((n for n, l in enumerate(lines) if l.strip()), default=-1) + 1
        lines.insert(at, f"{key} = {value}\n")
        new = "".join(lines)
    return set_section(text, header, new), True


def _tier0_ini(path: Path, label: str, i: int) -> str | None:
    if not path.is_file():
        return None
    spec = _TIER0[label]
    t = path.read_text()
    orig = t
    p1 = section(t, "Pad1")
    if not p1 or "SDL-0/" not in p1:
        return Skip(f"{label}: [Pad1] has no SDL bindings to clone from — "
                    f"player {i} left alone")
    header = f"Pad{i}"
    body = section(t, header)
    msgs: list[str] = []

    usable = bool(body) and "SDL-" in body and "Type = None" not in body
    if not usable:
        t = set_section(t, header, p1.replace("SDL-0/", f"SDL-{i - 1}/"))
        msgs.append(f"created {header}")
    # The Type line rides along with the cloned body, and on slot 1 it is the
    # only thing there is to fix.
    t, retyped = _set_ini_key(t, header, "Type", spec["type"])
    if retyped and not msgs:
        msgs.append(f"{header} set to {spec['type']}")

    if i >= 3:
        tap_section, tap_key, tap_value = spec["tap"]
        t, tapped = _set_ini_key(t, tap_section, tap_key, tap_value)
        if tapped:
            msgs.append(f"multitap enabled ({tap_key} = {tap_value})")

    if t == orig:
        return None
    backup(path); _atomic_write(path, t)
    return f"{label}: {', '.join(msgs)}"


# ── Entry point, called by gamepad_monitor.py on every new slot ────────────

def apply_profile(player_index: int, vendor: str, product: str, evdev_name: str,
                  dup_index: int = 0) -> list[str]:
    """Write/retarget every emulator's native config for `player_index` to
    the controller identified by `vendor`:`product`. `dup_index` = how many
    same-model pads sit in lower player slots (see module docstring) — it
    feeds every per-name/per-GUID device counter; 0 is always correct for
    the first pad of a model. Never raises — each emulator is isolated so
    one bad config doesn't block the others.

    Returns the messages of the steps that actually wrote something. Steps that
    gave up return a `Skip` and are logged as warnings instead: the caller's
    toast stays about what changed, but the journal finally says why an
    emulator was left alone."""
    if player_index < 1 or player_index > 4:
        # The slot cap is deliberate (see the module docstring), but a 5th pad
        # used to get a player number, a TV toast, and no config at all,
        # without a word anywhere.
        log.warning("controller_profiles: player %d is outside the 1-4 slots this "
                    "box profiles — %s:%s left unconfigured", player_index, vendor, product)
        return []
    name = resolve_name(vendor, product, evdev_name)
    results: list[str] = []
    steps = [
        ("ryujinx", lambda: _ryujinx(player_index, dup_index, vendor, product, name)),
        # 3DS/GBA/Wii U bind by a device GUID we can't synthesize — the user
        # "Scan mapping"s the pad once per emulator, and we restore that saved
        # config on connect (snapshot_restore). Single-player → slot 1 only.
        ("azahar", lambda: snapshot_restore("azahar", vendor, product)
                   if player_index == 1 else None),
        ("mgba", lambda: snapshot_restore("mgba", vendor, product)
                 if player_index == 1 else None),
        ("cemu", lambda: snapshot_restore("cemu", vendor, product)
                 if player_index == 1 else None),
        ("dolphin", lambda: _dolphin(player_index, dup_index, vendor, product, name)),
        ("rpcs3", lambda: _rpcs3(player_index, dup_index, vendor, product, name)),
        ("pcsx2", lambda: _tier0_ini(pcsx2_ini(), "pcsx2", player_index)),
        ("duckstation", lambda: _tier0_ini(DUCK_INI, "duckstation", player_index)),
        # melonds: single-player like the three above, and a saved mapping
        # always wins over the live synthesis.
        #
        # This used to read `snapshot_restore(...) or _melonds(...)`, and
        # snapshot_restore returns None for two different reasons: there is no
        # snapshot, or the snapshot is ALREADY in place. So the fallback ran
        # every other connection and overwrote the mapping the owner had
        # captured, which the next connection then restored — one session in
        # two was wrong. It also lacked the `player_index == 1` guard its three
        # neighbours have, so plugging in a second pad rewrote melonDS's one
        # and only player config for the wrong controller.
        ("melonds", lambda: None if player_index != 1 else (
            snapshot_restore("melonds", vendor, product)
            if snapshot_exists("melonds", vendor, product)
            else _melonds(player_index, vendor, product, name))),
    ]
    skipped: list[str] = []
    for emu, step in steps:
        try:
            msg = step()
        except Exception:
            log.exception("controller_profiles: %s failed for player %d (%s:%s)",
                         emu, player_index, vendor, product)
            skipped.append(f"{emu}: internal error (see traceback)")
            continue
        if isinstance(msg, Skip):
            skipped.append(str(msg))
        elif msg:
            results.append(msg)
    if skipped:
        log.warning("controller_profiles: player %d (%s:%s) — not configured: %s",
                    player_index, vendor, product, "; ".join(skipped))
    return results


def release_profile(player_index: int) -> list[str]:
    """Undo the "connected player" state a disconnected pad leaves behind.
    Only Dolphin's Wii Remote needs this: `Source = 1` keeps the emulated
    remote presented to the game as connected even with no input device bound,
    so a pad unplugged after co-op would haunt the next solo session as a
    phantom player. Reset that slot to Dolphin's inactive default. Role/device
    bound emulators (PS1/2/3, Switch…) just go input-less when a pad
    leaves — no phantom, nothing to undo. Never raises."""
    if player_index < 1 or player_index > 4:
        return []
    results: list[str] = []
    wii = DOLPHIN_DIR / "WiimoteNew.ini"
    if wii.is_file():
        try:
            t = wii.read_text()
            header = f"Wiimote{player_index}"
            # `Source = 0`, not "no Source line at all". Dolphin's compiled-in
            # default for Wiimote1 is WiimoteSource::Emulated
            # (Core/Config/WiimoteSettings.cpp), so deleting the key alongside
            # the body left an emulated remote presented to the game as
            # connected and bound to a pointer with no buttons. Wii Sports
            # started, asked for A, and neither pad nor keyboard could answer:
            # this function created the phantom it exists to remove.
            inactive = "Source = 0\nDevice = XInput2/0/Virtual core pointer\n"
            if section(t, header) != inactive:
                t = set_section(t, header, inactive)
                backup(wii); _atomic_write(wii, t)
                results.append(f"dolphin: {header} released (inactive)")
        except Exception:
            log.exception("controller_profiles: release failed for player %d", player_index)

    # GameCube ports have no Source key and no phantom, but the Device line
    # stays pinned to a pad that has left. The next pad to take a lower slot is
    # then written next to it, and two ports drive the same controller.
    gcpad = DOLPHIN_DIR / "GCPadNew.ini"
    if gcpad.is_file():
        try:
            t = gcpad.read_text()
            header = f"GCPad{player_index}"
            body = section(t, header)
            if body and re.search(r"^Device = SDL/", body, re.M):
                t = set_section(t, header,
                                re.sub(r"^Device = .*$", "Device =", body, flags=re.M))
                backup(gcpad); _atomic_write(gcpad, t)
                results.append(f"dolphin: {header} unbound")
        except Exception:
            log.exception("controller_profiles: GCPad release failed for player %d", player_index)
    return results


def scan_mapping() -> dict:
    """"Scan mapping" button: remember the ONE connected controller's current
    input config across the GUID-based emulators, so it auto-restores on every
    future connect. The user configures the pad once in each emulator's own
    input UI (auto-map), then triggers this."""
    pads = detect_pads()
    if len(pads) != 1:
        return {"ok": False,
                "error": ("connect exactly one controller (the one you just "
                          f"configured) — found {len(pads)}")}
    vendor, product, evdev = pads[0]
    saved, refused = snapshot_capture(vendor, product)
    # `refused` is the emulators whose config describes a different pad — the
    # user mapped one controller and pressed the button holding another, or
    # never mapped that emulator at all. Saying so beats a green "ok" that
    # quietly stores the wrong mapping under this pad's name.
    return {"ok": True, "controller": resolve_name(vendor, product, evdev),
            "saved": saved, "refused": refused}


# ── Manual/rescue entry point (install/apply-controller-model.sh) ──────────
# The live path is gamepad_monitor.py calling apply_profile() on every new
# connection — this is only for fixing already-connected pads without
# unplugging them (e.g. right after installing this feature).

def detect_pads(max_n: int = 4) -> list[tuple[str, str, str]]:
    """[(vendor, product, evdev_name), …], one per physical device (deduped
    by uniq/MAC), in the same order controller_registry.py would assign
    player slots — sorted by device path, lowest free slot first."""
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


def _main() -> None:
    import sys
    if len(sys.argv) > 1:
        vendor, _, product = sys.argv[1].lower().partition(":")
        name = sys.argv[2] if len(sys.argv) > 2 else resolve_name(vendor, product, "Generic Controller")
        pads = [(vendor, product, name)]
    else:
        pads = detect_pads()
        if not pads:
            sys.exit("No connected gamepad found (checked evdev for a BTN_SOUTH device). "
                     "Pass VID:PID explicitly, or check permissions (input group).")
    print(f"{'Auto-detected' if len(sys.argv) <= 1 else 'Forced'} "
         f"{len(pads)} controller(s):")
    for i, (v, p, n) in enumerate(pads, 1):
        resolved = resolve_name(v, p, n)
        print(f"  Player {i}: {resolved}  ({v}:{p})")
    print()
    model_counts: dict[tuple[str, str], int] = {}
    for i, (v, p, n) in enumerate(pads, 1):
        dup = model_counts.get((v, p), 0)
        results = apply_profile(i, v, p, n, dup)
        model_counts[(v, p)] = dup + 1
        print(f"Player {i}: " + ("; ".join(results) if results else "nothing to do"))
    print("\nDone. This also happens automatically now, live, whenever a "
         "controller connects (backend/services/gamepad_monitor.py) — "
         "this command is only for fixing already-connected pads without "
         "unplugging them.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    _main()
