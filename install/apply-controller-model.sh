#!/usr/bin/env bash
# ================================================================
#  GameCore — Auto-configure Player 1-4 from whatever controllers are
#  physically connected right now, across every emulator.
#
#  Console-style: controllers are assigned to slots in connection
#  order (same algorithm as backend/services/controller_registry.py —
#  first pad seen is Player 1, the next is Player 2, …), and each
#  emulator gets whichever player slots that implies, up to 4.
#
#  See docs/CONTROLLER_MODELS.md for the full rationale. Summary:
#   - Sony pads (DualShock 4, DualSense, …) share the same kernel
#     driver and report IDENTICAL raw SDL button/axis indices —
#     verified live on this box. So for citron/Cemu (which bind by
#     raw index + device GUID/uuid), this script finds an existing
#     slot's GUID and substitutes just the vendor/product bytes, or
#     clones slot 1's structure wholesale for a brand-new slot —
#     every button stays exactly where it was already configured.
#   - RPCS3 and Dolphin bind by SDL role NAME (already device-
#     agnostic) plus a literal device NAME string used only to pick
#     which physical pad feeds that slot — this script updates just
#     that name (or clones slot 1 for a new/broken slot).
#   - PCSX2, DuckStation, gopher64 bind by SDL role name with NO
#     device identity at all for slot 1 — but slots 2-4 there are
#     STILL tied to an SDL connection-order index (SDL-1/SDL-2/SDL-3)
#     that must exist as a real section, so this script creates it by
#     cloning slot 1's role bindings if missing; once created, no
#     further per-model work is ever needed for these three.
#   - azahar (3DS) and mgba (GBA): single-player hardware, no local
#     multi-controller concept — only Player 1 is ever touched.
#   - ppsspp/melonDS: skipped — no existing binding on this box to
#     clone from (never launched/configured yet).
#
#  Usage:
#    install/apply-controller-model.sh                  # auto-detect, up to 4
#    install/apply-controller-model.sh 054c:0ce6         # force a single VID:PID as Player 1
#    install/apply-controller-model.sh 054c:0ce6 "PS5 Controller"
#
#  Idempotent. Backs up every file it touches as <file>.bak-ctrlmodel
#  (once — re-running never overwrites an existing backup).
# ================================================================
set -euo pipefail

[[ $EUID -ne 0 ]] || { echo "Run me as the gaming user, not root."; exit 1; }

GAMECORE_PATH="${GAMECORE_PATH:-/opt/GameCore}"
DB_FILE="$GAMECORE_PATH/backend/data/gamecontrollerdb.txt"
# evdev lives in the core's venv, not necessarily in system python3.
PY="$GAMECORE_PATH/.venv/bin/python3"
[[ -x "$PY" ]] || PY="$(command -v python3)"

TARGET_VIDPID="${1:-}"
TARGET_NAME="${2:-}"

RYUJINX_DIR="$HOME/.var/app/io.github.ryubing.Ryujinx/config/Ryujinx"
CITRON="$HOME/.config/citron/qt-config.ini"
AZAHAR="$HOME/.var/app/org.azahar_emu.Azahar/config/azahar-emu/qt-config.ini"
DOLPHIN_DIR="$HOME/.var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu"
RPCS3_DEFAULT="$HOME/.config/rpcs3/input_configs/global/Default.yml"
CEMU_PROFILES="$HOME/.var/app/info.cemu.Cemu/config/Cemu/controllerProfiles"
MGBA_CONFIG="$HOME/.config/mgba/config.ini"
PCSX2="$HOME/.config/PCSX2/inis/PCSX2.ini"
DUCK="$HOME/.local/share/duckstation/settings.ini"

"$PY" - "$DB_FILE" "$TARGET_VIDPID" "$TARGET_NAME" \
       "$CITRON" "$AZAHAR" "$DOLPHIN_DIR" "$RPCS3_DEFAULT" "$CEMU_PROFILES" "$MGBA_CONFIG" \
       "$PCSX2" "$DUCK" <<'PYEOF'
import glob
import os
import re
import shutil
import sys
from pathlib import Path

(db_file, target_vidpid, target_name,
 citron, azahar, dolphin_dir, rpcs3_default, cemu_profiles, mgba_config,
 pcsx2, duck) = sys.argv[1:12]

GUID_RE = re.compile(r"\b([0-9a-fA-F]{32})\b")


def vidpid_of(guid: str) -> tuple[str, str]:
    """SDL packs vendor/product as little-endian 16-bit words at a fixed
    hex offset, stable across every GUID format revision we've seen on
    this box (03.. and 05.. bus-type prefixes both use it) — the same
    trick every web/native SDL_GameControllerDB consumer uses."""
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
    vendored gamecontrollerdb.txt — any platform entry works, the
    friendly name is the same string across platform variants."""
    try:
        text = Path(db_file).read_text(encoding="utf-8", errors="replace")
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


# ── Detect connected pads, in the SAME order controller_registry.py
#    would assign player slots (lowest free slot = first seen, sorted
#    by device path — see backend/services/gamepad_monitor.py) ────────────
def detect_pads(max_n: int = 4) -> list[tuple[str, str, str]]:
    """[(vendor, product, name), …] — one real gamepad per physical
    device (deduped by uniq/MAC, or by path when no MAC), up to max_n."""
    try:
        import evdev
    except ImportError:
        return []

    BTN_SOUTH = 0x130
    seen_keys: set[str] = set()
    pads: list[tuple[str, str, str]] = []
    for path in sorted(glob.glob("/dev/input/event*")):
        try:
            dev = evdev.InputDevice(path)
            caps = dev.capabilities()
            keys = caps.get(1, [])  # EV_KEY
            if BTN_SOUTH not in keys:
                dev.close()
                continue
            info = dev.info
            vendor = f"{info.vendor:04x}"
            product = f"{info.product:04x}"
            name = dev.name
            key = (dev.uniq or path)
            dev.close()
        except (PermissionError, OSError):
            continue
        if key in seen_keys:
            continue
        seen_keys.add(key)
        pads.append((vendor, product, name))
        if len(pads) >= max_n:
            break
    return pads


if target_vidpid:
    vendor, _, product = target_vidpid.lower().partition(":")
    name = target_name or db_name_for(vendor, product) or "Generic Controller"
    pads = [(vendor, product, name)]
else:
    pads = detect_pads()
    if not pads:
        sys.exit("No connected gamepad found. Pass VID:PID explicitly, "
                 "or check `evtest`/permissions (input group).")
    resolved = []
    for vendor, product, evdev_name in pads:
        name = db_name_for(vendor, product) or evdev_name
        resolved.append((vendor, product, name))
    pads = resolved
    print(f"Detected {len(pads)} controller(s), in connection order:")
    for i, (v, p, n) in enumerate(pads, 1):
        print(f"  Player {i}: {n}  ({v}:{p})")
    print()


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


# ── citron (Switch, up to 8 in principle — we handle 4) ─────────────────────
def do_citron(pads):
    p = Path(citron)
    if not p.is_file():
        print("citron   : SKIP — not configured on this box")
        return
    t = p.read_text()
    used_ports = sorted({int(m) for m in re.findall(r"port:(\d+)", t)})
    next_port = (used_ports[-1] + 1) if used_ports else 0
    changed_slots = []
    for i, (vendor, product, name) in enumerate(pads, 1):
        prefix = f"player_{i}_"
        has_slot = f"{prefix}connected=true" in t or any(
            line.startswith(prefix) for line in t.splitlines() if "button_a" in line
        )
        if has_slot:
            old_guid = None
            for line in t.splitlines():
                if line.startswith(prefix):
                    m = GUID_RE.search(line)
                    if m:
                        old_guid = m.group(1)
                        break
            if not old_guid:
                continue
            new_guid = swap_vidpid(old_guid, vendor, product)
            out, n = [], 0
            for line in t.splitlines(keepends=True):
                if line.startswith(prefix) and old_guid in line:
                    line = line.replace(old_guid, new_guid)
                    n += 1
                out.append(line)
            t = "".join(out)
            if n:
                changed_slots.append(f"Player {i} retargeted ({n} keys)")
        else:
            # Clone Player 1's keys wholesale under this new prefix.
            p1_guid = None
            cloned_lines = []
            for line in t.splitlines(keepends=True):
                if line.startswith("player_1_"):
                    if p1_guid is None:
                        m = GUID_RE.search(line)
                        if m:
                            p1_guid = m.group(1)
                    cloned_lines.append(line.replace("player_1_", prefix, 1))
            if not p1_guid:
                continue
            new_guid = swap_vidpid(p1_guid, vendor, product)
            cloned = "".join(cloned_lines).replace(p1_guid, new_guid)
            cloned = re.sub(r"port:\d+", f"port:{next_port}", cloned)
            cloned = cloned.replace(f"{prefix}connected=false", f"{prefix}connected=true")
            t = t.rstrip("\n") + "\n" + cloned
            next_port += 1
            changed_slots.append(f"Player {i} created (new slot, port {next_port - 1})")
    if changed_slots:
        backup(p); p.write_text(t)
        print("citron   : " + "; ".join(changed_slots))
    else:
        print("citron   : SKIP — no Player 1 SDL binding to clone from")


# ── azahar (3DS) / mgba (GBA) — single-player hardware, Player 1 only ───────
def do_single_player_guid(path_str, name_label, line_prefix, pads):
    p = Path(path_str)
    if not p.is_file():
        print(f"{name_label:9}: SKIP — not configured on this box")
        return
    vendor, product, target = pads[0]
    t = p.read_text()
    old_guid = None
    for line in t.splitlines():
        if line.startswith(line_prefix):
            m = GUID_RE.search(line)
            if m:
                old_guid = m.group(1)
                break
    if not old_guid:
        print(f"{name_label:9}: SKIP — no Player 1 SDL binding found")
        return
    new_guid = swap_vidpid(old_guid, vendor, product)
    out, n = [], 0
    for line in t.splitlines(keepends=True):
        if line.startswith(line_prefix) and old_guid in line:
            out.append(line.replace(old_guid, new_guid))
            n += 1
        else:
            out.append(line)
    if n:
        backup(p); p.write_text("".join(out))
        print(f"{name_label:9}: Player 1 retargeted ({n} keys) — single-player hardware")
    else:
        print(f"{name_label:9}: SKIP — no Player 1 SDL binding found")


def do_mgba(pads):
    p = Path(mgba_config)
    if not p.is_file():
        print("mgba     : SKIP — not configured on this box")
        return
    vendor, product, target = pads[0]
    t = p.read_text()
    m = re.search(r"^device0=([0-9a-fA-F]{32})$", t, re.M)
    if not m:
        print("mgba     : SKIP — no active SDL device binding found")
        return
    old_guid = m.group(1)
    new_guid = swap_vidpid(old_guid, vendor, product)
    backup(p)
    t = re.sub(r"^device0=[0-9a-fA-F]{32}$", f"device0={new_guid}", t, flags=re.M)
    sec = re.search(rf"^\[gba\.input-profile\.{old_guid}\]\n(.*?)(?=^\[|\Z)", t, re.S | re.M)
    if sec and f"[gba.input-profile.{new_guid}]" not in t:
        t += f"\n[gba.input-profile.{new_guid}]\n{sec.group(1)}"
    p.write_text(t)
    print("mgba     : Player 1 retargeted (active slot + saved profile) — single-player hardware")


# ── Cemu (Wii U, up to 4 Pro Controllers via controllerN.xml, 0-indexed) ────
def do_cemu(pads):
    if not os.path.isdir(cemu_profiles):
        print("cemu     : SKIP — no controller profile found")
        return
    slot0 = Path(cemu_profiles) / "controller0.xml"
    if not slot0.is_file():
        print("cemu     : SKIP — no controller profile found")
        return
    template = slot0.read_text()
    m = re.search(r"<uuid>(\d+)_([0-9a-fA-F]{32})</uuid>", template)
    if not m:
        print("cemu     : SKIP — controller0.xml has no SDL uuid")
        return
    results = []
    for i, (vendor, product, name) in enumerate(pads):
        f = Path(cemu_profiles) / f"controller{i}.xml"
        new_guid = swap_vidpid(m.group(2), vendor, product)
        if f.is_file():
            t = f.read_text()
            fm = re.search(r"<uuid>(\d+)_([0-9a-fA-F]{32})</uuid>", t)
            if not fm:
                continue
            backup(f)
            # Force the slot prefix to match the filename's own index too —
            # Dolphin had exactly this kind of stale-slot-index bug (GCPad2
            # silently pointed at slot 0), so don't just trust what's there.
            t = t.replace(f"<uuid>{fm.group(1)}_{fm.group(2)}</uuid>",
                          f"<uuid>{i}_{new_guid}</uuid>")
            t = re.sub(r"<display_name>[^<]*</display_name>",
                       f"<display_name>{name}</display_name>", t, count=1)
            f.write_text(t)
            results.append(f"slot {i} retargeted")
        else:
            t = template.replace(f"<uuid>{m.group(1)}_{m.group(2)}</uuid>",
                                 f"<uuid>{i}_{new_guid}</uuid>")
            t = re.sub(r"<display_name>[^<]*</display_name>",
                       f"<display_name>{name}</display_name>", t, count=1)
            f.write_text(t)
            results.append(f"slot {i} created")
    print("cemu     : " + ("; ".join(results) if results else "SKIP — nothing to do"))


# ── Dolphin (GameCube/Wii, GCPad1-4) — roles are semantic, name only ────────
def do_dolphin(pads):
    gcpad = Path(dolphin_dir) / "GCPadNew.ini"
    if not gcpad.is_file():
        print("dolphin  : SKIP — not configured on this box")
        return
    t = gcpad.read_text()
    p1 = section(t, "GCPad1")
    if not p1 or "Device = SDL/" not in p1:
        print("dolphin  : SKIP — no SDL GCPad1 mapping")
        return
    results = []
    for i, (vendor, product, name) in enumerate(pads, 1):
        header = f"GCPad{i}"
        body = section(t, header)
        # A real SDL binding uses semantic tokens like `Button S` — a
        # keyboard stub (or Dolphin's own unmapped default) doesn't.
        is_real = bool(body) and re.search(r"Device = SDL/\d+/", body) and \
            re.search(r"Buttons/A = `Button [SNEW]`", body)
        # Always rewrite index AND name together — a stale index here means
        # Player N silently reads Player 1's physical pad instead of its own
        # (found live on this box: GCPad2 said "SDL/0/", not "SDL/1/").
        source = body if is_real else p1
        new_body = re.sub(r"Device = SDL/\d+/[^\n]*", f"Device = SDL/{i - 1}/{name}", source)
        if new_body != body:
            t = set_section(t, header, new_body)
            results.append(f"GCPad{i} {'retargeted' if is_real else 'created'}")
    if results:
        backup(gcpad); gcpad.write_text(t)
        print("dolphin  : " + "; ".join(results) + " (button roles untouched)")
    else:
        print("dolphin  : SKIP — nothing to do")


# ── RPCS3 (PS3, Player 1-4 already exist) — roles semantic, name only ───────
def do_rpcs3(pads):
    p = Path(rpcs3_default)
    if not p.is_file():
        print("rpcs3    : SKIP — not configured on this box")
        return
    t = p.read_text()
    results, already_ok, no_slot = [], [], []
    for i, (vendor, product, name) in enumerate(pads, 1):
        m = re.search(rf"^Player {i} Input:\n(.*?)(?=^Player \d+ Input:|\Z)", t, re.S | re.M)
        if not m or "Handler: SDL" not in m.group(1):
            no_slot.append(f"Player {i}")
            continue
        block = m.group(1)
        block2 = re.sub(r"^(  Device: ).*$", rf"\g<1>{name} {i}", block, count=1, flags=re.M)
        if block2 != block:
            t = t[:m.start(1)] + block2 + t[m.end(1):]
            results.append(f"Player {i}")
        else:
            already_ok.append(f"Player {i}")
    if results:
        backup(p); p.write_text(t)
    msg = []
    if results:    msg.append("retargeted " + ", ".join(results))
    if already_ok: msg.append("already correct: " + ", ".join(already_ok))
    if no_slot:    msg.append("SKIP (no SDL slot): " + ", ".join(no_slot))
    print("rpcs3    : " + "; ".join(msg) + " (button roles untouched)" if msg else "rpcs3    : SKIP")


# ── PCSX2 / DuckStation — Tier 0, only the SDL INDEX needs to exist ─────────
def do_tier0_ini(path_str, name_label, pads):
    p = Path(path_str)
    if not p.is_file():
        print(f"{name_label:9}: SKIP — not configured on this box")
        return
    t = p.read_text()
    p1 = section(t, "Pad1")
    if not p1 or "SDL-0/" not in p1:
        print(f"{name_label:9}: SKIP — no SDL Pad1 mapping")
        return
    created = []
    for i in range(2, len(pads) + 1):
        header = f"Pad{i}"
        body = section(t, header)
        if body and "SDL-" in body and "Type = None" not in body:
            continue  # already a real binding — device-agnostic, nothing to do ever
        new_body = p1.replace("SDL-0/", f"SDL-{i - 1}/")
        t = set_section(t, header, new_body)
        created.append(header)
    if created:
        backup(p); p.write_text(t)
        print(f"{name_label:9}: created " + ", ".join(created) +
             " (device-agnostic — any controller in that USB/BT slot works forever)")
    else:
        print(f"{name_label:9}: OK — binds by SDL role name only, all slots already present")


do_citron(pads)
do_single_player_guid(azahar, "azahar", "profiles\\1\\", pads)
do_mgba(pads)
do_cemu(pads)
do_dolphin(pads)
do_rpcs3(pads)
do_tier0_ini(pcsx2, "pcsx2", pads)
do_tier0_ini(duck, "duckstation", pads)
print("gopher64 : OK — fully automatic, any connected controller auto-assigned (no config needed)")

print("\nDone. Physically confirm in each emulator's controller settings —")
print("RPCS3/Dolphin's Device dropdown should show the right pad per player.")
PYEOF
