"""melonDS (DS) — single-player, and it binds RAW SDL2 joystick values.

Those indices differ per controller AND per driver version: a DS4's shoulders
are b9/b10, an Xbox's b6/b7. The D-pad is a hat on both — and a hat is NOT a
button here, it carries its own encoding (see `_encode`). The vendored
gamecontrollerdb even ships conflicting Linux entries for one pad. So every
button, the face buttons included, is re-derived from the connected pad's
live SDL2 mapping.

The face buttons used to be left at the seed's A/B/X/Y = b0-b3, on the claim
that they were the same on every pad. An Xbox One / Series pad on Bluetooth
reports `x:b3,y:b4` (b2 is a gap): its X fired the DS's Y, its Y did nothing,
and the DS's X was on no button at all.

**A saved snapshot always wins over the synthesis.** The caller must ask
`snapshots.exists()` first: `restore(...) or _melonds(...)` conflated "no
snapshot" with "snapshot already applied", so the synthesis ran every other
connection and overwrote the mapping the owner had captured — one session in
two was wrong.

**The seed shipped `R = 86048778`, and that is now `10`.** `0x521000A` is
neither a button index nor a hat encoding (`0x100 | hat<<4 | dir`, so
0x101-0x1F8): no melonDS can read it, and R was simply dead. It survived
because the synthesis below repaired it at the first connection — measured,
86048778 before, 10 after — so the pack worked and nothing ever said the file
it shipped did not. Ten is what every other value in that section already is:
the DualShock 4's `rightshoulder:b10`, matching `L = 9`, `Start = 6`,
`Select = 4`. A seed is a coherent starting point the generator completes for
the pad in hand, and one whose only correct reading depends on a later repass
is a seed that hides its own faults.

Profiling touches slot 1 only, whatever player index arrives. It lacked that
guard once, so plugging in a second pad rewrote melonDS's one and only player
config for the wrong controller. Players 2-4 get their own melonDS instance at
launch: `launch_command` and multiplayer/.
"""
from __future__ import annotations

import re

from backend.services.configgen.helpers.base import atomic_write, backup
from backend.services.configgen.helpers.ini import extract_section, replace_section

EMU_ID = "melonds"

# The snapshot half of `snapshot-or-synth`. The dispatcher reads these off the
# module by name. Leaving them out cost nothing at import time and broke it at
# runtime: every pad connect raised AttributeError. The old code kept the same
# two closures in a central _SNAP_EMUS table, over the same section.
SECTION = "Instance0.Joystick"
extract = extract_section(SECTION)
_replace_joystick = replace_section(SECTION)


def replace(text: str, block: str) -> str:
    # A pre-daemon snapshot may bind L3 directly through SDL. With F12 selected
    # for the layout daemon, restoring it would trigger a second recalculation.
    # Leave legacy/custom configs alone unless the keyboard binding is F12.
    keyboard = extract_section("Instance0.Keyboard")(text)
    if re.search(r"^HK_SwapScreenEmphasis\s*=\s*16777275\s*$", keyboard, re.M):
        block = re.sub(r"^HK_SwapScreenEmphasis\s*=\s*-?\d+\s*$",
                       "HK_SwapScreenEmphasis = -1", block, flags=re.M)
    return _replace_joystick(text, block)


# melonDS [Instance0.Joystick] key → SDL GameController button name. The DS's
# A/B/X/Y take the pad's buttons of the same name, as the seed always did.
_FACE_KEYS = {"A": "a", "B": "b", "X": "x", "Y": "y"}
_SHOULDER_KEYS = {
    "L": "leftshoulder", "R": "rightshoulder", "Start": "start", "Select": "back",
}
_DPAD_KEYS = {
    "Up": "dpup", "Down": "dpdown", "Left": "dpleft", "Right": "dpright",
}
# There used to be a _DPAD_BUTTONS table here, holding one entry: a DualShock 4
# (054c:09cc) whose D-pad it forced to buttons 11-14, on the claim that melonDS
# "latches buttons 11-14 on a DS4 and the hat on an Xbox". That claim is false,
# and it is the whole reason a DS4's D-pad did nothing in melonDS while every
# other button worked.
#
# 11/12/13/14 are the SDL_GameControllerButton enum (DPAD_UP..DPAD_RIGHT).
# melonDS does not read that enum — it reads RAW SDL_Joystick indices. Measured
# against melonDS's own SDL (2.32.70, the org.kde.Platform runtime it links),
# a DS4 on Bluetooth goes through SDL's HIDAPI PS4 driver and reports:
#
#     buttons = 12  → valid indices 0..11, b11 is the TOUCHPAD click
#     hats    = 1   → dpup:h0.1  dpright:h0.2  dpdown:h0.4  dpleft:h0.8
#
# So Up=11 fired the touchpad and Down/Left/Right=12/13/14 were out of range —
# silently inert, no error, no log. The rest of the mapping looked fine only by
# coincidence: SDL's HIDAPI drivers emit raw buttons in GameController-enum
# order, so the two spaces agree from 0 to 10 and diverge at exactly 11.
#
# The lesson is the general one: never special-case a pad's D-pad into button
# indices. Trust the SDL hat token below — every Linux entry for 054c:09cc in
# the vendored gamecontrollerdb already said h0.


def _encode(token: str) -> int | None:
    """SDL raw token → melonDS joystick value. Buttons ('bN' → N) and hats
    ('hM.D' → 0x100 | M<<4 | SDL_HAT_dir). Axis tokens (triggers) return None —
    leave that key's existing binding rather than guess an axis encoding."""
    if re.fullmatch(r"b\d+", token):
        return int(token[1:])
    m = re.fullmatch(r"h(\d+)\.(\d+)", token)
    if m:
        return 0x100 | (int(m.group(1)) << 4) | int(m.group(2))
    return None


def synth_values(pad) -> tuple[dict[str, int], str] | None:
    """The joystick values melonDS needs for this pad: (key → value, source),
    or None when nothing can be derived and the existing bindings must stay."""
    mapping = pad.sdl2_mapping()
    vals: dict[str, int] = {}
    # Face, shoulders and D-pad alike: trust the SDL token, for every pad and
    # with no exceptions. The D-pad is a hat on a DS4 exactly as it is on an
    # Xbox, and _encode() gives hats their own encoding.
    if mapping:
        for key, sdl in (_FACE_KEYS | _SHOULDER_KEYS | _DPAD_KEYS).items():
            enc = _encode(mapping.get(sdl, ""))
            if enc is not None:
                vals[key] = enc
    if vals:
        return vals, "SDL live"
    # Fallback: at least the D-pad, via evdev. has_hat() answers True / False /
    # None. Only True is actionable: a hat always encodes the same way, whatever
    # the pad. False and None both mean "we do not know this pad's raw button
    # indices", and the hatless branch used to guess 11-14 there — the same
    # wrong-index-space guess that killed the DS4. Leave the existing bindings
    # instead, exactly as _encode() already does for axis tokens.
    if not pad.has_hat():
        return None
    return {"Up": 257, "Right": 258, "Down": 260, "Left": 264}, "hat fallback"


def set_joystick_keys(text: str, header: str, vals: dict[str, int]) -> tuple[str, int]:
    """Rewrite the bound keys of `[header]` in place. Returns (text, keys set)."""
    out, insec, n = [], False, 0
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("["):
            insec = (s == f"[{header}]")
        m = re.match(r"^(A|B|X|Y|L|R|Start|Select|Up|Down|Left|Right)\s*=\s*-?\d+\s*$", s)
        if insec and m and m.group(1) in vals:
            out.append(f"{m.group(1)} = {vals[m.group(1)]}"); n += 1
        else:
            out.append(line)
    return "\n".join(out) + "\n", n


def generate(player_index: int, pad, opts: dict) -> str | None:
    """melonDS (DS): only slot 1 here; the other players' instances are written
    at launch (`launch_command`). It binds raw SDL2 joystick inputs, whose
    indices differ per controller (a DS4's shoulders are b9/b10, an Xbox's
    b6/b7; a Bluetooth Xbox's X/Y are b3/b4; the D-pad is a hat, encoded as
    0x100|hat<<4|dir). Re-derive every button from the connected pad's live
    SDL2 mapping so it lands on the right physical input for any controller."""
    toml = opts["target"]
    if player_index != 1 or not toml.is_file():
        return None
    synth = synth_values(pad)
    if synth is None:
        return None
    vals, src = synth
    text, n = set_joystick_keys(toml.read_text(), SECTION, vals)
    if not n:
        return None
    backup(toml)
    atomic_write(toml, text)
    return f"melonds: {n} keys mapped ({src})"


def launch_command(*, rom_path: str, exec_path: str, exec_args: str,
                   players: list[dict], opts: dict | None) -> tuple[str, str] | None:
    """Two to four pads: one melonDS instance per player (multiplayer/).
    One pad, or no ROM: None, and the launch is exactly the solo one."""
    return _multiplayer().launch_command(
        rom_path=rom_path, exec_path=exec_path, exec_args=exec_args,
        players=players, opts=opts)


_SETUP = None


def _multiplayer():
    """multiplayer/setup.py, loaded once, the way rpcs3 loads rpcs3_smart."""
    global _SETUP
    if _SETUP is None:
        import importlib.util
        from pathlib import Path
        path = Path(__file__).resolve().parent / "multiplayer" / "setup.py"
        spec = importlib.util.spec_from_file_location("gamecore_melonds_multiplayer", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _SETUP = module
    return _SETUP
