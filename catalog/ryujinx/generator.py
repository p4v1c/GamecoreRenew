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

from backend.services.configgen.helpers.base import Skip, atomic_write, backup

EMU_ID = "ryujinx"


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

    # Ryujinx's OWN SDL2, not the host's. They disagree by one byte — the bus
    # type — and it is Ryujinx that has to recognise what we write. See
    # bundled_sdl2() for the measurement. Falls back to the host's SDL2 when
    # the emulator is a native install rather than a flatpak.
    new_guid = pad.guid_for(opts["app_id"])
    if not new_guid:
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
        if slot.get("id") == new_id and slot.get("name") == new_name and not stale:
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
    return f"ryujinx: Player {i} {action} (dup {dup}, {new_guid}){freed}"
