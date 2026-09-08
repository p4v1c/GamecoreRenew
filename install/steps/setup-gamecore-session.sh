#!/usr/bin/env bash
# ================================================================
#  setup-gamecore-session.sh — install (or migrate to) the console session.
#
#  One implementation, called by two callers: `install/arch.sh` on a fresh box
#  and `update/linux.sh` on a box that already exists. That is deliberate — a
#  migration written separately from the installation is a migration that
#  drifts from it, and the drift is only ever discovered on somebody's console.
#
#  Idempotent by construction: every action is "make it be this", never "do
#  this again". Running it twice changes nothing the second time.
#
#  What it installs:
#    /usr/local/bin/gamecore-session          the session program
#    /usr/share/xsessions/gamecore.desktop    the session SDDM can pick
#    ~/.config/systemd/user/gamecore-session.target
#    ~/.config/systemd/user/gamecore-ui.service   (tokens expanded)
#
#  The legacy kiosk remains enabled until gamecore-session-select arms the session.
#
#  What it does NOT do: switch SDDM to the new session. Arming is a separate
#  decision with a separate rollback — `gamecore-session-select gamecore`.
#  A migration that changed how a box boots without being asked would be
#  discovered by the owner, on their television, at the worst moment.
#
#  Usage:
#    sudo ./setup-gamecore-session.sh <user> <GAMECORE_PATH> <GAMECORE_DATA> <port>
# ================================================================
set -euo pipefail

# Everything is written under DESTDIR when it is set, and the systemd and
# ownership calls are skipped. That is what lets the tests run this script for
# real rather than read it: the alternative is a test that needs root and a
# machine it is allowed to reconfigure, which is a test nobody runs.
DESTDIR="${DESTDIR:-}"
_live() { [[ -z "$DESTDIR" ]]; }

if _live && [[ $EUID -ne 0 ]]; then
  echo "Run me with sudo (or set DESTDIR to install into a staging tree)."
  exit 1
fi

GC_USER="${1:?usage: $0 <user> <gamecore-path> <gamecore-data> <port>}"
GC_PATH="${2:?usage: $0 <user> <gamecore-path> <gamecore-data> <port>}"
GC_DATA="${3:-$GC_PATH}"
GC_PORT="${4:-8765}"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_ROOT="$(cd "${HERE}/.." && pwd)"

USER_HOME="${GAMECORE_USER_HOME:-$(getent passwd "$GC_USER" | cut -d: -f6)}"
[[ -n "$USER_HOME" ]] || { echo "ERROR: no home for user '$GC_USER'"; exit 1; }
UNIT_DIR="${DESTDIR}${USER_HOME}/.config/systemd/user"
BIN_DIR="${DESTDIR}/usr/local/bin"
XSESSIONS_DIR="${DESTDIR}/usr/share/xsessions"

SESSION_SRC="${INSTALL_ROOT}/bin/gamecore-session"
DESKTOP_SRC="${INSTALL_ROOT}/system/gamecore.desktop"
UNITS_SRC="${INSTALL_ROOT}/system/user"

for f in "$SESSION_SRC" "$DESKTOP_SRC" "$UNITS_SRC/gamecore-session.target" "$UNITS_SRC/gamecore-ui.service" "$INSTALL_ROOT/bin/gamecore-session-select" "$INSTALL_ROOT/bin/gamecore-xsetup"; do
  [[ -e "$f" ]] || { echo "ERROR: missing $f"; exit 1; }
done

# Keep the first pre-migration state, including absent destinations. Every
# installed file has an executable undo command; repeated installs keep it.
# The shared backup directory must remain writable by the player, who also
# places the pre-update SQLite snapshot there. Leave existing ownership alone.
if [[ ! -d "${DESTDIR}${USER_HOME}/verif-avant" ]]; then
  if _live; then
    install -d -o "$GC_USER" -g "$GC_USER" -m 755 "${DESTDIR}${USER_HOME}/verif-avant"
  else
    mkdir -p "${DESTDIR}${USER_HOME}/verif-avant"
  fi
fi
BACKUP="${DESTDIR}${USER_HOME}/verif-avant/gamecore-session"
backup() {
  local dest="$1" key="${1#"$DESTDIR"}" saved
  saved="$BACKUP/files$key"
  [[ -e "$BACKUP/recorded$key" ]] && return 0
  mkdir -p "$(dirname "$saved")" "$(dirname "$BACKUP/recorded$key")"
  [[ -f "$BACKUP/restore.sh" ]] || printf '#!/bin/bash\nset -euo pipefail\n' > "$BACKUP/restore.sh"
  if [[ -e "$dest" || -L "$dest" ]]; then
    cp -a -- "$dest" "$saved"
    printf 'rm -f -- %q; cp -a -- %q %q\n' "$dest" "$saved" "$dest" >> "$BACKUP/restore.sh"
  else
    printf 'rm -f -- %q\n' "$dest" >> "$BACKUP/restore.sh"
  fi
  touch "$BACKUP/recorded$key"
}
for dest in "$BIN_DIR/gamecore-session" "$BIN_DIR/gamecore-session-select" \
            "$BIN_DIR/gamecore-xsetup" "$XSESSIONS_DIR/gamecore.desktop" \
            "$UNIT_DIR/gamecore-session.target" "$UNIT_DIR/gamecore-ui.service" \
            "$UNIT_DIR/gamecore-session.target.wants/gamecore-ui.service"; do
  backup "$dest"
done

# ── the session program and its entry ────────────────────────────
# /usr/local/bin, root-owned, like the other two CLIs: SDDM runs this as the
# session, and a session command inside a directory the session's own user can
# rewrite is not a session command, it is an invitation.
install -d -m 755 "$BIN_DIR" "$XSESSIONS_DIR"
if _live; then
  install -m 755 -o root -g root "$SESSION_SRC" "$BIN_DIR/gamecore-session"
  install -m 644 -o root -g root "$DESKTOP_SRC" "$XSESSIONS_DIR/gamecore.desktop"
else
  install -m 755 "$SESSION_SRC" "$BIN_DIR/gamecore-session"
  install -m 644 "$DESKTOP_SRC" "$XSESSIONS_DIR/gamecore.desktop"
fi
for name in gamecore-session-select gamecore-xsetup; do
  install -m 755 "$INSTALL_ROOT/bin/$name" "$BIN_DIR/$name"
done
echo "  ✓ /usr/local/bin/gamecore-session, /usr/share/xsessions/gamecore.desktop"

# ── the user units ───────────────────────────────────────────────
if _live; then
  install -d -o "$GC_USER" -g "$GC_USER" -m 755 "$UNIT_DIR" "$UNIT_DIR/gamecore-session.target.wants"
  install -m 644 -o "$GC_USER" -g "$GC_USER" \
    "$UNITS_SRC/gamecore-session.target" "$UNIT_DIR/gamecore-session.target"
else
  install -d -m 755 "$UNIT_DIR" "$UNIT_DIR/gamecore-session.target.wants"
  install -m 644 "$UNITS_SRC/gamecore-session.target" "$UNIT_DIR/gamecore-session.target"
fi

# The tokens are the pack convention (@GAMECORE_PATH@ …), for the same reason:
# a unit that hardcodes /opt/GameCore is a unit that lies on every box whose
# operator chose somewhere else.
sed -e "s|@GAMECORE_PATH@|${GC_PATH}|g" \
    -e "s|@GAMECORE_DATA@|${GC_DATA}|g" \
    -e "s|@BACKEND_PORT@|${GC_PORT}|g" \
    "$UNITS_SRC/gamecore-ui.service" > "$UNIT_DIR/gamecore-ui.service"
_live && chown "$GC_USER:$GC_USER" "$UNIT_DIR/gamecore-ui.service"
chmod 644 "$UNIT_DIR/gamecore-ui.service"

# Enabled by symlink rather than by `systemctl --user enable`: this runs as
# root, and the user manager it would have to talk to may not be running at
# all during an installation.
ln -sf ../gamecore-ui.service "$UNIT_DIR/gamecore-session.target.wants/gamecore-ui.service"
echo "  ✓ user units in $UNIT_DIR"

# Keep the old system service and its enablement unchanged. Merely installing
# a session must not remove the kiosk from the next desktop login.

# Install the privileged OTA entry points in the same preparation, including
# their root-owned copies. Future updates can refresh them through this unit.
for dest in "${DESTDIR}/etc/systemd/system/gamecore-restart.service" \
            "${DESTDIR}/etc/systemd/system/gamecore-session-migrate.service" \
            "${DESTDIR}/etc/sudoers.d/gamecore-update" \
            "$BIN_DIR/gamecore-emu" "$BIN_DIR/gamecore-restart" "$BIN_DIR/gamecore-session-migrate"; do
  backup "$dest"
done
bash "$HERE/setup-update-permissions.sh" "$GC_USER"

# ── Leaving the console session, from the console session ────────
#
# The interface's "Mode bureau" runs the switch as root through sudo, and
# sudoers matches a command line exactly: `desktop --restart-dm` is a different
# command from `desktop` and needs its own line. Written here rather than only
# in arch.sh because arch.sh runs on a fresh install and this runs on every
# update — a box armed before the flag existed would otherwise be refused the
# one command that gets it back out.
#
# Three enumerated commands, no wildcard: the script writes SDDM configuration
# and restarts the display manager as root, so "any argument" is not a thing to
# hand out.
SUDOERS_SESSION="${DESTDIR}/etc/sudoers.d/gamecore-session"
backup "$SUDOERS_SESSION"
SESSION_TMP=$(mktemp "${SUDOERS_SESSION}.XXXXXX")
{
  echo "# Installed by install/steps/setup-gamecore-session.sh — do not edit."
  echo "${GC_USER} ALL=(root) NOPASSWD: /usr/local/bin/gamecore-session-select gamecore"
  echo "${GC_USER} ALL=(root) NOPASSWD: /usr/local/bin/gamecore-session-select desktop"
  echo "${GC_USER} ALL=(root) NOPASSWD: /usr/local/bin/gamecore-session-select desktop --restart-dm"
} > "$SESSION_TMP"
chmod 440 "$SESSION_TMP"
if _live && ! visudo -cf "$SESSION_TMP" >/dev/null; then
  rm -f "$SESSION_TMP"
  echo "  ⚠ sudoers validation failed — 'Mode bureau' will not be able to leave."
else
  mv -f "$SESSION_TMP" "$SUDOERS_SESSION"
  echo "  ✓ sudoers: leaving the console session (${SUDOERS_SESSION#"$DESTDIR"})"
fi

echo "  Roll back installed files: sudo bash $BACKUP/restore.sh"

# SDDM/PAM starts the user manager for the graphical login. Linger belongs
# to the installer's background-daemon setup; this preparation does not alter it.

echo "✅ Console session installed for '${GC_USER}'."
echo "   Arm it with:  sudo gamecore-session-select gamecore"
echo "   Back out with: sudo gamecore-session-select desktop"
