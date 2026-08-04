#!/usr/bin/env bash
# ================================================================
#  GameCore — Pre-configure players 2-4 as DualShock 4 in the LIVE
#  emulator configs (Ryujinx, Dolphin, PCSX2, DuckStation).
#
#  Fresh installs get this from catalog/<id>/seed/ automatically; this script
#  retrofits an already-installed box surgically: it only touches the
#  pad sections, everything else (your settings, game dirs, creds…)
#  is preserved. Backups: <file>.bak-multids4. Idempotent.
#
#  Run as the gaming user:  bash install/apply-multi-ds4.sh
# ================================================================
set -euo pipefail

[[ $EUID -ne 0 ]] || { echo "Run me as the gaming user, not root."; exit 1; }

PY="$(command -v python3)"

RYUJINX="$HOME/.var/app/io.github.ryubing.Ryujinx/config/Ryujinx/Config.json"
DOLPHIN_DIR="$HOME/.var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu"
PCSX2="$HOME/.var/app/net.pcsx2.PCSX2/config/PCSX2/inis/PCSX2.ini"
DUCK="$HOME/.local/share/duckstation/settings.ini"

backup() { [[ -f "$1" && ! -f "$1.bak-multids4" ]] && cp "$1" "$1.bak-multids4" || true; }

"$PY" - "$RYUJINX" "$DOLPHIN_DIR" "$PCSX2" "$DUCK" <<'EOF'
import json, re, shutil, sys
from pathlib import Path

ryujinx, dolphin_dir, pcsx2, duck = (Path(p) for p in sys.argv[1:5])

def backup(p: Path):
    b = p.with_name(p.name + ".bak-multids4")
    if p.is_file() and not b.exists():
        shutil.copy2(p, b)

def section(text, header):
    m = re.search(rf"^\[{re.escape(header)}\]\n(.*?)(?=^\[|\Z)", text, re.S | re.M)
    return m.group(1) if m else None

def set_section(text, header, body):
    pat = rf"^\[{re.escape(header)}\]\n.*?(?=^\[|\Z)"
    if re.search(pat, text, re.S | re.M):
        return re.sub(pat, f"[{header}]\n{body}", text, count=1, flags=re.S | re.M)
    return text.rstrip() + f"\n\n[{header}]\n{body}"

# ── Ryujinx: clone the live Player1 entry into Player2-4 ─────────────────────
if ryujinx.is_file():
    cfg = json.loads(ryujinx.read_text())
    ic = cfg.get("input_config") or []
    p1 = next((e for e in ic if e.get("player_index") == "Player1"), None)
    if p1 and "-" in str(p1.get("id", "")):
        backup(ryujinx)
        guid = p1["id"].split("-", 1)[1]
        keep = [e for e in ic if e.get("player_index") not in ("Player2", "Player3", "Player4")]
        for n in (2, 3, 4):
            e = json.loads(json.dumps(p1))
            e["id"] = f"{n-1}-{guid}"
            e["name"] = f"PS4 Controller ({n-1})"
            e["player_index"] = f"Player{n}"
            keep.append(e)
        cfg["input_config"] = keep
        ryujinx.write_text(json.dumps(cfg, indent=2) + "\n")
        print("ryujinx  : Player2-4 configured (from your live Player1 mapping)")
    else:
        print("ryujinx  : SKIP — no Player1 gamepad entry found")
else:
    print("ryujinx  : SKIP — Config.json not found")

# ── PCSX2 / DuckStation: Pad2 = Pad1 mapping on SDL-1 ────────────────────────
for path, name in ((pcsx2, "pcsx2"), (duck, "duckstation")):
    if not path.is_file():
        print(f"{name:9}: SKIP — ini not found")
        continue
    t = path.read_text()
    pad1 = section(t, "Pad1")
    if not pad1 or "SDL-0/" not in pad1:
        print(f"{name:9}: SKIP — no SDL Pad1 mapping")
        continue
    backup(path)
    path.write_text(set_section(t, "Pad2", pad1.replace("SDL-0/", "SDL-1/")))
    print(f"{name:9}: Pad2 configured (SDL-1)")

# ── Dolphin: GCPad2-4 on SDL/1-3, all four GC ports plugged ──────────────────
gcpad = dolphin_dir / "GCPadNew.ini"
if gcpad.is_file():
    t = gcpad.read_text()
    p1 = section(t, "GCPad1")
    if p1 and "Device = SDL/0/" in p1:
        backup(gcpad)
        for n in (2, 3, 4):
            body = section(t, f"GCPad{n}")
            # "has a Buttons/A line" was not enough to call a section mapped:
            # GCPad3/4 shipped with the D-Pad on `T`/`G`/`F`/`H` and Z on `D`,
            # keyboard keys from the box these configs were captured on. They
            # passed, so only the Device line was rewritten and players 3 and 4
            # ended up with a dead D-Pad. A bare single key between backticks is
            # the tell; `Pad N` and `Back` are roles and stay untouched, so a
            # deliberate remap is not overwritten.
            keyboard_leftover = body and re.search(
                r"(?:D-Pad/(?:Up|Down|Left|Right)|Buttons/Z) = `[^`]`", body)
            if body and "Buttons/A" in body and not keyboard_leftover:
                # mapped — just point it at pad n
                body = re.sub(r"Device = SDL/\d+/", f"Device = SDL/{n-1}/", body)
                if "Device = SDL/" not in body:
                    body = p1.replace("Device = SDL/0/", f"Device = SDL/{n-1}/")
            else:  # stub, or keyboard leftovers — full copy of GCPad1
                body = p1.replace("Device = SDL/0/", f"Device = SDL/{n-1}/")
            t = set_section(t, f"GCPad{n}", body)
        gcpad.write_text(t)
        print("dolphin  : GCPad2-4 configured (SDL/1-3)")
    else:
        print("dolphin  : SKIP — no SDL GCPad1 mapping")
else:
    print("dolphin  : SKIP — GCPadNew.ini not found")

dini = dolphin_dir / "Dolphin.ini"
if dini.is_file():
    t = dini.read_text()
    t2 = re.sub(r"^(SIDevice[123]) = 0$", r"\1 = 6", t, flags=re.M)
    if t2 != t:
        backup(dini)
        dini.write_text(t2)
    print("dolphin  : SIDevice1-3 = 6 (4 GC ports plugged)")
EOF

echo "Done. Connect up to 4 DS4 pads — join order = player order."
