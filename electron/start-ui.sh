#!/usr/bin/env bash
USER_UID=$(id -u)

# Chromium reaches PipeWire/PulseAudio through the user runtime dir. Systemd
# services don't set XDG_RUNTIME_DIR, and without it the UI has no audio
# output at all (emulators are unaffected — Flatpak sets it for them).
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$USER_UID}"

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

# Hide the mouse cursor after 5s of inactivity — X11-wide, so it also applies
# inside emulators and the Firefox kiosk apps (YouTube/Twitch). Guarded so a
# gamecore-ui restart never spawns a second daemon. Arch's `unclutter` package
# is unclutter-xfixes (--timeout/--fork); the legacy syntax is the fallback.
if command -v unclutter >/dev/null 2>&1 && ! pgrep -x unclutter >/dev/null 2>&1; then
    unclutter --timeout 5 --ignore-scrolling --fork >/dev/null 2>&1 \
        || { unclutter -idle 5 >/dev/null 2>&1 & }
fi

# Resolve the install dir from this script's location — GAMECORE_PATH is not
# necessarily /opt/GameCore.
GC_ELECTRON="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$GC_ELECTRON/node_modules/.bin/electron" "$GC_ELECTRON/main.js"
