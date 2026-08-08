"""RPCS3 (PS3) — role bindings, only the device NAME varies.

RPCS3's SDL handler names devices `"<name> <k>"` with k a **1-based counter
over devices SHARING THE SAME NAME** (sdl_pad_handler.cpp), not the player
number — a lone DualSense is "DualSense Wireless Controller 1" even as
Player 2. A non-matching string makes RPCS3 log "SDL: Adding empty device" and
the pad is silently dead in game.

`pad.name` must be what RPCS3's bundled SDL3 calls the pad, which is why it is
resolved against the system's libSDL3 with the pads actually connected and not
against gamecontrollerdb.txt: a DualSense is "DualSense Wireless Controller"
to SDL3, not "PS5 Controller".

Only the Device line used to be rewritten, and only if the slot already said
`Handler: SDL`. But the state RPCS3 leaves a slot in when its Device matches
nothing is exactly `Handler: "Null"` with every binding blanked — so the one
case that needed repairing was the one case that returned early, silently, on
every connection, for ever. Players 2-4 on the reference box were in that state
for a week. A slot like that is now rebuilt from a healthy one: the bindings
are role names, identical from one controller to the next, so the clone is
correct by construction.
"""
from __future__ import annotations

import re
from collections.abc import Collection

from backend.services.configgen.controllers import SDL3_TRUSTED
from backend.services.configgen.helpers.base import Skip, atomic_write, backup

EMU_ID = "rpcs3"


def _block(text: str, i: int) -> re.Match | None:
    return re.search(rf"^Player {i} Input:\n(.*?)(?=^Player \d+ Input:|\Z)",
                     text, re.S | re.M)


def _is_bound(block: str) -> bool:
    """A slot that will actually drive a pad: the SDL handler, and bindings
    that are not all empty strings."""
    if "Handler: SDL" not in block:
        return False
    return bool(re.search(r'^\s+(?:Cross|Circle|Square|Triangle|Start):\s*(?!""|$)\S',
                          block, re.M))


def generate(player_index: int, pad, opts: dict) -> str | None:
    # RPCS3 matches this string against its own SDL3 enumeration, so a name
    # nobody could vouch for is not a lesser config — it is a dead pad plus a
    # config that looks right. The only symptom used to be "SDL: Adding empty
    # device" in RPCS3's log, which nobody reads from a sofa. Leaving the slot
    # as it is at least keeps whatever worked before.
    if pad.name.source not in SDL3_TRUSTED:
        return Skip(f"rpcs3: no SDL3 name for {pad.vendor}:{pad.product} "
                    f"({pad.evdev_name!r} is the kernel's name, not SDL3's) — "
                    f"Player {player_index} left as it was")

    yml = opts["target"]
    if not yml.is_file():
        return Skip(f"rpcs3: no input config at {yml} — nothing to retarget")
    text = yml.read_text()
    m = _block(text, player_index)
    if not m:
        return Skip(f"rpcs3: Config has no 'Player {player_index} Input:' block")
    block = m.group(1)

    if _is_bound(block):
        source, action = block, "retargeted"
    else:
        donor = next((d.group(1) for k in range(1, 8) if k != player_index
                      and (d := _block(text, k)) and _is_bound(d.group(1))), None)
        if donor is None:
            return Skip(f"rpcs3: Player {player_index} is unbound and no other "
                        f"player is bound — nothing to clone from")
        source, action = donor, "rebuilt"

    # A device name is arbitrary text; a lambda keeps re.sub from reading a
    # backslash in it as a group reference.
    new_block = re.sub(r"^(  Device: ).*$",
                       lambda mm: f"{mm.group(1)}{pad.name} {pad.dup_index + 1}",
                       source, count=1, flags=re.M)
    if new_block == block:
        return None
    text = text[:m.start(1)] + new_block + text[m.end(1):]
    backup(yml)
    atomic_write(yml, text)
    return f"rpcs3: Player {player_index} {action} ({pad.name} {pad.dup_index + 1})"


def release(player_index: int, opts: dict,
            occupied: Collection[int] = ()) -> list[str]:
    """Stop naming a device in a slot no pad holds.

    RPCS3 does NOT go input-less when a pad leaves — that assumption is what
    left the reference box showing four players with one DualShock 4 plugged
    in, Player 4 still reading "Xbox One Wireless Controller 3". A PS3 game
    asking for four controllers got four, two of them attached to nothing.

    `Device: ""` and not a deleted key, not a deleted block: an empty Device is
    exactly what the seed ships for a slot nobody is using, so this is the
    byte-exact inverse of what generate() wrote and nothing else in the file
    moves. Handler and bindings stay as they are, which also means the next pad
    to take this slot is a plain retarget rather than a rebuild — and leaves
    the slot usable as a donor for a sibling that needs repairing.

    `occupied` is unused: RPCS3 stores nothing about the roster, only about the
    slot. It is in the signature because the dispatcher has one signature.
    """
    yml = opts["target"]
    if not yml.is_file():
        return []
    text = yml.read_text()
    m = _block(text, player_index)
    if not m:
        return []
    block = m.group(1)
    new_block = re.sub(r'^(  Device: ).*$', lambda mm: f'{mm.group(1)}""',
                       block, count=1, flags=re.M)
    if new_block == block:
        return []
    backup(yml)
    atomic_write(yml, text[:m.start(1)] + new_block + text[m.end(1):])
    return [f"rpcs3: Player {player_index} unbound"]
