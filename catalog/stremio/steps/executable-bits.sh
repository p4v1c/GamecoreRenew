#!/usr/bin/env bash
# The tile launches `bash /opt/Stremio/stremio-tv.sh`, and that script execs the
# Python helpers beside it. git preserves the executable bit, so this is a
# repair rather than a step — but a checkout made through an archive, or a
# repository where the bit was never committed, produces a tile that opens
# nothing and says nothing. Cheap to make certain.
set -uo pipefail
DIR=/opt/Stremio
[[ -d "$DIR" ]] || { echo "no $DIR checkout" >&2; exit 1; }
chmod +x "$DIR"/stremio-tv.sh 2>/dev/null || true
chmod +x "$DIR"/*.py 2>/dev/null || true
