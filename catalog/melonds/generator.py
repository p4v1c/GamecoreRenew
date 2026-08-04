"""melonDS (DS) — single-player, and it binds RAW SDL2 joystick values.

Those indices differ per controller AND per driver version: a DS4's shoulders
are b9/b10, an Xbox's b6/b7; its D-pad is a hat, a DS4's is buttons 11-14. The
vendored gamecontrollerdb even ships conflicting Linux entries for one pad. So
the shoulders / start / select / D-pad are re-derived from the connected pad's
live SDL2 mapping. Face buttons (A/B/X/Y = b0-b3) are consistent and left
untouched.

**A saved snapshot always wins over the synthesis.** The caller must ask
`snapshots.exists()` first: `restore(...) or _melonds(...)` conflated "no
snapshot" with "snapshot already applied", so the synthesis ran every other
connection and overwrote the mapping the owner had captured — one session in
two was wrong.

Single-player: only slot 1 is ever touched, whatever player index arrives. It
lacked that guard once, so plugging in a second pad rewrote melonDS's one and
only player config for the wrong controller.
"""
from __future__ import annotations

import re

from backend.services.configgen.helpers.base import atomic_write, backup
from backend.services.configgen.helpers.ini import extract_section, replace_section

EMU_ID = "melonds"

# The snapshot half of `snapshot-or-synth`. The dispatcher reads these off the
# module by name, and so does "Scan mapping" — which skips any pack that has no
# `extract`, silently. Leaving them out cost nothing at import time and broke
# both paths at runtime: every pad connect raised AttributeError, and melonDS
# dropped out of Scan mapping without a word. The old code kept the same two
# closures in a central _SNAP_EMUS table, over the same section.
SECTION = "Instance0.Joystick"
extract = extract_section(SECTION)
replace = replace_section(SECTION)


# melonDS [Instance0.Joystick] key → SDL GameController button name.
_SHOULDER_KEYS = {
    "L": "leftshoulder", "R": "rightshoulder", "Start": "start", "Select": "back",
}
_DPAD_KEYS = {
    "Up": "dpup", "Down": "dpdown", "Left": "dpleft", "Right": "dpright",
}
# Controllers whose D-pad melonDS's own SDL reads as BUTTONS, not the hat that
# SDL's GameController mapping reports (verified by what melonDS records when
# you bind the D-pad in-app). SDL says h0 for both a DS4 and an Xbox, but
# melonDS latches buttons 11-14 on a DualShock 4 and the hat on an Xbox — so
# the hat token can't be trusted here; list the button exceptions instead.
_DPAD_BUTTONS = {
    ("054c", "09cc"): {"Up": 11, "Down": 12, "Left": 13, "Right": 14},  # DualShock 4
}


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


def generate(player_index: int, pad, opts: dict) -> str | None:
    """melonDS (DS) is single-player — only slot 1. It binds raw SDL2 joystick
    inputs, whose indices differ per controller (a DS4's shoulders are b9/b10,
    an Xbox's b6/b7; its D-pad is a hat, a DS4's is buttons 11-14). Re-derive
    the shoulders / start / select / D-pad from the connected pad's live SDL2
    mapping so they land on the right physical inputs for any controller. Face
    buttons (A/B/X/Y = b0-b3) are consistent and left untouched."""
    i = player_index
    toml = opts["target"]
    if i != 1 or not toml.is_file():
        return None
    mapping = pad.sdl2_mapping()
    vals: dict[str, int] = {}
    if mapping:
        for key, sdl in _SHOULDER_KEYS.items():
            enc = _encode(mapping.get(sdl, ""))
            if enc is not None:
                vals[key] = enc
    # D-pad: a known button-exception controller wins; otherwise trust the SDL
    # hat token (works for hat pads like the Xbox).
    override = _DPAD_BUTTONS.get(pad.vidpid)
    if override:
        vals.update(override)
    elif mapping:
        for key, sdl in _DPAD_KEYS.items():
            enc = _encode(mapping.get(sdl, ""))
            if enc is not None:
                vals[key] = enc
    src = "SDL live"
    if not vals:                       # fallback: at least the D-pad, via evdev
        hat = pad.has_hat()
        if hat is None:
            return None
        vals = ({"Up": 257, "Right": 258, "Down": 260, "Left": 264} if hat
                else {"Up": 11, "Down": 12, "Left": 13, "Right": 14})
        src = "hat fallback"
    out, insec, n = [], False, 0
    for line in toml.read_text().splitlines():
        s = line.strip()
        if s.startswith("["):
            insec = (s == "[Instance0.Joystick]")
        m = re.match(r"^(L|R|Start|Select|Up|Down|Left|Right)\s*=\s*-?\d+\s*$", s)
        if insec and m and m.group(1) in vals:
            out.append(f"{m.group(1)} = {vals[m.group(1)]}"); n += 1
        else:
            out.append(line)
    if not n:
        return None
    backup(toml)
    atomic_write(toml, "\n".join(out) + "\n")
    return f"melonds: {n} keys mapped ({src})"
