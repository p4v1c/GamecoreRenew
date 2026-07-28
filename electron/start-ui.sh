#!/usr/bin/env bash
USER_UID=$(id -u)

# Chromium reaches PipeWire/PulseAudio through the user runtime dir. Systemd
# services don't set XDG_RUNTIME_DIR, and without it the UI has no audio
# output at all (emulators are unaffected — Flatpak sets it for them).
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$USER_UID}"

# ── Find the live X display and its auth cookie ──────────────────────────────
# Where the cookie lives depends on who started X, and getting this wrong means
# the kiosk never appears:
#   · SDDM's X11 session  → /tmp/xauth_XXXXXX   (QTemporaryFile, owned by the user)
#   · kwin_wayland/Xwayland → /run/user/<uid>/xauth_XXXXXX
#   · a plain startx      → ~/.Xauthority
# Search all three, newest first, and never assume — every candidate is proved
# by actually connecting to the display with it.
candidates=()
while IFS= read -r c; do
    [[ -n "$c" ]] && candidates+=("$c")
done < <(find /tmp "/run/user/$USER_UID" -maxdepth 1 -name 'xauth_*' -uid "$USER_UID" \
              -printf '%T@ %p\n' 2>/dev/null | sort -rn | cut -d' ' -f2-)
[[ -f "$HOME/.Xauthority" ]] && candidates+=("$HOME/.Xauthority")
# An XAUTHORITY inherited from the environment is the best hint of all.
[[ -n "${XAUTHORITY:-}" && -f "${XAUTHORITY}" ]] && candidates=("$XAUTHORITY" ${candidates[@]+"${candidates[@]}"})

# Displays actually listening, rather than a hardcoded guess.
displays=()
for sock in /tmp/.X11-unix/X*; do
    [[ -e "$sock" ]] && displays+=(":${sock##*/X}")
done
[[ ${#displays[@]} -gt 0 ]] || displays=(:0 :1 :2)

found=false
for D in "${displays[@]}"; do
    for XA in ${candidates[@]+"${candidates[@]}"} __none__; do
        if [[ "$XA" == "__none__" ]]; then
            # No cookie at all: some servers accept a local connection anyway.
            # Note this must UNSET XAUTHORITY, never set it to "" — an empty
            # value makes Xau skip ~/.Xauthority too.
            if env -u XAUTHORITY DISPLAY="$D" xdpyinfo >/dev/null 2>&1; then
                unset XAUTHORITY; export DISPLAY="$D"; found=true; break 2
            fi
        elif XAUTHORITY="$XA" DISPLAY="$D" xdpyinfo >/dev/null 2>&1; then
            export XAUTHORITY="$XA"; export DISPLAY="$D"; found=true; break 2
        fi
    done
done
if ! $found; then
    echo "start-ui: no reachable X display (tried ${displays[*]}) — is the session X11?" >&2
    exit 1
fi

# Hide the mouse cursor after 5s of inactivity — X11-wide, so it also applies
# inside emulators and the Firefox kiosk apps (YouTube/Twitch). Guarded so a
# gamecore-ui restart never spawns a second daemon. Arch's `unclutter` package
# is unclutter-xfixes (--timeout/--fork); the legacy syntax is the fallback.
if command -v unclutter >/dev/null 2>&1 && ! pgrep -x unclutter >/dev/null 2>&1; then
    unclutter --timeout 5 --ignore-scrolling --fork >/dev/null 2>&1 \
        || { unclutter -idle 5 >/dev/null 2>&1 & }
fi

# Re-pin 1920x1080 inside the session. SDDM's DisplayCommand already did it
# for the bare X server, but Plasma's KScreen module loads afterwards and
# applies the output's EDID-preferred mode — 3840x2160 on a 4K TV — undoing
# it. By the time this runs the session (and kded) is up, so the mode sticks.
# The bezel overlays in main.js are sized to a fixed 1920x1080 and would
# otherwise cover a quarter of the screen.
[ -x /usr/local/bin/gamecore-xsetup ] && /usr/local/bin/gamecore-xsetup >/dev/null 2>&1

# Resolve the install dir from this script's location — GAMECORE_PATH is not
# necessarily /opt/GameCore.
GC_ELECTRON="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# node_modules/.bin/electron is created by npm. When the installer had to
# provision the binary by hand (npm postinstall skipped or npm failed), that
# symlink can be missing — fall back to the real binary rather than dying.
ELECTRON_BIN="$GC_ELECTRON/node_modules/.bin/electron"
[ -e "$ELECTRON_BIN" ] || ELECTRON_BIN="$GC_ELECTRON/node_modules/electron/dist/electron"
exec "$ELECTRON_BIN" "$GC_ELECTRON/main.js"
