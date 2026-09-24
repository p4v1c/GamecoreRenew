"""Focused compatibility tests for the Snes9x pack generator."""
from pathlib import Path
import importlib.util

from backend.services.configgen import inputs

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("snes9x_generator", HERE / "generator.py")
g = importlib.util.module_from_spec(spec)
assert spec.loader
g_spec_loader = spec.loader
g_spec_loader.exec_module(g)


def model(mapping):
    return inputs.PadInputs("guid", "sdl", mapping)


def test_face_buttons_are_snes_positions_not_letter_names():
    m = model({
        "a": inputs.Input("button", 0), "b": inputs.Input("button", 1),
        "x": inputs.Input("button", 2), "y": inputs.Input("button", 3),
    })
    v = g._values_for(m, 1, 6)
    assert v["b_b"] == "Joystick 1 Button 0"
    assert v["b_a"] == "Joystick 1 Button 1"
    assert v["b_y"] == "Joystick 1 Button 2"
    assert v["b_x"] == "Joystick 1 Button 3"


def test_hat_uses_axis_count_from_official_probe():
    m = model({
        "dpup": inputs.Input("hat", 0, "up"),
        "dpdown": inputs.Input("hat", 0, "down"),
        "dpleft": inputs.Input("hat", 0, "left"),
        "dpright": inputs.Input("hat", 0, "right"),
    })
    v = g._values_for(m, 2, 6)
    assert v["b_up"] == "Joystick 2 Axis 6 + 40%"
    assert v["b_down"] == "Joystick 2 Axis 6 - 40%"
    assert v["b_left"] == "Joystick 2 Axis 7 - 40%"
    assert v["b_right"] == "Joystick 2 Axis 7 + 40%"


def test_live_slot_uses_roster_and_official_sdl2_seam(monkeypatch):
    pad = type("Pad", (), {"vendor":"054c", "product":"09cc", "dup_index":0})()
    seen = []
    monkeypatch.setattr(g.controllers, "bundled_sdl2", lambda app: "/stub/libSDL2.so")
    monkeypatch.setattr(
        g.controllers, "sdl2_probe",
        lambda v,p,lib="": (seen.append((v,p,lib)) or {"guid":"0"*32,"axes":"6","map":"x"}),
    )
    assert g._live_joystick(2, pad, {"app_id":"com.snes9x.Snes9x"}) == (2, 6)
    assert seen == [("054c","09cc","/stub/libSDL2.so")]


def test_axis_count_falls_back_to_mapping_tokens():
    answer = {"map":"g,Pad,leftx:a0,lefty:a1,rightx:a2,righty:a3,lefttrigger:+a4,righttrigger:a5,"}
    assert g._physical_axis_count(answer) == 6


def test_snapshot_retargets_player_and_roster_device():
    text = "[Joypad 0]\nb_a = Unset\n\n[Joypad 1]\nb_a = Unset\n"
    block = "[Joypad 0]\nb_a = Joystick 1 Button 1\n"
    out = g._replace_port(1, 2)(text, block)
    assert "[Joypad 0]\nb_a = Unset" in out
    assert "[Joypad 1]\nb_a = Joystick 2 Button 1" in out


def test_release_only_clears_owned_normal_bindings(tmp_path):
    target = tmp_path / "snes9x.conf"
    target.write_text(
        "[Joypad 0]\n"
        "b_a = Joystick 1 Button 1\n"
        "b_a_turbo = Keyboard t\n"
        "custom_future_key = keep-me\n"
    )
    messages = g.release(1, {"target": target})
    out = target.read_text()
    assert messages == ["snes9x: player 1 released"]
    assert "b_a = Unset" in out
    assert "b_a_turbo = Keyboard t" in out
    assert "custom_future_key = keep-me" in out


def test_snapshot_public_helpers_round_trip_the_real_seed():
    seed = (HERE / "seed" / "snes9x.conf").read_text()
    block = g.extract(seed)
    assert block.startswith("[Joypad 0]\n")
    assert g.extract(g.replace(seed, block)).strip() == block.strip()


def test_no_private_sdl_subprocess_is_left_in_pack():
    source = (HERE / "generator.py").read_text()
    assert "subprocess" not in source
    assert "controllers.sdl2_probe" in source


def test_pack_rom_extensions_match_snes9x_gtk_163_file_filter():
    import json
    meta = json.loads((HERE / "pack.json").read_text())
    assert set(meta["roms"]["extensions"]) == {
        "*.sfc", "*.smc", "*.fig", "*.swc",
        "*.jma", "*.zip", "*.gd3", "*.gz", "*.bs",
    }
    assert "*.7z" not in meta["roms"]["extensions"]
