#!/usr/bin/env bash
# ================================================================
#  GameCore — OTA Update Script — Linux (Arch / Debian)
#  Called by the backend when "Apply Update" is clicked in Settings.
# ================================================================
set -euo pipefail

# ── Distro detection ─────────────────────────────────────────────
if command -v pacman &>/dev/null; then
  DISTRO="arch"
elif command -v apt-get &>/dev/null; then
  DISTRO="debian"
else
  DISTRO="unknown"
fi
echo "[update] Detected distro: ${DISTRO}"

REPO="p4v1c/GamecoreRenew"
ASSET="gamecore-ota.tar.gz"
TMP_DIR="/tmp/gamecore_ota"
GAMECORE_PATH="${GAMECORE_PATH:-/opt/GameCore}"

echo "[update] Checking latest release..."
API_URL="https://api.github.com/repos/${REPO}/releases/latest"
RELEASE=$(curl -sf "$API_URL") || { echo "[update] ERROR: GitHub unreachable"; exit 1; }

LATEST_TAG=$(echo "$RELEASE" | grep -o '"tag_name":"[^"]*"' | cut -d'"' -f4)
DOWNLOAD_URL=$(echo "$RELEASE" | grep -o "\"browser_download_url\":\"[^\"]*${ASSET}\"" | cut -d'"' -f4)

if [[ -z "$DOWNLOAD_URL" ]]; then
  echo "[update] ERROR: Asset '${ASSET}' not found in release ${LATEST_TAG}"
  exit 1
fi

echo "[update] Latest: ${LATEST_TAG}"
echo "[update] Downloading ${ASSET}..."
rm -rf "$TMP_DIR"
mkdir -p "$TMP_DIR"

curl -L --progress-bar -o "${TMP_DIR}/${ASSET}" "$DOWNLOAD_URL"
echo "[update] Download complete."

echo "[update] Extracting..."
tar -xzf "${TMP_DIR}/${ASSET}" -C "$TMP_DIR"

# The tar may extract into a subdirectory (e.g. GamecoreRenew-v2.0.0/).
# Find the actual source root: prefer a dir that contains backend/, else use TMP_DIR itself.
SRC_DIR="$TMP_DIR"
EXTRACTED=$(find "$TMP_DIR" -maxdepth 1 -mindepth 1 -type d | head -1)
if [[ -n "$EXTRACTED" && -d "${EXTRACTED}/backend" ]]; then
  SRC_DIR="$EXTRACTED"
fi
echo "[update] Source directory: ${SRC_DIR}"

echo "[update] Stopping services..."
systemctl stop gamecore-ui.service 2>/dev/null || true
systemctl stop gamecore-backend.service 2>/dev/null || true

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
  --exclude='assets/overlays/' \
  --exclude='assets/logos/' \
  "${SRC_DIR}/" "${GAMECORE_PATH}/"

# Write the new version tag so the backend reports it correctly on next start
echo "${LATEST_TAG}" > "${GAMECORE_PATH}/VERSION"
echo "[update] Version set to ${LATEST_TAG}"

echo "[update] Updating Python dependencies..."
"${GAMECORE_PATH}/.venv/bin/pip" install -q -r "${GAMECORE_PATH}/backend/requirements.txt"

echo "[update] Rebuilding frontend..."
cd "${GAMECORE_PATH}/frontend"
npm install --silent
npm run build

echo "[update] Restarting services..."
systemctl start gamecore-backend.service
sleep 2
systemctl start gamecore-ui.service

echo "[update] Done! Now running ${LATEST_TAG}"
