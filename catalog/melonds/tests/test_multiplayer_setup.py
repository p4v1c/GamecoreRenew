"""melonDS local multiplayer, backend half: when it starts, what it writes.

One pad must change nothing at all; two to four write one instance per pad
and wrap melonDS in the launcher.
"""
from __future__ import annotations

import importlib.util
import shlex
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


setup = _load("tested_melonds_mp_setup", HERE.parent / "multiplayer" / "setup.py")
generator = _load("tested_melonds_generator", HERE.parent / "generator.py")

DS4 = {"vendor": "054c", "product": "09cc", "name": "Wireless Controller"}
XBOX = {"vendor": "045e", "product": "02fd", "name": "Xbox Wireless Controller"}
TOML = """[Instance0]
JoystickID = 0
SaveFilePath = ""

[Instance0.Joystick]
A = 0
B = 1
L = 9
R = 10
Start = 6
Select = 4
Up = 257
Down = 260
Left = 264
Right = 258

[Instance0.Window0]
Enabled = true
"""


def _opts(tmp_path: Path) -> dict:
    target = tmp_path / "melonDS.toml"
    target.write_text(TOML)
    return {"target": target, "home": tmp_path, "snap_dir": tmp_path / "snaps",
            "app_id": "net.kuribo64.melonDS"}


def _fake_synth(pad):
    # An Xbox pad on SDL: shoulders b4/b5, Start b7, Select b6.
    return {"L": 4, "R": 5, "Start": 7, "Select": 6}, "SDL live"


def _launch(opts, players, rom="/roms/Game.nds"):
    return setup.launch_command(
        rom_path=rom, exec_path="flatpak", exec_args="run net.kuribo64.melonDS -f",
        players=players, opts=opts, synth=_fake_synth,
        set_keys=generator.set_joystick_keys)


def test_one_pad_writes_nothing_and_keeps_the_command(tmp_path, monkeypatch):
    monkeypatch.setattr(setup, "sdl_joysticks", lambda app_id: 1 / 0)
    opts = _opts(tmp_path)
    assert _launch(opts, [{"player": 1, "key": "aa:bb:cc:dd:ee:01", **DS4}]) is None
    assert opts["target"].read_text() == TOML


def test_no_rom_is_never_multiplayer(tmp_path):
    players = [{"player": n, "key": f"k{n}", **DS4} for n in (1, 2)]
    assert _launch(_opts(tmp_path), players, rom="") is None


def test_two_pads_wrap_melonds_without_fullscreen(tmp_path, monkeypatch):
    monkeypatch.setattr(setup, "sdl_joysticks", lambda app_id: [])
    players = [{"player": n, "key": f"k{n}", **DS4} for n in (1, 2)]
    exe, args = _launch(_opts(tmp_path), players)
    argv = shlex.split(args)
    assert exe == sys.executable
    assert argv[:4] == [str(setup.LAUNCHER), "--players", "2", "--"]
    assert argv[4:] == ["flatpak", "run", setup.A11Y_FLAG, "net.kuribo64.melonDS"]


def test_more_than_four_pads_open_four_instances(tmp_path, monkeypatch):
    monkeypatch.setattr(setup, "sdl_joysticks", lambda app_id: [])
    players = [{"player": n, "key": f"k{n}", **DS4} for n in range(1, 6)]
    _exe, args = _launch(_opts(tmp_path), players)
    assert shlex.split(args)[2] == "4"


def test_each_player_gets_its_sdl_index_and_players_2_on_their_bindings(tmp_path, monkeypatch):
    monkeypatch.setattr(setup, "sdl_joysticks", lambda app_id: [(0, "/dev/hidraw3"),
                                                                (1, "/dev/input/event7")])
    monkeypatch.setattr(setup, "device_ids", lambda path: {
        "/dev/hidraw3": {"/dev/hidraw3", "11:22:33:44:55:66"},
        "/dev/input/event7": {"/dev/input/event7", "/sys/devices/x/hid1"},
        "/dev/input/event5": {"/dev/input/event5", "/sys/devices/x/hid1"},
    }.get(path, {path}))
    opts = _opts(tmp_path)
    # Player 1 is the USB Xbox (keyed by its event node), player 2 the BT DS4.
    players = [{"player": 1, "key": "/dev/input/event5", **XBOX},
               {"player": 2, "key": "11:22:33:44:55:66", **DS4}]
    _launch(opts, players)
    text = opts["target"].read_text()
    from backend.services.configgen.helpers.ini import section
    assert "JoystickID = 1" in section(text, "Instance0")
    assert "JoystickID = 0" in section(text, "Instance1")
    p2 = section(text, "Instance1.Joystick")
    assert "L = 4" in p2 and "Start = 7" in p2 and "A = 0" in p2
    # Player 1's bindings belong to the connect-time profiling, untouched here.
    assert section(text, "Instance0.Joystick") == section(TOML, "Instance0.Joystick")


def test_a_captured_mapping_beats_the_synthesis(tmp_path, monkeypatch):
    monkeypatch.setattr(setup, "sdl_joysticks", lambda app_id: [])
    opts = _opts(tmp_path)
    snap = opts["snap_dir"] / "melonds" / "045e_02fd.snap"
    snap.parent.mkdir(parents=True)
    snap.write_text("[Instance0.Joystick]\nA = 1\nB = 0\nL = 6\nR = 7\n")
    _launch(opts, [{"player": 1, "key": "k1", **DS4}, {"player": 2, "key": "k2", **XBOX}])
    from backend.services.configgen.helpers.ini import section
    assert section(opts["target"].read_text(), "Instance1.Joystick") == "A = 1\nB = 0\nL = 6\nR = 7\n"


def test_a_slot_gap_does_not_open_an_empty_window(tmp_path, monkeypatch):
    monkeypatch.setattr(setup, "sdl_joysticks", lambda app_id: [])
    players = [{"player": 1, "key": "k1", **DS4}, {"player": 3, "key": "k3", **DS4}]
    _exe, args = _launch(_opts(tmp_path), players)
    assert shlex.split(args)[2] == "2"


def test_solo_after_multiplayer_gives_instance_1_its_joystick_back(tmp_path, monkeypatch):
    monkeypatch.setattr(setup, "sdl_joysticks", lambda app_id: [(0, "b"), (1, "a")])
    opts = _opts(tmp_path)
    _launch(opts, [{"player": 1, "key": "a", **DS4}, {"player": 2, "key": "b", **DS4}])
    from backend.services.configgen.helpers.ini import section
    assert "JoystickID = 1" in section(opts["target"].read_text(), "Instance0")
    _launch(opts, [{"player": 1, "key": "a", **DS4}])
    assert "JoystickID = 0" in section(opts["target"].read_text(), "Instance0")
    assert not (tmp_path / setup.STATE_FILE).exists()


def test_autoconfig_off_launches_multiplayer_and_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(setup, "sdl_joysticks", lambda app_id: 1 / 0)
    players = [{"player": n, "key": f"k{n}", **DS4} for n in (1, 2)]
    assert _launch(None, players) is not None


def test_device_ids_join_hidraw_and_event_nodes_of_one_pad(tmp_path):
    hid = tmp_path / "devices/0005:054C:09CC.0003"
    hid.mkdir(parents=True)
    (hid / "uevent").write_text("HID_ID=0005:0000054C:000009CC\nHID_UNIQ=A4:AE:12:00:00:01\n")
    (tmp_path / "class/hidraw/hidraw1").mkdir(parents=True)
    (tmp_path / "class/hidraw/hidraw1/device").symlink_to(hid)
    node = tmp_path / "devices/0005:054C:09CC.0003/input/input9"
    node.mkdir(parents=True)
    (node / "uniq").write_text("a4:ae:12:00:00:01\n")
    (node / "device").symlink_to(hid)
    (tmp_path / "class/input/event4").mkdir(parents=True)
    (tmp_path / "class/input/event4/device").symlink_to(node)

    raw = setup.device_ids("/dev/hidraw1", tmp_path)
    ev = setup.device_ids("/dev/input/event4", tmp_path)
    assert str(hid) in raw and str(hid) in ev
    assert "a4:ae:12:00:00:01" in raw and "a4:ae:12:00:00:01" in ev


def test_a_pad_sdl_does_not_list_keeps_its_joystick_id():
    players = [{"player": 1, "key": "a"}, {"player": 2, "key": "gone"}]
    assert setup.assign_joysticks(players, [(0, "a")], ids_of=lambda p: {p}) == {1: 0}
