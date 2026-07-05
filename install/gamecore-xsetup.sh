#!/bin/sh
# GameCore — force 1920x1080 at the display-server level.
#
# Run by SDDM as root at X startup (via DisplayCommand), BEFORE any session,
# so the whole X server is pinned to 1080p: the GameCore kiosk, the emulators
# (fullscreen), and the overlay bezels (sized to a fixed 1920x1080 in
# electron/main.js) all inherit it. The box targets 1080p — a 4K TV would
# otherwise switch the session to 4K (perf hit + the overlay would only cover
# a quarter of the screen).
#
# Always exits 0: a failure here must never stop X from starting.

[ -x /usr/bin/xrandr ] || exit 0

OUT=$(xrandr 2>/dev/null | awk '/ connected/{print $1; exit}')
[ -n "$OUT" ] || exit 0

if ! xrandr --output "$OUT" --mode 1920x1080 2>/dev/null; then
    # EDID doesn't advertise 1080p (rare) — add a standard 60 Hz mode.
    if command -v cvt >/dev/null 2>&1; then
        TIMINGS=$(cvt 1920 1080 60 2>/dev/null | sed -n 's/^Modeline "[^"]*"//p')
        if [ -n "$TIMINGS" ]; then
            xrandr --newmode gc1080 $TIMINGS 2>/dev/null
            xrandr --addmode "$OUT" gc1080 2>/dev/null
            xrandr --output "$OUT" --mode gc1080 2>/dev/null
        fi
    fi
fi

exit 0
