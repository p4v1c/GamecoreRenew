"""GameCube / Wii — which section is a real pad config, and which is a leftover.

Moved out of backend/tests/test_controller_profiles.py in phase 4: a pack's
tests arrive with the pack. The assertions are unchanged — each one still
encodes the failure that taught us the rule.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from backend.services.configgen.controllers import Pad          # noqa: E402
from backend.services.configgen.helpers.base import Skip        # noqa: E402
from backend.services.configgen.helpers.ini import section, set_section  # noqa: E402


def _load(pack_id):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        f"gen_{pack_id}", ROOT / "catalog" / pack_id / "generator.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


gen = _load("dolphin")

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




def _dolphin(i, dup, vendor, product, name, _dir=None):
    """The pre-phase-4 call shape, so the assertions below are untouched."""
    return gen.generate(i, Pad(vendor, product, name, dup),
                        {"config_dir": _DIR[0], "controllers": {}})


_DIR = [None]


@pytest.fixture
def dolphin_dir(tmp_path):
    _DIR[0] = tmp_path
    return tmp_path


def test_a_section_with_a_keyboard_dpad_is_rewritten(dolphin_dir):
    """The bug: it was judged 'real', so only its Device line was replaced."""
    write_ini(dolphin_dir, {"GCPad1": GOOD_PAD, "GCPad3": KEYBOARD_PAD})

    msg = _dolphin(3, 2, "054c", "09cc", "PS4 Controller")
    assert msg and "GCPad3" in msg, msg

    body = section((dolphin_dir / "GCPadNew.ini").read_text(), "GCPad3")
    assert "D-Pad/Up = `Pad N`" in body, "the D-Pad must come back as an SDL role"
    assert "`T`" not in body and "`G`" not in body, "keyboard keys must be gone"
    assert "Buttons/Z = Back" in body, "Z too"
    assert "Device = SDL/2/PS4 Controller" in body, "and it still targets this pad"

def test_a_real_section_is_only_retargeted(dolphin_dir):
    """Retarget, do not clone: everything but the Device line is left alone."""
    write_ini(dolphin_dir, {"GCPad1": GOOD_PAD,
                            "GCPad2": GOOD_PAD.replace("SDL/0/", "SDL/9/")})

    _dolphin(2, 1, "054c", "09cc", "PS4 Controller")

    body = section((dolphin_dir / "GCPadNew.ini").read_text(), "GCPad2")
    assert "Device = SDL/1/PS4 Controller" in body
    assert "D-Pad/Up = `Pad N`" in body

def test_a_hand_customised_mapping_is_not_thrown_away(dolphin_dir):
    """A D-Pad deliberately bound to a stick is not a keyboard leftover.

    The check looks for a bare single key, not for an exact `Pad N`, precisely
    so this config survives.
    """
    write_ini(dolphin_dir, {"GCPad1": GOOD_PAD,
                            "GCPad2": CUSTOM_PAD.replace("SDL/0/", "SDL/9/")})

    _dolphin(2, 1, "054c", "09cc", "PS4 Controller")

    body = section((dolphin_dir / "GCPadNew.ini").read_text(), "GCPad2")
    assert "D-Pad/Up = `Right Y+`" in body, "the user's choice is kept"
    assert "Device = SDL/1/PS4 Controller" in body

def test_an_empty_section_is_created_from_gcpad1(dolphin_dir):
    write_ini(dolphin_dir, {"GCPad1": GOOD_PAD, "GCPad4": "Device = XInput2/0/Virtual core pointer\n"})

    _dolphin(4, 3, "054c", "09cc", "PS4 Controller")

    body = section((dolphin_dir / "GCPadNew.ini").read_text(), "GCPad4")
    assert "Buttons/A = `Button S`" in body
    assert "D-Pad/Up = `Pad N`" in body
    assert "Device = SDL/3/PS4 Controller" in body

def test_a_contaminated_gcpad1_repairs_itself(dolphin_dir):
    """The bug that shipped: GCPad1 was the donor AND the broken section.

    Only its Device line was rewritten, so the D-Pad and Z stayed on keyboard
    keys for player 1 in every GameCube game, while player 2 — the one section
    that happened to be correct — worked fine.
    """
    write_ini(dolphin_dir, {"GCPad1": KEYBOARD_PAD, "GCPad2": GOOD_PAD})

    msg = _dolphin(1, 0, "054c", "09cc", "PS4 Controller")

    body = section((dolphin_dir / "GCPadNew.ini").read_text(), "GCPad1")
    assert "`T`" not in body and "`D`" not in body, "keyboard keys must be gone"
    assert "D-Pad/Up = `Pad N`" in body and "Buttons/Z = Back" in body
    assert "Device = SDL/0/PS4 Controller" in body
    assert "GCPad2" in (msg or ""), "it should say where the bindings came from"

def test_every_section_broken_falls_back_to_the_template(dolphin_dir):
    """No healthy donor anywhere — the canonical body lives in the code."""
    write_ini(dolphin_dir, {f"GCPad{n}": KEYBOARD_PAD for n in (1, 2, 3, 4)})

    _dolphin(3, 0, "054c", "09cc", "PS4 Controller")

    body = section((dolphin_dir / "GCPadNew.ini").read_text(), "GCPad3")
    assert gen._gcpad_is_real(body)
    assert "Main Stick/Up = `Left Y+`" in body and "Triggers/L = `Shoulder L`" in body

def test_a_keyboard_modifier_does_not_survive(dolphin_dir):
    """`Main Stick/Modifier = `Shift`` passed the old blacklist, and a keyboard
    held down shrank three players' stick range."""
    write_ini(dolphin_dir, {"GCPad1": GOOD_PAD + "Main Stick/Modifier = `Shift`\n"})

    _dolphin(1, 0, "054c", "09cc", "PS4 Controller")

    body = section((dolphin_dir / "GCPadNew.ini").read_text(), "GCPad1")
    assert "Modifier" not in body

def test_one_pad_cannot_hold_two_ports(dolphin_dir):
    """GCPad2 and GCPad3 both held `SDL/0/Xbox One Controller` on the box, and
    Mario Party moved two characters together."""
    write_ini(dolphin_dir, {"GCPad1": GOOD_PAD,
                            "GCPad3": GOOD_PAD.replace("SDL/0/", "SDL/0/")})

    _dolphin(1, 0, "054c", "09cc", "PS4 Controller")

    t = (dolphin_dir / "GCPadNew.ini").read_text()
    assert "Device = SDL/0/PS4 Controller" in section(t, "GCPad1")
    assert "Device =\n" in section(t, "GCPad3"), "the stale duplicate is unbound"

def test_profiling_twice_changes_nothing(dolphin_dir):
    """The scan runs every three seconds for the whole session."""
    write_ini(dolphin_dir, {"GCPad1": KEYBOARD_PAD, "GCPad2": GOOD_PAD})
    _dolphin(1, 0, "054c", "09cc", "PS4 Controller")

    before = (dolphin_dir / "GCPadNew.ini").read_text()
    assert _dolphin(1, 0, "054c", "09cc", "PS4 Controller") is None
    assert (dolphin_dir / "GCPadNew.ini").read_text() == before


# ── release_profile must neutralise Source, not delete it ────────────────────
