#!/usr/bin/env bash
# Bring up X on the live ISO and hand over to .xinitrc.
#
# Split out of .automated_script.sh so that the fallback path below is testable
# by reading it: when X will not start, the operator must land on a root shell
# WITH an explanation, not on a blank screen. A live ISO that fails silently is
# indistinguishable from a bad burn, and that is what gets reported.
set -uo pipefail
# Deliberately no `set -e`: every failure here has a handler, and the one thing
# this script must never do is exit without telling anyone why.

LOG=/var/log/gamecore-iso-session.log

say() { echo "[gamecore-iso] $*" | tee -a "$LOG"; }

# The live root is a squashfs+tmpfs overlay, so this file exists only in RAM —
# which is also why the fallback below prints the path: nobody will find it
# after a reboot, they have to look now.
: > "$LOG"

if ! command -v startx >/dev/null 2>&1; then
  say "xorg-xinit is not installed — cannot start the graphical installer."
  say "Install GameCore from this shell instead:"
  say "  gamecore-disk-install.sh --help"
  exec /usr/bin/bash --login
fi

say "Starting X for the GameCore installer…"
# vt1: startx picks a free VT on its own, and the one it picks is not the one
# the autologin is on. The session then comes up on a VT nobody is looking at,
# which reads as "it hung at the login prompt".
startx /root/.xinitrc -- vt1 >>"$LOG" 2>&1
rc=$?

# Reached when X exits: either the operator closed the installer, or X never
# came up. Both end here, and both need a usable machine afterwards.
if [[ $rc -ne 0 ]]; then
  say "X exited with status $rc — see $LOG for the server's own output."
  say "Try the 'safe graphics' entry from the boot menu, or install from here:"
  say "  gamecore-disk-install.sh --help"
fi

exec /usr/bin/bash --login
