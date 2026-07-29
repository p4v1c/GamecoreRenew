"""Unit tests for the emulator profilers (services.controller_profiles).

Focused on _dolphin's "is this section already a real pad config?" decision,
which is what decides between retargeting a section and rewriting it. Getting
that wrong is invisible until someone plays: the pad connects, the emulator
launches, and only the D-Pad is dead.

Run under pytest:  pytest backend/tests/test_controller_profiles.py
Or directly:       python backend/tests/test_controller_profiles.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from backend.services import controller_profiles as cp


GOOD_PAD = """\
Device = SDL/0/PS4 Controller
Buttons/A = `Button S`
Buttons/B = `Button E`
Buttons/X = `Button W`
Buttons/Y = `Button N`
Buttons/Z = Back
Buttons/Start = Start
D-Pad/Up = `Pad N`
D-Pad/Down = `Pad S`
D-Pad/Left = `Pad W`
D-Pad/Right = `Pad E`
"""

# What GCPad1/3/4 actually shipped: SDL device, SDL face buttons, and a D-Pad
# and Z left on the keyboard of the machine the config was captured on.
KEYBOARD_PAD = """\
Device = SDL/0/PS4 Controller
Buttons/A = `Button S`
Buttons/B = `Button E`
Buttons/X = `Button W`
Buttons/Y = `Button N`
Buttons/Z = `D`
Buttons/Start = Start
D-Pad/Up = `T`
D-Pad/Down = `G`
D-Pad/Left = `F`
D-Pad/Right = `H`
"""

# Someone who deliberately put the D-Pad on the right stick. Not our business.
CUSTOM_PAD = GOOD_PAD.replace("D-Pad/Up = `Pad N`", "D-Pad/Up = `Right Y+`")


def write_ini(d: Path, sections: dict[str, str]) -> Path:
    p = d / "GCPadNew.ini"
    p.write_text("".join(f"[{h}]\n{b}" for h, b in sections.items()))
    return p


@pytest.fixture
def dolphin_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(cp, "DOLPHIN_DIR", tmp_path)
    return tmp_path


def test_a_section_with_a_keyboard_dpad_is_rewritten(dolphin_dir):
    """The bug: it was judged 'real', so only its Device line was replaced."""
    write_ini(dolphin_dir, {"GCPad1": GOOD_PAD, "GCPad3": KEYBOARD_PAD})

    msg = cp._dolphin(3, 2, "054c", "09cc", "PS4 Controller")
    assert msg and "GCPad3" in msg, msg

    body = cp.section((dolphin_dir / "GCPadNew.ini").read_text(), "GCPad3")
    assert "D-Pad/Up = `Pad N`" in body, "the D-Pad must come back as an SDL role"
    assert "`T`" not in body and "`G`" not in body, "keyboard keys must be gone"
    assert "Buttons/Z = Back" in body, "Z too"
    assert "Device = SDL/2/PS4 Controller" in body, "and it still targets this pad"


def test_a_real_section_is_only_retargeted(dolphin_dir):
    """Retarget, do not clone: everything but the Device line is left alone."""
    write_ini(dolphin_dir, {"GCPad1": GOOD_PAD,
                            "GCPad2": GOOD_PAD.replace("SDL/0/", "SDL/9/")})

    cp._dolphin(2, 1, "054c", "09cc", "PS4 Controller")

    body = cp.section((dolphin_dir / "GCPadNew.ini").read_text(), "GCPad2")
    assert "Device = SDL/1/PS4 Controller" in body
    assert "D-Pad/Up = `Pad N`" in body


def test_a_hand_customised_mapping_is_not_thrown_away(dolphin_dir):
    """A D-Pad deliberately bound to a stick is not a keyboard leftover.

    The check looks for a bare single key, not for an exact `Pad N`, precisely
    so this config survives.
    """
    write_ini(dolphin_dir, {"GCPad1": GOOD_PAD,
                            "GCPad2": CUSTOM_PAD.replace("SDL/0/", "SDL/9/")})

    cp._dolphin(2, 1, "054c", "09cc", "PS4 Controller")

    body = cp.section((dolphin_dir / "GCPadNew.ini").read_text(), "GCPad2")
    assert "D-Pad/Up = `Right Y+`" in body, "the user's choice is kept"
    assert "Device = SDL/1/PS4 Controller" in body


def test_an_empty_section_is_created_from_gcpad1(dolphin_dir):
    write_ini(dolphin_dir, {"GCPad1": GOOD_PAD, "GCPad4": "Device = XInput2/0/Virtual core pointer\n"})

    cp._dolphin(4, 3, "054c", "09cc", "PS4 Controller")

    body = cp.section((dolphin_dir / "GCPadNew.ini").read_text(), "GCPad4")
    assert "Buttons/A = `Button S`" in body
    assert "D-Pad/Up = `Pad N`" in body
    assert "Device = SDL/3/PS4 Controller" in body


def test_the_shipped_ini_has_no_keyboard_bindings_left():
    """The config that goes out with the box — GCPad1, 3 and 4 had them."""
    import re
    ini = Path(__file__).resolve().parents[2] / "emu-configs/dolphin/GCPadNew.ini"
    leftovers = re.findall(r"^(?:D-Pad/\w+|Buttons/Z) = `[^`]`$", ini.read_text(), re.M)
    assert leftovers == [], leftovers

    for n in (1, 2, 3, 4):
        body = cp.section(ini.read_text(), f"GCPad{n}")
        assert body, f"GCPad{n} missing"
        assert body.count("`Pad ") == 4, f"GCPad{n} D-Pad is not on SDL roles"
        assert "Buttons/Z = Back" in body, f"GCPad{n} Z is not on an SDL role"


if __name__ == "__main__":
    import tempfile

    for fn in (test_a_section_with_a_keyboard_dpad_is_rewritten,
               test_a_real_section_is_only_retargeted,
               test_a_hand_customised_mapping_is_not_thrown_away,
               test_an_empty_section_is_created_from_gcpad1):
        saved = cp.DOLPHIN_DIR
        with tempfile.TemporaryDirectory() as tmp:
            cp.DOLPHIN_DIR = Path(tmp)
            try:
                fn(Path(tmp))
            finally:
                cp.DOLPHIN_DIR = saved
        print(f"[OK ] {fn.__name__}")

    test_the_shipped_ini_has_no_keyboard_bindings_left()
    print("[OK ] test_the_shipped_ini_has_no_keyboard_bindings_left")
    print("\nAll tests passed.")
