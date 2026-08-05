"""The games that are DIRECTORIES, and what they call themselves.

Split out of gamemedia.py. PS3, PS4 and decompressed PSP dumps are not files
but directory trees, usually named by serial — `BLUS30443` tells a scraper
nothing. The real title sits in a PARAM.SFO inside the tree, so it is read from
there instead of guessed from the directory name.

Imported by gamemedia.py, which re-exports every public name below — no caller
outside this package changes an import.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

# ── Local identity: the games that are DIRECTORIES ──────────────────────────
#
# PS3, PS4 and decompressed PSP dumps are not files but directory trees.
# Consequence: no hash is possible (a directory has none), and the directory name
# is whatever the user felt like typing.
#
# Measured against the API on "Uncharted 2":
#
#   romnom = directory name "Uncharted 2"          → 404
#   romnom = TITLE from PARAM.SFO                   → 200, 152 media
#   romnom = TITLE_ID "BCES00509"                  → 404
#   serialnum = TITLE_ID                           → 404
#   romtype=folder                                 → 404
#
# So the right key is the TITLE the game gives itself, read from its PARAM.SFO.
# It is also a better input for LaunchBox than the directory name. The serial is
# only useful for tracing, the API does not accept it.

_SFO_PATHS = ("PS3_GAME/PARAM.SFO", "PARAM.SFO", "sce_sys/param.sfo",
              "PSP_GAME/PARAM.SFO", "PS3_GAME/PARAM.sfo")
# ™ and ® are in the SFO but not in the ScreenScraper database.
_SFO_NOISE = str.maketrans({"™": "", "®": "", "©": "", " ": " "})


def read_sfo(folder: Path) -> dict[str, str]:
    """{TITLE, TITLE_ID, …} from a game directory's PARAM.SFO, or {}.

    A minimal reader, deliberately copied here rather than imported from
    GameCore: this script must run on its own, on any machine, dependency-free.
    """
    import struct
    for rel in _SFO_PATHS:
        p = folder / rel
        try:
            if not p.is_file() or p.stat().st_size > 1 << 20:   # a real SFO is KB
                continue
            raw = p.read_bytes()
        except OSError:
            continue
        try:
            magic, _ver, key_tbl, data_tbl, count = struct.unpack_from("<4sIIII", raw, 0)
            if magic != b"\x00PSF":
                continue
            out: dict[str, str] = {}
            for i in range(min(count, 512)):
                k_off, fmt, length, _max, d_off = struct.unpack_from("<HHIII", raw, 20 + 16 * i)
                key = raw[key_tbl + k_off:raw.index(b"\x00", key_tbl + k_off)].decode(
                    "utf-8", "replace")
                blob = raw[data_tbl + d_off:data_tbl + d_off + length]
                if fmt == 0x0404:                              # entier 32 bits
                    out[key] = str(struct.unpack("<I", blob[:4])[0])
                else:                                          # UTF-8 string
                    out[key] = blob.split(b"\x00", 1)[0].decode("utf-8", "replace")
            return out
        except (struct.error, ValueError, IndexError):
            continue
    return {}


def local_identity(target: Path) -> dict[str, str]:
    """Title and serial the game gives itself, when it is a directory."""
    if not target.is_dir():
        return {}
    meta = read_sfo(target)
    title = (meta.get("TITLE") or "").translate(_SFO_NOISE)
    # An SFO TITLE is sometimes MULTILINE: Uncharted 3 declares itself
    # "Uncharted 3: Drake's Deception\nGame of the Year". Sent as is, the romnom
    # gave a 404; truncated to its first line, 141 media.
    title = re.sub(r"\s+", " ", title.split("\n")[0]).strip()
    return {"title": title, "serial": (meta.get("TITLE_ID") or "").strip()} if title else {}
