#!/usr/bin/env bash
# Build the offline LaunchBox index, so a fresh box has a metadata source at all.
#
#     build-media-index.sh <GAMECORE_PATH> <USER_NAME>
#
# Why this exists
# ---------------
# GameCore has two metadata tiers. ScreenScraper matches by file hash and is
# exact, but it needs DEVELOPER credentials granted on request on their forum —
# most boxes have none. LaunchBox needs no account at all and works offline once
# indexed: 185 000 games, 92 % hit rate measured over 1950 ROMs.
#
# Nothing built it. The installer never mentioned gamescrape, and the backend
# deliberately refuses to build it itself (106 MB of download from inside an
# HTTP handler would block the request for minutes). So the tier only ever
# existed if a human ran `--refresh` by hand — and until the fix that ships
# alongside this file, doing that put the index in ~/.cache/gamescrape, where
# the backend never looks.
#
# The result, found on the reference box: `status()` reporting
# `launchbox_index: false` with 234 MB of index sitting on disk two directories
# away, and every lookup falling through to a ScreenScraper account most
# installs do not have. A box with neither tier shows no title, no synopsis and
# no cover, and nothing anywhere says why.
#
# Never fatal
# -----------
# A failure here costs metadata, not the install. arch.sh warns and carries on
# for a dozen recoverable failures and reports them in its closing summary,
# because a missing description is a degraded box while an aborted installer at
# 80 % is a machine that is neither installed nor clean. This script therefore
# always exits 0, and says what went wrong.
#
# Skipping it
# -----------
#   GAMECORE_SKIP_MEDIA_INDEX=1   never build it
#   --minimal                     arch.sh does not call this at all
#
# Either way the box works; it just resolves media online, or not at all.
# Building it later is one command, printed below when it is skipped.
set -uo pipefail

GC_PATH="${1:?usage: build-media-index.sh <GAMECORE_PATH> <USER_NAME>}"
GC_USER="${2:?usage: build-media-index.sh <GAMECORE_PATH> <USER_NAME>}"
# The 234 MB index is a cache the player accumulates, so it follows the data
# root. Defaults to the install, where every box built before the split has it.
GC_DATA="${GAMECORE_DATA:-$GC_PATH}"

YLW='\033[1;33m'; GRN='\033[1;32m'; RST='\033[0m'
ok()   { echo -e "  ${GRN}✓${RST} $*"; }
warn() { echo -e "  ${YLW}⚠  $*${RST}"; }
info() { echo -e "  $*"; }

# arch.sh runs as root and must drop to the GameCore user, or the index lands
# root-owned and the backend cannot refresh it later. Run by hand by that user
# it needs no sudo at all — and asking for one would make the step unrunnable
# for anyone without a sudoers rule, and untestable outside a real install.
as_user() {
  if [[ "$EUID" -eq 0 && "$GC_USER" != "root" ]]; then
    sudo -u "$GC_USER" -H "$@"
  else
    "$@"
  fi
}

GS="$GC_PATH/backend/services/gamemedia/gamescrape.py"
INDEX_DIR="$GC_DATA/emu/gamescrape"
INDEX="$INDEX_DIR/launchbox.sqlite"

# The command that builds it, spelled once. The two root variables are what
# make gamescrape.py resolve the index to $GC_DATA/emu/gamescrape rather than
# to the invoking user's ~/.cache — see resolve_index_dir() in that file.
HOWTO="sudo -u $GC_USER GAMECORE_PATH=$GC_PATH GAMECORE_DATA=$GC_DATA python3 $GS --refresh"

if [[ "${GAMECORE_SKIP_MEDIA_INDEX:-0}" == "1" ]]; then
  info "Media index skipped (GAMECORE_SKIP_MEDIA_INDEX=1)."
  info "Build it later with:  $HOWTO"
  exit 0
fi

if [[ ! -f "$GS" ]]; then
  warn "gamescrape.py not found at $GS — media index skipped."
  exit 0
fi

# Idempotent: re-running the installer is documented as safe, and re-downloading
# 234 MB because the operator ran it twice is not "safe", it is rude. The
# backend's own staleness rule (a schema bump disables the tier) is the reason
# the file merely existing is not enough — but rebuilding on every run to catch
# that case would cost every operator 234 MB for a case that almost never fires.
# Present and non-empty is treated as done; `--refresh` by hand is the cure.
if [[ -s "$INDEX" ]]; then
  ok "Media index already present ($(du -h "$INDEX" | cut -f1)) — kept."
  exit 0
fi

# Transient cost is roughly double the final size: Metadata.zip is downloaded
# beside the database, and the new index is built to a .tmp before replacing it.
# A box that runs out of disk here leaves a half-written index, which the schema
# check would then reject on every request — so it is refused up front instead.
NEED_MB=700
AVAIL_MB=$(df -Pm "$GC_PATH" 2>/dev/null | awk 'NR==2 {print $4}')
if [[ -n "${AVAIL_MB:-}" ]] && (( AVAIL_MB < NEED_MB )); then
  warn "Only ${AVAIL_MB} MB free under $GC_PATH, ${NEED_MB} MB needed — media index skipped."
  info "Build it later with:  $HOWTO"
  exit 0
fi

echo "  Downloading and indexing the LaunchBox dump (234 MB, 1-2 min)…"
echo "  No account needed; this is what gives a box titles and covers offline."

as_user mkdir -p "$INDEX_DIR"

# stdlib only, so the backend venv is not needed and this runs before it exists.
if as_user env "GAMECORE_PATH=$GC_PATH" "GAMECORE_DATA=$GC_DATA" python3 "$GS" --refresh; then
  if [[ -s "$INDEX" ]]; then
    ok "Media index built ($(du -h "$INDEX" | cut -f1)) — 185 000 games, offline."
  else
    # Exit 0 with nothing written: the shape of failure that is hardest to
    # notice, so it is named rather than trusted.
    warn "gamescrape reported success but wrote no index — media index unavailable."
    info "Retry with:  $HOWTO"
  fi
else
  warn "Media index could not be built (network? disk?) — the box works without it."
  info "Retry with:  $HOWTO"
fi

exit 0
