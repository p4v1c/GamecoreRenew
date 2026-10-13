#!/usr/bin/env bash
# ================================================================
#  setup-rest-mode.sh — the root pieces of Rest mode.
#
#    /etc/sudoers.d/gamecore-rest            the backend may run `systemctl suspend`
#    /usr/local/bin/gamecore-wake-setup      arms USB wake on the BT adapter and pads
#    /etc/systemd/system/gamecore-wake.service   runs it at every boot (enabled)
#    /etc/udev/rules.d/90-gamecore-wake.rules    and for devices plugged in later
#    /etc/systemd/logind.conf.d/90-gamecore.conf power key sleeps; 15 s to close games
#
#  Called by setup-gamecore-session.sh, so a fresh install (arch.sh) and every
#  OTA (gamecore-session-migrate.service) both run it. Idempotent: a file is
#  replaced only when its content changed, and only a change reloads or
#  re-runs anything.
#
#  Usage:  sudo ./setup-rest-mode.sh <gamecore-user>
#  DESTDIR stages everything under a directory and skips systemd/udev (tests).
# ================================================================
set -euo pipefail

DESTDIR="${DESTDIR:-}"
_live() { [[ -z "$DESTDIR" ]]; }

[[ $EUID -eq 0 || -n "$DESTDIR" ]] || { echo "Run me with sudo."; exit 1; }
GC_USER="${1:?usage: $0 <gamecore-user>}"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_ROOT="$(cd "${HERE}/.." && pwd)"
HELPER_SRC="${INSTALL_ROOT}/bin/gamecore-wake-setup"
UNIT_SRC="${INSTALL_ROOT}/system/gamecore-wake.service"
RULE_SRC="${INSTALL_ROOT}/system/90-gamecore-wake.rules"
LOGIND_SRC="${INSTALL_ROOT}/system/logind-gamecore.conf"

HELPER="${DESTDIR}/usr/local/bin/gamecore-wake-setup"
UNIT="${DESTDIR}/etc/systemd/system/gamecore-wake.service"
WANTS="${DESTDIR}/etc/systemd/system/multi-user.target.wants"
RULE="${DESTDIR}/etc/udev/rules.d/90-gamecore-wake.rules"
SUDOERS="${DESTDIR}/etc/sudoers.d/gamecore-rest"
LOGIND_CONF="${DESTDIR}/etc/systemd/logind.conf.d/90-gamecore.conf"

for f in "$HELPER_SRC" "$UNIT_SRC" "$RULE_SRC" "$LOGIND_SRC"; do
  [[ -f "$f" ]] || { echo "ERROR: missing $f"; exit 1; }
done

# Copy $1 to $2 with mode $3 unless identical. Exit 0 = changed, 1 = unchanged.
install_if_changed() {
  if [[ -f "$2" ]] && cmp -s "$1" "$2"; then
    return 1
  fi
  install -d -m 755 "$(dirname "$2")"
  if _live; then
    install -m "$3" -o root -g root "$1" "$2"
  else
    install -m "$3" "$1" "$2"
  fi
  return 0
}

changed_unit=false changed_helper=false changed_rule=false changed_logind=false
install_if_changed "$UNIT_SRC" "$UNIT" 644 && changed_unit=true
install_if_changed "$HELPER_SRC" "$HELPER" 755 && changed_helper=true
install_if_changed "$RULE_SRC" "$RULE" 644 && changed_rule=true
install_if_changed "$LOGIND_SRC" "$LOGIND_CONF" 644 && changed_logind=true

# Enabled by symlink: during an install the manager may not be answering.
install -d -m 755 "$WANTS"
ln -sfn ../gamecore-wake.service "$WANTS/gamecore-wake.service"

# Exactly one command, no argument left open.
SUDOERS_TMP="$(mktemp)"
trap 'rm -f "$SUDOERS_TMP"' EXIT
{
  echo "# Installed by install/steps/setup-rest-mode.sh — do not edit."
  echo "${GC_USER} ALL=(root) NOPASSWD: /usr/bin/systemctl suspend"
} > "$SUDOERS_TMP"
if [[ -f "$SUDOERS" ]] && cmp -s "$SUDOERS_TMP" "$SUDOERS"; then
  echo "  ✓ sudoers: rest mode (unchanged)"
elif _live && ! visudo -cf "$SUDOERS_TMP" >/dev/null; then
  echo "  ⚠ sudoers validation failed: Rest mode will not be able to sleep."
else
  install -d -m 755 "$(dirname "$SUDOERS")"
  install -m 440 "$SUDOERS_TMP" "$SUDOERS"
  echo "  ✓ sudoers: rest mode (${SUDOERS#"$DESTDIR"})"
fi

if _live; then
  if $changed_unit; then systemctl daemon-reload; fi
  # Applied now, so the first update arms wake without waiting for a reboot.
  if $changed_unit || $changed_helper || ! systemctl is-active --quiet gamecore-wake.service; then
    systemctl restart gamecore-wake.service \
      || echo "  ⚠ gamecore-wake.service failed (see journalctl -u gamecore-wake)"
  fi
  if $changed_rule; then udevadm control --reload || true; fi
  # Reload, never restart: restarting logind ends the graphical session.
  # Reload is SIGHUP, which only a logind that declares it (systemd 254+)
  # handles; on an older one SIGHUP would kill it, so it waits for a boot.
  if $changed_logind; then
    if [[ "$(systemctl show -p CanReload --value systemd-logind.service 2>/dev/null)" == "yes" ]]; then
      systemctl reload systemd-logind.service \
        || echo "  ⚠ logind did not reload: the power key change applies at the next boot"
    else
      echo "  ⚠ logind cannot reload here: the power key change applies at the next boot"
    fi
  fi
fi
echo "  ✓ rest mode: wake helper, gamecore-wake.service, udev rule, logind drop-in"
