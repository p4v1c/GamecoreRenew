"""azahar (3DS) — snapshot restore, NOT GUID substitution.

Its bindings are raw button indices tied to a GUID that cannot be synthesised
from a VID:PID. Measured on the reference box: azahar records
`button_up = "button:11"` for a DualShock 4 — the same raw index melonDS uses —
while SDL's own GameController mapping calls that pad's D-pad a hat and button
11 the touchpad. Different SDL versions, different joystick layout, same pad.

Single-player here: only slot 1 is ever touched.
"""
from __future__ import annotations

from backend.services.configgen import snapshots

import re

EMU_ID = "azahar"


def _az_prefix(text: str) -> str:
    """The `profiles\\N\\` prefix azahar is actually using.

    Qt writes array entries 1-based (`profiles\\1\\…`) but stores the selected
    index 0-based in `profile=`. `profiles\\1\\` was hardcoded, which is right
    only while `profile=0` — true today, false the moment a second input
    profile is created and picked, at which point a snapshot restore would
    rewrite the profile the owner is not using.
    """
    m = re.search(r"^profile=(\d+)$", text, re.M)
    return f"profiles\\{int(m.group(1)) + 1 if m else 1}\\"


def _az_extract(text: str) -> str:
    prefix = _az_prefix(text)
    return "".join(l for l in text.splitlines(keepends=True) if l.startswith(prefix))


def _az_replace(text: str, block: str) -> str:
    prefix = _az_prefix(text)
    if not block.endswith("\n"):
        block += "\n"
    # A snapshot taken under a different active profile carries that profile's
    # prefix; re-key it onto the one in use rather than writing a dead index.
    block = re.sub(r"^profiles\\\d+\\", lambda _: prefix, block, flags=re.M)
    out, done = [], False
    for l in text.splitlines(keepends=True):
        if l.startswith(prefix):
            if not done:
                out.append(block); done = True
        else:
            out.append(l)
    if not done:
        out.append(block)
    return "".join(out)


extract = _az_extract
replace = _az_replace


def generate(player_index: int, pad, opts: dict) -> str | None:
    """Restore this pad's saved mapping, if there is one. Slot 1 only."""
    if player_index != 1:
        return None
    return snapshots.restore(opts["snap_dir"], EMU_ID, opts["target"],
                             extract, replace, pad.vendor, pad.product)
