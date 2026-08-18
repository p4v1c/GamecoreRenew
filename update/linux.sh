#!/usr/bin/env bash
# ================================================================
#  GameCore — OTA Update Script — Arch / Manjaro
#  Called by the backend when "Apply Update" is clicked in Settings.
#
#  Runs as the backend's user, WITHOUT stopping the backend: files are
#  replaced and rebuilt in place (the running process keeps its old code
#  in memory), then services are restarted by the detached
#  gamecore-restart.service unit — never from inside this script, which
#  would kill it (it lives in the backend's cgroup).
#  One-time setup for the restart step: install/steps/setup-update-permissions.sh
# ================================================================
set -uo pipefail

fail() { echo "[update] ERROR: $*"; exit 1; }

REPO="p4v1c/GamecoreRenew"
ASSET="gamecore-ota.tar.gz"
GAMECORE_PATH="${GAMECORE_PATH:-/opt/GameCore}"
# Where the player's data lives. Defaults to the install, which is where every
# box created before the code/data split keeps it — so on those boxes the two
# variables name the same directory and this script behaves exactly as it did.
#
# ── When the data has actually moved ────────────────────────────────────────
# The excludes on the deploy rsync below (emu/, config/, assets/overlays/,
# assets/logos/) exist for one reason: those directories sit INSIDE the tree
# being rsynced into. Once GAMECORE_DATA is a separate tree they are no longer
# inside it, the excludes protect nothing, and this script can do the simple
# thing instead — replace the whole install, `--delete` included, so that a
# file removed from a release actually disappears from the box rather than
# lingering for ever.
#
# That is the eventual shape and it is a real improvement: the case-by-case
# preservation below is the only reason an update cannot be a clean swap.
#
# **Nothing is removed here, and the order matters.** While the data is still
# inside the install — which is true of every box that will receive this
# release — dropping an exclude means the rsync deletes the ROM library on the
# first update. The excludes go when the bytes have gone, not before, and the
# check is `is_split` below rather than anybody's memory of which phase shipped.
#
# Where the data is, when the caller did not say. Launched from the Settings
# screen this script inherits the backend's environment and knows. Typed at a
# shell it does not — a shell has no GAMECORE_DATA — and it would fall back to
# the install: the catalogue merge and every new theme would land in the copy
# of config/ that a migrated box no longer reads, quietly, with a green log.
# The backend's systemd unit is where the migration sets the variable, so it
# is read from there. Same shape as install/bin/gamecore-addon, which must
# stay self-contained (it is copied to /usr/local/bin) — hence the copy.
_data_root_from_backend_unit() {
  command -v systemctl >/dev/null 2>&1 || return 0
  local env kv
  env="$(systemctl show gamecore-backend.service -p Environment --value 2>/dev/null)" || return 0
  for kv in $env; do
    if [[ "$kv" == GAMECORE_DATA=* ]]; then
      printf '%s\n' "${kv#GAMECORE_DATA=}"
      return 0
    fi
  done
}
if [[ -z "${GAMECORE_DATA:-}" ]]; then
  GAMECORE_DATA="$(_data_root_from_backend_unit)"
fi
GAMECORE_DATA="${GAMECORE_DATA:-$GAMECORE_PATH}"

# Only one update at a time. The backend refuses a second /api/update/apply,
# but this is the guard that holds if it is ever started another way — two runs
# used to share a fixed /tmp/gamecore_ota, and the second one's `rm -rf` landed
# in the middle of the first one's rsync into GAMECORE_PATH.
LOCK_FILE="${TMPDIR:-/tmp}/gamecore_ota.lock"
if command -v flock >/dev/null; then
  exec 9>"$LOCK_FILE" || fail "cannot open lock file ${LOCK_FILE}"
  flock -n 9 || fail "another update is already running"
fi

# A private working directory, so concurrent runs cannot collide even without
# flock, and so a stale one is never inherited.
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/gamecore_ota.XXXXXXXX")" || fail "cannot create a work directory"
cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

command -v python3 >/dev/null || fail "python3 not found"

echo "[update] Checking latest release..."
API_URL="https://api.github.com/repos/${REPO}/releases/latest"
RELEASE=$(curl -sf "$API_URL") || fail "GitHub API unreachable (${API_URL})"

# The GitHub API returns pretty-printed JSON — parse it properly, never with grep.
LATEST_TAG=$(printf '%s' "$RELEASE" | python3 -c \
  'import json,sys; print(json.load(sys.stdin).get("tag_name",""))') \
  || fail "could not parse release JSON"
DOWNLOAD_URL=$(printf '%s' "$RELEASE" | python3 -c '
import json, sys
data = json.load(sys.stdin)
name = sys.argv[1]
print(next((a["browser_download_url"] for a in data.get("assets", []) if a["name"] == name), ""))
' "$ASSET") || fail "could not parse release assets"

[[ -n "$LATEST_TAG" ]]    || fail "no tag_name in latest release"
[[ -n "$DOWNLOAD_URL" ]]  || fail "asset '${ASSET}' not found in release ${LATEST_TAG}"

echo "[update] Latest: ${LATEST_TAG}"
echo "[update] Downloading ${ASSET}..."
mkdir -p "$TMP_DIR/src"
curl -sfL -o "${TMP_DIR}/${ASSET}" "$DOWNLOAD_URL" || fail "download failed (${DOWNLOAD_URL})"
echo "[update] Download complete."

echo "[update] Extracting..."
# Extract into src/ so the archive itself is never rsynced into GAMECORE_PATH.
tar -xzf "${TMP_DIR}/${ASSET}" -C "${TMP_DIR}/src" || fail "archive extraction failed"

# The tar may extract flat or into a subdirectory (e.g. GamecoreRenew-v2.0.0/).
SRC_DIR="${TMP_DIR}/src"
if [[ ! -d "${SRC_DIR}/backend" ]]; then
  EXTRACTED=$(find "${SRC_DIR}" -maxdepth 1 -mindepth 1 -type d | head -1)
  [[ -n "$EXTRACTED" && -d "${EXTRACTED}/backend" ]] || fail "no backend/ found in archive"
  SRC_DIR="$EXTRACTED"
fi
echo "[update] Source directory: ${SRC_DIR}"

# Disk space, before touching anything. An rsync that runs out of space part
# way leaves GAMECORE_PATH half old and half new, and update/linux.sh cannot
# install a specific tag — there is no way back from that except by hand.
# Ask for twice the payload, which covers the copy plus the snapshot below.
_need_kb=$(du -sk "${SRC_DIR}" 2>/dev/null | cut -f1)
_free_kb=$(df -Pk "${GAMECORE_PATH}" 2>/dev/null | awk 'NR==2 {print $4}')
if [[ -n "$_need_kb" && -n "$_free_kb" ]] && (( _free_kb < _need_kb * 2 )); then
  # fail() is defined at the top of this file; the definition shellcheck found
  # is the REDEFINITION further down, which adds the restore hint once there is
  # a snapshot to restore from. Before that point there is nothing to restore,
  # and the plain one is the right one.
  # shellcheck disable=SC2218
  fail "not enough free space on $(df -Ph "${GAMECORE_PATH}" | awk 'NR==2 {print $6}') — \
need ~$(( _need_kb * 2 / 1024 )) MB, have $(( _free_kb / 1024 )) MB"
fi

# Snapshot the current install before overwriting it. --link-dest makes this
# hardlinks rather than copies, so it costs directory entries and no data.
#
# Scope matters, and the reason is not obvious: a hardlinked snapshot shares
# inodes with the live tree, so anything that writes IN PLACE changes both
# copies at once. rsync is safe — it writes a temp file and renames, giving a
# new inode — but `pip install` into .venv and `npm install` into node_modules
# are not, and neither is the `echo > VERSION` at the end of this script. Those
# are excluded: they are rebuilt from the release anyway, so there is nothing
# in them worth going back to. What is left is exactly the code rsync replaces,
# which is what the snapshot is for.
#
# Deliberately NOT restored automatically. A trap that rolls back on any
# failure has to be right about a machine whose state it does not know, and
# this path could not be exercised here — an automatic restore that goes wrong
# turns a recoverable update into an unbootable box. The snapshot plus the
# exact command is the part that is safe to ship untested.
PREV_DIR="${GAMECORE_PATH}.prev"
if rm -rf "$PREV_DIR" 2>/dev/null && \
   rsync -a --delete \
     --exclude='.venv/' --exclude='node_modules/' --exclude='emu/' \
     --exclude='config/' --exclude='VERSION' \
     --link-dest="${GAMECORE_PATH}/" "${GAMECORE_PATH}/" "${PREV_DIR}/" 2>/dev/null; then
  echo "[update] Snapshot of the current install: ${PREV_DIR}"
  restore_hint() {
    echo "[update] To go back to the code that was running before this update:"
    echo "[update]   sudo rsync -a ${PREV_DIR}/ ${GAMECORE_PATH}/"
    echo "[update]   sudo systemctl restart gamecore-backend gamecore-ui"
    echo "[update] (no --delete: the snapshot excludes .venv, node_modules, emu/ and"
    echo "[update]  config/, which must not be removed from the live install)"
  }
else
  echo "[update] WARNING: could not snapshot the current install — no easy way back if this fails."
  restore_hint() { :; }
fi

# From here on, a failure leaves files half-replaced: say how to undo it.
fail() { echo "[update] ERROR: $*"; restore_hint; exit 1; }

echo "[update] Installing new files..."
# Excluded paths are user data — never overwrite them:
#   config/     → systems.json, controller mappings, playtime DB
#   emu/        → ROMs and covers
#   assets/overlays/  → user-uploaded bezels
#   assets/logos/     → user-uploaded logos
#   .venv/      → Python virtualenv (rebuilt separately)
#
# catalog/ is deliberately NOT in this list, and that is the whole point of the
# pack migration. It carries the shipped logos and the curated seeds, which are
# project content, not user data: the emulators' real configs live in
# ~/.var/app/**, and catalog/<id>/seed/ is only the reference tree
# install-emu-configs.sh copies FROM — read-only at runtime, nothing in
# backend/ or electron/ ever writes to it.
#
# Its predecessor emu-configs/ was excluded once, and it cost: a corrected
# controller mapping could reach GitHub and never reach a box.
# emu-configs/dolphin/GCPadNew.ini was fixed upstream, a test locked the fix in,
# and the box kept its keyboard D-Pad for good. Same reasoning now applies to
# the logos, which moved out of assets/logos/ into catalog/<id>/logo.png for
# exactly this reason — assets/logos/ stays excluded below so a logo the
# operator uploaded by hand is still never overwritten.
#
# Shipping catalog/ here does NOT touch a running emulator's config — deploying
# that stays a deliberate act:
#     bash /opt/GameCore/install/steps/install-emu-configs.sh
#
# config/ is excluded wholesale, which is what preserves config/catalog.d/ —
# the operator's own packs — across every update.
if [[ "${GAMECORE_DATA}" != "${GAMECORE_PATH}" ]]; then
  # Said out loud because it changes what the excludes below are worth, and
  # because an operator reading a log after a bad update needs to know which
  # of the two shapes the box was in.
  echo "[update] Data lives at ${GAMECORE_DATA}, outside the install."
  echo "[update] The excludes below are now redundant but still harmless."
fi
rsync -a \
  --exclude='.venv/' \
  --exclude='emu/' \
  --exclude='config/' \
  --exclude='assets/overlays/' \
  --exclude='assets/logos/' \
  "${SRC_DIR}/" "${GAMECORE_PATH}/" || fail "rsync failed"

# Themes: install what is missing, and update what the release ships a newer
# version of.
#
# A theme is code, so a new one shipped with a release has to be able to reach
# the box — config/ is excluded wholesale above, so nothing else would bring it.
# This used to stop there: a theme the box already had was skipped, always. The
# reasoning was that a theme on the box is the player's, and it held right up
# until a bundled theme had a bug. Then the fix reached GitHub, reached the
# archive, reached this loop — and was thrown away on every box that had ever
# installed that theme. Correcting one meant deleting its folder over SSH.
#
# So the decision is now the same one the rest of this script makes about the
# release itself: compare versions. `version` is a mandatory field of
# theme.json (docs/themes/README.md §4), it is the author's own statement that
# something changed, and it is already required — nothing new has to be
# published for this to work.
#
#   on the box, not in the release   never touched. A theme you wrote is yours;
#                                    this loop only ever looks at what shipped.
#   in the release, not on the box   installed, as before.
#   both, release version newer      replaced, previous kept in .prev/<id>.
#   both, same or older              left alone. Re-running an update, or
#                                    installing an older release, changes nothing.
#
# The cost is the honest one: editing a bundled theme in place without bumping
# its version means a later release can replace your edit. The previous copy is
# kept under config/themes/.prev/<id>/ so it is recoverable rather than gone —
# `list_themes()` skips any directory starting with `.` or `_`, so nothing put
# there is ever offered to a player. Only the most recent replacement is kept,
# the same single-snapshot rule as ${GAMECORE_PATH}.prev above.
#
# The player's selection (config/theme.json) is untouched throughout — it is
# not in the archive.

# Strictly-newer test, tolerant of anything a manifest might contain: this runs
# on a version string written by a theme author, so it must not raise on
# '1.2.0-beta', 'v3', or ''. Same shape as _version_int in routers/update.py.
_theme_newer() {
  python3 - "$1" "$2" <<'PYEOF' 2>/dev/null
import re, sys
def key(v):
    nums = re.findall(r"\d+", v or "")[:3]
    return tuple(int(n) for n in (nums + ["0", "0", "0"])[:3])
sys.exit(0 if key(sys.argv[1]) > key(sys.argv[2]) else 1)
PYEOF
}

# Empty means "could not read it" — never a version. A theme whose manifest is
# missing, truncated or not JSON is one this script must not make decisions
# about, and the caller treats an empty answer as "leave it alone".
_theme_version() {
  python3 - "${1}/theme.json" <<'PYEOF' 2>/dev/null
import json, sys
try:
    print(str(json.load(open(sys.argv[1])).get("version", "")))
except Exception:
    print("")
PYEOF
}

# ── One-off: retire config/themes/_shared/ ──────────────────────────────────
#
# `_shared/` held the settings screen and the power menu that Shelf and Summer
# both imported. They are host code now, shipped in the frontend bundle, and no
# theme imports that path any more.
#
# The loop below cannot clear it. Its central promise is "on the box, not in the
# release → never touched", which is what keeps an operator's own theme safe
# from an update; a generic prune of anything missing from the release would
# delete exactly the themes that promise protects. So this retirement is NAMED,
# and it happens once.
#
# Left alone, the directory is inert — `list_themes()` skips any name starting
# with `_`, so it is never offered and never loaded. It is removed because a
# stale copy of a screen that moved is the kind of thing somebody edits in three
# months wondering why nothing changes.
#
# Moved to .prev/ rather than deleted, the same recovery the replace path uses:
# an operator who put something of their own in there gets it back from a known
# place instead of from a backup they may not have.
_retire_shared_dir() {
  local _dir="${1}/_shared"
  [[ -d "$_dir" ]] || return 0
  # Only the directory this project shipped. Both markers, not either: an
  # operator who keeps their own `_shared` for their own reasons has no reason
  # to have our screen in it, and this must not take it from them.
  [[ -f "${_dir}/theme.json" && -f "${_dir}/settings/screen.js" ]] || {
    echo "[update] themes/_shared is not the one this project shipped — left untouched."
    return 0
  }
  mkdir -p "${1}/.prev"
  rm -rf "${1:?}/.prev/_shared"
  if mv "$_dir" "${1}/.prev/_shared"; then
    echo "[update] themes/_shared retired (moved to themes/.prev/_shared) — its code is in the bundle now."
  else
    echo "[update] WARNING: could not retire themes/_shared (non-fatal, it is inert)."
  fi
}

if [[ -d "${SRC_DIR}/config/themes" ]]; then
  # The data root, not the install: a theme is installed content, and once the
  # two trees separate this loop would otherwise write into a read-only root
  # and drop every bundled theme on the floor. Identical while GAMECORE_DATA
  # defaults to GAMECORE_PATH, which is every box today.
  _themes_dir="${GAMECORE_DATA}/config/themes"
  _themes_prev="${_themes_dir}/.prev"
  mkdir -p "$_themes_dir"
  _installed=0 _updated=0 _kept=0
  for _theme in "${SRC_DIR}/config/themes/"*/; do
    [[ -d "$_theme" ]] || continue
    _id="$(basename "$_theme")"
    _dest="${_themes_dir}/${_id}"

    if [[ ! -e "$_dest" ]]; then
      if cp -a "$_theme" "$_dest"; then
        _installed=$((_installed + 1))
      else
        echo "[update] WARNING: could not install theme ${_id} (non-fatal)."
      fi
      continue
    fi

    _have="$(_theme_version "$_dest")"
    _want="$(_theme_version "$_theme")"
    if [[ -z "$_want" ]]; then
      echo "[update] WARNING: theme ${_id} ships no readable version — left untouched."
      _kept=$((_kept + 1)); continue
    fi
    if [[ -z "$_have" ]]; then
      echo "[update] Theme ${_id}: no readable version on this box — left untouched (${_want} available)."
      _kept=$((_kept + 1)); continue
    fi
    if ! _theme_newer "$_want" "$_have"; then
      _kept=$((_kept + 1)); continue
    fi

    # Staged, then swapped by rename. The theme directory is live code the UI
    # imports by path, so it must never be observed half-written and must never
    # briefly not exist — an `rm -rf` followed by a `cp` that runs out of space
    # leaves the box with no theme at all, which is a box with no interface.
    # Staging area and destination are in the same directory, so both renames
    # are atomic, and a `.`-prefixed leftover from a killed run is invisible to
    # the theme scanner and cleared by the next one.
    _stage="${_themes_dir}/.incoming-${_id}"
    rm -rf "$_stage"
    if ! cp -a "$_theme" "$_stage"; then
      rm -rf "$_stage"
      echo "[update] WARNING: could not stage theme ${_id} — kept ${_have} (non-fatal)."
      _kept=$((_kept + 1)); continue
    fi

    mkdir -p "$_themes_prev"
    # :? on both halves. An empty _id would make this wipe the whole .prev
    # directory rather than one theme, and an rm -rf is not the place to trust
    # that a loop variable is always set.
    rm -rf "${_themes_prev:?}/${_id:?}"
    if ! mv "$_dest" "${_themes_prev}/${_id}"; then
      rm -rf "$_stage"
      echo "[update] WARNING: could not set theme ${_id} aside — kept ${_have} (non-fatal)."
      _kept=$((_kept + 1)); continue
    fi

    if mv "$_stage" "$_dest"; then
      echo "[update] Theme ${_id}: ${_have} -> ${_want} (previous kept in themes/.prev/${_id})"
      _updated=$((_updated + 1))
    else
      # Put the old one back rather than leave the slot empty.
      mv "${_themes_prev}/${_id}" "$_dest" 2>/dev/null
      rm -rf "$_stage"
      echo "[update] WARNING: could not install theme ${_id} — restored ${_have} (non-fatal)."
      _kept=$((_kept + 1))
    fi
  done
  echo "[update] Themes: ${_installed} installed, ${_updated} updated, ${_kept} left untouched."
  _retire_shared_dir "$_themes_dir"
fi

# frontend/dist is pure build output (CI ships it complete). Mirror it exactly
# — without --delete the old content-hashed bundles (index-<hash>.js) would
# pile up forever; only the one index.html references is ever served.
if [[ -d "${SRC_DIR}/frontend/dist" ]]; then
  rsync -a --delete "${SRC_DIR}/frontend/dist/" "${GAMECORE_PATH}/frontend/dist/" \
    && echo "[update] Frontend dist mirrored (stale bundles pruned)." \
    || echo "[update] WARNING: dist mirror failed (non-fatal)."
fi

# frontend/src likewise, so the sources on the box always match the dist above.
# They used to be left untouched by every update: the box then ran a current
# build on top of first-install sources, and any rebuild there (the fallback
# below, or a hand-run `npm run build`) silently reverted the UI by months.
# --delete is safe here — node_modules/ lives in frontend/, not frontend/src/.
if [[ -d "${SRC_DIR}/frontend/src" ]]; then
  rsync -a --delete "${SRC_DIR}/frontend/src/" "${GAMECORE_PATH}/frontend/src/" \
    && echo "[update] Frontend sources synced." \
    || echo "[update] WARNING: source sync failed (non-fatal)."
else
  echo "[update] NOTE: this release ships no frontend sources — the ones on disk"
  echo "[update]       may be older than the bundle being installed."
fi

echo "[update] Updating Python dependencies..."
"${GAMECORE_PATH}/.venv/bin/pip" install -q -r "${GAMECORE_PATH}/backend/requirements.txt" \
  || fail "pip install failed"

if [[ -d "${SRC_DIR}/frontend/dist" ]]; then
  echo "[update] Frontend delivered prebuilt by CI — no rebuild needed."
else
  # Safe now that the sources were synced above: this builds the release's own
  # code, not whatever happened to be sitting on the box.
  echo "[update] Rebuilding frontend..."
  cd "${GAMECORE_PATH}/frontend" || fail "frontend directory missing"
  npm install --silent || fail "npm install failed"
  npm run build        || fail "frontend build failed"
fi

# Caddy's config is NOT part of an OTA. /etc/caddy/Caddyfile is written only by
# install/arch.sh (which templates the backend port into it) and needs root, so
# a security fix to the shipped Caddyfile — a route that should not be exposed,
# a gate that approves too much — reaches no installed box on its own. Nothing
# said so, either. At least notice, and say what to do about it.
if [[ -f /etc/caddy/Caddyfile && -f "${GAMECORE_PATH}/install/system/Caddyfile" ]]; then
  # Compare against the shipped file with the same port substitution arch.sh
  # applies, so a box on a non-default port is not flagged every single update.
  _live_port=$(grep -oE '127\.0\.0\.1:[0-9]+' /etc/caddy/Caddyfile | head -1 | cut -d: -f2)
  _live_port=${_live_port:-8765}
  if ! sed "s|127\.0\.0\.1:8765|127.0.0.1:${_live_port}|g" \
       "${GAMECORE_PATH}/install/system/Caddyfile" | diff -q - /etc/caddy/Caddyfile >/dev/null 2>&1; then
    echo "[update] NOTE: /etc/caddy/Caddyfile differs from the one shipped in this release."
    echo "[update]       An update cannot rewrite it (root, and the port is templated per box)."
    echo "[update]       If you have not customised it, apply the new one with:"
    echo "[update]         sudo sed 's|127.0.0.1:8765|127.0.0.1:${_live_port}|g' \\"
    echo "[update]           ${GAMECORE_PATH}/install/system/Caddyfile > /etc/caddy/Caddyfile \\"
    echo "[update]           && sudo systemctl reload caddy"
  fi
fi

# Same blind spot as the Caddyfile above: the systemd units are written only by
# install/arch.sh and live under /etc, so an ordering fix reaches no installed
# box on its own. This one matters — without the wait, the backend starts
# before X and every game launch fails until the service is restarted by hand.
#
# The code-side fix (process_manager retries a failed probe instead of latching
# it) ships with this update and is what actually repairs a running box; this
# only removes the first failed launch after a cold boot.
#
# Read the unit as systemd sees it — file plus drop-ins — not the file alone.
# An operator who applies the fix the right way, as a drop-in that leaves the
# installer's file and override.conf untouched, must not be told on every
# update that it is missing.
if command -v systemctl >/dev/null 2>&1 \
   && [[ -f /etc/systemd/system/gamecore-backend.service ]] \
   && ! systemctl cat gamecore-backend.service 2>/dev/null | grep -q '^ExecStartPre='; then
  echo "[update] NOTE: gamecore-backend.service starts without waiting for the X display."
  echo "[update]       Harmless now — the backend retries the probe — but it costs one"
  echo "[update]       failed launch after each cold boot. To apply the new ordering"
  echo "[update]       without touching the unit file or override.conf, put the"
  echo "[update]       After=display-manager.service and ExecStartPre= lines from"
  echo "[update]         ${GAMECORE_PATH}/install/arch.sh   (search: FastAPI Backend)"
  echo "[update]       in a drop-in:"
  echo "[update]         /etc/systemd/system/gamecore-backend.service.d/x-display.conf"
  echo "[update]       then: sudo systemctl daemon-reload   (takes effect at the next start)"
fi

# The addon CLI lives in /usr/local/bin — a path root controls, so that an
# addon's install.sh cannot rewrite the tool that runs it — and only
# install/arch.sh puts it there. Same blind spot as the Caddyfile and the
# units above: a fix to the CLI reaches GitHub, reaches this archive, lands in
# install/bin/, and the copy every command actually runs is the one from the
# day the box was installed. This one matters for the data split: a CLI from
# before it does not know GAMECORE_DATA, and the first `gamecore-addon update`
# after the data moves would bake the old root into every addon's unit.
if [[ -f /usr/local/bin/gamecore-addon && -f "${GAMECORE_PATH}/install/bin/gamecore-addon" ]] \
   && ! cmp -s /usr/local/bin/gamecore-addon "${GAMECORE_PATH}/install/bin/gamecore-addon"; then
  echo "[update] NOTE: /usr/local/bin/gamecore-addon is not the one this release ships."
  echo "[update]       An update cannot replace it (root). Apply the new one with:"
  echo "[update]         sudo install -m 755 ${GAMECORE_PATH}/install/bin/gamecore-addon /usr/local/bin/gamecore-addon"
fi

# config/systems.json is excluded from the rsync above — deliberately, it is
# the box's identity — so nothing shipped in a release used to reach the grid.
# This block handled that by PRINTING the commands the owner was expected to
# type by hand to migrate the N64 slot from gopher64 to Rosalie's Mupen GUI.
# Nobody types those, and the tile went on launching an emulator the installer
# no longer installs.
#
# It merges now, conservatively (backend/services/catalog/merge.py):
#   · a tile the operator added by hand is kept, untouched;
#   · an emulator new in this release is added;
#   · a launcher is repaired ONLY when it is stale — it names a Flatpak app id
#     no pack declares, or its path does not resolve on this box. A native
#     binary in lib/ that exists is never pushed back to Flatpak;
#   · `extensions` gains what it is missing and loses nothing. A machine
#     installed before *.cue was added to duckstation scanned *.bin and not
#     *.cue: the .cue shadowed the .bin and was then filtered out, and the
#     library went from one PS1 game to none.
#
# The previous file is kept as systems.json.bak-merge. A malformed grid is
# reported and left alone: an update must not take the interface down because
# a hand edit left a trailing comma.
# Two roots, and the merge is told both. The catalogue and `lib/` are code
# and come from GAMECORE_PATH; systems.json, catalog.d/ (the operator's own
# packs) and catalog-removed.json are the player's and come from GAMECORE_DATA.
# One argument used to serve for both, which was correct for exactly as long
# as the two directories were the same one — and silently wrong afterwards:
# every update would have merged into the abandoned copy under the install,
# and the grid the box actually reads would never have gained a new emulator,
# a repaired launcher or a console list again.
echo "[update] Merging the shipped catalogue into ${GAMECORE_DATA}/config/systems.json..."
"${GAMECORE_PATH}/.venv/bin/python3" - "${GAMECORE_PATH}" "${GAMECORE_DATA}" <<'PYEOF' || \
  echo "[update] WARNING: catalogue merge failed (non-fatal) — the grid is unchanged."
import sys
from pathlib import Path

root, data = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(root))
from backend.services.catalog import load_catalog
from backend.services.catalog.merge import merge_file

notes = merge_file(data / "config" / "systems.json",
                   load_catalog(root / "catalog", data / "config" / "catalog.d"),
                   root, data_root=data)
for n in notes:
    print(f"[update]   {n}")
if not notes:
    print("[update]   nothing to change.")
PYEOF

# Third thing an OTA cannot rewrite: the desktop shortcut. arch.sh writes it
# pointing at install/bin/gamecore-launcher, which is maintained here — but a
# box that was set up by hand, or before that shortcut existed, can be pointing
# somewhere else entirely.
#
# Worth a word because the consequence is invisible and nasty. The variant
# found on the reference box ran `sudo systemctl is-active`, which needs no
# root and is not covered by the NOPASSWD rule, so every click failed two sudo
# authentications and walked pam_faillock closer to locking the user's account.
for _d in "$HOME/Desktop/GameCore.desktop" "$HOME/Bureau/GameCore.desktop"; do
  [[ -f "$_d" ]] || continue
  if ! grep -q "^Exec=${GAMECORE_PATH}/install/bin/gamecore-launcher" "$_d"; then
    echo "[update] NOTE: $_d does not run the shipped launcher."
    echo "[update]       It points at: $(grep -m1 '^Exec=' "$_d" | cut -d= -f2-)"
    echo "[update]       An update cannot rewrite a file outside ${GAMECORE_PATH}. Fix with:"
    echo "[update]         sed -i 's|^Exec=.*|Exec=${GAMECORE_PATH}/install/bin/gamecore-launcher|' \\"
    echo "[update]           '$_d'"
  fi
done

echo "[update] Clearing Electron UI cache (stale cached bundles hide the new frontend)..."
# The UI is still running here — it may write some cache back on exit, which
# is why electron/main.js also clears the HTTP cache on every start. This rm
# handles the common case and older UIs that predate that change.
for d in "$HOME/.config/gamecore-electron" "$HOME/.config/GameCore"; do
  rm -rf "$d/Cache" "$d/Code Cache" "$d/GPUCache" 2>/dev/null
done

# Write the new version tag LAST — after every step that can still fail.
#
# It used to be written before pip and the frontend build. If the network
# dropped in between, the script exited via fail() with VERSION already
# claiming the new release: the box ran new files against old dependencies,
# and GET /api/update/check compared that VERSION to the latest tag, decided
# it was up to date, and stopped offering the update. The only way to retry
# was over SSH.
echo "${LATEST_TAG}" > "${GAMECORE_PATH}/VERSION"
echo "[update] Version set to ${LATEST_TAG}"

# ── Privileges a release added after this box was installed ────────────────
#
# Sudoers rules are written ONCE, by arch.sh and setup-update-permissions.sh, at
# INSTALL time. An OTA replaces code and nothing else — it runs as the backend's
# user and cannot grant itself anything. So every rule added in a later release
# is simply absent on every box installed before it, for ever, and the feature
# it gates is dead without a word.
#
# Found on the reference box, running a release fourteen tags old:
#   · no rule for /usr/local/bin/gamecore-emu, and the CLI not installed at all
#     — so "install an emulator" from the Systems screen could not work. The
#     endpoint exists, the catalogue lists seventeen packs, and the button was
#     never going to do anything.
#   · no rule for cpupower, so standby.py never dropped or raised the governor.
#     It logs at debug and carries on, which is why nobody saw it: the only
#     trace was `sudo: a password is required` in the journal.
#
# This cannot be repaired from here — that is the point of the rule being
# root-owned. What it CAN do is stop the drift being invisible: check what the
# release expects against what this box grants, and name the one command that
# fixes it. A dead feature that says so is a support question; a dead feature
# that does not is a bug report about something else entirely.
# NOPASSWD is the only thing that counts, and `sudo -n -l <command>` does NOT
# test it: on a box whose owner is in wheel, `(ALL) ALL` means every command is
# permitted — with a password. The backend always calls `sudo -n`, which never
# prompts, so a rule that is merely "allowed" is a rule that fails. The list is
# therefore read once and searched for the NOPASSWD entries themselves.
sudo_rules="$(sudo -n -l 2>/dev/null || true)"

# The rules to expect are READ FROM THE INSTALLERS THIS UPDATE JUST SHIPPED,
# never typed here. A hardcoded list would cover the two rules that happened to
# be missing the day this was written and go stale on the third — which is the
# very drift it exists to catch. arch.sh and setup-update-permissions.sh are the
# only writers of sudoers rules, and they are both in the OTA archive.
expected_cmds="$(grep -rhoE 'NOPASSWD: *[^"]*' \
                   "${GAMECORE_PATH}/install/arch.sh" \
                   "${GAMECORE_PATH}/install/steps/setup-update-permissions.sh" 2>/dev/null \
                 | sed 's/NOPASSWD: *//' \
                 | tr ',' '\n' \
                 | grep -oE '/[a-zA-Z0-9/._-]+' \
                 | sort -u)"

missing_rules=""
while IFS= read -r cmd; do
  [[ -n "$cmd" ]] || continue
  # Match on the binary name: the granted rule carries its arguments too
  # ("systemctl start gamecore-ui.service"), and comparing whole lines would
  # report a difference for every rule that has any.
  grep -q "NOPASSWD:.*$(basename "$cmd")" <<<"$sudo_rules" \
    || missing_rules="${missing_rules}  · ${cmd}\n"
done <<<"$expected_cmds"
if [[ -n "$missing_rules" ]]; then
  echo "[update]"
  echo "[update] This box is missing privileges that later releases added, so the"
  echo "[update] following do nothing at all — silently, until this notice:"
  # Each line gets its own prefix: `printf "[update] %b"` prints it once and
  # the rest of the list comes out unprefixed, which the UI streams verbatim.
  printf "%b" "$missing_rules" | while IFS= read -r line; do
    echo "[update] $line"
  done
  echo "[update] Grant them once (root, no reinstall, nothing else changes):"
  echo "[update]   sudo ${GAMECORE_PATH}/install/steps/setup-update-permissions.sh ${USER}"
  echo "[update] and, for anything above that step does not cover, the matching"
  echo "[update] NOPASSWD line from ${GAMECORE_PATH}/install/arch.sh (search: sudoers)."
  echo "[update]"
fi

echo "[update] Scheduling service restart (detached)..."
# --no-block: return immediately; the restart runs in its own unit, outside
# this script's cgroup, ~2s after we exit (see gamecore-restart.service).
if sudo -n systemctl start --no-block gamecore-restart.service 2>/dev/null; then
  echo "[update] Done! ${LATEST_TAG} installed — services restarting in a few seconds."
else
  echo "[update] Files installed (${LATEST_TAG}) but automatic restart is not set up."
  echo "[update] Run once:  sudo ${GAMECORE_PATH}/install/steps/setup-update-permissions.sh"
  echo "[update] Then restart manually:  sudo systemctl restart gamecore-backend gamecore-ui"
fi
