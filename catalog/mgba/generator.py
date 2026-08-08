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

from backend.services.configgen import derive, snapshots

from backend.services.configgen.helpers.base import atomic_write, backup
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


# mGBA's own key ids (GBAKey), confirmed by the config this box carries:
# `hat0Right=4`, `hat0Left=5`, `hat0Up=6`, `hat0Down=7`.
#
# Note the two halves of the file read in OPPOSITE directions, which is mGBA's
# format and not a mistake here: `key<Name>=<sdl button index>` names the GBA
# key and stores the pad's button, while `hat0<Dir>=<gba key id>` names the
# pad's hat direction and stores the GBA key. Writing one in the other's shape
# produces a file mGBA loads in silence and ignores.
_GBA_KEY = {"a": 0, "b": 1, "select": 2, "start": 3,
            "right": 4, "left": 5, "up": 6, "down": 7, "r": 8, "l": 9}

# mGBA control → the SDL field the wizard captured it from.
_FROM_SDL = {"a": "a", "b": "b", "l": "leftshoulder", "r": "rightshoulder",
             "select": "back", "start": "start",
             "up": "dpup", "down": "dpdown", "left": "dpleft", "right": "dpright"}

# The deflection mGBA itself recorded as the point where an axis counts as
# pressed. Carried over rather than chosen: 12288 is 37.5% of an axis, and a
# value invented here would change how far a stick has to move.
_AXIS_VALUE = 12288

# Which SDL stick drives the D-pad when the pad has no digital one.
_AXIS_DIRECTIONS = (("Left", "leftx", "-"), ("Right", "leftx", "+"),
                    ("Up", "lefty", "-"), ("Down", "lefty", "+"))


def _derive_block(pad) -> str | None:
    """[gba.input.SDLB] built from the wizard's capture, or None."""
    got = derive.bindings_for(pad.vendor, pad.product, EMU_ID)
    if not got:
        return None
    guid, bindings = got

    lines = [f"device0={guid}\n"]
    bound = False
    for control, field in _FROM_SDL.items():
        inp = bindings.get(field)
        name = control.capitalize() if len(control) > 1 else control.upper()
        if inp is None or inp.kind == "axis":
            # -1 is mGBA's own "nothing bound", and writing it MATTERS: the
            # section is replaced wholesale, so a key simply left out keeps
            # whatever the previous pad put there.
            lines.append(f"key{name}=-1\n")
            continue
        if inp.kind == "button":
            lines.append(f"key{name}={inp.index}\n")
            bound = True
        else:
            # A hat direction is stored the other way round — see _GBA_KEY.
            lines.append(f"hat{inp.index}{inp.direction.capitalize()}="
                         f"{_GBA_KEY[control]}\n")
            lines.append(f"key{name}=-1\n")
            bound = True

    # A pad with neither a D-pad nor a hat still has a stick, and a GBA with no
    # direction at all is unplayable.
    if not any(bindings.get(f) and bindings[f].kind in ("button", "hat")
               for f in ("dpup", "dpdown", "dpleft", "dpright")):
        for name, field, sign in _AXIS_DIRECTIONS:
            axis = bindings.get(field)
            if axis is None or axis.kind != "axis":
                continue
            lines.append(f"axis{name}Axis={sign}{axis.index}\n")
            lines.append(f"axis{name}Value="
                         f"{'-' if sign == '-' else ''}{_AXIS_VALUE}\n")
            bound = True

    if not bound:
        return None
    return "[gba.input.SDLB]\n" + "".join(sorted(lines[1:])) + lines[0] + "\n"


def generate(player_index: int, pad, opts: dict) -> str | None:
    """Restore the saved mapping, or build one from the wizard's capture.

    A hand-made snapshot always wins — the owner configured mGBA themselves and
    that is not ours to replace.
    """
    if player_index != 1:
        return None
    if snapshots.exists(opts["snap_dir"], EMU_ID, pad.vendor, pad.product):
        return snapshots.restore(opts["snap_dir"], EMU_ID, opts["target"],
                                 extract, replace, pad.vendor, pad.product)

    target = opts["target"]
    if not target.is_file():
        return None
    text = target.read_text()
    block = _derive_block(pad)
    if not block:
        return None
    if extract(text).strip() == block.strip():
        return None                                   # already applied
    backup(target)
    atomic_write(target, replace(text, block))
    return f"{EMU_ID}: built from the captured mapping ({pad.vendor}:{pad.product})"
