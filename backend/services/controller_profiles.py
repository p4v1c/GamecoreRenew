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
  - Ryujinx binds by a device GUID. DualShock 4 and DualSense share the same
    kernel driver and report IDENTICAL raw indices (verified live) — only the
    GUID's vendor/product bytes differ, at a fixed, format-stable hex offset.
    Retargeting a slot is therefore a pure GUID substitution, and every button
    assignment the owner already validated stays exactly where it is. The
    accompanying index is, again, NOT the player slot: the `id` prefix
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
MGBA_CONFIG = HOME / ".config/mgba/config.ini"
MELONDS_TOML = HOME / ".var/app/net.kuribo64.melonDS/config/melonDS/melonDS.toml"
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


def backup(p: Path) -> None:
    b = p.with_name(p.name + ".bak-ctrlmodel")
    if p.is_file() and not b.exists():
        shutil.copy2(p, b)


def section(text: str, header: str) -> str | None:
    m = re.search(rf"^\[{re.escape(header)}\]\n(.*?)(?=^\[|\Z)", text, re.S | re.M)
    return m.group(1) if m else None


def set_section(text: str, header: str, body: str) -> str:
    pat = rf"^\[{re.escape(header)}\]\n.*?(?=^\[|\Z)"
    if re.search(pat, text, re.S | re.M):
        return re.sub(pat, f"[{header}]\n{body}", text, count=1, flags=re.S | re.M)
    return text.rstrip() + f"\n\n[{header}]\n{body}"


# ── Ryujinx (Switch, up to 8 in principle — we honor players 1-4) ───────────

def _ryu_guid_vidpid(dashed_guid: str) -> tuple[str, str] | None:
    """(vendor, product) from a Ryujinx dashed SDL GUID. Ryujinx's bundled
    SDL2 lays out the vendor at [8:12] big-endian and the product at [16:20]
    little-endian (`00000003-054c-0000-cc09-…` → 054c / 09cc)."""
    g = dashed_guid.replace("-", "")
    if len(g) != 32:
        return None
    return g[8:12].lower(), (g[18:20] + g[16:18]).lower()


def _ryu_swap_vidpid(dashed_guid: str, vendor: str, product: str) -> str:
    """Best-effort GUID for a controller Ryujinx has never bound here: swap the
    vendor/product into a reference GUID (vendor [8:12] BE, product [16:20] LE).
    Reliable only within the reference's own brand/family — Ryujinx's SDL2 also
    encodes bus/version/driver bytes that differ per model, which is why
    _ryujinx() prefers a GUID Ryujinx has actually written (see there)."""
    g = dashed_guid.replace("-", "")
    if len(g) != 32:
        return dashed_guid
    g = g[:8] + vendor + g[12:16] + product[2:4] + product[0:2] + g[20:]
    return f"{g[0:8]}-{g[8:12]}-{g[12:16]}-{g[16:20]}-{g[20:32]}"


def _ryujinx(i: int, dup: int, vendor: str, product: str, name: str) -> str | None:
    """Ryujinx binds each slot in Config.json's `input_config` list by
    `player_index` (`Player1`..`Player8`) and an `id` `"<dup>-<SDL GUID>"`,
    where <dup> counts pads sharing that GUID (NOT the player number).

    The GUID must be the exact string Ryujinx's bundled SDL2 computes for the
    device — and that encodes bus/version/driver bytes we can't derive from
    vendor:product alone (a DS4 is `00000003-054c-…-…6800`, an Xbox pad
    `00000005-045e-…-…09090000`). So we can't synthesize it blindly across
    brands. Instead we LEARN: reuse the exact GUID Ryujinx already wrote for a
    pad of this vendor:product (in any slot — the curated Config.json seeds the
    box's own pads, and once a user assigns a new pad in Ryujinx it's captured
    here). Only the first time an unseen brand appears do we fall back to a
    best-effort swap from Player1's GUID, which may need a one-off manual
    'Input Device' pick in Ryujinx — after which this learns it."""
    if not RYUJINX_CFG.is_file():
        return None
    try:
        cfg = json.loads(RYUJINX_CFG.read_text())
    except (OSError, ValueError):
        return None
    ic = cfg.get("input_config")
    if not isinstance(ic, list):
        return None
    pi = f"Player{i}"
    p1 = next((e for e in ic if e.get("player_index") == "Player1"), None)
    if p1 is None or "-" not in str(p1.get("id", "")):
        return None
    # Prefer a GUID Ryujinx has actually written for this vendor:product.
    known = None
    for e in ic:
        eid = str(e.get("id", ""))
        if "-" in eid and _ryu_guid_vidpid(eid.split("-", 1)[1]) == (vendor.lower(), product.lower()):
            known = eid.split("-", 1)[1]
            break
    if known:
        new_guid, how = known, "matched"
    else:
        new_guid = _ryu_swap_vidpid(str(p1["id"]).split("-", 1)[1], vendor, product)
        how = "best-effort"
    slot = next((e for e in ic if e.get("player_index") == pi), None)
    if slot is not None:
        slot["id"] = f"{dup}-{new_guid}"
        slot["name"] = f"{name} ({dup})"
        action = "retargeted"
    else:                                              # clone Player1 into slot i
        clone = json.loads(json.dumps(p1))
        clone["player_index"] = pi
        clone["id"] = f"{dup}-{new_guid}"
        clone["name"] = f"{name} ({dup})"
        ic.append(clone)
        action = "created"
    backup(RYUJINX_CFG)
    RYUJINX_CFG.write_text(json.dumps(cfg, indent=2) + "\n")
    return f"ryujinx: Player {i} {action} ({how} GUID, dup {dup})"


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
    backup(path); path.write_text("".join(out))
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


def _az_extract(text: str) -> str:
    return "".join(l for l in text.splitlines(keepends=True)
                   if l.startswith("profiles\\1\\"))


def _az_replace(text: str, block: str) -> str:
    if not block.endswith("\n"):
        block += "\n"
    out, done = [], False
    for l in text.splitlines(keepends=True):
        if l.startswith("profiles\\1\\"):
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


# mgba: profiles persist per GUID in [gba.input-profile.<GUID>]; `device0=` picks
# the active one. Capture device0 + its profile section; restore both so mgba
# points at the connected pad's own profile.
def _mgba_extract(text: str) -> str:
    lines = text.splitlines(keepends=True)
    dev = next((l for l in lines if l.startswith("device0=")), "")
    guid = dev.split("=", 1)[1].strip() if "=" in dev else ""
    s, e = _sect_bounds(lines, f"gba.input-profile.{guid}") if guid else (None, None)
    return dev + ("".join(lines[s:e]) if s is not None else "")


def _mgba_replace(text: str, block: str) -> str:
    blines = block.splitlines(keepends=True)
    dev = next((l for l in blines if l.startswith("device0=")), "")
    guid = dev.split("=", 1)[1].strip() if "=" in dev else ""
    sect = "".join(l for l in blines if not l.startswith("device0="))
    out, dev_set = [], False
    for l in text.splitlines(keepends=True):
        if l.startswith("device0="):
            out.append(dev if dev.endswith("\n") else dev + "\n"); dev_set = True
        else:
            out.append(l)
    if not dev_set and dev:
        out.insert(0, dev if dev.endswith("\n") else dev + "\n")
    result = "".join(out)
    if guid and sect.strip():
        result = _sect_replace(f"gba.input-profile.{guid}")(result, sect)
    return result


# emu_id → (config-path getter, extract(text)→block, replace(text, block)→text)
_SNAP_EMUS = {
    "azahar":  (lambda: AZAHAR, _az_extract, _az_replace),
    "melonds": (lambda: MELONDS_TOML, _sect_extract("Instance0.Joystick"),
                _sect_replace("Instance0.Joystick")),
    "mgba":    (lambda: MGBA_CONFIG, _mgba_extract, _mgba_replace),
    "cemu":    (lambda: CEMU_PROFILES / "controller0.xml", _whole_extract, _whole_replace),
}


def _snap_path(emu_id: str, vendor: str, product: str) -> Path:
    return SNAP_DIR / emu_id / f"{vendor.lower()}_{product.lower()}.snap"


def snapshot_capture(vendor: str, product: str) -> list[str]:
    """Save each GUID-emulator's CURRENT input config for this controller — the
    'Scan mapping' action, after the user has auto-mapped the pad in-emulator."""
    saved = []
    for emu_id, (pathfn, extract, _r) in _SNAP_EMUS.items():
        path = pathfn()
        if not path.is_file():
            continue
        block = extract(path.read_text())
        if not block.strip():
            continue
        snap = _snap_path(emu_id, vendor, product)
        snap.parent.mkdir(parents=True, exist_ok=True)
        snap.write_text(block)
        saved.append(emu_id)
    return saved


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
    backup(path); path.write_text(replace(text, block))
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


def _sdl2_live_mapping(vendor: str, product: str) -> dict[str, str] | None:
    """Live SDL2 GameController mapping (SDL name → raw token like 'b6'/'h0.1')
    for the connected vendor:product. Run in a SUBPROCESS: melonDS binds by raw
    SDL2 joystick index, but those indices differ per controller AND per driver
    version — the vendored gamecontrollerdb even ships conflicting Linux entries
    for one pad (an Xbox is b4/b5 or b6/b7). The only reliable source is the
    exact SDL2 the emulator uses; the backend itself loads SDL3, so we shell out
    to read SDL2's own numbering. None on any failure."""
    script = (
        "import ctypes,os,sys\n"
        "os.environ['SDL_VIDEODRIVER']='dummy'\n"
        "v=int(sys.argv[1],16);p=int(sys.argv[2],16)\n"
        "try: s=ctypes.CDLL('libSDL2-2.0.so.0')\n"
        "except OSError: sys.exit(0)\n"
        "s.SDL_GameControllerMappingForDeviceIndex.restype=ctypes.c_char_p\n"
        "s.SDL_GameControllerMappingForDeviceIndex.argtypes=[ctypes.c_int]\n"
        "s.SDL_JoystickGetDeviceVendor.restype=ctypes.c_uint16\n"
        "s.SDL_JoystickGetDeviceProduct.restype=ctypes.c_uint16\n"
        "s.SDL_JoystickGetDeviceVendor.argtypes=[ctypes.c_int]\n"
        "s.SDL_JoystickGetDeviceProduct.argtypes=[ctypes.c_int]\n"
        "if s.SDL_Init(0x2000)!=0: sys.exit(0)\n"
        "for i in range(s.SDL_NumJoysticks()):\n"
        " if s.SDL_JoystickGetDeviceVendor(i)==v and s.SDL_JoystickGetDeviceProduct(i)==p:\n"
        "  m=s.SDL_GameControllerMappingForDeviceIndex(i)\n"
        "  print(m.decode()) if m else None; break\n"
        "s.SDL_Quit()\n"
    )
    try:
        r = subprocess.run([sys.executable, "-c", script, vendor, product],
                           capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.SubprocessError):
        return None
    line = r.stdout.strip()
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
    if i != 1 or not MELONDS_TOML.is_file():
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
    for line in MELONDS_TOML.read_text().splitlines():
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
    backup(MELONDS_TOML)
    MELONDS_TOML.write_text("\n".join(out) + "\n")
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


def _dolphin(i: int, dup: int, vendor: str, product: str, name: str) -> str | None:
    """Retarget BOTH of Dolphin's input configs for player `i` onto the pad.
    Dolphin qualifies devices as SDL/<k>/<name> where <k> is a 0-based counter
    over devices SHARING THE SAME NAME (ciface DeviceContainer), not a global
    index — a lone DualSense is SDL/0/... even as Player 2. `name` must be what
    Dolphin's bundled SDL3 calls the pad.
      • GameCube (GCPadNew.ini): clone the working GCPad1, swap the Device line.
      • Wii (WiimoteNew.ini): write the canonical Wiimote+Nunchuk gamepad
        template above with this pad's Device — the old per-pad config was a
        keyboard/mouse frankenstein and slots 2-4 were empty (Virtual pointer).
    Dolphin binds by SDL role, so `SDL/<dup>/<name>` is all that varies. Either
    file may be absent/unconfigured; we do whichever we can."""
    device = f"SDL/{dup}/{name}"
    msgs: list[str] = []

    gcpad = DOLPHIN_DIR / "GCPadNew.ini"
    if gcpad.is_file():
        t = gcpad.read_text()
        p1 = section(t, "GCPad1")
        if p1 and "Device = SDL/" in p1:
            header = f"GCPad{i}"
            body = section(t, header)
            # A section only counts as usable if it is genuinely a pad config.
            # GCPad1/3/4 shipped with the D-Pad on `T`/`G`/`F`/`H` and Z on `D` —
            # keyboard keys left over from the machine the configs were captured
            # on. They satisfied both checks below, so this function rewrote only
            # their Device line: on a fresh install with one pad, the D-Pad did
            # nothing and Z (targeting) was unusable in every GameCube game,
            # while player 2 — the one section that was correct — worked fine.
            #
            # The third test asks "is any of this a bare keyboard key", not "is
            # it exactly `Pad N`", so that someone who deliberately remapped
            # their D-Pad onto a stick does not have that thrown away and
            # replaced with a clone of GCPad1.
            keyboard_leftover = bool(body) and re.search(
                r"(?:D-Pad/(?:Up|Down|Left|Right)|Buttons/Z) = `[^`]`", body)
            is_real = bool(body) and re.search(r"Device = SDL/\d+/", body) and \
                re.search(r"Buttons/A = `Button [SNEW]`", body) and \
                not keyboard_leftover
            source = body if is_real else p1
            new_body = re.sub(r"Device = SDL/\d+/[^\n]*", f"Device = {device}", source)
            if new_body != body:
                t = set_section(t, header, new_body)
                backup(gcpad); gcpad.write_text(t)
                msgs.append(f"GCPad{i} {'retargeted' if is_real else 'created'}")

    wii = DOLPHIN_DIR / "WiimoteNew.ini"
    if wii.is_file():
        t = wii.read_text()
        header = f"Wiimote{i}"
        new_body = _WIIMOTE_BODY.format(device=device)
        if section(t, header) != new_body:
            t = set_section(t, header, new_body)
            backup(wii); wii.write_text(t)
            msgs.append(f"Wiimote{i} set")

    if not msgs:
        return None
    return f"dolphin: {', '.join(msgs)} (SDL/{dup}/{name})"


# ── RPCS3 (PS3, Player 1-4 already exist) — roles semantic, name only ───────

def _rpcs3(i: int, dup: int, vendor: str, product: str, name: str) -> str | None:
    """RPCS3's SDL handler names devices "<name> <k>" with k a 1-based
    counter over devices SHARING THE SAME NAME (sdl_pad_handler.cpp), not
    the player number — a lone DualSense is "DualSense Wireless
    Controller 1" even as Player 2. A non-matching string makes RPCS3 log
    "SDL: Adding empty device" and the pad is silently dead in game.
    `name` must be what RPCS3's bundled SDL3 calls the pad."""
    yml = rpcs3_default()
    if not yml.is_file():
        return None
    t = yml.read_text()
    m = re.search(rf"^Player {i} Input:\n(.*?)(?=^Player \d+ Input:|\Z)", t, re.S | re.M)
    if not m or "Handler: SDL" not in m.group(1):
        return None
    block = m.group(1)
    block2 = re.sub(r"^(  Device: ).*$", rf"\g<1>{name} {dup + 1}", block, count=1, flags=re.M)
    if block2 == block:
        return None
    t = t[:m.start(1)] + block2 + t[m.end(1):]
    backup(yml); yml.write_text(t)
    return f"rpcs3: Player {i} retargeted ({name} {dup + 1})"


# ── PCSX2 / DuckStation — Tier 0, only the SDL index needs to exist ─────────

def _tier0_ini(path: Path, label: str, i: int) -> str | None:
    if i == 1 or not path.is_file():
        return None
    t = path.read_text()
    p1 = section(t, "Pad1")
    if not p1 or "SDL-0/" not in p1:
        return None
    header = f"Pad{i}"
    body = section(t, header)
    if body and "SDL-" in body and "Type = None" not in body:
        return None  # already a real, device-agnostic binding — nothing to do, ever
    new_body = p1.replace("SDL-0/", f"SDL-{i - 1}/")
    t = set_section(t, header, new_body)
    backup(path); path.write_text(t)
    return f"{label}: created {header} (device-agnostic from here on)"


# ── Entry point, called by gamepad_monitor.py on every new slot ────────────

def apply_profile(player_index: int, vendor: str, product: str, evdev_name: str,
                  dup_index: int = 0) -> list[str]:
    """Write/retarget every emulator's native config for `player_index` to
    the controller identified by `vendor`:`product`. `dup_index` = how many
    same-model pads sit in lower player slots (see module docstring) — it
    feeds every per-name/per-GUID device counter; 0 is always correct for
    the first pad of a model. Never raises — each emulator is isolated so
    one bad config doesn't block the others."""
    if player_index < 1 or player_index > 4:
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
        # melonds: a saved mapping wins; else fall back to the live synthesis.
        ("melonds", lambda: (snapshot_restore("melonds", vendor, product)
                             or _melonds(player_index, vendor, product, name))),
    ]
    for emu, step in steps:
        try:
            msg = step()
        except Exception:
            log.exception("controller_profiles: %s failed for player %d (%s:%s)",
                         emu, player_index, vendor, product)
            continue
        if msg:
            results.append(msg)
    return results


def release_profile(player_index: int) -> list[str]:
    """Undo the "connected player" state a disconnected pad leaves behind.
    Only Dolphin's Wii Remote needs this: `Source = 1` keeps the emulated
    remote presented to the game as connected even with no input device bound,
    so a pad unplugged after co-op would haunt the next solo session as a
    phantom player. Reset that slot to Dolphin's inactive default. Role/device
    bound emulators (GameCube, PS1/2/3, Switch…) just go input-less when a pad
    leaves — no phantom, nothing to undo. Never raises."""
    if player_index < 1 or player_index > 4:
        return []
    results: list[str] = []
    wii = DOLPHIN_DIR / "WiimoteNew.ini"
    if wii.is_file():
        try:
            t = wii.read_text()
            header = f"Wiimote{player_index}"
            inactive = "Device = XInput2/0/Virtual core pointer\n"
            if section(t, header) != inactive:
                t = set_section(t, header, inactive)
                backup(wii); wii.write_text(t)
                results.append(f"dolphin: {header} released (inactive)")
        except Exception:
            log.exception("controller_profiles: release failed for player %d", player_index)
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
    saved = snapshot_capture(vendor, product)
    return {"ok": True, "controller": resolve_name(vendor, product, evdev),
            "saved": saved}


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
