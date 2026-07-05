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

# ── Force 1920x1080 ──────────────────────────────────────────────────────────
# The box targets 1080p. On a 4K TV the whole session (UI, games, overlays)
# would otherwise switch to 4K: a perf hit, and the overlay bezels — sized to
# a fixed 1920x1080 in electron/main.js — would only cover a quarter of the
# screen. Pin the connected output to 1080p; games and overlays inherit it.
force_1080p() {
    command -v xrandr >/dev/null 2>&1 || return 0
    local out
    out=$(xrandr 2>/dev/null | awk '/ connected/{print $1; exit}')
    [[ -n "$out" ]] || return 0
    xrandr --output "$out" --mode 1920x1080 2>/dev/null && return 0
    # EDID doesn't advertise 1080p (rare) — add a standard 60 Hz mode.
    command -v cvt >/dev/null 2>&1 || return 0
    local timings
    timings=$(cvt 1920 1080 60 2>/dev/null | sed -n 's/^Modeline "[^"]*"//p')
    [[ -n "$timings" ]] || return 0
    xrandr --newmode gc1080 $timings 2>/dev/null
    xrandr --addmode "$out" gc1080 2>/dev/null
    xrandr --output "$out" --mode gc1080 2>/dev/null
}
force_1080p

exec /opt/GameCore/electron/node_modules/.bin/electron /opt/GameCore/electron/main.js
