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
TMP_DIR="/tmp/gamecore_ota"
GAMECORE_PATH="${GAMECORE_PATH:-/opt/GameCore}"

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
rm -rf "$TMP_DIR"
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

echo "[update] Installing new files..."
# Excluded paths are user data — never overwrite them:
#   config/     → systems.json, controller mappings, playtime DB
#   emu/        → ROMs and covers
#   assets/overlays/  → user-uploaded bezels
#   assets/logos/     → user-uploaded logos
#   .venv/      → Python virtualenv (rebuilt separately)
rsync -a \
  --exclude='.venv/' \
  --exclude='emu/' \
  --exclude='config/' \
  --exclude='emu-configs/' \
  --exclude='assets/overlays/' \
  --exclude='assets/logos/' \
  "${SRC_DIR}/" "${GAMECORE_PATH}/" || fail "rsync failed"

# Themes are the one thing under config/ that is code, not user data: they ship
# with the release and have to reach the box like any other fix. Synced on their
# own, after the exclude above, and deliberately WITHOUT --delete so a theme the
# player dropped in themselves is never removed by an update. Their selection
# (config/theme.json) is untouched — it is not in the archive.
if [[ -d "${SRC_DIR}/config/themes" ]]; then
  rsync -a "${SRC_DIR}/config/themes/" "${GAMECORE_PATH}/config/themes/" \
    && echo "[update] Bundled themes synced (player-installed themes kept)." \
    || echo "[update] WARNING: theme sync failed (non-fatal)."
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

# Write the new version tag so the backend reports it correctly on next start
echo "${LATEST_TAG}" > "${GAMECORE_PATH}/VERSION"
echo "[update] Version set to ${LATEST_TAG}"

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

echo "[update] Clearing Electron UI cache (stale cached bundles hide the new frontend)..."
# The UI is still running here — it may write some cache back on exit, which
# is why electron/main.js also clears the HTTP cache on every start. This rm
# handles the common case and older UIs that predate that change.
for d in "$HOME/.config/gamecore-electron" "$HOME/.config/GameCore"; do
  rm -rf "$d/Cache" "$d/Code Cache" "$d/GPUCache" 2>/dev/null
done

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
