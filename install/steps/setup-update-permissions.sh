#!/usr/bin/env bash
# One-time root setup for what the backend cannot do alone:
#   - gamecore-restart.service (system unit doing the restart)
#   - a sudoers drop-in letting the GameCore user, without a password:
#       · start ONLY that unit;
#       · run ONLY /usr/local/bin/gamecore-emu.
#
# gamecore-emu rather than `flatpak install`: a NOPASSWD flatpak rule would let
# the user install ANY app as root. gamecore-emu refuses ids the catalogue does
# not declare, and config/catalog.d/ packs are data-only (no generator,
# postInstall, services…), so the rule cannot run arbitrary code.
#
# Usage:  sudo ./setup-update-permissions.sh [gamecore-user]
set -euo pipefail

DESTDIR="${DESTDIR:-}"
_live() { [[ -z "$DESTDIR" ]]; }

[[ $EUID -eq 0 || -n "$DESTDIR" ]] || { echo "Run me with sudo."; exit 1; }

GC_USER="${1:-${SUDO_USER:-}}"
[[ -n "$GC_USER" ]] || { echo "usage: sudo $0 <gamecore-user>"; exit 1; }
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# One directory per KIND of file, so neither of these sits beside this script:
# `install/steps/` holds steps, the unit lives in `install/system/` and the CLI
# in `install/bin/`. Both paths were `${HERE}/…` until the reorganisation moved
# the files and left the references behind — see the failure below.
INSTALL_ROOT="$(cd "${HERE}/.." && pwd)"
UNIT_SRC="${INSTALL_ROOT}/system/gamecore-restart.service"
MIGRATE_SRC="${INSTALL_ROOT}/system/gamecore-session-migrate.service"
EMU_SRC="${INSTALL_ROOT}/bin/gamecore-emu"

# Fatal, and it did not used to be. With no `set -e`, a failed `install` here
# printed one line, carried on, wrote a sudoers file holding only half the
# rules, and exited 0 — so arch.sh answered "OTA restart permissions
# installed." for a step that had installed neither the unit nor the CLI.
#
# Every box built after the reorganisation therefore came up with no
# gamecore-restart.service (the OTA cannot restart itself) and no
# /usr/local/bin/gamecore-emu (installing an emulator from the interface
# silently does nothing), announced as a success. A green tick on a step that
# did not run is worse than the red one it replaced.
[[ -f "$UNIT_SRC" ]] || { echo "ERROR: missing $UNIT_SRC"; exit 1; }

install -d "${DESTDIR}/etc/systemd/system" "${DESTDIR}/etc/sudoers.d" "${DESTDIR}/usr/local/bin"
RESTART_HELPER_SRC="${INSTALL_ROOT}/bin/gamecore-restart"
MIGRATE_HELPER_SRC="${INSTALL_ROOT}/bin/gamecore-session-migrate"
install -m 755 "$RESTART_HELPER_SRC" "${DESTDIR}/usr/local/bin/gamecore-restart"
install -m 755 "$MIGRATE_HELPER_SRC" "${DESTDIR}/usr/local/bin/gamecore-session-migrate"
install -m 644 "$UNIT_SRC" "${DESTDIR}/etc/systemd/system/gamecore-restart.service" \
  || { echo "ERROR: could not install gamecore-restart.service"; exit 1; }

# The console-session migration, same shape and same reasoning: the updater
# runs unprivileged, this writes to /usr/local/bin and /usr/share/xsessions.
# Its arguments come from the root-owned manifest, so the rule below grants one
# action with one set of arguments rather than a script with a free parameter.
[[ -f "$MIGRATE_SRC" ]] || { echo "ERROR: missing $MIGRATE_SRC"; exit 1; }
install -m 644 "$MIGRATE_SRC" "${DESTDIR}/etc/systemd/system/gamecore-session-migrate.service" \
  || { echo "ERROR: could not install gamecore-session-migrate.service"; exit 1; }
if _live; then systemctl daemon-reload; fi

# The CLI has to live at a path root controls. Left in $GAMECORE_PATH it would
# be writable by the GameCore user, and a sudoers rule pointing at a file that
# user can rewrite is not a restriction at all — it is a root shell with extra
# steps. /usr/local/bin is root-owned, and this is the same place
# gamecore-addon is installed to.
if [[ -f "$EMU_SRC" ]]; then
  if _live; then
    install -m 755 -o root -g root "$EMU_SRC" "${DESTDIR}/usr/local/bin/gamecore-emu"
  else
    install -m 755 "$EMU_SRC" "${DESTDIR}/usr/local/bin/gamecore-emu"
  fi
  EMU_RULE="${GC_USER} ALL=(root) NOPASSWD: /usr/local/bin/gamecore-emu"
else
  echo "⚠  $EMU_SRC not found — hot install will not be available."
  EMU_RULE=""
fi

SUDOERS_FILE="${DESTDIR}/etc/sudoers.d/gamecore-update"
SUDOERS_TMP=$(mktemp "${SUDOERS_FILE}.XXXXXX")
trap 'rm -f "$SUDOERS_TMP"' EXIT
{
  echo "${GC_USER} ALL=(root) NOPASSWD: /usr/bin/systemctl start --no-block gamecore-restart.service"
  echo "${GC_USER} ALL=(root) NOPASSWD: /usr/bin/systemctl start gamecore-session-migrate.service"
  [[ -n "$EMU_RULE" ]] && echo "$EMU_RULE"
} > "$SUDOERS_TMP"
chmod 440 "$SUDOERS_TMP"
if _live; then visudo -cf "$SUDOERS_TMP" || { echo "sudoers validation failed, aborted"; exit 1; }; fi
mv -f "$SUDOERS_TMP" "$SUDOERS_FILE"

echo "✅ Permissions installed for user '${GC_USER}'."
echo "   Units:   gamecore-restart.service, gamecore-session-migrate.service"
echo "   Sudoers: ${SUDOERS_FILE}"
[[ -n "$EMU_RULE" ]] && echo "   CLI:     /usr/local/bin/gamecore-emu (hot install)"
