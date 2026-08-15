"""mGBA (GBA) — synthesised from the pad, with a saved snapshot winning.

mgba keeps the ACTIVE binding table in [gba.input.SDLB] — every keyA/keyL/hat0
lives there, along with `device0=`, the GUID of the pad it belongs to. The
per-GUID [gba.input-profile.<GUID>] sections hold tilt and gyro axes and
nothing else.

Three faults were measured here at once, each hiding the next.

**The snapshots hold no buttons.** An older `extract` captured `device0=` plus
that GUID section — six gyro keys and not one button, 180 bytes for both saved
controllers on the reference box. `_mgba_extract` was fixed; the files were
not, and they are what `exists()` still finds. Worse, they made restore() a
permanent no-op that reported success: the already-applied test compares a
whole [gba.input.SDLB] against a block that has none, never matches, and so
rewrote the file at every single connect — measured, same md5, "restored saved
mapping" in the log each time. `_carries_bindings()` is the answer: a snapshot
with no binding table is not a mapping, whatever it is, and treating it as one
is what kept the synthesis below from ever running.

**The seed is one particular DualShock 4.** `keyL=9, keyR=10, keySelect=4,
keyStart=6` are that pad's raw SDL indices and nothing more general — measured
live, SDL2 reports exactly `leftshoulder:b9 rightshoulder:b10 back:b4 start:b6`
for a 054c:09cc. So mGBA "worked" on a Sony pad by numerical coincidence, and
on an Xbox one the owner got: "Y ouvre la map, carré rien, L1 c'est mon
inventaire". A seed is a starting point, not a config; completing it for the
pad that is actually here is this file's job, and `inputs.for_pad()` is where
the indices come from.

**It was writing into a directory nothing reads** — see
`configgen.resolve_config_dir`, fixed there rather than here.
"""
from __future__ import annotations

import logging
import re

from backend.services.configgen import inputs, snapshots

from backend.services.configgen.helpers.base import atomic_write, backup
from backend.services.configgen.helpers.ini import (
    iter_sections, replace_section, section_bounds,
)

log = logging.getLogger(__name__)

EMU_ID = "mgba"
SECTION = "gba.input.SDLB"

# Pads whose saved snapshot was found to hold no bindings. Said once each: this
# runs on every connect, and a line repeated every three seconds is how the one
# line that names the cause gets buried.
_reported_empty: set[tuple[str, str]] = set()


def _mgba_extract(text: str) -> str:
    lines = text.splitlines(keepends=True)
    s, e = section_bounds(lines, SECTION)
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
    """Apply a captured block, including anything it puts before a header.

    `iter_sections` starts collecting at the first `[header]` and drops
    whatever precedes it — silently, which is how a snapshot beginning with a
    bare `device0=` line lost the only field that says which pad it is for.
    Those keys are not homeless: they are [gba.input.SDLB]'s, because that is
    the section the extract that produced them read them out of. Placing them
    back there is the inverse of that extract, not a guess about a stray line.
    """
    lines = block.splitlines(keepends=True)
    first = next((i for i, l in enumerate(lines)
                  if l.strip().startswith("[")), len(lines))
    leading = "".join(lines[:first])
    sections = iter_sections("".join(lines[first:]))
    if leading.strip():
        body = next((b for h, b in sections if h == SECTION), f"[{SECTION}]\n")
        sections = [(h, b) for h, b in sections if h != SECTION]
        sections.insert(0, (SECTION, body.rstrip("\n") + "\n" + leading))
    for header, body in sections:
        text = replace_section(header)(text, body)
    return text


extract = _mgba_extract
replace = _mgba_replace


def _carries_bindings(block: str) -> bool:
    """Whether a saved block actually holds a binding table.

    The whole test: does it contain [gba.input.SDLB]. The gyro-only files this
    box carries do not, and a snapshot that cannot restore a single button must
    not stand in the way of a synthesis that can — a restore is meant to give
    the owner back the mapping THEY made, and there is none in these.
    """
    return any(header == SECTION for header, _body in iter_sections(block))


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

# mGBA control → the control name in the abstract input model.
_FROM_SDL = {"a": "a", "b": "b", "l": "leftshoulder", "r": "rightshoulder",
             "select": "back", "start": "start",
             "up": "dpup", "down": "dpdown", "left": "dpleft", "right": "dpright"}

# The deflection mGBA itself recorded as the point where an axis counts as
# pressed. Carried over rather than chosen: 12288 is 37.5% of an axis, and a
# value invented here would change how far a stick has to move.
_AXIS_VALUE = 12288

# Which stick direction drives which GBA direction, when a stick drives one.
_AXIS_DIRECTIONS = (("Left", "leftx", "-"), ("Right", "leftx", "+"),
                    ("Up", "lefty", "-"), ("Down", "lefty", "+"))

# What this generator owns inside [gba.input.SDLB], and therefore what it is
# allowed to remove. Everything else in that section — `tiltAxisX`,
# `gyroAxisY`, `gyroSensitivity` — belongs to mGBA and to whoever configured
# the motion controls, and is carried across untouched.
#
# This is the package's "write only the sections you own" rule applied one
# level down, and it has to be: mGBA keeps its bindings and its gyro settings
# in the SAME section, so replacing the section wholesale would silently take
# the owner's tilt configuration with it every time a pad connected.
_OWNED = re.compile(r"^(device0|key[A-Za-z]+|hat\d+(Up|Down|Left|Right)"
                    r"|axis[A-Za-z]+(Axis|Value))=")


def _bindings_for(pad, app_id: str) -> dict[str, str] | None:
    """The `key=value` lines this pad needs, or None when it cannot be read."""
    model = inputs.for_pad(pad, app_id)
    if model is None:
        return None

    keys: dict[str, str] = {"device0": model.guid}
    bound = False
    for control, field in _FROM_SDL.items():
        inp = model.get(field)
        name = control.capitalize() if len(control) > 1 else control.upper()
        # -1 is mGBA's own "nothing bound", and writing it MATTERS: every owned
        # key is cleared before these are applied, so a key simply left out
        # would keep whatever the previous pad — or the seed — put there.
        keys[f"key{name}"] = "-1"
        if inp is None or inp.kind == "axis":
            continue
        if inp.kind == "button":
            keys[f"key{name}"] = str(inp.index)
        else:
            # A hat direction is stored the other way round — see _GBA_KEY.
            keys[f"hat{inp.index}{inp.direction.capitalize()}"] = str(_GBA_KEY[control])
        bound = True

    # The stick drives the D-pad TOO, not only when there is no other way.
    # `_derive_block` used to emit these as a fallback for a pad with neither a
    # D-pad nor a hat, which reads sensibly and would have been a regression
    # here: the seed binds both on this box, so a DualShock 4 — which has a
    # perfectly good hat — moves Link with the stick today, and a synthesis
    # that dropped the axis lines would take that away from a system the owner
    # reported working.
    for name, field, sign in _AXIS_DIRECTIONS:
        axis = model.get(field)
        if axis is None or axis.kind != "axis":
            continue
        keys[f"axis{name}Axis"] = f"{sign}{axis.index}"
        keys[f"axis{name}Value"] = f"{'-' if sign == '-' else ''}{_AXIS_VALUE}"
        bound = True

    return keys if bound else None


def _apply(text: str, keys: dict[str, str]) -> str:
    """[gba.input.SDLB] with every owned key replaced and the rest kept."""
    lines = text.splitlines(keepends=True)
    start, end = section_bounds(lines, SECTION)
    kept = ([l for l in lines[start + 1:end] if not _OWNED.match(l.strip())]
            if start is not None else [])
    body = (f"[{SECTION}]\n"
            + "".join(f"{k}={keys[k]}\n" for k in sorted(keys))
            + "".join(kept))
    return replace_section(SECTION)(text, body)


def generate(player_index: int, pad, opts: dict) -> str | None:
    """Restore the saved mapping, or build one for the pad that is here.

    A hand-made snapshot always wins — the owner configured mGBA themselves and
    that is not ours to replace. A snapshot that holds no bindings is not one.
    """
    if player_index != 1:
        return None
    target = opts["target"]
    if not target.is_file():
        return None

    if snapshots.exists(opts["snap_dir"], EMU_ID, pad.vendor, pad.product):
        saved = snapshots.snap_path(opts["snap_dir"], EMU_ID,
                                    pad.vendor, pad.product).read_text()
        if _carries_bindings(saved):
            return snapshots.restore(opts["snap_dir"], EMU_ID, target,
                                     extract, replace, pad.vendor, pad.product)
        if (pad.vendor, pad.product) not in _reported_empty:
            _reported_empty.add((pad.vendor, pad.product))
            log.info("configgen: mgba's saved mapping for %s:%s holds no "
                     "[%s] — it was captured before that section was, so "
                     "there are no buttons in it. Building from the pad "
                     "instead; \"Scan mapping\" replaces it with a real one.",
                     pad.vendor, pad.product, SECTION)

    text = target.read_text()
    keys = _bindings_for(pad, opts.get("app_id", ""))
    if not keys:
        return None
    updated = _apply(text, keys)
    if updated == text:
        return None                                   # already applied
    backup(target)
    atomic_write(target, updated)
    return f"{EMU_ID}: {len(keys) - 1} inputs mapped ({pad.vendor}:{pad.product})"
