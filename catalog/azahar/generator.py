"""azahar (3DS) — snapshot restore, NOT GUID substitution.

Its bindings are raw button indices tied to a GUID that cannot be synthesised
from a VID:PID. Measured on the reference box: azahar records
`button_up = "button:11"` for a DualShock 4 — the same raw index melonDS uses —
while SDL's own GameController mapping calls that pad's D-pad a hat and button
11 the touchpad. Different SDL versions, different joystick layout, same pad.

Single-player here: only slot 1 is ever touched.
"""
from __future__ import annotations

from backend.services.configgen import derive, snapshots
from backend.services.configgen.helpers.base import atomic_write, backup

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


# 3DS control → the SDL field the wizard captures it from.
#
# `button_a` takes SDL's `a` — the SOUTH face button — and not the eastern one
# a 3DS's A sits at. That is what the snapshot this box already carries does
# (`button_a="button:0"` for a DualShock 4, i.e. Cross), and matching the
# owner's own choice matters more here than matching Nintendo's silkscreen.
_FROM_SDL = {
    "button_a": "a", "button_b": "b", "button_x": "x", "button_y": "y",
    "button_l": "leftshoulder", "button_r": "rightshoulder",
    "button_zl": "lefttrigger", "button_zr": "righttrigger",
    "button_start": "start", "button_select": "back", "button_home": "guide",
    "button_up": "dpup", "button_down": "dpdown",
    "button_left": "dpleft", "button_right": "dpright",
}

# The two analogue sticks, as azahar stores them: one compound `analog_from_
# button` value per stick, four directions inside it. `modifier_scale` is the
# value azahar itself wrote for each — 0.68 for the circle pad, 0.5 for the C
# stick — and is carried over rather than invented.
_STICKS = (("circle_pad", "leftx", "lefty", "0.680000"),
           ("c_stick", "rightx", "righty", "0.500000"))


def _stick(axis_x, axis_y, guid: str, scale: str) -> str | None:
    """One compound stick binding, or None when the pad has no such stick."""
    if axis_x is None or axis_y is None:
        return None
    parts = {"engine": "analog_from_button", "modifier_scale": scale}
    for name, axis, sign in (("left", axis_x, "-"), ("right", axis_x, "+"),
                             ("up", axis_y, "-"), ("down", axis_y, "+")):
        # The threshold carries the sign too: azahar wrote `threshold$0-0.5`
        # for the negative halves and `threshold$00.5` for the positive ones.
        half = derive.Input("axis", axis.index, sign)
        inner = derive.azahar_binding(half, guid, 0.5 if sign == "+" else -0.5)
        parts[name] = derive.azahar_compound(inner)
    return ",".join(f"{k}:{parts[k]}" for k in sorted(parts))


def _derive_block(pad, prefix: str) -> str | None:
    """azahar's whole input block, built from what the wizard captured.

    None when there is no capture for this pad, or when SDL does not read it
    through the driver the capture came from — see derive.evdev_driven().
    """
    got = derive.bindings_for(pad.vendor, pad.product, EMU_ID)
    if not got:
        return None
    guid, bindings = got

    lines: list[str] = []

    def put(key: str, value: str) -> None:
        lines.append(f'{prefix}{key}="{value}"\n')
        # azahar writes a `\default` companion for every binding, and a value
        # without one is a value its UI shows as unset.
        lines.append(f"{prefix}{key}\\default=false\n")

    for control, field in _FROM_SDL.items():
        inp = bindings.get(field)
        if inp is None:
            continue
        # A trigger the pad reports as a button is a button; the capture says
        # which, and forcing an axis here is how a digital L2 stops working.
        threshold = 0.5
        put(control, derive.azahar_binding(inp, guid, threshold))

    for name, x_field, y_field, scale in _STICKS:
        value = _stick(bindings.get(x_field), bindings.get(y_field), guid, scale)
        if value:
            put(name, value)

    if not lines:
        return None
    # Sorted, because Qt writes an ini's keys sorted and an unsorted block would
    # make every future diff against a real capture unreadable.
    return "".join(sorted(lines))


def generate(player_index: int, pad, opts: dict) -> str | None:
    """Restore this pad's saved mapping, or build one from the wizard's capture.

    Slot 1 only. A hand-made snapshot ALWAYS wins: it is the owner's own work
    inside azahar's UI, and a derivation that overwrote it would be this
    pipeline destroying exactly what it exists to preserve.
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
    block = _derive_block(pad, _az_prefix(text))
    if not block:
        return None
    if extract(text).strip() == block.strip():
        return None                                   # already applied
    backup(target)
    atomic_write(target, replace(text, block))
    return f"{EMU_ID}: built from the captured mapping ({pad.vendor}:{pad.product})"
