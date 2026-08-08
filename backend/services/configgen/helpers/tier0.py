"""PCSX2 and DuckStation: role bindings, an SDL index, and the multitap.

Shared rather than copied into both packs — if a function appears in two
generators it belongs here. The two emulators differ only in three values,
which their packs declare (`controllers.padType`, `controllers.multitap`).

Both bind by SDL role name with NO device identity at all, so the bindings
themselves are correct forever, whatever the pad. What slots 2-4 still need is
an SDL-index section to exist, a `Type` line naming a pad that actually has
sticks, and — for slots 3+ — the multitap.

**The multitap is a condition, not a detail.** PS1 and PS2 have two physical
ports. PCSX2 refuses slot 3+ at the SIO2 level while `IsMultitapPortEnabled(port)`
is false, and DuckStation only wires Pad1/Pad2 while `MultitapMode` is
Disabled — so writing `[Pad3]` and reporting success promised a third player
who could never move. Enabling the tap on port 1 gives that port slots 1/3/4/5,
port 2 staying Pad2: four players, at the cost of a virtual accessory the games
that ignore multitaps ignore anyway.

**`Type` matters on slot 1 too.** DuckStation shipped `Type = DigitalController`
while [Pad1] held every analog binding it needs (LDown, RUp, L3, R3, LargeMotor,
SmallMotor). The upstream DigitalController declares 14 digital inputs and
nothing else, so those eleven lines were dead: sticks inert, no rumble, Ape
Escape unplayable. It is the only Sony-side fault that hits player 1, and it
could never be repaired because the writer returned immediately for i == 1.
"""
from __future__ import annotations

from collections.abc import Collection
from pathlib import Path

from .base import Skip, atomic_write, backup
from .ini import section, set_key, set_section


def apply(path: Path, label: str, player_index: int, *, pad_type: str,
          multitap: dict | None) -> str | None:
    if not path.is_file():
        return None
    text = path.read_text()
    original = text

    p1 = section(text, "Pad1")
    if not p1 or "SDL-0/" not in p1:
        return Skip(f"{label}: [Pad1] has no SDL bindings to clone from — "
                    f"player {player_index} left alone")

    header = f"Pad{player_index}"
    body = section(text, header)
    messages: list[str] = []

    usable = bool(body) and "SDL-" in body and "Type = None" not in body
    if not usable:
        text = set_section(text, header, p1.replace("SDL-0/", f"SDL-{player_index - 1}/"))
        messages.append(f"created {header}")

    # The Type line rides along with the cloned body, and on slot 1 it is the
    # only thing there is to fix.
    text, retyped = set_key(text, header, "Type", pad_type)
    if retyped and not messages:
        messages.append(f"{header} set to {pad_type}")

    if multitap and player_index >= multitap["fromPlayer"]:
        text, tapped = set_key(text, multitap["section"], multitap["key"],
                               multitap["value"])
        if tapped:
            messages.append(f"multitap enabled ({multitap['key']} = {multitap['value']})")

    if text == original:
        return None
    backup(path)
    atomic_write(path, text)
    return f"{label}: {', '.join(messages)}"


def release(path: Path, label: str, player_index: int, *,
            multitap: dict | None, occupied: Collection[int] = ()) -> list[str]:
    """The inverse of the only thing here that is not per-slot: the multitap.

    The `[PadN]` sections are deliberately left alone. Both emulators bind by
    SDL role with no device identity at all, so a section for a slot nobody
    holds names nothing and drives nothing — there is no ghost to remove, and
    rewriting bindings that are correct forever would be churn.

    The multitap is the opposite: it is a property of the ROSTER. `apply()`
    turns it on as soon as a player at or above `fromPlayer` arrives, which is
    required — PCSX2 refuses slot 3 at the SIO2 level while
    `IsMultitapPortEnabled(port)` is false. Nothing ever turned it off, so the
    seed's `MultitapPort1 = false` was a state the box left once and never came
    back to: after a single session at four, every solo session afterwards ran
    with a virtual accessory plugged into port 1.

    And it cannot be decided from `player_index`. Releasing slot 4 says nothing
    about whether slot 3 is still occupied. That is why `occupied` exists in
    this signature at all, and why passing a bare index was not enough.
    """
    if not path.is_file() or not multitap:
        return []
    if any(p >= multitap["fromPlayer"] for p in occupied):
        return []                       # somebody still needs the port

    text = path.read_text()
    text, changed = set_key(text, multitap["section"], multitap["key"],
                            multitap["offValue"])
    if not changed:
        return []
    backup(path)
    atomic_write(path, text)
    return [f"{label}: multitap disabled "
            f"({multitap['key']} = {multitap['offValue']})"]
