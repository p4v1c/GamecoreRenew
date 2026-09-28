"""Switch (Eden) bindings: positional buttons, Eden's GUID, one port per same-GUID pad."""
import importlib.util
import re
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.services.configgen import inputs, seed  # noqa: E402
from backend.services.configgen.controllers import Pad  # noqa: E402
from backend.services.configgen.helpers.base import Skip  # noqa: E402

SEED = ROOT / "catalog/switch/seed/qt-config.ini"
DS4_GUID = "030000004c050000cc09000000016800"


def _load():
    spec = importlib.util.spec_from_file_location("gen_switch", ROOT / "catalog/switch/generator.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gen = _load()

# A DualShock 4 as SDL describes it: buttons, a hat D-pad, analogue triggers.
DS4 = inputs.PadInputs(DS4_GUID, "sdl", {
    c: t for c, t in (
        (name, inputs.parse_token(tok)) for name, tok in (
            ("a", "b0"), ("b", "b1"), ("x", "b2"), ("y", "b3"), ("back", "b4"),
            ("guide", "b5"), ("start", "b6"), ("leftstick", "b7"), ("rightstick", "b8"),
            ("leftshoulder", "b9"), ("rightshoulder", "b10"),
            ("dpup", "h0.1"), ("dpdown", "h0.4"), ("dpleft", "h0.8"), ("dpright", "h0.2"),
            ("leftx", "a0"), ("lefty", "a1"), ("rightx", "a2"), ("righty", "a3"),
            ("lefttrigger", "a4"), ("righttrigger", "a5")))})


@pytest.fixture
def box(tmp_path, monkeypatch):
    target = tmp_path / "qt-config.ini"
    shutil.copy(SEED, target)
    monkeypatch.setattr(gen.inputs, "for_pad",
                        lambda pad, app_id="": DS4 if pad.vendor == "054c" else None)
    return {"target": target, "snap_dir": tmp_path / "snaps", "app_id": "dev.eden_emu.eden"}


def _value(text: str, key: str) -> str:
    return re.search(rf"^{re.escape(key)}=(.*)$", text, re.M).group(1)


def test_eden_guid_clears_the_name_crc():
    assert gen.eden_guid("05008fe54c050000cc09000000006800") == "050000004c050000cc09000000006800"


def test_player_one_gets_positional_buttons_on_edens_guid(box):
    msg = gen.generate(1, Pad("054c", "09cc", "Wireless Controller", 0), box)
    text = box["target"].read_text()
    guid = gen.eden_guid(DS4_GUID)
    # Switch A is the east button: SDL's `b`.
    assert _value(text, "player_0_button_a") == f'"engine:sdl,port:0,guid:{guid},button:1"'
    assert _value(text, "player_0_button_dup") == f'"engine:sdl,port:0,guid:{guid},hat:0,direction:up"'
    assert "axis:4,threshold:0.5,invert:+" in _value(text, "player_0_button_zl")
    assert "axis_x:0,axis_y:1" in _value(text, "player_0_lstick")
    assert _value(text, "player_0_connected") == "true"
    assert "player_0_button_a\\default=false" in text
    assert "player 1" in msg


def test_a_second_identical_pad_is_port_one_in_player_two(box):
    gen.generate(1, Pad("054c", "09cc", "Wireless Controller", 0), box)
    gen.generate(2, Pad("054c", "09cc", "Wireless Controller", 1), box)
    text = box["target"].read_text()
    assert "port:1," in _value(text, "player_1_button_a")
    assert _value(text, "player_1_connected") == "true"
    assert "port:0," in _value(text, "player_0_button_a")


def test_a_pad_edens_sdl_cannot_describe_is_left_alone(box):
    before = box["target"].read_text()
    msg = gen.generate(1, Pad("1d79", "0f0f", "Generic USB Gamepad", 0), box)
    assert isinstance(msg, Skip)
    assert box["target"].read_text() == before


def test_the_same_call_twice_writes_nothing_the_second_time(box):
    pad = Pad("054c", "09cc", "Wireless Controller", 0)
    assert gen.generate(1, pad, box)
    assert gen.generate(1, pad, box) is None


def test_release_disconnects_and_keeps_the_bindings(box):
    gen.generate(2, Pad("054c", "09cc", "Wireless Controller", 0), box)
    bound = _value(box["target"].read_text(), "player_1_button_a")
    assert gen.release(2, box) == ["switch: player 2 disconnected"]
    text = box["target"].read_text()
    assert _value(text, "player_1_connected") == "false"
    assert _value(text, "player_1_button_a") == bound
    assert gen.release(2, box) == []


def test_a_snapshot_wins_and_is_replayed_on_the_players_port(box):
    snap = box["snap_dir"] / "switch" / "054c_09cc.snap"
    snap.parent.mkdir(parents=True)
    guid = gen.eden_guid(DS4_GUID)
    snap.write_text(f'player_0_button_a="engine:sdl,port:0,guid:{guid},button:7"\n'
                    "player_0_connected=true\n")
    gen.generate(3, Pad("054c", "09cc", "Wireless Controller", 2), box)
    text = box["target"].read_text()
    assert _value(text, "player_2_button_a") == f'"engine:sdl,port:2,guid:{guid},button:7"'
    assert _value(text, "player_2_connected") == "true"


def test_no_config_yet_means_nothing_to_write(box):
    box["target"].unlink()
    assert gen.generate(1, Pad("054c", "09cc", "Wireless Controller", 0), box) is None


def test_the_dlc_folder_follows_the_data_root(tmp_path):
    seed.deploy(SEED.parent, tmp_path / "eden", home=Path("/home/x"),
                gamecore_path=Path("/opt/GameCore"), gamecore_data=Path("/userdata"))
    text = (tmp_path / "eden/qt-config.ini").read_text()
    assert "external_content_dirs\\1\\path=/userdata/emu/Switch DLC & Updates" in text
    assert "@" not in text.split("[UI]")[0].split("[Data%20Storage]")[1]
