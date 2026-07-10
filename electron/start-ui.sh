#!/usr/bin/env bash
USER_UID=$(id -u)

for D in :1 :0 :2; do
    XAUTH_TRY=$(find /run/user/$USER_UID -name "xauth_*" 2>/dev/null | head -1)
    if XAUTHORITY="$XAUTH_TRY" xdpyinfo -display "$D" >/dev/null 2>&1; then
        export DISPLAY="$D"
        break
    fi
done

XAUTH=$(find /run/user/$USER_UID -name "xauth_*" 2>/dev/null | head -1)
if [[ -n "$XAUTH" ]]; then
    export XAUTHORITY="$XAUTH"
elif [[ -f "$HOME/.Xauthority" ]]; then
    export XAUTHORITY="$HOME/.Xauthority"
fi

# Resolve the install dir from this script's location — GAMECORE_PATH is not
# necessarily /opt/GameCore.
GC_ELECTRON="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$GC_ELECTRON/node_modules/.bin/electron" "$GC_ELECTRON/main.js"
