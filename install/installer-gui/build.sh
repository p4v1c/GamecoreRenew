#!/usr/bin/env bash
# Build the standalone GameCore installer binary (PyInstaller onefile).
# Output: install/installer-gui/dist/gamecore-installer
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

VENV=".buildvenv"
[[ -x "$VENV/bin/python" ]] || python3 -m venv "$VENV"
# Pinned to exactly what .github/workflows/release.yml builds with. A binary
# built here that behaves differently from the released one is worse than no
# local build at all — the whole point of testing it is that it is the same.
"$VENV/bin/pip" install -q 'pyside6==6.11.1' 'pyinstaller==6.21.0'

# The .spec carries the onefile/windowed settings AND the list of libraries that
# must NOT be bundled — see the comment at its top. There is no CLI flag for the
# second, so building without the spec silently reintroduces the crash it fixes.
"$VENV/bin/pyinstaller" --noconfirm --clean gamecore-installer.spec

echo
echo "→ Binary: $(pwd)/dist/gamecore-installer"
echo "  Ship it as a release asset; users just download and run it."
echo
echo "  Test it by typing a letter into a field on a ROLLING distro"
echo "  (Arch/Manjaro): that is where the runner-vs-host library gap bites,"
echo "  and a bundle carrying libxkbcommon again segfaults on the first key."
