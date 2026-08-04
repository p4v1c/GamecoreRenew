"""mGBA (GBA) — snapshot restore.

mgba keeps the ACTIVE binding table in [gba.input.SDLB] — every keyA/keyL/hat0
lives there, along with `device0=`, the GUID of the pad it belongs to. The
per-GUID [gba.input-profile.<GUID>] sections hold tilt and gyro axes and
nothing else.

The snapshot used to capture `device0=` plus that GUID section, i.e. six gyro
keys and not one button: 180 bytes on the reference box, for both saved
controllers. "Scan mapping" reported success, restore announced "restored saved
mapping", and no button ever moved.
"""
from __future__ import annotations

from backend.services.configgen import snapshots

from backend.services.configgen.helpers.ini import (
    iter_sections, replace_section, section_bounds,
)

EMU_ID = "mgba"


def _mgba_extract(text: str) -> str:
    lines = text.splitlines(keepends=True)
    s, e = section_bounds(lines, "gba.input.SDLB")
    if s is None:
        return ""
    block = "".join(lines[s:e])
    guid = next((l.split("=", 1)[1].strip() for l in lines[s:e]
                 if l.startswith("device0=")), "")
    if guid:
        gs, ge = section_bounds(lines, f"gba.input-profile.{guid}")
        if gs is not None:
            block += "".join(lines[gs:ge])
    return block


def _mgba_replace(text: str, block: str) -> str:
    for header, body in iter_sections(block):
        text = replace_section(header)(text, body)
    return text


extract = _mgba_extract
replace = _mgba_replace


def generate(player_index: int, pad, opts: dict) -> str | None:
    if player_index != 1:
        return None
    return snapshots.restore(opts["snap_dir"], EMU_ID, opts["target"],
                             extract, replace, pad.vendor, pad.product)
