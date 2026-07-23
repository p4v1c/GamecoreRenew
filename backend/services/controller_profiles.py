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
  - Ryujinx, azahar, mgba, Cemu bind by a device GUID/uuid. DualShock 4 and
    DualSense share the same kernel driver and report IDENTICAL raw indices
    (verified live) — only the GUID's vendor/product bytes differ, at a fixed,
    format-stable hex offset. Retargeting a slot (or cloning slot 1 into a new
    slot) is a pure GUID substitution — every button assignment already
    validated by the owner stays exactly where it is. But the accompanying
    index is, again, NOT the player slot: Ryujinx's `id` prefix (`<dup>-<GUID>`
    in Config.json) counts pads sharing the same GUID — a lone DualSense is
    dup 0 even as Player 2, a wrong dup binds a device that isn't there — and
    Cemu's `<uuid>k_guid</uuid>` prefix is the same per-GUID counter
    (SDLControllerProvider guid_counter). Ryujinx slots live as objects in the
    `input_config` list keyed by `player_index` (`Player1`..).
  - azahar (3DS) and mgba (GBA): single-player hardware — only slot 1 is
    ever touched, regardless of which player index is passed in.
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


def _mgba(i: int, vendor: str, product: str, name: str) -> str | None:
    if i != 1 or not MGBA_CONFIG.is_file():
        return None
    t = MGBA_CONFIG.read_text()
    m = re.search(r"^device0=([0-9a-fA-F]{32})$", t, re.M)
    if not m:
        return None
    old_guid = m.group(1)
    new_guid = swap_vidpid(old_guid, vendor, product)
    backup(MGBA_CONFIG)
    t = re.sub(r"^device0=[0-9a-fA-F]{32}$", f"device0={new_guid}", t, flags=re.M)
    sec = re.search(rf"^\[gba\.input-profile\.{old_guid}\]\n(.*?)(?=^\[|\Z)", t, re.S | re.M)
    if sec and f"[gba.input-profile.{new_guid}]" not in t:
        t += f"\n[gba.input-profile.{new_guid}]\n{sec.group(1)}"
    MGBA_CONFIG.write_text(t)
    return "mgba: Player 1 retargeted (active slot + saved profile)"


def _pad_has_hat(vendor: str, product: str) -> bool | None:
    """Whether the connected pad exposes its D-pad as an evdev hat (ABS_HAT0X,
    code 0x10) rather than buttons. Xbox and most pads use a hat; a DS4 over
    the HIDAPI/hid-sony path exposes the D-pad as buttons 11-14 instead. None
    when the pad can't be found (leave the config untouched)."""
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


def _melonds(i: int, vendor: str, product: str, name: str) -> str | None:
    """melonDS (DS) is single-player — only slot 1. It binds raw SDL joystick
    inputs: the face buttons are consistent across pads, but the D-pad is not
    — a hat pad (Xbox, most third-party) needs melonDS's HAT encoding, while a
    DS4 exposes the D-pad as buttons 11-14. Adapt just the four D-pad keys in
    [Instance0.Joystick] to whichever the connected controller uses."""
    if i != 1 or not MELONDS_TOML.is_file():
        return None
    hat = _pad_has_hat(vendor, product)
    if hat is None:
        return None
    # HAT 0: 0x100 | SDL_HAT_dir (UP=1, RIGHT=2, DOWN=4, LEFT=8).
    dpad = ({"Up": 257, "Right": 258, "Down": 260, "Left": 264} if hat
            else {"Up": 11, "Down": 12, "Left": 13, "Right": 14})
    out, insec, n = [], False, 0
    for line in MELONDS_TOML.read_text().splitlines():
        s = line.strip()
        if s.startswith("["):
            insec = (s == "[Instance0.Joystick]")
        m = re.match(r"^(Up|Down|Left|Right)\s*=\s*-?\d+\s*$", s)
        if insec and m and m.group(1) in dpad:
            out.append(f"{m.group(1)} = {dpad[m.group(1)]}"); n += 1
        else:
            out.append(line)
    if not n:
        return None
    backup(MELONDS_TOML)
    MELONDS_TOML.write_text("\n".join(out) + "\n")
    return f"melonds: D-pad set ({'hat' if hat else 'buttons'})"


# ── Cemu (Wii U, controllerN.xml, 0-indexed) ────────────────────────────────

def _cemu(i: int, dup: int, vendor: str, product: str, name: str) -> str | None:
    """controller<idx>.xml is the emulated Wii U controller slot (player-1,
    0-based), but the <uuid> prefix is Cemu's per-GUID duplicate counter
    (SDLControllerProvider guid_counter) — a lone pad of its model is
    always 0_<guid>, whichever player slot it occupies."""
    slot0 = CEMU_PROFILES / "controller0.xml"
    if not slot0.is_file():
        return None
    template = slot0.read_text()
    m = re.search(r"<uuid>(\d+)_([0-9a-fA-F]{32})</uuid>", template)
    if not m:
        return None
    idx = i - 1
    f = CEMU_PROFILES / f"controller{idx}.xml"
    new_guid = swap_vidpid(m.group(2), vendor, product)
    if f.is_file():
        t = f.read_text()
        fm = re.search(r"<uuid>(\d+)_([0-9a-fA-F]{32})</uuid>", t)
        if not fm:
            return None
        backup(f)
        t = t.replace(f"<uuid>{fm.group(1)}_{fm.group(2)}</uuid>", f"<uuid>{dup}_{new_guid}</uuid>")
        t = re.sub(r"<display_name>[^<]*</display_name>", f"<display_name>{name}</display_name>", t, count=1)
        f.write_text(t)
        return f"cemu: slot {idx} retargeted (uuid {dup}_)"
    t = template.replace(f"<uuid>{m.group(1)}_{m.group(2)}</uuid>", f"<uuid>{dup}_{new_guid}</uuid>")
    t = re.sub(r"<display_name>[^<]*</display_name>", f"<display_name>{name}</display_name>", t, count=1)
    f.write_text(t)
    return f"cemu: slot {idx} created (uuid {dup}_)"


# ── Dolphin (GameCube/Wii, GCPad1-4) — roles semantic, index+name only ──────

def _dolphin(i: int, dup: int, vendor: str, product: str, name: str) -> str | None:
    """Dolphin qualifies devices as SDL/<k>/<name> where <k> is a 0-based
    counter over devices SHARING THE SAME NAME (ciface DeviceContainer),
    not a global index — a lone DualSense is SDL/0/... even as Player 2.
    `name` must be what Dolphin's bundled SDL3 calls the pad."""
    gcpad = DOLPHIN_DIR / "GCPadNew.ini"
    if not gcpad.is_file():
        return None
    t = gcpad.read_text()
    p1 = section(t, "GCPad1")
    if not p1 or "Device = SDL/" not in p1:
        return None
    header = f"GCPad{i}"
    body = section(t, header)
    is_real = bool(body) and re.search(r"Device = SDL/\d+/", body) and \
        re.search(r"Buttons/A = `Button [SNEW]`", body)
    source = body if is_real else p1
    new_body = re.sub(r"Device = SDL/\d+/[^\n]*", f"Device = SDL/{dup}/{name}", source)
    if new_body == body:
        return None
    t = set_section(t, header, new_body)
    backup(gcpad); gcpad.write_text(t)
    return f"dolphin: {header} {'retargeted' if is_real else 'created'} (SDL/{dup}/{name})"


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
        ("azahar", lambda: _single_player_guid(AZAHAR, "azahar", "profiles\\1\\",
                                              player_index, vendor, product, name)),
        ("mgba", lambda: _mgba(player_index, vendor, product, name)),
        ("cemu", lambda: _cemu(player_index, dup_index, vendor, product, name)),
        ("dolphin", lambda: _dolphin(player_index, dup_index, vendor, product, name)),
        ("rpcs3", lambda: _rpcs3(player_index, dup_index, vendor, product, name)),
        ("pcsx2", lambda: _tier0_ini(pcsx2_ini(), "pcsx2", player_index)),
        ("duckstation", lambda: _tier0_ini(DUCK_INI, "duckstation", player_index)),
        ("melonds", lambda: _melonds(player_index, vendor, product, name)),
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
