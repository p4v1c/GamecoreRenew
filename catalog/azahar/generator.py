"""azahar (3DS) — a saved snapshot first, otherwise built from azahar's own SDL.

Its bindings are raw button indices tied to a GUID, and for a long time neither
could be produced: azahar records `button_up = "button:11"` for a DualShock 4
while SDL's own GameController mapping calls that pad's D-pad a hat and button
11 the touchpad. That contradiction is what made this pack `snapshot-restore`
and sent the owner out to azahar's own settings screen, which is where the
validation session found it — "rien ne répond, comme prévu".

**It is not a contradiction. It is two SDLs.** Measured on this box, same
physical DualShock 4, same instant:

    host libSDL2-2.0.so.0, which is sdl2-compat over SDL3
        dpup:h0.1  dpdown:h0.4  dpleft:h0.8  dpright:h0.2   touchpad:b11
    org.kde.Platform 6.9's real SDL 2.32.10, which is what azahar links
        dpup:b11   dpdown:b12   dpleft:b13   dpright:b14    touchpad:b15

The second line is azahar's snapshot, derived rather than copied. azahar ships
no libSDL2 of its own, so `bundled_sdl2()` used to answer "" for it and the
host's was substituted — see the note there. Asking the RUNTIME's instead makes
this synthesisable, and the rule the whole package turns on is unbroken: the
GUID and the indices come from the one SDL that will read them.

Single-player here: only slot 1 is ever touched.
"""
from __future__ import annotations

from backend.services.configgen import derive, inputs, snapshots
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


def _derive_block(pad, prefix: str, app_id: str = "") -> str | None:
    """azahar's whole input block, built for the pad that is connected.

    `app_id` is azahar's, and it is load-bearing rather than informational: it
    is what sends the question to azahar's own SDL rather than the host's, and
    those two disagree about this pad — see the module docstring. It used to be
    `EMU_ID`, the pack id, which `derive.bindings_for` accepted and ignored.

    None when neither source can describe the pad. Nothing plausible is
    invented then: an azahar config of invented indices looks correct, survives
    reboots, and is undiagnosable from a sofa.
    """
    model = inputs.for_pad(pad, app_id)
    if model is None:
        return None
    guid, bindings = model.guid, model.inputs

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
    """Restore this pad's saved mapping, or build one for it.

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
    block = _derive_block(pad, _az_prefix(text), opts.get("app_id", ""))
    if not block:
        return None
    if extract(text).strip() == block.strip():
        return None                                   # already applied
    backup(target)
    atomic_write(target, replace(text, block))
    return f"{EMU_ID}: built for {pad.vendor}:{pad.product}"
