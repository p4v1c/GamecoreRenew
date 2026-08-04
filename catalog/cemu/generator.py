"""Cemu (Wii U) — snapshot restore, one XML file per player slot.

controller0.xml is Player 1's whole config, so extract/replace are the identity
on the file.

Measured on the reference box: Cemu wrote
`<uuid>0_05009b514c050000cc09000000810000</uuid>` for a DualShock 4, where the
host's SDL3 reports 05008fe5…6800 for the same pad. Both the name CRC and the
driver tail differ. Substituting the host's answer would write a device Cemu
never sees — which is why this is a snapshot and not a GUID rewrite.

Single-player here: only slot 1 is ever touched.
"""
from __future__ import annotations

from backend.services.configgen import snapshots


EMU_ID = "cemu"


def extract(text: str) -> str:
    return text


def replace(_text: str, block: str) -> str:
    return block


def generate(player_index: int, pad, opts: dict) -> str | None:
    if player_index != 1:
        return None
    return snapshots.restore(opts["snap_dir"], EMU_ID, opts["target"],
                             extract, replace, pad.vendor, pad.product)
