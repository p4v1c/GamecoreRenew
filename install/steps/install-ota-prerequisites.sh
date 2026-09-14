#!/usr/bin/env bash
# Install the small, reviewed set of distribution packages that shipped code
# now requires on boxes which already exist.
#
# This is deliberately not a general package hook.  An OTA may add an exact
# package name here, but it cannot pass a package, a repository or pacman
# arguments at runtime.  The existing root-owned session-migration unit calls
# this step; update/linux.sh itself remains unprivileged.
set -euo pipefail

DESTDIR="${DESTDIR:-}"
PACMAN="${GAMECORE_PACMAN:-pacman}"
PKG_MANIFEST="${GAMECORE_PKG_MANIFEST:-${DESTDIR}/var/lib/gamecore/pacman-installed}"

if [[ $EUID -ne 0 && -z "$DESTDIR" ]]; then
  echo "Run me as root (or set DESTDIR for a fixture)." >&2
  exit 1
fi

# A staged session install must never query or alter its host's package DB.
# Tests which exercise this step under DESTDIR provide a pacman fixture.
if [[ -n "$DESTDIR" && -z "${GAMECORE_PACMAN:-}" ]]; then
  echo "  · system prerequisites skipped in staged tree"
  exit 0
fi

# Exact names only.  No full-system upgrade: a feature prerequisite is not
# authority to roll the distribution underneath a living-room box.
REQUIRED=(p7zip)
missing=()
for package in "${REQUIRED[@]}"; do
  "$PACMAN" -Qq "$package" >/dev/null 2>&1 || missing+=("$package")
done

if (( ${#missing[@]} == 0 )); then
  echo "  ✓ OTA system prerequisites already installed"
  exit 0
fi

echo "  · installing OTA system prerequisites: ${missing[*]}"
"$PACMAN" -S --noconfirm --needed "${missing[@]}"

# uninstall.sh removes only packages GameCore itself added.  Record after a
# successful install: a failed pacman must not claim ownership of anything.
mkdir -p "$(dirname "$PKG_MANIFEST")"
touch "$PKG_MANIFEST"
for package in "${missing[@]}"; do
  grep -qxF "$package" "$PKG_MANIFEST" 2>/dev/null \
    || printf '%s\n' "$package" >> "$PKG_MANIFEST"
done
echo "  ✓ OTA system prerequisites installed"
