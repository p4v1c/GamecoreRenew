#!/usr/bin/env bash
# ================================================================
#  GameCore — Adapt config/systems.json to a Flatpak-only machine
#
#  The reference box launches some emulators from native binaries in
#  lib/ (kept out of git — too big, machine-specific). On a fresh
#  install those don't exist: every system whose configured launcher is
#  missing is rewritten to its Flatpak equivalent (DuckStation to the
#  AppImage the installer downloads). Systems whose launcher exists are
#  left untouched, so re-running on the reference box is a no-op.
#
#  Usage:  bash install/flatpakify-systems.sh [GAMECORE_PATH]
# ================================================================
set -euo pipefail

GAMECORE_PATH="${1:-${GAMECORE_PATH:-/opt/GameCore}}"

python3 - "$GAMECORE_PATH" <<'EOF'
import json, os, shutil, sys

root = sys.argv[1]
path = os.path.join(root, "config", "systems.json")
systems = json.load(open(path))

# system id → (path, args) on a Flatpak-only machine
FLATPAK_MAP = {
    "citron":      ("flatpak", "run io.github.ryubing.Ryujinx"),          # Switch via Ryujinx
    "duckstation": ("bin/duckstation.AppImage", "-fullscreen"),
    "pcsx2":       ("flatpak", "run net.pcsx2.PCSX2 -fullscreen"),
    "rpcs3":       ("flatpak", "run net.rpcs3.RPCS3 --fullscreen --no-gui"),
    "gopher64":    ("flatpak", "run io.github.gopher64.gopher64 -f"),
    "melonds":     ("flatpak", "run net.kuribo64.melonDS -f"),
    "mgba":        ("flatpak", "run io.mgba.mGBA --fullscreen"),
}

def launcher_exists(p: str) -> bool:
    if not p or p == "flatpak":
        return True                      # already flatpak — nothing to adapt
    if os.path.isabs(p):
        return os.path.exists(p)
    if "/" in p:                         # relative to the install dir only
        return os.path.exists(os.path.join(root, p))
    return shutil.which(p) is not None   # bare command → PATH lookup

changed = []
for s in systems:
    sid = s.get("id", "")
    if sid in FLATPAK_MAP and not launcher_exists(s.get("path", "")):
        s["path"], s["args"] = FLATPAK_MAP[sid]
        changed.append(sid)

if changed:
    json.dump(systems, open(path, "w"), indent=2, ensure_ascii=False)
    print(f"[flatpakify] rewritten to Flatpak launchers: {', '.join(changed)}")
else:
    print("[flatpakify] all configured launchers exist — nothing to change.")
EOF
