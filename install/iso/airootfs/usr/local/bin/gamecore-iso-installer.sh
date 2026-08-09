#!/usr/bin/env bash
# Launch the GameCore wizard against the payload baked into the ISO.
#
# The wizard is the same install/installer-gui/gamecore_installer.py that ships
# as a PyInstaller binary on the release page — run from source here, against
# the distro's own PySide6. See packages.x86_64 for why that is the better half
# of the deal on an ISO.
set -uo pipefail

# Where build.sh stages the release. Everything the install needs is under it:
# the GameCore tree, the Python wheels and the prebuilt node_modules. Nothing
# below this line is allowed to reach the network.
GAMECORE_ISO_PAYLOAD="${GAMECORE_ISO_PAYLOAD:-/usr/share/gamecore}"
SRC="$GAMECORE_ISO_PAYLOAD/src"

fail() {
  echo "[gamecore-iso] $*" >&2
  # Held open on purpose. This runs as the only X client, so an exit here closes
  # the session and the message with it — the operator sees a flash and a
  # console. Refusing to die is what makes the message readable.
  echo "[gamecore-iso] press Enter for a shell." >&2
  read -r _ || true
  exec /usr/bin/bash --login
}

# The payload is staged at BUILD time, and its absence means the ISO was built
# without build.sh (mkarchiso run by hand on the profile). Everything downstream
# would then fail much later and much less clearly — the wizard would come up,
# collect an hour of choices, and die at the copy step.
[[ -d "$SRC/install" && -f "$SRC/install/arch.sh" ]] \
  || fail "no GameCore payload at $SRC — this ISO was not built by install/iso/build.sh."

export GAMECORE_ISO=1
export GAMECORE_ISO_PAYLOAD
# Read by gamecore_installer.py: with it set, the wizard skips its "download the
# latest release" engine entirely and installs from this tree.
export GAMECORE_SRC="$SRC"

exec python3 "$SRC/install/installer-gui/gamecore_installer.py"
