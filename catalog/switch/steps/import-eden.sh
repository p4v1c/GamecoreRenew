#!/usr/bin/env bash
# Eden ran the Switch before Ryujinx: its keys, firmware and saves are the box's
# only copy. Copies what Ryujinx lacks; never writes to Eden.
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHONPATH="$GAMECORE_PATH" exec python3 eden_import.py \
  --home "$HOME" --gamecore-path "$GAMECORE_PATH" --gamecore-data "$GAMECORE_DATA"
