"""The N64 slot — Rosalie's Mupen GUI. Snapshot ONLY, deliberately.

The id stays `gopher64` even though it launches RMG: gopher64 sets no WM_CLASS
on its window, so the bezel overlay could never find it.

Nothing here synthesises an RMG mapping. Two attempts failed against what RMG
actually writes:

    PluggedIn = True
    DeviceName = "PS4 Controller"
    DevicePath = "/dev/hidraw0"
    DeviceSerial = "40:1b:5f:b9:ea:8d"
    A_Name = "cross"   …

`PluggedIn` is what attaches a controller to the port — without it the game
itself says "connect a controller to socket 1", however complete the rest looks.
`DevicePath` is a host path that can move between boots, and the button names
are per-controller (`cross`, `square` for a DualShock 4, not the generic `a`,
`x` of the fallback_profile RMG ships).

**gopher64 is NOT covered by controller profiling**, and the module docstring
once claimed otherwise. `controller_assignment` sits at
[null, null, null, null] — measured, still true on the reference box. Binding a
pad to an N64 port is a separate step nothing here performs. This stays inert
until someone presses "Scan mapping".
"""
from __future__ import annotations

from backend.services.configgen import snapshots

from backend.services.configgen.helpers.ini import iter_sections

EMU_ID = "gopher64"


_RMG_INPUT_PREFIX = "Rosalie's Mupen GUI - Input Plugin"


def _rmg_extract(text: str) -> str:
    return "".join(body for header, body in iter_sections(text)
                   if header.startswith(_RMG_INPUT_PREFIX))


def _rmg_replace(text: str, block: str) -> str:
    keep = [(h, b) for h, b in iter_sections(text)
            if not h.startswith(_RMG_INPUT_PREFIX)]
    out = "".join(b for _h, b in keep)
    if not out.endswith("\n"):
        out += "\n"
    return out + block if block.endswith("\n") else out + block + "\n"


extract = _rmg_extract
replace = _rmg_replace


def generate(player_index: int, pad, opts: dict) -> str | None:
    if player_index != 1:
        return None
    return snapshots.restore(opts["snap_dir"], EMU_ID, opts["target"],
                             extract, replace, pad.vendor, pad.product)
