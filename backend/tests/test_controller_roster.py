"""The controller screen's roster: which controls a pad has, and how well the
box knows it.

The screen draws the standard layout by position, so a control that is missing
here is drawn as absent. Getting this wrong fakes a right stick on an arcade
stick, or hides one on a DualShock 4.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.main import app                               # noqa: E402
from backend.services import controller_roster as roster   # noqa: E402
from backend.services.configgen.controllers import ResolvedName  # noqa: E402

DS4_MAP = ("a:b0,b:b1,x:b3,y:b2,back:b8,guide:b10,start:b9,leftstick:b11,"
           "rightstick:b12,leftshoulder:b4,rightshoulder:b5,dpup:h0.1,dpdown:h0.4,"
           "dpleft:h0.8,dpright:h0.2,leftx:a0,lefty:a1,rightx:a3,righty:a4,"
           "lefttrigger:a2,righttrigger:a5,platform:Linux,")
STICK_MAP = ("a:b1,b:b2,x:b0,y:b3,back:b8,start:b9,guide:b12,leftshoulder:b4,"
             "rightshoulder:b5,lefttrigger:b6,righttrigger:b7,dpup:h0.1,dpdown:h0.4,"
             "dpleft:h0.8,dpright:h0.2,platform:Linux,")


def test_a_full_pad_has_every_control_and_analog_triggers():
    got = roster.parse_controls(DS4_MAP)
    assert set(got["controls"]) == set(roster._SDL_CONTROLS.values())
    assert got["analogTriggers"] is True


def test_an_arcade_stick_has_no_sticks_and_button_triggers():
    got = roster.parse_controls(STICK_MAP)
    assert "ls" not in got["controls"] and "rs" not in got["controls"]
    assert {"l2", "r2", "home"} <= set(got["controls"])
    assert got["analogTriggers"] is False


def test_a_skipped_button_in_the_wizard_is_absent():
    got = roster.parse_controls("a:b0,b:b1,x:b2,y:b3,guide:,platform:Linux,")
    assert "home" not in got["controls"]


@pytest.fixture
def two_pads(monkeypatch):
    monkeypatch.setattr(roster.gamepad_monitor, "roster", lambda: {
        "40:1b:5f:b9:ea:8d": ("054c", "09cc", "Wireless Controller", 0x05),
        "/dev/input/event9": ("0079", "0006", "DragonRise Inc. Generic USB Joystick", 0x03),
    })
    slots = {"40:1b:5f:b9:ea:8d": 1, "/dev/input/event9": 2}
    monkeypatch.setattr(roster.controller_registry, "player_for", slots.get)
    monkeypatch.setattr(roster.battery, "read_batteries", lambda: [
        {"player": 1, "level": 85, "charging": True}])
    names = {"054c": ResolvedName("PS4 Controller", "sdl3_live"),
             "0079": ResolvedName("DragonRise Inc. Generic USB Joystick", "unknown")}
    monkeypatch.setattr(roster, "resolve_name", lambda v, p, n: names[v])
    monkeypatch.setattr(roster, "display_name", lambda v, p, n: str(names[v]))
    monkeypatch.setattr(roster, "sdl2_probe",
                        lambda v, p: {"map": DS4_MAP} if v == "054c" else {})
    monkeypatch.setattr(roster.mapping_db, "read_user", lambda: [])


def test_the_roster_joins_slot_battery_connection_and_identity(two_pads):
    ds4, generic = roster.connected_pads()
    assert (ds4["player"], ds4["name"], ds4["connection"]) == (1, "PS4 Controller", "Bluetooth")
    assert (ds4["battery"], ds4["charging"], ds4["known"]) == (85, True, "sdl")
    assert generic["known"] == "unknown"
    assert generic["controls"] is None          # no SDL mapping: layout unknown
    assert generic["battery"] is None and generic["connection"] == "USB"
    # What a profile keeps: the MAC, else the model (a devnode moves on replug).
    assert (ds4["id"], generic["id"]) == ("40:1b:5f:b9:ea:8d", "0079:0006")


def test_a_wizard_capture_counts_as_mapped_and_gives_the_layout(two_pads, monkeypatch):
    guid = "03000000790000000600000010010000"
    monkeypatch.setattr(roster.mapping_db, "read_user",
                        lambda: [f"{guid},Mapped pad,{STICK_MAP}"])
    generic = roster.connected_pads()[1]
    assert generic["known"] == "mapped"
    assert "ls" not in generic["controls"]


def test_the_route_serves_the_roster(two_pads):
    body = TestClient(app).get("/api/controllers/pads").json()
    assert [p["player"] for p in body["pads"]] == [1, 2]
