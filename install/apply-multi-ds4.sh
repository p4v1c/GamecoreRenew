#!/usr/bin/env bash
# ================================================================
#  GameCore — Pre-configure players 2-4 as DualShock 4 in the LIVE
#  emulator configs (citron-neo, Dolphin, PCSX2, DuckStation).
#
#  Fresh installs get this from emu-configs/ automatically; this script
#  retrofits an already-installed box surgically: it only touches the
#  pad sections, everything else (your settings, game dirs, creds…)
#  is preserved. Backups: <file>.bak-multids4. Idempotent.
#
#  Run as the gaming user:  bash install/apply-multi-ds4.sh
# ================================================================
set -euo pipefail

[[ $EUID -ne 0 ]] || { echo "Run me as the gaming user, not root."; exit 1; }

PY="$(command -v python3)"

CITRON_NEO="$HOME/.config/citron/qt-config.ini"   # citron-neo keeps the citron dir name
DOLPHIN_DIR="$HOME/.var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu"
PCSX2="$HOME/.var/app/net.pcsx2.PCSX2/config/PCSX2/inis/PCSX2.ini"
DUCK="$HOME/.local/share/duckstation/settings.ini"

backup() { [[ -f "$1" && ! -f "$1.bak-multids4" ]] && cp "$1" "$1.bak-multids4" || true; }

"$PY" - "$CITRON_NEO" "$DOLPHIN_DIR" "$PCSX2" "$DUCK" <<'EOF'
import json, re, shutil, sys
from pathlib import Path

citron_neo, dolphin_dir, pcsx2, duck = (Path(p) for p in sys.argv[1:5])

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

# ── citron-neo: clone the live player_0 (Player 1) into players 2-4 ──────────
# Sections are 0-based (player_0_* IS Player 1). Identical DS4 pads keep the
# same GUID — citron-neo tells them apart by `port:` (its per-GUID counter).
if citron_neo.is_file():
    t = citron_neo.read_text()
    lines = t.splitlines(keepends=True)
    p0 = [l for l in lines if l.startswith("player_0_")]
    if p0:
        backup(citron_neo)
        for n in (2, 3, 4):
            pref = f"player_{n-1}_"
            clone = "".join(
                re.sub(r"port:\d+", f"port:{n-1}", l.replace("player_0_", pref, 1))
                for l in p0
            ).replace(f"{pref}connected=false", f"{pref}connected=true")
            lines = [l for l in lines if not l.startswith(pref)]
            last = max(i for i, l in enumerate(lines) if l.startswith("player_0_"))
            if not lines[last].endswith("\n"):
                lines[last] += "\n"
            lines.insert(last + 1, clone)
        citron_neo.write_text("".join(lines))
        print("citron-neo: players 2-4 configured (from your live Player 1 mapping)")
    else:
        print("citron-neo: SKIP — no player_0 mapping found")
else:
    print("citron-neo: SKIP — qt-config.ini not found")

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
            if body and "Buttons/A" in body:  # mapped — just point it at pad n
                body = re.sub(r"Device = SDL/\d+/", f"Device = SDL/{n-1}/", body)
                if "Device = SDL/" not in body:
                    body = p1.replace("Device = SDL/0/", f"Device = SDL/{n-1}/")
            else:  # stub (mouse/empty) — full copy of GCPad1
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
