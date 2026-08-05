#!/usr/bin/env bash
# Generate EmberTV's TLS certificate NOW rather than at first service start.
#
# The next step imports it into the Firefox kiosk profile, and it can only
# import a certificate that exists. Doing it here is what makes the first
# launch free of a certificate warning — required for the unattended and ISO
# paths, where there is nobody in front of the TV to click "accept".
#
# Runs as the gaming user (postInstall always does), which is also the owner of
# /opt/Twitch-TV — see the pack's `sources` block.
set -uo pipefail

CHECKOUT=/opt/Twitch-TV

if [[ -f "$CHECKOUT/cert/cert.pem" ]]; then
  echo "certificate already present"
  exit 0
fi
if [[ ! -f "$CHECKOUT/make-cert.sh" ]]; then
  echo "no make-cert.sh in $CHECKOUT — the checkout is incomplete" >&2
  exit 1
fi
bash "$CHECKOUT/make-cert.sh" >/dev/null 2>&1
