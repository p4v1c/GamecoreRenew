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
#  What it retires, and this is the part that must not be half-done:
#    the SYSTEM gamecore-ui.service is disabled AND masked. Two units starting
#    two Electrons against one X server is the failure this step exists to make
#    impossible, and "disabled" alone is not enough — anything that calls
#    `systemctl start gamecore-ui` (gamecore-launcher did, for years) would
#    bring the old one back on top of the new one.
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

for f in "$SESSION_SRC" "$DESKTOP_SRC" "$UNITS_SRC/gamecore-session.target" "$UNITS_SRC/gamecore-ui.service"; do
  [[ -e "$f" ]] || { echo "ERROR: missing $f"; exit 1; }
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

# ── the old system unit, retired ─────────────────────────────────
#
# Masked, not merely disabled. `gamecore-launcher` and every habit built around
# it call `systemctl start gamecore-ui.service`; on a migrated box that would
# start a second Electron over the session's own, against the same X server and
# the same backend. Masking makes that call fail loudly instead.
OLD_UNIT="${DESTDIR}/etc/systemd/system/gamecore-ui.service"
if [[ -f "$OLD_UNIT" ]]; then
  _live && { systemctl disable --now gamecore-ui.service 2>/dev/null || true; }
  # The unit file is kept, moved aside: an operator rolling back wants it, and
  # the uninstaller needs to know it was ours.
  mv -f "$OLD_UNIT" "${OLD_UNIT}.pre-session" 2>/dev/null || true
fi
if _live; then
  systemctl mask gamecore-ui.service 2>/dev/null || true
  systemctl daemon-reload
fi
echo "  ✓ the system-wide gamecore-ui.service is stopped and masked"

# ── linger ───────────────────────────────────────────────────────
# The user manager must exist before the session starts, because the session
# talks to it. It is already enabled on every box that has addons or a pack
# daemon; doing it here makes the session independent of that.
_live && { loginctl enable-linger "$GC_USER" 2>/dev/null || true; }

echo "✅ Console session installed for '${GC_USER}'."
echo "   Arm it with:  sudo gamecore-session-select gamecore"
echo "   Back out with: sudo gamecore-session-select desktop"
