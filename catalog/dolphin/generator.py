"""Dolphin (GameCube / Wii) — two input configs, one Device line each.

Dolphin qualifies devices as `SDL/<k>/<name>` where <k> is a **0-based counter
over devices SHARING THE SAME NAME** (ciface DeviceContainer), not a global
index — a lone DualSense is SDL/0/... even as Player 2. `pad.name` must be what
Dolphin's bundled SDL3 calls the pad.

  · GameCube (GCPadNew.ini): keep the slot's own bindings when they are real,
    else take them from another healthy slot, else from the canonical template.
    Only the Device line varies per pad.
  · Wii (WiimoteNew.ini): write the canonical Wiimote+Nunchuk gamepad template
    with this pad's Device — the old per-pad config was a keyboard/mouse
    frankenstein and slots 2-4 were empty (Virtual pointer).

The donor used to be GCPad1, unconditionally and untested — and on the
reference box GCPad1 was itself the contaminated section (D-Pad on `T`/`G`/`F`/
`H`, Z on `D`). So slot 1 repaired itself with itself, slots 3 and 4 cloned the
contamination, and only slot 2 — the one section that happened to be correct —
worked.
"""
from __future__ import annotations

import logging
import re
from collections.abc import Collection

from backend.services.configgen.controllers import SDL3_TRUSTED
from backend.services.configgen.helpers.base import Skip, atomic_write, backup
from backend.services.configgen.helpers.ini import section, set_section

log = logging.getLogger(__name__)

EMU_ID = "dolphin"


_WIIMOTE_BODY = (
    "Source = 1\n"
    "Device = {device}\n"
    "Buttons/A = `Button S`\n"
    "Buttons/B = `Trigger R`\n"
    "Buttons/1 = `Button W`\n"
    "Buttons/2 = `Button N`\n"
    "Buttons/- = `Back`\n"
    "Buttons/+ = `Start`\n"
    "Buttons/Home = `Thumb R`\n"
    "D-Pad/Up = `Pad N`\n"
    "D-Pad/Down = `Pad S`\n"
    "D-Pad/Left = `Pad W`\n"
    "D-Pad/Right = `Pad E`\n"
    "IR/Up = `Right Y+`\n"
    "IR/Down = `Right Y-`\n"
    "IR/Left = `Right X-`\n"
    "IR/Right = `Right X+`\n"
    # Tilt (roll/pitch the remote) on the SAME right stick as IR: 2D games use
    # tilt (NSMB Wii "Tilt Lift" seesaws) but not the pointer, 3D pointer games
    # use IR but ignore tilt — so one stick serves both with no real conflict.
    "Tilt/Forward = `Right Y+`\n"
    "Tilt/Backward = `Right Y-`\n"
    "Tilt/Left = `Right X-`\n"
    "Tilt/Right = `Right X+`\n"
    "Shake/X = `Button E`\n"
    "Shake/Y = `Button E`\n"
    "Shake/Z = `Button E`\n"
    "Extension = Nunchuk\n"
    "Nunchuk/Buttons/C = `Shoulder L`\n"
    "Nunchuk/Buttons/Z = `Trigger L`\n"
    "Nunchuk/Stick/Up = `Left Y+`\n"
    "Nunchuk/Stick/Down = `Left Y-`\n"
    "Nunchuk/Stick/Left = `Left X-`\n"
    "Nunchuk/Stick/Right = `Left X+`\n"
    "Nunchuk/Stick/Calibration = 100.00 141.42 100.00 141.42 100.00 141.42 100.00 141.42\n"
    "Nunchuk/Shake/X = `Shoulder R`\n"
    "Nunchuk/Shake/Y = `Shoulder R`\n"
    "Nunchuk/Shake/Z = `Shoulder R`\n"
)


# Canonical "any gamepad plays GameCube" bindings — every value is a
# device-agnostic SDL role token, so the same body fits a DualShock, an Xbox
# pad or a generic USB stick; only the Device line is per-pad.
#
# No Calibration line: a calibration is a measurement of one physical stick,
# and Dolphin falls back to a perfect circle without it, which is right for a
# pad nobody has measured. No Modifier line either: `Main Stick/Modifier =
# `Shift`` came from the machine these configs were captured on, and it lets a
# plugged-in keyboard shrink a player's stick range.
_GCPAD_BODY = (
    "Device = {device}\n"
    "Buttons/A = `Button S`\n"
    "Buttons/B = `Button E`\n"
    "Buttons/X = `Button W`\n"
    "Buttons/Y = `Button N`\n"
    "Buttons/Z = Back\n"
    "Buttons/Start = Start\n"
    "D-Pad/Up = `Pad N`\n"
    "D-Pad/Down = `Pad S`\n"
    "D-Pad/Left = `Pad W`\n"
    "D-Pad/Right = `Pad E`\n"
    "Main Stick/Up = `Left Y+`\n"
    "Main Stick/Down = `Left Y-`\n"
    "Main Stick/Left = `Left X-`\n"
    "Main Stick/Right = `Left X+`\n"
    "C-Stick/Up = `Right Y+`\n"
    "C-Stick/Down = `Right Y-`\n"
    "C-Stick/Left = `Right X-`\n"
    "C-Stick/Right = `Right X+`\n"
    "Triggers/L = `Shoulder L`\n"
    "Triggers/R = `Shoulder R`\n"
    "Triggers/L-Analog = `Trigger L`\n"
    "Triggers/R-Analog = `Trigger R`\n"
)

# The SDL role tokens Dolphin writes for a gamepad. A value outside this set is
# a keyboard key, a mouse axis, or something else that will not follow the pad.
_GC_SDL_TOKEN = re.compile(
    r"`?(?:Button [NESW]|Pad [NESW]|Shoulder [LR]|Trigger [LR]|Thumb [LR]|"
    r"(?:Left|Right) [XY][+-]|Back|Start|Guide)`?$")

# The keys that name a physical input. Everything else in a GCPad section is a
# number or a tuning knob (Calibration, Dead Zone, Range, Modifier) and says
# nothing about which device the section follows.
#
# Presence is not required: Dolphin omits a binding the owner never made, and
# an unbound C-Stick is a choice, not a leftover. What is required is that
# every action key that IS there names an SDL role.
_GC_ACTION_KEY = re.compile(
    r"(?:Buttons/(?:A|B|X|Y|Z|Start)|D-Pad/(?:Up|Down|Left|Right)|"
    r"(?:Main Stick|C-Stick)/(?:Up|Down|Left|Right)|"
    r"Triggers/(?:L|R|L-Analog|R-Analog))$")

def _gc_values(body: str) -> dict[str, str]:
    return {k.strip(): v.strip()
            for line in body.splitlines() if "=" in line
            for k, _, v in (line.partition("="),)}


def _gcpad_is_real(body: str | None) -> bool:
    """Is this GCPad section a usable gamepad config, or a leftover?

    The old test asked "does any of the D-Pad or Z look like a bare keyboard
    key", which is a blacklist: `Buttons/Z = `D`` was caught, `Main Stick/
    Modifier = `Shift`` was not. This asks the opposite question — is every
    binding a device-agnostic SDL role token — which is what "works with any
    controller" actually means. Someone who deliberately put their D-Pad on a
    stick still passes, because a stick token is a role token; a config
    captured on a machine with a keyboard does not.
    """
    if not body or not re.search(r"Device = SDL/\d+/", body):
        return False
    values = _gc_values(body)
    if not _GC_SDL_TOKEN.match(values.get("Buttons/A", "")):
        return False        # no face buttons: a skeleton, not a config
    return all(_GC_SDL_TOKEN.match(v)
               for k, v in values.items() if _GC_ACTION_KEY.match(k))

def generate(player_index: int, pad, opts: dict) -> str | None:
    """Retarget BOTH of Dolphin's input configs for player `i` onto the pad.
    Dolphin qualifies devices as SDL/<k>/<name> where <k> is a 0-based counter
    over devices SHARING THE SAME NAME (ciface DeviceContainer), not a global
    index — a lone DualSense is SDL/0/... even as Player 2. `name` must be what
    Dolphin's bundled SDL3 calls the pad.
      • GameCube (GCPadNew.ini): keep the slot's own bindings when they are
        real, else take them from another healthy slot, else from the canonical
        template above. Only the Device line varies per pad.
      • Wii (WiimoteNew.ini): write the canonical Wiimote+Nunchuk gamepad
        template with this pad's Device — the old per-pad config was a
        keyboard/mouse frankenstein and slots 2-4 were empty (Virtual pointer).
    Dolphin binds by SDL role, so `SDL/<dup>/<name>` is all that varies. Either
    file may be absent/unconfigured; we do whichever we can.

    The donor used to be GCPad1, unconditionally and untested — and on this box
    GCPad1 was itself the contaminated section (D-Pad on `T`/`G`/`F`/`H`, Z on
    `D`). So slot 1 repaired itself with itself, slots 3 and 4 cloned the
    contamination, and only slot 2 — the one section that happened to be
    correct — worked. The fix has to live in the code and not in
    catalog/dolphin/seed/GCPadNew.ini. That seed used to pin
    `Device = SDL/0..3/PS4 Controller`, which is dead input on any box without a
    DualShock 4 until a pad connects and this function repairs it; the seed now
    names no device and check-catalog.py fails the build if one comes back.
    """
    # Dolphin qualifies devices as SDL/<k>/<name> and looks that string up in
    # its own ciface enumeration, so a guessed name is a device Dolphin has
    # never heard of — GCPad silently unbound, Wiimote on a virtual pointer.
    # Writing nothing keeps whatever the slot had; writing a guess does not.
    if pad.name.source not in SDL3_TRUSTED:
        return Skip(f"dolphin: no SDL3 name for {pad.vendor}:{pad.product} "
                    f"({pad.evdev_name!r} is the kernel's name, not SDL3's) — "
                    f"player {player_index} left as it was")

    i, device = player_index, f"SDL/{pad.dup_index}/{pad.name}"
    dolphin_dir = opts["config_dir"]
    msgs: list[str] = []

    gcpad = dolphin_dir / "GCPadNew.ini"
    if gcpad.is_file():
        t = gcpad.read_text()
        header = f"GCPad{i}"
        body = section(t, header)
        if _gcpad_is_real(body):
            source, origin = body, "retargeted"
        else:
            # Any healthy sibling first — it may carry a remap the owner made
            # on purpose — then the template. Never an untested GCPad1.
            donor_k = _gc_donor_index(t, i)
            if donor_k:
                source, origin = section(t, f"GCPad{donor_k}"), f"rebuilt from GCPad{donor_k}"
            else:
                source, origin = _GCPAD_BODY, "rebuilt from template"
        # A plain replacement, not a regex one: an SDL device name is arbitrary
        # text and may hold backslashes that re.sub would read as escapes.
        new_body = re.sub(r"^Device = .*$", lambda _: f"Device = {device}",
                          source, count=1, flags=re.M)
        if not new_body.startswith("Device = ") and "\nDevice = " not in new_body:
            new_body = f"Device = {device}\n" + new_body
        # A calibration is a measurement of one physical stick. Cloned onto
        # another pad it is simply wrong, so it does not travel with a donor.
        new_body = re.sub(r"^.*/Calibration = .*\n", "", new_body, flags=re.M)
        # `Main Stick/Modifier = `Shift`` and `C-Stick/Modifier = `Ctrl`` are
        # keyboard leftovers that survive an otherwise healthy section: holding
        # Shift on a plugged-in keyboard shrinks the stick range of whoever
        # owns this port.
        new_body = re.sub(r"^.*/Modifier = `[^`]*`\n", "", new_body, flags=re.M)
        if new_body != body:
            t = set_section(t, header, new_body)
            msgs.append(f"GCPad{i} {origin}")
        # One physical pad cannot hold two GameCube ports. GCPad2 and GCPad3
        # both ended up on `SDL/0/Xbox One Controller`, and Mario Party moved
        # two characters at once.
        stolen = _gc_release_others(t, i, device)
        if stolen != t:
            t = stolen
            msgs.append(f"freed the duplicate {device}")
        if msgs:
            backup(gcpad); atomic_write(gcpad, t)

    wii = dolphin_dir / "WiimoteNew.ini"
    if wii.is_file():
        t = wii.read_text()
        header = f"Wiimote{i}"
        new_body = _WIIMOTE_BODY.format(device=device)
        if section(t, header) != new_body:
            t = set_section(t, header, new_body)
            backup(wii); atomic_write(wii, t)
            msgs.append(f"Wiimote{i} set")

    if not msgs:
        return None
    return f"dolphin: {', '.join(msgs)} ({device})"


def _gc_donor_index(text: str, i: int) -> int:
    return next((k for k in range(1, 5)
                 if k != i and _gcpad_is_real(section(text, f"GCPad{k}"))), 0)


def _gc_release_others(text: str, i: int, device: str) -> str:
    """Blank the Device line of every other GCPad bound to the same pad."""
    for k in range(1, 5):
        if k == i:
            continue
        body = section(text, f"GCPad{k}")
        if body and re.search(rf"^Device = {re.escape(device)}$", body, re.M):
            text = set_section(text, f"GCPad{k}",
                               re.sub(r"^Device = .*$", "Device =", body, flags=re.M))
    return text


def release(player_index: int, opts: dict,
            occupied: Collection[int] = ()) -> list[str]:
    """Undo the "connected player" state a disconnected pad leaves behind.

    `Source = 1` keeps the emulated Wii Remote presented to the game as
    connected even with no input device bound, so a pad unplugged after co-op
    would haunt the next solo session as a phantom player.

    **This function was correct and GCPad4 was dirty anyway.** With one pad
    connected the reference box still had `GCPad4 = SDL/3/PS4 Controller`, and
    the reason was not here: nothing ever CALLED it for slot 4. The monitor
    released a slot only on a departure it had witnessed, and a pad unplugged
    while the box was off raises no departure event — at startup `was` is
    empty. So the one generator that had an inverse never got to run it. The
    sweep in `_reconcile` is what fixes that, and it is why the other
    generators needed one too rather than a fix here.

    `occupied` is unused: nothing Dolphin stores is about the roster. It is in
    the signature because the dispatcher has one signature, and the pack that
    does need it (the multitap) proved a slot index alone is not enough.

    `Source = 0`, not "no Source line at all": Dolphin's compiled-in default
    for Wiimote1 is WiimoteSource::Emulated, so deleting the key alongside the
    body left an emulated remote presented to the game as connected and bound
    to a pointer with no buttons. Wii Sports started, asked for A, and neither
    pad nor keyboard could answer — this function created the phantom it exists
    to remove.
    """
    dolphin_dir = opts["config_dir"]
    results: list[str] = []

    wii = dolphin_dir / "WiimoteNew.ini"
    if wii.is_file():
        try:
            t = wii.read_text()
            header = f"Wiimote{player_index}"
            inactive = "Source = 0\nDevice = XInput2/0/Virtual core pointer\n"
            if section(t, header) != inactive:
                t = set_section(t, header, inactive)
                backup(wii); atomic_write(wii, t)
                results.append(f"dolphin: {header} released (inactive)")
        except Exception:
            log.exception("dolphin: release failed for player %d", player_index)

    # GameCube ports have no Source key and no phantom, but the Device line
    # stays pinned to a pad that has left. The next pad to take a lower slot is
    # then written next to it, and two ports drive the same controller.
    gcpad = dolphin_dir / "GCPadNew.ini"
    if gcpad.is_file():
        try:
            t = gcpad.read_text()
            header = f"GCPad{player_index}"
            body = section(t, header)
            if body and re.search(r"^Device = SDL/", body, re.M):
                t = set_section(t, header,
                                re.sub(r"^Device = .*$", "Device =", body, flags=re.M))
                backup(gcpad); atomic_write(gcpad, t)
                results.append(f"dolphin: {header} unbound")
        except Exception:
            log.exception("dolphin: GCPad release failed for player %d", player_index)
    return results
