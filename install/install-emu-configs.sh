#!/usr/bin/env bash
# ================================================================
#  GameCore — Deploy curated emulator configs (emu-configs/)
#  Run as the gaming user (NOT root):  bash install/install-emu-configs.sh
#
#  Copies each emu-configs/<emulator>/ tree into the emulator's real
#  config location — Flatpak app dirs for everything except DuckStation
#  and citron-neo (installed as AppImages → native XDG paths). Existing
#  files are
#  backed up as <name>.bak-preinstall. Absolute paths inside the configs
#  (harvested on a box where HOME was /home/pavic) are rewritten to the
#  current user's HOME.
# ================================================================
set -euo pipefail

[[ $EUID -ne 0 ]] || { echo "Run me as the gaming user, not root."; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_ROOT="$(dirname "$SCRIPT_DIR")/emu-configs"
SRC_HOME="/home/pavic"   # HOME on the box the configs were harvested from
GAMECORE_PATH="${GAMECORE_PATH:-/opt/GameCore}"

[[ -d "$SRC_ROOT" ]] || { echo "emu-configs/ not found next to install/ — nothing to do."; exit 1; }

GRN='\033[1;32m'; YLW='\033[1;33m'; RST='\033[0m'
ok()   { echo -e "  ${GRN}✓${RST} $*"; }
skip() { echo -e "  ${YLW}·${RST} $*"; }

# emulator-id → destination directory
declare -A DEST=(
  [duckstation]="$HOME/.local/share/duckstation"
  [pcsx2]="$HOME/.var/app/net.pcsx2.PCSX2/config/PCSX2/inis"
  [rpcs3]="$HOME/.var/app/net.rpcs3.RPCS3/config/rpcs3"
  [gopher64]="$HOME/.var/app/io.github.gopher64.gopher64/config/gopher64"
  [melonds]="$HOME/.var/app/net.kuribo64.melonDS/config/melonDS"
  [mgba]="$HOME/.var/app/io.mgba.mGBA/config/mgba"
  [azahar]="$HOME/.var/app/org.azahar_emu.Azahar/config/azahar-emu"
  [dolphin]="$HOME/.var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu"
  [ppsspp]="$HOME/.var/app/org.ppsspp.PPSSPP/config/ppsspp/PSP/SYSTEM"
  [cemu]="$HOME/.var/app/info.cemu.Cemu/config/Cemu"
  [citron-neo]="$HOME/.config/citron"   # citron-neo keeps the citron dir name
  [shadps4]="$HOME/.var/app/net.shadps4.shadPS4/config/shadps4"
  [xenia]="$GAMECORE_PATH/lib/xenia"   # portable: config lives next to xenia_canary.exe
)

echo "Deploying emulator configs from ${SRC_ROOT}"
echo

for emu in "${!DEST[@]}"; do
  src="${SRC_ROOT}/${emu}"
  dest="${DEST[$emu]}"

  if [[ ! -d "$src" ]]; then
    skip "$emu — no config bundled, skipped."
    continue
  fi

  mkdir -p "$dest"

  # Copy file by file, preserving sub-tree, backing up what exists.
  while IFS= read -r -d '' f; do
    rel="${f#"$src"/}"
    tgt="${dest}/${rel}"
    mkdir -p "$(dirname "$tgt")"
    [[ -f "$tgt" ]] && cp "$tgt" "${tgt}.bak-preinstall"
    cp "$f" "$tgt"
    # Rewrite the harvest box's HOME to this user's HOME (text configs only).
    if [[ "$HOME" != "$SRC_HOME" ]] && grep -qI "$SRC_HOME" "$tgt" 2>/dev/null; then
      sed -i "s|${SRC_HOME}|${HOME}|g" "$tgt"
    fi
  done < <(find "$src" -type f -print0)

  ok "$emu → $dest"
done

echo
echo "Done. Overwritten files were saved as *.bak-preinstall."
