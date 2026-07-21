#!/usr/bin/env bash
# ================================================================
#  GameCore — manual/rescue entry point for controller profiling.
#
#  The REAL, live mechanism is backend/services/gamepad_monitor.py:
#  every time a controller takes a NEW player slot (including at backend
#  startup), it calls controller_profiles.apply_profile() automatically —
#  whichever controller connects first becomes Player 1 for every
#  emulator, the second becomes Player 2, and so on, with the correct
#  native config for whatever TYPE of controller it actually is. No slot
#  is ever hardcoded to a brand. See docs/CONTROLLER_MODELS.md.
#
#  This script exists only to fix ALREADY-connected pads without having
#  to unplug/replug them (e.g. right after installing this feature, or as
#  a rescue tool if something needs re-applying by hand).
#
#  Usage:
#    install/apply-controller-model.sh                  # auto-detect, up to 4
#    install/apply-controller-model.sh 054c:0ce6         # force a single VID:PID as Player 1
#    install/apply-controller-model.sh 054c:0ce6 "PS5 Controller"
# ================================================================
set -euo pipefail

[[ $EUID -ne 0 ]] || { echo "Run me as the gaming user, not root."; exit 1; }

GAMECORE_PATH="${GAMECORE_PATH:-/opt/GameCore}"
PY="$GAMECORE_PATH/.venv/bin/python3"
[[ -x "$PY" ]] || { echo "Core venv not found at $PY — is GameCore installed?"; exit 1; }

cd "$GAMECORE_PATH"
exec "$PY" -m backend.services.controller_profiles "$@"
