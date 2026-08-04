#!/usr/bin/env bash
# ================================================================
#  GameCore — Deploy curated emulator configs (catalog/<id>/seed/)
#  Run as the gaming user (NOT root):  bash install/install-emu-configs.sh
#
#  Copies each catalog/<emulator>/seed/ tree into the emulator's real
#  config location — Flatpak app dirs for everything except DuckStation
#  (installed as an AppImage → native XDG path). Existing files are
#  backed up as <name>.bak-preinstall.
#
#  The seeds used to live in emu-configs/<emulator>/ and carried a literal
#  /home/pavic, harvested from the box they were taken on and rewritten here
#  by a sed pass. They now carry an @HOME@ token instead, so a personal
#  username no longer ships in a public repository and the substitution is
#  explicit rather than a search-and-replace that could hit anything.
# ================================================================
set -euo pipefail

[[ $EUID -ne 0 ]] || { echo "Run me as the gaming user, not root."; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CATALOG_ROOT="$(dirname "$SCRIPT_DIR")/catalog"
GAMECORE_PATH="${GAMECORE_PATH:-/opt/GameCore}"

[[ -d "$CATALOG_ROOT" ]] || { echo "catalog/ not found next to install/ — nothing to do."; exit 1; }

GRN='\033[1;32m'; YLW='\033[1;33m'; RST='\033[0m'
ok()   { echo -e "  ${GRN}✓${RST} $*"; }
skip() { echo -e "  ${YLW}·${RST} $*"; }

# emulator-id → destination directory, FROM THE CATALOGUE.
#
# This map used to be written out by hand here, and copied again into
# uninstall.sh. That is what let the N64 slot rot: the migration from gopher64
# to Rosalie's Mupen GUI updated arch.sh and systems.json but not this file, so
# the curated config was deployed to
# ~/.var/app/io.github.gopher64.gopher64/config/gopher64 — a directory the
# `mkdir -p` below CREATED — while RMG read
# ~/.var/app/com.github.Rosalie241.RMG/config/RMG/ and never saw it. A green
# tick, no error, and the config silently never applied.
#
# catalog-query.py resolves @FLATPAK_CONFIG@ from the SAME install.appId the
# installer installs, so the two cannot drift apart again.
#
# Third column: the native destination, for the emulators a box can run outside
# Flatpak (mgba, melonds). Deploy to the tree that EXISTS, or the curated config
# lands next to an uninstalled flatpak and nothing ever reads it.
declare -A DEST=()
while IFS=$'\t' read -r emu dest native; do
  [[ -n "$emu" ]] || continue
  if [[ -n "$native" && ! -d "${dest%/*/*}" && -d "$native" ]]; then
    DEST[$emu]="$native"
  else
    DEST[$emu]="$dest"
  fi
done < <(python3 "$(dirname "$SCRIPT_DIR")/scripts/catalog-query.py" config-dest \
           --home "$HOME" --gamecore-path "$GAMECORE_PATH")

[[ ${#DEST[@]} -gt 0 ]] || { echo "catalog: no pack declares a config destination."; exit 1; }

echo "Deploying emulator configs from ${CATALOG_ROOT}/<id>/seed"
echo

for emu in "${!DEST[@]}"; do
  src="${CATALOG_ROOT}/${emu}/seed"
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
    # Substitute the seed tokens (text configs only). @HOME@ replaces the
    # literal /home/pavic two independent sed passes used to chase.
    if grep -qI '@HOME@\|@GAMECORE_PATH@' "$staged" 2>/dev/null; then
      sed -i -e "s|@HOME@|${HOME}|g" -e "s|@GAMECORE_PATH@|${GAMECORE_PATH}|g" "$staged"
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
