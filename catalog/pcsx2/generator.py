"""PCSX2 (PS2) — role bindings, an SDL index, and the multitap for slots 3+.

All the mechanics live in the shared tier0 helper: PCSX2 and DuckStation differ
only in three values, and those are declared in pack.json
(`controllers.padType`, `controllers.multitap`).
"""
from __future__ import annotations

from collections.abc import Collection

from backend.services.configgen.helpers import tier0

EMU_ID = "pcsx2"


def generate(player_index: int, pad, opts: dict) -> str | None:
    ctl = opts["controllers"]
    return tier0.apply(opts["target"], EMU_ID, player_index,
                       pad_type=ctl["padType"], multitap=ctl.get("multitap"))


def release(player_index: int, opts: dict,
            occupied: Collection[int] = ()) -> list[str]:
    ctl = opts["controllers"]
    return tier0.release(opts["target"], EMU_ID, player_index,
                         multitap=ctl.get("multitap"), occupied=occupied)
