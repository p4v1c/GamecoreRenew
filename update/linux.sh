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
#  One-time setup for the restart step: install/setup-update-permissions.sh
# ================================================================
set -uo pipefail

fail() { echo "[update] ERROR: $*"; exit 1; }

REPO="p4v1c/GamecoreRenew"
ASSET="gamecore-ota.tar.gz"
GAMECORE_PATH="${GAMECORE_PATH:-/opt/GameCore}"

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
# emu-configs/ used to be in this list, and it does not belong: it is not user
# data. The emulators' real configs live in ~/.var/app/**, and emu-configs/ is
# the reference tree install-emu-configs.sh copies FROM — read-only at runtime,
# nothing in backend/ or electron/ ever writes to it. Excluding it meant a
# corrected controller mapping could reach GitHub and never reach a box:
# emu-configs/dolphin/GCPadNew.ini was fixed upstream, a test locked the fix in,
# and the box kept its keyboard D-Pad for good. Shipping it here does NOT touch
# a running emulator's config — deploying that stays a deliberate act:
#     bash /opt/GameCore/install/install-emu-configs.sh
rsync -a \
  --exclude='.venv/' \
  --exclude='emu/' \
  --exclude='config/' \
  --exclude='assets/overlays/' \
  --exclude='assets/logos/' \
  "${SRC_DIR}/" "${GAMECORE_PATH}/" || fail "rsync failed"

# Themes: install what is missing, never touch what is there.
#
# A theme is code, so a new one shipped with a release has to be able to reach
# the box — config/ is excluded wholesale above, so nothing else would bring it.
# But a theme on the box is the player's: they may have edited a bundled one, or
# copied it and kept the name. So the unit is the theme directory, not the file.
# If config/themes/<id>/ exists, it is skipped entirely — no merge, no partial
# overwrite that would leave one theme built from two different releases.
#
# Updating a bundled theme is therefore a manual act: delete its folder and run
# the update again, or copy it in by hand. Their selection (config/theme.json)
# is untouched either way — it is not in the archive.
if [[ -d "${SRC_DIR}/config/themes" ]]; then
  mkdir -p "${GAMECORE_PATH}/config/themes"
  _installed=0 _kept=0
  for _theme in "${SRC_DIR}/config/themes/"*/; do
    [[ -d "$_theme" ]] || continue
    _id="$(basename "$_theme")"
    if [[ -e "${GAMECORE_PATH}/config/themes/${_id}" ]]; then
      _kept=$((_kept + 1))
      continue
    fi
    if cp -a "$_theme" "${GAMECORE_PATH}/config/themes/${_id}"; then
      _installed=$((_installed + 1))
    else
      echo "[update] WARNING: could not install theme ${_id} (non-fatal)."
    fi
  done
  echo "[update] Themes: ${_installed} installed, ${_kept} left untouched."
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
if [[ -f /etc/caddy/Caddyfile && -f "${GAMECORE_PATH}/install/Caddyfile" ]]; then
  # Compare against the shipped file with the same port substitution arch.sh
  # applies, so a box on a non-default port is not flagged every single update.
  _live_port=$(grep -oE '127\.0\.0\.1:[0-9]+' /etc/caddy/Caddyfile | head -1 | cut -d: -f2)
  _live_port=${_live_port:-8765}
  if ! sed "s|127\.0\.0\.1:8765|127.0.0.1:${_live_port}|g" \
       "${GAMECORE_PATH}/install/Caddyfile" | diff -q - /etc/caddy/Caddyfile >/dev/null 2>&1; then
    echo "[update] NOTE: /etc/caddy/Caddyfile differs from the one shipped in this release."
    echo "[update]       An update cannot rewrite it (root, and the port is templated per box)."
    echo "[update]       If you have not customised it, apply the new one with:"
    echo "[update]         sudo sed 's|127.0.0.1:8765|127.0.0.1:${_live_port}|g' \\"
    echo "[update]           ${GAMECORE_PATH}/install/Caddyfile > /etc/caddy/Caddyfile \\"
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
if [[ -f /etc/systemd/system/gamecore-backend.service ]] \
   && ! grep -q 'ExecStartPre' /etc/systemd/system/gamecore-backend.service; then
  echo "[update] NOTE: gamecore-backend.service starts without waiting for the X display."
  echo "[update]       Harmless now — the backend retries the probe — but it costs one"
  echo "[update]       failed launch after each cold boot. To apply the new ordering:"
  echo "[update]         sudo systemctl edit --full gamecore-backend.service"
  echo "[update]       and copy the ExecStartPre line from:"
  echo "[update]         ${GAMECORE_PATH}/install/arch.sh   (search: FastAPI Backend)"
fi

# Third thing an OTA cannot rewrite: the desktop shortcut. arch.sh writes it
# pointing at install/gamecore-launcher.sh, which is maintained here — but a
# box that was set up by hand, or before that shortcut existed, can be pointing
# somewhere else entirely.
#
# Worth a word because the consequence is invisible and nasty. The variant
# found on the reference box ran `sudo systemctl is-active`, which needs no
# root and is not covered by the NOPASSWD rule, so every click failed two sudo
# authentications and walked pam_faillock closer to locking the user's account.
for _d in "$HOME/Desktop/GameCore.desktop" "$HOME/Bureau/GameCore.desktop"; do
  [[ -f "$_d" ]] || continue
  if ! grep -q "^Exec=${GAMECORE_PATH}/install/gamecore-launcher.sh" "$_d"; then
    echo "[update] NOTE: $_d does not run the shipped launcher."
    echo "[update]       It points at: $(grep -m1 '^Exec=' "$_d" | cut -d= -f2-)"
    echo "[update]       An update cannot rewrite a file outside ${GAMECORE_PATH}. Fix with:"
    echo "[update]         sed -i 's|^Exec=.*|Exec=${GAMECORE_PATH}/install/gamecore-launcher.sh|' \\"
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

echo "[update] Scheduling service restart (detached)..."
# --no-block: return immediately; the restart runs in its own unit, outside
# this script's cgroup, ~2s after we exit (see gamecore-restart.service).
if sudo -n systemctl start --no-block gamecore-restart.service 2>/dev/null; then
  echo "[update] Done! ${LATEST_TAG} installed — services restarting in a few seconds."
else
  echo "[update] Files installed (${LATEST_TAG}) but automatic restart is not set up."
  echo "[update] Run once:  sudo ${GAMECORE_PATH}/install/setup-update-permissions.sh"
  echo "[update] Then restart manually:  sudo systemctl restart gamecore-backend gamecore-ui"
fi
