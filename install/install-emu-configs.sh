#!/usr/bin/env bash
# ================================================================
#  GameCore — Deploy curated emulator configs (emu-configs/)
#  Run as the gaming user (NOT root):  bash install/install-emu-configs.sh
#
#  Copies each emu-configs/<emulator>/ tree into the emulator's real
#  config location — Flatpak app dirs for everything except DuckStation
#  (installed as an AppImage → native XDG path). Existing files are
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
  [ryujinx]="$HOME/.var/app/io.github.ryubing.Ryujinx/config/Ryujinx"
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

  # A run interrupted mid-copy leaves *.gamecore-staged behind; they would be
  # mistaken for emulator config files by anything that scans the directory.
  find "$dest" -name '*.gamecore-staged' -delete 2>/dev/null || true

  # Copy file by file, preserving sub-tree, backing up what was there first.
  #
  # The file is prepared in full (including the HOME rewrite) BEFORE anything
  # is compared or copied, so the backup decision can be made against the exact
  # bytes that are about to land. That is what makes a re-run safe:
  #
  #   · target absent            → no backup, we are introducing the file
  #   · target == what we install → no backup, it is already our own copy
  #                                 (this is the re-run case; backing it up
  #                                 would record GameCore's config as if it
  #                                 were the user's, and uninstall would then
  #                                 "restore" our file instead of deleting it)
  #   · target differs, no backup yet → back it up, it is theirs
  #   · a backup already exists  → never touch it, it holds the real original
  while IFS= read -r -d '' f; do
    rel="${f#"$src"/}"
    tgt="${dest}/${rel}"
    mkdir -p "$(dirname "$tgt")"

    staged="${tgt}.gamecore-staged"
    cp "$f" "$staged"
    # Rewrite the harvest box's HOME to this user's HOME (text configs only).
    if [[ "$HOME" != "$SRC_HOME" ]] && grep -qI "$SRC_HOME" "$staged" 2>/dev/null; then
      sed -i "s|${SRC_HOME}|${HOME}|g" "$staged"
    fi

    if [[ -f "$tgt" && ! -e "${tgt}.bak-preinstall" ]] && ! cmp -s "$staged" "$tgt"; then
      cp "$tgt" "${tgt}.bak-preinstall"
    fi
    mv -f "$staged" "$tgt"
  done < <(find "$src" -type f -print0)

  ok "$emu → $dest"
done

echo
echo "Done. Overwritten files were saved as *.bak-preinstall."
