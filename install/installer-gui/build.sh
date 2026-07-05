#!/usr/bin/env bash
# Build the standalone GameCore installer binary (PyInstaller onefile).
# Output: install/installer-gui/dist/gamecore-installer
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

VENV=".buildvenv"
[[ -x "$VENV/bin/python" ]] || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pyside6 pyinstaller

"$VENV/bin/pyinstaller" --noconfirm --clean --onefile --windowed \
  --name gamecore-installer gamecore_installer.py

echo
echo "→ Binary: $(pwd)/dist/gamecore-installer"
echo "  Ship it as a release asset; users just download and run it."
