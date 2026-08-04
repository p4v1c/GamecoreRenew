#!/usr/bin/env bash
# ================================================================
#  revert-migration.sh — put the box back exactly as it was
#
#      bash scripts/revert-migration.sh --list          what can be restored
#      bash scripts/revert-migration.sh <TIMESTAMP>     restore that snapshot
#      bash scripts/revert-migration.sh <TS> --dry-run  say what it would do
#
#  Written and tested BEFORE the migration, not after. A revert path that has
#  never been exercised is a hope, not a plan.
#
#  What it restores:
#    /opt/GameCore              the whole install
#    ~/.var/app                 every Flatpak emulator's config and save data
#    ~/.config/{rpcs3,mgba,melonDS}, ~/.local/share/duckstation
#
#  How: the live directory is MOVED aside (never deleted), then the backup is
#  moved into place. So a failed revert leaves both copies on disk and nothing
#  is lost — the cost is a rename, not a 350 GB copy.
#
#  The displaced live tree is kept as <path>.replaced-<TS>. Delete it yourself
#  once you are satisfied; this script never removes data.
# ================================================================
set -uo pipefail

RED='\033[1;31m'; GRN='\033[1;32m'; YLW='\033[1;33m'; RST='\033[0m'
ok()   { echo -e "  ${GRN}✓${RST} $*"; }
warn() { echo -e "  ${YLW}⚠${RST} $*"; }
die()  { echo -e "${RED}[revert] $*${RST}" >&2; exit 1; }

GAMECORE_PATH="${GAMECORE_PATH:-/opt/GameCore}"
TARGETS=(
  "$GAMECORE_PATH"
  "$HOME/.var/app"
  "$HOME/.config/rpcs3"
  "$HOME/.config/mgba"
  "$HOME/.config/melonDS"
  "$HOME/.local/share/duckstation"
)

if [[ "${1:-}" == "--list" || $# -eq 0 ]]; then
  echo "Snapshots available:"
  found=0
  for t in "${TARGETS[@]}"; do
    for b in "$t".bak-*; do
      [[ -e "$b" ]] || continue
      found=1
      printf "  %-14s %s\n" "${b##*.bak-}" "$b"
    done
  done
  [[ $found -eq 1 ]] || echo "  (none)"
  echo
  echo "Restore with:  bash $0 <TIMESTAMP>"
  exit 0
fi

TS="$1"
DRY=false
[[ "${2:-}" == "--dry-run" ]] && DRY=true
NOW=$(date +%Y%m%d-%H%M%S)

# Refuse a partial revert. Restoring /opt without ~/.var/app would leave the
# emulator configs written by the new controller pipeline in place — a state
# the box was never in, and the hardest kind to debug.
missing=()
for t in "${TARGETS[@]}"; do
  [[ -e "${t}.bak-${TS}" || ! -e "$t" ]] || missing+=("${t}.bak-${TS}")
done
if [[ ${#missing[@]} -gt 0 ]]; then
  echo -e "${RED}[revert] snapshot $TS is incomplete:${RST}" >&2
  printf '  missing %s\n' "${missing[@]}" >&2
  die "refusing a partial revert — run --list to see what exists"
fi

echo "Reverting to snapshot $TS"
$DRY && echo -e "${YLW}  (dry run — nothing will be moved)${RST}"
echo

# Services first: restoring files under a running backend leaves it holding
# deleted inodes and writing to a tree that no longer exists.
if ! $DRY; then
  sudo -n systemctl stop gamecore-ui gamecore-backend 2>/dev/null \
    && ok "services stopped" \
    || warn "could not stop the services (no sudo?) — restart them yourself afterwards"
fi

for t in "${TARGETS[@]}"; do
  b="${t}.bak-${TS}"
  [[ -e "$b" ]] || { warn "$t — no snapshot, left alone"; continue; }
  if $DRY; then
    echo "  would move $t -> ${t}.replaced-${NOW}"
    echo "  would move $b -> $t"
    continue
  fi
  if [[ -e "$t" ]]; then
    mv "$t" "${t}.replaced-${NOW}" || die "could not move $t aside — nothing changed for it"
  fi
  mv "$b" "$t" || {
    # Put the live tree back rather than leave the path empty.
    [[ -e "${t}.replaced-${NOW}" ]] && mv "${t}.replaced-${NOW}" "$t"
    die "could not restore $b — $t was put back"
  }
  ok "$t restored (previous kept as ${t}.replaced-${NOW})"
done

if ! $DRY; then
  echo
  sudo -n systemctl start gamecore-backend 2>/dev/null \
    && ok "gamecore-backend started" \
    || warn "start gamecore-backend yourself: sudo systemctl start gamecore-backend"
  sleep 3
  port=$(grep -oP 'GAMECORE_BACKEND_PORT=\K[0-9]+' \
         /etc/systemd/system/gamecore-backend.service 2>/dev/null || echo 8765)
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 \
         "http://127.0.0.1:${port}/api/sysinfo" 2>/dev/null)
  [[ "$code" == 200 ]] && ok "API answers on $port" || warn "API on $port answered '$code'"
  echo "  VERSION: $(cat "$GAMECORE_PATH/VERSION" 2>/dev/null)"
  echo
  echo "  The trees that were in place are kept as *.replaced-${NOW}."
  echo "  Nothing was deleted. Remove them yourself when you are satisfied."
fi
