"""Ryujinx (Switch) — binds by a GUID, and it must be the EXACT one.

Ryujinx resolves every slot through `_gamepadsIds.IndexOf(id)`. No match is
-1, and -1 disposes the slot **in silence** — no log, no "already assigned"
mark in Input Settings, nothing. So the GUID has to be right, and it carries
bus type, version and driver signature on top of vendor/product: the same
DualShock 4 has different GUIDs over USB and over Bluetooth.

It is read from the emulator's OWN bundled SDL2 and converted, never derived
from a vendor:product. Measured on the reference box, same pad, same instant:
the host says bus 0x05, Ryujinx's SDL2 says 0x03. Writing the host's answer
made IndexOf return -1 and the controller applet appear on screen.

The accompanying index counts **per GUID**, not per player
(SDL2GamepadDriver.GenerateGamepadId walks guidIndex up while the id is taken).
"""
from __future__ import annotations

import json
from collections.abc import Collection

from backend.services.configgen.controllers import (
    GUID_PROBE_FAILED,
    GUID_UNREACHABLE,
)
from backend.services.configgen.helpers.base import Skip, atomic_write, backup

EMU_ID = "ryujinx"

# Nintendo puts A on the RIGHT and B at the BOTTOM; SDL — and every pad this
# box will ever see — puts A at the bottom and B on the right. X and Y are
# swapped the same way.
#
#            position      SDL / PlayStation      Nintendo Switch
#            bottom        A  (Cross)             B
#            right         B  (Circle)            A
#            left          X  (Square)            Y
#            top           Y  (Triangle)          X
#
# The seed shipped `button_a = A`, which reads as an identity and is not one:
# it wires the Switch's A — drawn on the RIGHT of every on-screen prompt — to
# the pad's BOTTOM button. Reported from the couch, DualShock 4: "X -> O,
# carré -> triangle". It is not a pad-specific fault; all four slots carried
# it, so an Xbox pad was equally wrong.
#
# Binding by POSITION is what makes an on-screen "press A" land under the
# thumb that is already over the right-hand button.
_FACE_BY_POSITION = {"button_a": "B", "button_b": "A",
                     "button_x": "Y", "button_y": "X"}

# The exact shape the old seed wrote. Repaired ONLY when it matches to the
# letter: an owner who rebound their face buttons inside Ryujinx has made a
# choice, and this is not the place to overrule it.
_FACE_LETTER_IDENTITY = {"button_a": "A", "button_b": "B",
                         "button_x": "X", "button_y": "Y"}


def _repair_face_buttons(ic: list) -> int:
    """Re-point the four face buttons of every slot still on the old seed map.

    Returns how many slots were changed.

    Applied to the WHOLE list rather than to the slot being profiled, and for
    the same reason `_reconcile` re-profiles the whole roster: players 2-4
    inherit their config from the seed and are never otherwise rewritten, so a
    fix aimed at one slot would leave the other three wrong for ever.
    """
    fixed = 0
    for entry in ic:
        joycon = entry.get("right_joycon")
        if not isinstance(joycon, dict):
            continue
        if all(joycon.get(k) == v for k, v in _FACE_LETTER_IDENTITY.items()):
            joycon.update(_FACE_BY_POSITION)
            fixed += 1
    return fixed


def generate(player_index: int, pad, opts: dict) -> str | None:
    """Ryujinx binds each slot in Config.json's `input_config` list by
    `player_index` (`Player1`..`Player8`) and an `id` `"<dup>-<SDL GUID>"`,
    where <dup> counts pads sharing that GUID (SDL2GamepadDriver.
    GenerateGamepadId walks `guidIndex` up while the id is taken) — NOT the
    player number.

    NpadManager.DriverConfigurationUpdate resolves that id with
    `_gamepadsIds.IndexOf(id)`. No match means -1, means the slot is disposed,
    silently — no log, no "already assigned" mark in Input Settings, nothing.

    So the GUID has to be exactly right, and it used to be neither read nor
    computed. It was copied from another entry that merely shared a
    vendor:product — which breaks the moment a pad changes transport, because
    the bus and driver bytes change and only vendor/product were compared — or
    else fabricated by substituting vendor/product into a reference GUID, which
    produced strings no device has ever had (a DualShock 4 GUID with Xbox
    vendor bytes keeps the DS4's bus 0x0003 and HIDAPI signature; the real Xbox
    pad is bus 0x0005 with a different tail). Worse, the fabricated GUID parsed
    back to the right vendor:product, so the next pass adopted it as "a GUID
    Ryujinx wrote" and logged a match. Once wrong, always wrong.

    Nothing needs guessing: ask SDL2 for the pad's actual GUID and convert
    (ryu_guid_from_sdl2). If SDL2 cannot be reached, say so and change nothing
    — an invented id is worse than an untouched slot.
    """
    i, dup = player_index, pad.dup_index
    cfg_path = opts["target"]
    if not cfg_path.is_file():
        return None
    try:
        cfg = json.loads(cfg_path.read_text())
    except (OSError, ValueError) as e:
        return Skip(f"ryujinx: Config.json unreadable ({e.__class__.__name__})")
    ic = cfg.get("input_config")
    if not isinstance(ic, list):
        return Skip("ryujinx: Config.json has no input_config list")

    # Before anything about THIS pad: repair the face buttons of every slot
    # still carrying the old seed's letter-identity map. A box installed
    # before the fix keeps that map for ever otherwise — nothing else in this
    # generator ever touches the button table.
    repaired = _repair_face_buttons(ic)

    # Ryujinx's OWN SDL2, not the host's. They disagree by one byte — the bus
    # type — and it is Ryujinx that has to recognise what we write. See
    # bundled_sdl2() for the measurement. Falls back to the host's SDL2 when
    # the emulator is a native install rather than a flatpak.
    new_guid, why = pad.guid_for(opts["app_id"])
    if not new_guid:
        # The refusal is the same in every case — an invented id is worse than
        # an untouched slot — but the sentence is not. This one said "SDL2
        # would not report a GUID" for all three, and on the reference box the
        # case that fired was the probe failing to run at the instant a
        # Bluetooth pad connected. SDL had never been asked; measured
        # afterwards it answered ten times out of ten. Naming the wrong cause
        # cost a diagnosis that went looking at gamecontrollerdb and
        # /dev/input permissions, neither of which was involved.
        if why == GUID_PROBE_FAILED:
            return Skip(f"ryujinx: the SDL2 probe for {pad.vendor}:{pad.product} "
                        f"could not be run — Player {i} left as it was")
        if why == GUID_UNREACHABLE:
            return Skip(f"ryujinx: {opts['app_id']} could not be located, so its "
                        f"own SDL2 could not be asked — Player {i} left as it was")
        return Skip(f"ryujinx: SDL2 would not report a GUID for "
                    f"{pad.vendor}:{pad.product} — Player {i} left as it was")

    # A pad template to clone from, for a slot that does not exist yet or that
    # currently belongs to the keyboard. Any gamepad slot will do; the button
    # map is role-based, so it carries over between controller types.
    model = next((e for e in ic if e.get("backend") == "GamepadSDL2"), None)
    pi = f"Player{i}"
    slot = next((e for e in ic if e.get("player_index") == pi), None)
    new_id = f"{dup}-{new_guid}"
    new_name = f"{pad.name} ({dup})"

    # Any OTHER slot claiming this exact id is a fossil of a session where this
    # same pad held a different player number — and it is not inert. Ryujinx
    # resolves every slot through _gamepadsIds.IndexOf(id), so two slots
    # carrying one id both resolve to the one physical pad: the game sees two
    # controllers connected and the player drives a phantom alongside himself.
    #
    # Measured on the reference box. A DualShock 4 was profiled into slot 2 in
    # one session and slot 1 in a later one, and both entries ended up holding
    # 0-e58f0005-054c-0000-cc09-000000006800.
    #
    # release_profile does not cover this. It assumes a device-bound emulator
    # "just goes input-less when a pad leaves", which holds only while the
    # stale id names a pad that is gone; here it names one that is connected.
    # And nothing else would ever notice, because a slot is only ever rewritten
    # for the player being profiled.
    #
    # Removing rather than blanking: an absent player_index is exactly what
    # Ryujinx reads as "this slot is not configured", and a slot claiming
    # another player's pad is an artefact, never something the owner set up.
    stale = [e for e in ic if e.get("id") == new_id and e.get("player_index") != pi]
    for e in stale:
        ic.remove(e)
    freed = "".join(f", freed {e.get('player_index')}" for e in stale)

    if slot is not None and slot.get("backend") == "GamepadSDL2":
        # `not stale` matters: on a box where the duplicate already exists, the
        # slot being profiled is usually the one that is *right*, and returning
        # early here would leave the phantom in place for good.
        # `not repaired` for the same reason `not stale` is here: on a box
        # that still carries the old face-button map, the slot being profiled
        # is usually the one whose id and name are already right, and
        # returning early would leave every slot's buttons wrong for good.
        if (slot.get("id") == new_id and slot.get("name") == new_name
                and not stale and not repaired):
            return None                     # already correct — do not rewrite 11 KB
        # Read before mutating: once the id is written it always equals new_id.
        action = "deduplicated" if slot.get("id") == new_id else "retargeted"
        slot["id"], slot["name"] = new_id, new_name
    else:
        # An existing non-gamepad slot used to have its id mutated in place,
        # which left a keyboard config claiming to be an SDL device: the pad
        # did not work and neither did the keyboard.
        if model is None:
            return Skip(f"ryujinx: no gamepad slot to clone from — Player {i} left as it was")
        clone = json.loads(json.dumps(model))
        clone["player_index"] = pi
        clone["id"], clone["name"] = new_id, new_name
        if slot is not None:
            ic[ic.index(slot)] = clone
            action = "replaced (was a keyboard slot)"
        else:
            ic.append(clone)
            action = "created"
    backup(cfg_path)
    atomic_write(cfg_path, json.dumps(cfg, indent=2) + "\n")
    face = (f"; face buttons re-pointed by position on {repaired} slot"
            f"{'s' if repaired > 1 else ''}") if repaired else ""
    return f"ryujinx: Player {i} {action} (dup {dup}, {new_guid}){freed}{face}"


def release(player_index: int, opts: dict,
            occupied: Collection[int] = ()) -> list[str]:
    """Unbind the gamepad slot no pad holds, without destroying the template.

    generate() already says why a stale entry is not inert — two slots carrying
    one id both resolve to the one physical pad, and the game sees a phantom
    alongside the player. On the reference box Players 3 and 4 kept indexes 2
    and 3, which Input Settings presents as configured players.

    **The id is blanked, not the entry removed, and that is not a detail.**
    Removing looked right — the generator's own comment observes that an absent
    `player_index` is what Ryujinx reads as "not configured" — but it is a trap
    door. generate() builds a missing slot by CLONING the first GamepadSDL2
    entry it finds, so once the last one is gone there is no template left:
    `model is None`, `Skip("no gamepad slot to clone from")`, and Ryujinx can
    never be configured again by any number of reconnections.

    Measured, on this developer's own box and not in theory: a run left
    `input_config` an empty list, and no pad could take a slot afterwards.

    An empty id is what the SEED ships for an unused slot, so this is the
    byte-exact inverse of what generate() wrote — the same choice RPCS3's
    release makes with `Device: ""`. Ryujinx resolves it through
    `_gamepadsIds.IndexOf("")`, gets -1 and disposes the slot, which is exactly
    "no player here". That silent disposal is a FAILURE when the id was meant
    to name a pad; it is the intended outcome when the slot is meant to be
    empty. And the owner's per-slot tuning — deadzones, motion, rumble — stays
    where it is instead of being thrown away and re-cloned from someone else's.

    Only `GamepadSDL2` entries. A slot the owner set up for a keyboard is
    theirs, was never written by us, and is not ours to touch.

    `occupied` is unused: Ryujinx stores nothing about the roster.
    """
    cfg_path = opts["target"]
    if not cfg_path.is_file():
        return []
    try:
        cfg = json.loads(cfg_path.read_text())
    except (OSError, ValueError):
        return []
    ic = cfg.get("input_config")
    if not isinstance(ic, list):
        return []

    pi = f"Player{player_index}"
    freed = [e for e in ic
             if e.get("player_index") == pi and e.get("backend") == "GamepadSDL2"
             and (e.get("id") or e.get("name"))]
    if not freed:
        return []
    for e in freed:
        e["id"], e["name"] = "", ""
    backup(cfg_path)
    atomic_write(cfg_path, json.dumps(cfg, indent=2) + "\n")
    return [f"ryujinx: Player {player_index} unbound"]
