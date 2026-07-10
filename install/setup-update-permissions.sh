#!/usr/bin/env bash
# One-time root setup so the OTA update can restart GameCore's services.
# Installs:
#   - gamecore-restart.service  (system unit doing the actual restart)
#   - a sudoers drop-in letting the GameCore user start ONLY that unit,
#     without a password (the update script runs unprivileged).
# Usage:  sudo ./setup-update-permissions.sh [gamecore-user]
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "Run me with sudo."; exit 1; }

GC_USER="${1:-${SUDO_USER:-}}"
[[ -n "$GC_USER" ]] || { echo "usage: sudo $0 <gamecore-user>"; exit 1; }
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

install -m 644 "${HERE}/gamecore-restart.service" /etc/systemd/system/gamecore-restart.service
systemctl daemon-reload

SUDOERS_FILE="/etc/sudoers.d/gamecore-update"
echo "${GC_USER} ALL=(root) NOPASSWD: /usr/bin/systemctl start --no-block gamecore-restart.service" > "$SUDOERS_FILE"
chmod 440 "$SUDOERS_FILE"
visudo -cf "$SUDOERS_FILE" || { rm -f "$SUDOERS_FILE"; echo "sudoers validation failed, aborted"; exit 1; }

echo "✅ OTA restart permissions installed for user '${GC_USER}'."
echo "   Unit:    gamecore-restart.service"
echo "   Sudoers: ${SUDOERS_FILE}"
