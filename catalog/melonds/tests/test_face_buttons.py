"""The DS's A/B/X/Y follow the pad's own button numbers.

They used to stay at the seed's b0-b3 for every pad. An Xbox One / Series pad
on Bluetooth reports x:b3, y:b4: its X fired the DS's Y, its Y did nothing,
and the DS's X was on no button — "the Xbox X is not detected", in a
two-player Mario Party where player 2 inherits player 1's face buttons.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))

spec = importlib.util.spec_from_file_location("tested_melonds_generator_face", HERE.parent / "generator.py")
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)

from backend.services.configgen.helpers.ini import section  # noqa: E402

# SDL's mapping for an Xbox Series pad on Bluetooth (045e:0b13), from the
# vendored gamecontrollerdb.
XBOX_BT = {"a": "b0", "b": "b1", "x": "b3", "y": "b4", "leftshoulder": "b6",
           "rightshoulder": "b7", "back": "b10", "start": "b11",
           "dpup": "h0.1", "dpright": "h0.2", "dpdown": "h0.4", "dpleft": "h0.8"}
SEED = """[Instance0.Joystick]
A = 0
B = 1
X = 2
Y = 3
L = 9
R = 10
Start = 6
Select = 4
Up = 257
Down = 260
Left = 264
Right = 258
"""


class Pad:
    def __init__(self, mapping):
        self._mapping = mapping

    def sdl2_mapping(self):
        return self._mapping

    def has_hat(self):
        return True


def test_a_bluetooth_xbox_gets_its_x_and_y():
    vals, _src = generator.synth_values(Pad(XBOX_BT))
    assert (vals["A"], vals["B"], vals["X"], vals["Y"]) == (0, 1, 3, 4)
    text, _n = generator.set_joystick_keys(SEED, "Instance0.Joystick", vals)
    body = section(text, "Instance0.Joystick")
    assert "X = 3" in body and "Y = 4" in body and "L = 6" in body and "Start = 11" in body


def test_slot_one_is_rewritten_for_the_pad_in_hand(tmp_path):
    toml = tmp_path / "melonDS.toml"
    toml.write_text(SEED)
    assert generator.generate(1, Pad(XBOX_BT), {"target": toml})
    body = section(toml.read_text(), "Instance0.Joystick")
    assert "X = 3" in body and "Y = 4" in body


def test_player_two_on_xbox_does_not_inherit_player_ones_face_buttons():
    """Players 2-4 start from player 1's section: a DS4's b2/b3 must not stay."""
    from importlib import util
    setup_spec = util.spec_from_file_location("tested_melonds_mp_face", HERE.parent / "multiplayer" / "setup.py")
    setup = util.module_from_spec(setup_spec)
    setup_spec.loader.exec_module(setup)

    class SnapPad(Pad):
        vendor, product = "045e", "0b13"

    block = setup.joystick_block(SnapPad(XBOX_BT), "Instance1.Joystick", section(SEED, "Instance0.Joystick"),
                                 Path("/nonexistent"), generator.synth_values, generator.set_joystick_keys)
    assert "X = 3" in block and "Y = 4" in block


def test_a_mapping_without_face_buttons_leaves_them_alone():
    vals, _src = generator.synth_values(Pad({"leftshoulder": "b4"}))
    assert vals == {"L": 4}
