"""Gamescope defaults: fullscreen at the TV's mode, never over the owner's values."""
import importlib.util
import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

FILES = Path(__file__).resolve().parents[1] / "files"
sys.path.insert(0, str(FILES))
spec = importlib.util.spec_from_file_location("test_lutris_gamescope", FILES / "lutris_gamescope.py")
gs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gs)

APP = "net.lutris.Lutris"
XRANDR = """Screen 0: minimum 320 x 200, current 5760 x 2160, maximum 16384 x 16384
DP-1 connected 1920x1080+3840+0 (normal left inverted right x axis y axis) 527mm x 296mm
   1920x1080     60.00*+
HDMI-A-0 connected primary 3840x2160+0+0 (normal left inverted right x axis y axis) 1600mm x 900mm
   3840x2160     60.00*+  30.00
   1920x1080     60.00    59.94
HDMI-A-1 disconnected (normal left inverted right x axis y axis)
"""


def system_yml(home):
    return home / ".var/app" / APP / "data/lutris/system.yml"


def read(home):
    return yaml.safe_load(system_yml(home).read_text())["system"]


def test_the_primary_output_gives_the_mode():
    assert gs.parse_mode(XRANDR) == "3840x2160"
    assert gs.parse_mode("eDP-1 connected 1280x800+0+0 (normal)\n") == "1280x800"
    # Connected but off: no geometry, no mode.
    assert gs.parse_mode("HDMI-1 connected (normal left)\n") is None
    assert gs.parse_mode("") is None


def test_a_fresh_lutris_gets_fullscreen_gamescope_at_the_tv_mode(tmp_path):
    line = gs.apply(tmp_path, APP, "3840x2160")
    assert "gamescope=True" in line
    assert read(tmp_path) == {"gamescope": True, "gamescope_window_mode": "-f",
                              "gamescope_output_res": "3840x2160",
                              "gamescope_game_res": "3840x2160"}


def test_a_new_tv_is_followed_but_the_owners_choice_is_kept(tmp_path):
    gs.apply(tmp_path, APP, "1920x1080")
    gs.apply(tmp_path, APP, "3840x2160")
    assert read(tmp_path)["gamescope_output_res"] == "3840x2160"

    doc = yaml.safe_load(system_yml(tmp_path).read_text())
    doc["system"].update(gamescope=False, gamescope_game_res="1280x720")
    system_yml(tmp_path).write_text(yaml.safe_dump(doc))
    gs.apply(tmp_path, APP, "2560x1440")
    system = read(tmp_path)
    assert system["gamescope"] is False
    assert system["gamescope_game_res"] == "1280x720"
    assert system["gamescope_output_res"] == "2560x1440"


def test_values_the_owner_set_before_the_first_launch_are_never_taken(tmp_path):
    system_yml(tmp_path).parent.mkdir(parents=True)
    system_yml(tmp_path).write_text("system:\n  gamemode: true\n  gamescope_output_res: 1920x1080\n")
    gs.apply(tmp_path, APP, "3840x2160")
    system = read(tmp_path)
    assert system["gamescope_output_res"] == "1920x1080"
    assert system["gamescope_game_res"] == "3840x2160"
    assert system["gamemode"] is True
    # Later TVs move only the value GameCore wrote.
    gs.apply(tmp_path, APP, "2560x1440")
    assert read(tmp_path)["gamescope_output_res"] == "1920x1080"
    assert read(tmp_path)["gamescope_game_res"] == "2560x1440"


def test_no_display_or_an_unreadable_file_changes_nothing(tmp_path):
    assert "left as they are" in gs.apply(tmp_path, APP, None)
    assert not system_yml(tmp_path).exists()
    system_yml(tmp_path).parent.mkdir(parents=True)
    system_yml(tmp_path).write_text("system: [broken\n")
    assert "left alone" in gs.apply(tmp_path, APP, "1920x1080")
    assert system_yml(tmp_path).read_text() == "system: [broken\n"


def test_without_a_display_xrandr_is_not_asked(monkeypatch):
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.setattr(gs.subprocess, "run", lambda *a, **k: pytest.fail("xrandr ran"))
    assert gs.current_mode() is None
