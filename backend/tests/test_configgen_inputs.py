"""The abstract input model — and above all, where its numbers come from.

`configgen/inputs.py` exists because four generators out of nine could
synthesise nothing: there was no way to ask "which raw index is this pad's L1,
and is it even a button". The shape of the answer is the easy half and it is
borrowed — Recalbox's configgen has carried an `Input(name, type, id, …)` for
years. The hard half is the SOURCE, because two sources exist on this box and
they disagree about the same physical controller:

    the wizard's capture   read through SDL's linux joystick driver
    SDL's own mapping      read through whichever driver SDL uses — HIDAPI for
                           the Sony, Microsoft and Nintendo families

A model that took the wrong one would produce a config full of plausible
numbers binding the wrong things, which is worse than writing nothing: it looks
correct, survives reboots, and is undiagnosable from a sofa. So the tests that
matter here are not "does it parse a token", they are "which source answered,
and what happens when neither can".

Every mapping below was measured. The DualShock 4's came out of this box's
libSDL2 with the pad connected; the Xbox pad's is the vendored
gamecontrollerdb line for the GUID mGBA itself wrote for that controller.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.services.configgen import controllers, derive, inputs  # noqa: E402
from backend.services.configgen import mapping_db                   # noqa: E402
from backend.services.configgen.controllers import Pad              # noqa: E402

DS4_GUID = "03008fe54c050000cc09000000016800"
DS4_MAP = (
    "a:b0,b:b1,back:b4,dpdown:h0.4,dpleft:h0.8,dpright:h0.2,dpup:h0.1,"
    "guide:b5,leftshoulder:b9,leftstick:b7,lefttrigger:a4,leftx:a0,lefty:a1,"
    "rightshoulder:b10,rightstick:b8,righttrigger:a5,rightx:a2,righty:a3,"
    "start:b6,x:b2,y:b3,touchpad:b11,crc:e58f")

XBOX_GUID = "050018dc5e040000fd02000003090000"
XBOX_MAP = (
    "a:b0,b:b1,back:b15,dpdown:h0.4,dpleft:h0.8,dpright:h0.2,dpup:h0.1,"
    "guide:b16,leftshoulder:b6,leftstick:b13,lefttrigger:a5,leftx:a0,lefty:a1,"
    "rightshoulder:b7,rightstick:b14,righttrigger:a4,rightx:a2,righty:a3,"
    "start:b11,x:b3,y:b4,platform:Linux")

PAD = Pad(vendor="054c", product="09cc", evdev_name="Wireless Controller")


@pytest.fixture(autouse=True)
def no_wizard(monkeypatch):
    """A box where the wizard has never run — every box, until it is not.

    `bindings_for` returns on its first line then, which is the ordering that
    keeps a hotplug from paying for an SDL subprocess per generator.
    """
    monkeypatch.setattr(mapping_db, "read_user", list)


def _sdl(monkeypatch, guid: str, mapping: str) -> None:
    monkeypatch.setattr(controllers, "sdl2_probe",
                        lambda v, p, lib="": {"guid": guid,
                                              "map": f"{guid},A Pad,{mapping},"})


# ── the shape ────────────────────────────────────────────────────────────────

def test_the_token_grammar_is_one_grammar():
    """`derive` used to carry its own copy of the parser. Two parsers for one
    grammar is two places for `h0.8` to stop meaning left, and only one of them
    would have had a test."""
    assert derive.parse_token is inputs.parse_token
    assert derive.Input is inputs.Input


def test_a_control_carries_its_physical_form(monkeypatch):
    """The whole point of the model. A number alone cannot be written: mGBA
    stores a button as `keyA=<n>` and a hat direction the other way round as
    `hat0Up=<gba key>`, and melonDS folds a hat into `0x100|hat<<4|dir`."""
    _sdl(monkeypatch, DS4_GUID, DS4_MAP)
    model = inputs.for_pad(PAD)

    assert model.get("a") == inputs.Input("button", 0)
    assert model.get("dpup") == inputs.Input("hat", 0, "up")
    assert model.get("lefttrigger") == inputs.Input("axis", 4, "+")


def test_a_hat_is_not_offered_as_a_button(monkeypatch):
    """`button()` answers only for a real button. A DualShock 4's D-pad is a
    hat, and writing its hat number where a button index belongs gives a file
    the emulator loads in silence and ignores."""
    _sdl(monkeypatch, DS4_GUID, DS4_MAP)
    model = inputs.for_pad(PAD)

    assert model.button("a") == 0
    assert model.button("dpup") is None, "a hat is not a button"
    assert model.button("lefttrigger") is None, "and neither is an axis"


def test_fields_that_are_not_controls_are_left_out(monkeypatch):
    """`platform:Linux`, `crc:e58f` and `touchpad:b11` are real SDL fields and
    none of them is a control. Parsing them in would offer a generator a
    binding for something nobody asked for."""
    _sdl(monkeypatch, DS4_GUID, DS4_MAP)
    model = inputs.for_pad(PAD)

    assert set(model.inputs) <= set(inputs.CONTROLS)
    assert "touchpad" not in model.inputs and "crc" not in model.inputs


# ── where the numbers come from ──────────────────────────────────────────────

def test_two_pads_do_not_get_the_same_numbers(monkeypatch):
    """The fault this exists to end. mGBA's seed hard-coded a DualShock 4's
    indices, so on an Xbox pad Select landed on Y and Start on the left
    shoulder — reported in game, word for word."""
    _sdl(monkeypatch, DS4_GUID, DS4_MAP)
    ds4 = inputs.for_pad(PAD)
    _sdl(monkeypatch, XBOX_GUID, XBOX_MAP)
    xbox = inputs.for_pad(Pad(vendor="045e", product="02fd"))

    assert ds4.button("back") == 4 and xbox.button("back") == 15
    assert ds4.button("start") == 6 and xbox.button("start") == 11
    assert ds4.button("leftshoulder") == 9 and xbox.button("leftshoulder") == 6
    assert ds4.button("a") == 0 and xbox.button("a") == 0, (
        "the face buttons DO agree, which is why a Sony-shaped seed looked "
        "like it worked")


def test_sdl_answers_for_the_pads_the_wizard_is_refused_for(monkeypatch):
    """The resolution of D4, stated as a test.

    `evdev_driven()` refuses a capture for any pad SDL drives through HIDAPI —
    Sony, Microsoft, Nintendo, which is nearly every modern controller — and
    that refusal is correct. It was read as the wizard being pointless. It is
    the opposite: a pad SDL has a HIDAPI driver for is a pad SDL ships a
    mapping for, so the source the capture cannot supply is already there.
    """
    monkeypatch.setattr(mapping_db, "read_user", lambda: ["a line"])
    monkeypatch.setattr(derive, "evdev_driven", lambda v, p: False)
    _sdl(monkeypatch, DS4_GUID, DS4_MAP)

    model = inputs.for_pad(PAD)
    assert model is not None, "a HIDAPI pad ended up with no model at all"
    assert model.source == "sdl"
    assert model.button("leftshoulder") == 9


def test_a_capture_wins_when_it_is_offered(monkeypatch):
    """The owner mapped this pad button by button, and by the time the capture
    is offered at all `evdev_driven()` has established it describes the driver
    SDL is really using. Their measurement beats a driver's table."""
    monkeypatch.setattr(
        derive, "bindings_for",
        lambda v, p, app_id="": ("cafe" * 8, {"a": inputs.Input("button", 7)}))
    _sdl(monkeypatch, DS4_GUID, DS4_MAP)

    model = inputs.for_pad(PAD)
    assert model.source == "wizard"
    assert model.button("a") == 7, "SDL's b0 overrode the owner's own capture"


def test_neither_source_means_no_model(monkeypatch):
    """Not a default, not a guess. A generator handed None must write nothing:
    invented indices produce a config that looks correct and is not."""
    monkeypatch.setattr(controllers, "sdl2_probe", lambda v, p, lib="": {})
    assert inputs.for_pad(PAD) is None


def test_a_probe_with_a_guid_and_no_mapping_is_not_a_model(monkeypatch):
    """SDL knowing a pad's identity says nothing about its button order. This
    is the ordinary state of an unrecognised controller, and it is precisely
    the one the wizard exists for."""
    monkeypatch.setattr(controllers, "sdl2_probe",
                        lambda v, p, lib="": {"guid": DS4_GUID})
    assert inputs.for_pad(PAD) is None


def test_the_guid_and_the_indices_come_from_one_probe(monkeypatch):
    """The invariant. Mixing them is the failure `controllers.py` documents at
    length reached by another road — the host's SDL3 says bus 0x05 for a
    Bluetooth DualShock 4 where Ryujinx's bundled SDL2 says 0x03, and an id
    from one library beside indices from another binds nothing."""
    seen: list[str] = []

    def probe(vendor, product, lib=""):
        seen.append(lib)
        return {"guid": DS4_GUID, "map": f"{DS4_GUID},A Pad,{DS4_MAP},"}

    monkeypatch.setattr(controllers, "sdl2_probe", probe)
    model = inputs.for_pad(PAD)

    assert model.guid == DS4_GUID
    assert len(seen) == 1, f"the model was assembled from {len(seen)} probes"


def test_a_native_emulator_is_asked_of_the_host_sdl(monkeypatch):
    """`app_id` is empty for an emulator this box runs outside its flatpak —
    `configgen.generator_opts` decides that from what the box LAUNCHES — and
    then the host's SDL2 really is that emulator's SDL2. mGBA on the reference
    box is exactly this: `/usr/bin/mgba-qt`, linked against the same
    libSDL2-2.0.so.0 this probe loads."""
    def bundled(app_id):
        raise AssertionError("a native emulator has no bundled SDL to look up")

    monkeypatch.setattr(controllers, "bundled_sdl2", bundled)
    _sdl(monkeypatch, DS4_GUID, DS4_MAP)

    assert inputs.for_pad(PAD, app_id="").source == "sdl"
