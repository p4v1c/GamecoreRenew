"""Minimal PARAM.SFO reader (title, serial, version, category).

Same binary format on PS3, PS4 and PSP — mirrored from the rpcs3-manager
addon so the core backend can read game metadata without the addon.
"""
import logging
import struct
from pathlib import Path

log = logging.getLogger(__name__)


def parse_bytes(d: bytes) -> dict:
    """Return the PARAM.SFO key/value table ({} on any error)."""
    try:
        magic, _ver, key_tbl, data_tbl, count = struct.unpack_from("<4sIIII", d, 0)
        if magic != b"\x00PSF":
            return {}
        out = {}
        for i in range(count):
            key_off, fmt, length, _max, data_off = struct.unpack_from("<HHIII", d, 20 + i * 16)
            key = d[key_tbl + key_off : d.index(b"\x00", key_tbl + key_off)].decode()
            raw = d[data_tbl + data_off : data_tbl + data_off + length]
            if fmt in (0x0204, 0x0004):  # utf8 / non-terminated utf8
                out[key] = raw.rstrip(b"\x00").decode("utf-8", "replace")
            else:  # 0x0404 — uint32
                out[key] = struct.unpack("<I", raw[:4])[0]
        return out
    except Exception:
        return {}


# A real PARAM.SFO is a few kilobytes. The cap is here because read_bytes()
# had none and the file comes from a game dump: a 512 MB PARAM.SFO took the
# backend's RSS from 43 MB to 540 MB, measured, and the prefetch loop reads one
# per game.
_MAX_SFO_BYTES = 1024 * 1024


def parse(path: Path) -> dict:
    try:
        if path.stat().st_size > _MAX_SFO_BYTES:
            log.warning("sfo: %s is %d bytes — too large to be a PARAM.SFO, ignoring",
                        path, path.stat().st_size)
            return {}
        return parse_bytes(path.read_bytes())
    except Exception:
        return {}
