#!/usr/bin/env bash
# Read-only preflight. Never replace running code if its privileged migration
# cannot be called afterwards. Paths can be staged by tests.
set -euo pipefail
units="${GAMECORE_SYSTEM_UNITS:-/etc/systemd/system}"
bins="${GAMECORE_SYSTEM_BINS:-/usr/local/bin}"
missing=false
for file in "$units/gamecore-session-migrate.service" "$units/gamecore-restart.service" \
            "$bins/gamecore-session-migrate" "$bins/gamecore-restart" \
            "$bins/gamecore-session-select"; do
  [[ -f "$file" ]] || missing=true
done
# Merely being allowed with a password is insufficient for an unattended OTA.
permissions=$(sudo -n -l 2>/dev/null || true)
for command in 'start gamecore-session-migrate.service' 'start --no-block gamecore-restart.service'; do
  if ! printf '%s\n' "$permissions" | grep 'NOPASSWD:' | grep -Fq "/usr/bin/systemctl $command"; then
    missing=true
  fi
done
# The manifest the migration reads is not on every box — one installed before
# it existed has none — so this asks the helper itself whether it can resolve
# an installation, rather than testing for a file. One implementation: the
# preflight and the real run cannot disagree about whether this box can be
# migrated, which is exactly what happened on the reference machine when they
# could: every file was in place, the check passed, and the migration died on
# a missing manifest AFTER the code had been replaced.
if [[ -x "$bins/gamecore-session-migrate" ]] \
   && ! "$bins/gamecore-session-migrate" --check >/dev/null 2>&1; then
  echo '[update] ERROR: the console migration cannot tell where this installation is.'
  echo '[update] No running code has been replaced.'
  echo "[update] Diagnose with:  $bins/gamecore-session-migrate --check"
  exit 1
fi

if $missing; then
  echo '[update] ERROR: this installation needs the one-time console/OTA preparation.'
  echo '[update] No running code has been replaced.'
  echo '[update] From the NEW release checkout, run as administrator:'
  echo '[update]   sudo bash install/steps/setup-gamecore-session.sh <user> <install-path> <data-path> <port>'
  echo '[update] This keeps the legacy kiosk running and does not arm the console.'
  exit 1
fi
