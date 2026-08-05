#!/usr/bin/env bash
# One-time root setup for the two things the backend cannot do on its own.
#
# Installs:
#   - gamecore-restart.service  (system unit doing the actual restart)
#   - a sudoers drop-in letting the GameCore user:
#       · start ONLY that unit, without a password (the update script runs
#         unprivileged);
#       · run ONLY /usr/local/bin/gamecore-emu, so an emulator can be added
#         from the interface without re-running the installer.
#
# Why gamecore-emu and not `flatpak install`:
#
#   A NOPASSWD rule for flatpak would let the GameCore user install ANY
#   application from any configured remote, as root. The rule below names one
#   script instead, and that script refuses any id the catalogue does not
#   declare (`require_ids`) — so the argument an attacker could control selects
#   among the packs that shipped with the release, and nothing else. There is
#   deliberately no "install from this URL" anywhere in the chain.
#
#   That narrowness is also what makes the data-only rule for
#   config/catalog.d/ load-bearing rather than decorative: a pack dropped there
#   cannot carry generator.py, postInstall, services, sources or packages, so
#   naming it here cannot run code either. See config/catalog.d/README.md.
#
# Usage:  sudo ./setup-update-permissions.sh [gamecore-user]
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "Run me with sudo."; exit 1; }

GC_USER="${1:-${SUDO_USER:-}}"
[[ -n "$GC_USER" ]] || { echo "usage: sudo $0 <gamecore-user>"; exit 1; }
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

install -m 644 "${HERE}/gamecore-restart.service" /etc/systemd/system/gamecore-restart.service
systemctl daemon-reload

# The CLI has to live at a path root controls. Left in $GAMECORE_PATH it would
# be writable by the GameCore user, and a sudoers rule pointing at a file that
# user can rewrite is not a restriction at all — it is a root shell with extra
# steps. /usr/local/bin is root-owned, and this is the same place
# gamecore-addon is installed to.
if [[ -f "${HERE}/gamecore-emu" ]]; then
  install -m 755 -o root -g root "${HERE}/gamecore-emu" /usr/local/bin/gamecore-emu
  EMU_RULE="${GC_USER} ALL=(root) NOPASSWD: /usr/local/bin/gamecore-emu"
else
  echo "⚠  install/bin/gamecore-emu not found — hot install will not be available."
  EMU_RULE=""
fi

SUDOERS_FILE="/etc/sudoers.d/gamecore-update"
{
  echo "${GC_USER} ALL=(root) NOPASSWD: /usr/bin/systemctl start --no-block gamecore-restart.service"
  [[ -n "$EMU_RULE" ]] && echo "$EMU_RULE"
} > "$SUDOERS_FILE"
chmod 440 "$SUDOERS_FILE"
visudo -cf "$SUDOERS_FILE" || { rm -f "$SUDOERS_FILE"; echo "sudoers validation failed, aborted"; exit 1; }

echo "✅ Permissions installed for user '${GC_USER}'."
echo "   Unit:    gamecore-restart.service"
echo "   Sudoers: ${SUDOERS_FILE}"
[[ -n "$EMU_RULE" ]] && echo "   CLI:     /usr/local/bin/gamecore-emu (hot install)"
