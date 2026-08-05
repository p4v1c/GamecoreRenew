#!/usr/bin/env bash
# Trust EmberTV's self-signed certificate inside the twitch-tv Firefox profile.
#
# The profile is a plain directory launched with `firefox --profile <dir>`, so
# there is no profiles.ini to register and no flaky -CreateProfile run. Its NSS
# database may not exist yet on a fresh box: create an empty one, then import.
#
# Every step is tolerant on purpose. A certificate hiccup costs one warning at
# first launch; it must never be the reason an install is reported as failed.
set -uo pipefail

CERT=/opt/Twitch-TV/cert/cert.pem
PROFILE="$HOME/.mozilla/firefox/twitch-tv"
NICK="EmberTV localhost"

[[ -f "$CERT" ]]              || { echo "no certificate to trust yet" >&2; exit 1; }
command -v certutil >/dev/null || { echo "certutil not installed (nss)" >&2; exit 1; }

mkdir -p "$PROFILE"
if [[ ! -f "$PROFILE/cert9.db" ]]; then
  certutil -N --empty-password -d sql:"$PROFILE" \
    || { echo "NSS database init failed" >&2; exit 1; }
fi

# Delete before adding: re-running the installer after the cert was regenerated
# would otherwise leave the OLD one trusted under the same nickname.
certutil -D -n "$NICK" -d sql:"$PROFILE" 2>/dev/null || true
certutil -A -n "$NICK" -t "P,," -i "$CERT" -d sql:"$PROFILE"
