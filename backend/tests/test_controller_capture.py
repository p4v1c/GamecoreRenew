"""The mapping wizard's capture — evdev events in, an SDL mapping line out.

The dangerous failure here is not a crash. It is a mapping whose every number
is plausible and shifted by one: SDL numbers a pad's buttons by walking its
declared capabilities in a fixed order, so a derivation that gets the order
wrong still produces the right COUNT of bindings, writes cleanly, and gives a
controller where every button does someone else's job.

Counts therefore prove nothing on their own, and the layouts below are not
invented. They were measured through /dev/uinput against the real SDL by
`scripts/verify-sdl-layout.py`, which creates each of these pads, presses every
one of its inputs in turn and asks SDL which of ITS indices moved. That script
is not in the suite — CI has no /dev/uinput and it is not worth a skip in the
gate — so what it measured is replayed here.

Re-run it after touching `sdl_layout()`:

    python3 scripts/verify-sdl-layout.py --press

The last run: 5 pads, 59 keys and 22 axes, every input landing on the derived
index, agreed by the host's SDL3 and SDL2 and by the four SDLs the emulators
bundle. Swapping the two button loops — the single most tempting simplification
in that function — moves every index and the script reports it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.services import controller_capture as cap             # noqa: E402
from backend.services.configgen import mapping_db                  # noqa: E402

# evdev codes, spelled out so the test does not need python-evdev either.
BTN_SOUTH, BTN_EAST, BTN_NORTH, BTN_WEST = 0x130, 0x131, 0x133, 0x134
BTN_TL, BTN_TR = 0x136, 0x137
BTN_SELECT, BTN_START, BTN_MODE = 0x13A, 0x13B, 0x13C
BTN_THUMBL, BTN_THUMBR = 0x13D, 0x13E
BTN_TRIGGER, BTN_THUMB = 0x120, 0x121
KEY_A, KEY_ENTER = 0x1E, 0x1C
ABS_X, ABS_Y, ABS_Z, ABS_RX, ABS_RY, ABS_RZ = 0, 1, 2, 3, 4, 5
ABS_HAT0X, ABS_HAT0Y, ABS_HAT1X, ABS_HAT1Y = 0x10, 0x11, 0x12, 0x13

FACE = [BTN_SOUTH, BTN_EAST, BTN_NORTH, BTN_WEST, BTN_TL, BTN_TR,
        BTN_SELECT, BTN_START, BTN_MODE, BTN_THUMBL, BTN_THUMBR]

# (keys, axes) → (buttons, axes, hats), as the REAL SDL reported them.
MEASURED = {
    "plain-pad": ((FACE, [ABS_X, ABS_Y, ABS_RX, ABS_RY, ABS_Z, ABS_RZ,
                          ABS_HAT0X, ABS_HAT0Y]), (11, 6, 1)),
    "keyboard-keys": ((FACE + [BTN_TRIGGER, BTN_THUMB, KEY_A, KEY_ENTER],
                       [ABS_X, ABS_Y]), (15, 2, 0)),
    "hats-only": ((FACE, [ABS_HAT0X, ABS_HAT0Y]), (11, 0, 1)),
    "two-hats": ((FACE, [ABS_X, ABS_Y, ABS_HAT0X, ABS_HAT0Y,
                         ABS_HAT1X, ABS_HAT1Y]), (11, 2, 2)),
    "sparse-axes": ((FACE, [ABS_X, ABS_RZ, ABS_HAT0X, ABS_HAT0Y]), (11, 2, 1)),
}


@pytest.mark.parametrize("pad", sorted(MEASURED))
def test_the_counts_match_what_sdl_reported(pad):
    """Necessary, not sufficient — see the module docstring for the other
    half."""
    (keys, axes), expected = MEASURED[pad]

    assert cap.sdl_layout(keys, axes).counts == expected


def test_keyboard_range_keys_are_numbered_after_the_gamepad_buttons():
    """The rule that is easy to get backwards and impossible to notice.

    SDL walks BTN_JOYSTICK..KEY_MAX first, THEN everything below. Arcade
    sticks and pad clones declare keyboard-range keys, and numbering those
    first shifts every index a real gamepad uses — measured: the swap puts
    BTN_SOUTH on b2 where SDL has it on b0.
    """
    keys = FACE + [BTN_TRIGGER, BTN_THUMB, KEY_A, KEY_ENTER]

    layout = cap.sdl_layout(keys, [ABS_X, ABS_Y])

    assert layout.buttons[BTN_TRIGGER] == 0, "BTN_JOYSTICK is the first button"
    assert layout.buttons[BTN_SOUTH] == 2
    assert layout.buttons[KEY_ENTER] == 13, "keyboard keys come last"
    assert layout.buttons[KEY_A] == 14


def test_the_hat_range_is_skipped_by_the_axis_walk():
    """A d-pad reported as a hat is not an axis. Counting it as one gives every
    stick an index one too high, and there is no symptom until a stick is
    pushed."""
    layout = cap.sdl_layout(FACE, [ABS_X, ABS_Y, ABS_HAT0X, ABS_HAT0Y, ABS_RX])

    assert layout.axes == {ABS_X: 0, ABS_Y: 1, ABS_RX: 2}
    assert layout.hats == {ABS_HAT0X: 0, ABS_HAT0Y: 0}


def test_axis_indices_follow_position_not_code():
    """`sparse-axes` exists for this: ABS_RZ is code 5 and the second axis
    declared. A derivation keyed on the code number would call it a5."""
    layout = cap.sdl_layout(FACE, [ABS_X, ABS_RZ])

    assert layout.axes == {ABS_X: 0, ABS_RZ: 1}


def test_a_second_hat_is_its_own_index():
    layout = cap.sdl_layout(FACE, [ABS_HAT0X, ABS_HAT0Y, ABS_HAT1X, ABS_HAT1Y])

    assert layout.hats == {ABS_HAT0X: 0, ABS_HAT0Y: 0,
                           ABS_HAT1X: 1, ABS_HAT1Y: 1}


# ── one event to one token ───────────────────────────────────────────────────

@pytest.fixture
def layout():
    return cap.sdl_layout(FACE, [ABS_X, ABS_Y, ABS_Z, ABS_HAT0X, ABS_HAT0Y])


def test_a_press_becomes_a_button_token(layout):
    assert cap.binding_for(layout, cap.EV_KEY, BTN_SOUTH, 1) == "b0"
    assert cap.binding_for(layout, cap.EV_KEY, BTN_MODE, 1) == "b8"


def test_a_release_says_nothing(layout):
    """Binding on the release would record the button the player let go of
    while reaching for the next one."""
    assert cap.binding_for(layout, cap.EV_KEY, BTN_SOUTH, 0) is None


def test_an_undeclared_input_is_unmappable(layout):
    """Not "mapped to something plausible": a code the device never declared
    has no SDL index at all, and inventing one writes a binding for a button
    that does not exist."""
    assert cap.binding_for(layout, cap.EV_KEY, 0x2FE, 1) is None
    assert cap.binding_for(layout, cap.EV_ABS, ABS_RY, 30000) is None


def test_the_hat_bitmask_is_sdls_and_not_the_kernels(layout):
    """evdev reports a hat as two signed axes; SDL folds them into one
    bitfield per hat. up=1 right=2 down=4 left=8, and the vertical axis is
    POSITIVE downwards."""
    assert cap.binding_for(layout, cap.EV_ABS, ABS_HAT0X, 1) == "h0.2"
    assert cap.binding_for(layout, cap.EV_ABS, ABS_HAT0X, -1) == "h0.8"
    assert cap.binding_for(layout, cap.EV_ABS, ABS_HAT0Y, 1) == "h0.4"
    assert cap.binding_for(layout, cap.EV_ABS, ABS_HAT0Y, -1) == "h0.1"
    assert cap.binding_for(layout, cap.EV_ABS, ABS_HAT0X, 0) is None, "centred"


# The two axes a DualShock 4 really declares, read from this box with the pad
# connected. They are identical apart from where they sit — which is the whole
# reason the old `flat` test could not work.
DS4_STICK = cap.Axis(minimum=0, maximum=255, rest=128)
DS4_TRIGGER = cap.Axis(minimum=0, maximum=255, rest=0)
CENTRED_STICK = cap.Axis(minimum=-32768, maximum=32767, rest=0)


def test_a_resting_stick_does_not_bind_anything(layout):
    """The single most common way a naive capture loop produces garbage: an
    analogue stick at rest drifts continuously, so the first button the player
    is asked for gets bound to whichever axis twitched.

    This used to compare `abs(value)` against the kernel's `flat`, which only
    works for an axis centred on zero. A DualShock 4's ABS_X is `0..255` with
    `flat=0` resting at 128, so the guard passed EVERY reading — the pad sitting
    still on a table drove the wizard by itself.
    """
    assert cap.binding_for(layout, cap.EV_ABS, ABS_X, 128, DS4_STICK) is None
    assert cap.binding_for(layout, cap.EV_ABS, ABS_X, 133, DS4_STICK) is None
    assert cap.binding_for(layout, cap.EV_ABS, ABS_X, 255, DS4_STICK) == "a0"
    assert cap.binding_for(layout, cap.EV_ABS, ABS_X, 0, DS4_STICK) == "a0", (
        "pushed the other way is just as pushed")
    # And the axis that DOES rest at zero still behaves.
    assert cap.binding_for(layout, cap.EV_ABS, ABS_X, 900, CENTRED_STICK) is None
    assert cap.binding_for(layout, cap.EV_ABS, ABS_X, 30000, CENTRED_STICK) == "a0"


def test_a_trigger_is_told_from_a_stick_by_where_it_rests(layout):
    """Nothing in the descriptor separates them — a DualShock 4 declares both
    as `0..255`. Only the resting value does, and travel is therefore measured
    per direction: a stick can move 127 from its midpoint, a trigger 255 from
    its minimum, and dividing by the full span would make a fully pushed stick
    read as half pressed."""
    assert cap.binding_for(layout, cap.EV_ABS, ABS_Z, 255, DS4_TRIGGER) == "a2"
    assert cap.binding_for(layout, cap.EV_ABS, ABS_Z, 20, DS4_TRIGGER) is None
    # The same number read two ways. 160 is 63% of a trigger's travel and only
    # 25% of a stick's; 51 is 61% of a stick's and 20% of a trigger's.
    assert cap.binding_for(layout, cap.EV_ABS, ABS_Z, 160, DS4_TRIGGER) == "a2"
    assert cap.binding_for(layout, cap.EV_ABS, ABS_X, 160, DS4_STICK) is None
    assert cap.binding_for(layout, cap.EV_ABS, ABS_X, 51, DS4_STICK) == "a0"
    assert cap.binding_for(layout, cap.EV_ABS, ABS_Z, 51, DS4_TRIGGER) is None


def test_an_axis_nobody_can_describe_is_unmappable(layout):
    """Refusal, not a guess. Without knowing where an axis rests there is no
    way to read its value at all, and a wrong reading here is a binding on
    something the player never touched."""
    assert cap.binding_for(layout, cap.EV_ABS, ABS_X, 30000, None) is None


def test_a_direction_can_be_narrowed_to_half_an_axis(layout):
    """A trigger resting at its minimum and a stick resting at centre produce
    the same event. Only the step being asked for knows which, so the sign is
    applied by the caller rather than guessed here."""
    assert cap.half_axis("a2", 30000) == "+a2"
    assert cap.half_axis("a2", -30000) == "-a2"
    assert cap.half_axis("b3", 1) == "b3", "a button has no half"


def test_which_half_is_measured_from_rest_not_from_zero(layout):
    """A DualShock 4 stick runs 0..255 from its midpoint, so every reading is
    positive: pushing it left came out `+a0`, the same token as pushing it
    right, and a wizard step asking for a direction recorded the wrong one."""
    assert cap.half_axis("a0", 255, DS4_STICK) == "+a0"
    assert cap.half_axis("a0", 0, DS4_STICK) == "-a0"


# ── which nodes a session reads ──────────────────────────────────────────────

def test_a_motion_sensor_node_is_not_a_joystick():
    """Measured on this box: a DualShock 4 lying untouched emitted 4335 events
    in three seconds from its `Motion Sensors` node, which `binding_for` turned
    into 2561 axis tokens named a0..a5 — the same names as the real pad's
    sticks, because each node is numbered from its own capabilities. Every one
    armed the wizard's hold timer, and a hold skips the step."""
    assert cap._is_joystick(FACE)
    assert not cap._is_joystick([]), "the DS4 motion node declares no keys"
    # Its touchpad node: BTN_LEFT, BTN_TOOL_FINGER, BTN_TOUCH, BTN_TOOL_DOUBLETAP
    assert not cap._is_joystick([0x110, 0x145, 0x14A, 0x14D])


def test_a_pad_with_no_gamepad_names_is_still_a_joystick():
    """The kernel's joystick range, not just the gamepad one: an arcade stick
    or a clone declaring BTN_TRIGGER/BTN_THUMB must still be read, and so must
    a pad with more buttons than names that spills into BTN_TRIGGER_HAPPY."""
    assert cap._is_joystick([BTN_TRIGGER, BTN_THUMB])
    assert cap._is_joystick([0x2C0, 0x2C1])
    assert not cap._is_joystick([KEY_A, KEY_ENTER]), "a keyboard is not one"


# ── the line ─────────────────────────────────────────────────────────────────

GUID = "03000325adde0000efbe000011010000"


def test_the_line_is_a_valid_sdl_mapping():
    line = cap.mapping_line(GUID, "Generic USB Gamepad",
                            {"a": "b0", "b": "b1", "leftx": "a0",
                             "dpup": "h0.1", "lefttrigger": "+a2"})

    assert mapping_db.parse(line), f"our own parser rejects what we write: {line}"
    assert line.startswith(f"{GUID},Generic USB Gamepad,")
    assert line.endswith("platform:Linux,")
    assert "dpup:h0.1" in line and "lefttrigger:+a2" in line


def test_the_field_order_is_stable():
    """The same pad mapped twice must produce the same line, whatever order the
    player happened to press things in — otherwise two captures of one pad
    cannot be diffed, and `upsert` cannot tell an update from a new entry."""
    bindings = {"a": "b0", "b": "b1", "start": "b9", "leftx": "a0"}

    first = cap.mapping_line(GUID, "Pad", bindings)
    second = cap.mapping_line(GUID, "Pad", dict(reversed(list(bindings.items()))))

    assert first == second


def test_a_comma_in_the_name_cannot_break_the_line():
    """The device name is the second CSV field and it comes from the pad, which
    means from a stranger. One comma would shift every binding into the wrong
    column and SDL would read the mapping as a different pad's."""
    line = cap.mapping_line(GUID, "Acme, Inc. Pad", {"a": "b0"})

    guid, name, _bindings = mapping_db.parse(line)
    assert guid == GUID and "," not in name


def test_an_empty_capture_is_refused():
    """A line with a GUID, a name and no binding parses as valid and maps
    nothing. Written to the served database it SHADOWS the community entry for
    that pad — last line wins — so an abandoned wizard would take away a
    mapping that worked."""
    with pytest.raises(ValueError):
        cap.mapping_line(GUID, "Pad", {})
    with pytest.raises(ValueError):
        cap.mapping_line(GUID, "   ", {"a": "b0"})


# ── the session ──────────────────────────────────────────────────────────────

@pytest.fixture
def clean_session():
    cap.cancel()
    yield
    cap.cancel()


def test_commit_without_a_session_is_refused(clean_session):
    assert cap.commit({"a": "b0"})["ok"] is False


def test_the_wizard_refuses_to_start_with_two_pads(clean_session, monkeypatch):
    """The same rule "Scan mapping" applies: with two pads connected there is
    no way to know which one is in the owner's hands, and a mapping filed under
    the wrong GUID is a wrong answer that survives reboots."""
    monkeypatch.setattr(cap, "detect_pads",
                        lambda *a, **k: [("054c", "09cc", "A"), ("045e", "02fd", "B")])

    result = cap.start()

    assert result["ok"] is False and "exactly one" in result["error"]


def test_a_pad_no_sdl_can_name_is_refused(clean_session, monkeypatch):
    """A GUID is what SDL looks a mapping up by. Without one there is nothing
    to file the capture under, and writing it under an invented id is the
    "invented identity" this pipeline refuses everywhere else."""
    monkeypatch.setattr(cap, "detect_pads", lambda *a, **k: [("1d79", "0f0f", "Pad")])
    monkeypatch.setattr(cap, "_pad_nodes",
                        lambda v, p: ("aa:bb", {"/dev/input/event9": cap.sdl_layout(FACE, [])}))
    monkeypatch.setattr(cap, "sdl_guids", lambda *a, **k: [])

    result = cap.start()

    assert result["ok"] is False and "GUID" in result["error"]


def test_a_capture_is_written_once_per_sdl_identity(clean_session, monkeypatch, tmp_path):
    """The same pad has several GUIDs at once — the host's SDL3 says `0500…`
    where Ryujinx's bundled SDL2 says `0300…`, one byte of bus type apart. A
    mapping filed under one is invisible to the emulators that compute the
    other, which is exactly the "works in RPCS3, dead in Ryujinx" this avoids.
    """
    monkeypatch.setattr(mapping_db, "USER_DB", tmp_path / "user.txt")
    monkeypatch.setattr(mapping_db, "SERVED_DB", tmp_path / "served.txt")
    monkeypatch.setattr(mapping_db, "DB_FILE", tmp_path / "community.txt")
    (tmp_path / "community.txt").write_text("# nothing\n")

    guids = ["05008fe54c050000cc09000000006800", "03008fe54c050000cc09000000006800"]
    monkeypatch.setattr(cap, "detect_pads", lambda *a, **k: [("054c", "09cc", "Pad")])
    monkeypatch.setattr(cap, "_pad_nodes",
                        lambda v, p: ("84:30", {"/dev/input/event9": cap.sdl_layout(FACE, [])}))
    monkeypatch.setattr(cap, "sdl_guids", lambda *a, **k: guids)
    monkeypatch.setattr(cap, "display_name", lambda *a: "Generic Pad")

    assert cap.start()["ok"] is True
    result = cap.commit({"a": "b0", "b": "b1", "start": "b9"})

    assert result["ok"] is True
    written = mapping_db.read_user()
    assert len(written) == 2, written
    assert {mapping_db.parse(ln)[0] for ln in written} == set(guids)


def test_committing_closes_the_session(clean_session, monkeypatch, tmp_path):
    """A session left open holds file descriptors on /dev/input and would let a
    second commit re-file whatever the first wrote."""
    monkeypatch.setattr(mapping_db, "USER_DB", tmp_path / "user.txt")
    monkeypatch.setattr(mapping_db, "SERVED_DB", tmp_path / "served.txt")
    monkeypatch.setattr(mapping_db, "DB_FILE", tmp_path / "community.txt")
    (tmp_path / "community.txt").write_text("# nothing\n")
    monkeypatch.setattr(cap, "detect_pads", lambda *a, **k: [("054c", "09cc", "Pad")])
    monkeypatch.setattr(cap, "_pad_nodes",
                        lambda v, p: ("84:30", {"/dev/input/event9": cap.sdl_layout(FACE, [])}))
    monkeypatch.setattr(cap, "sdl_guids", lambda *a, **k: [GUID])
    monkeypatch.setattr(cap, "display_name", lambda *a: "Pad")

    cap.start()
    cap.commit({"a": "b0"})

    assert cap.current() is None
    assert cap.commit({"a": "b1"})["ok"] is False


def test_the_missing_buttons_are_reported(clean_session, monkeypatch, tmp_path):
    """A pad with no right stick is normal; a pad with no Start is a capture
    the player abandoned. The UI can only tell them apart if the backend says
    which required fields are absent."""
    monkeypatch.setattr(mapping_db, "USER_DB", tmp_path / "user.txt")
    monkeypatch.setattr(mapping_db, "SERVED_DB", tmp_path / "served.txt")
    monkeypatch.setattr(mapping_db, "DB_FILE", tmp_path / "community.txt")
    (tmp_path / "community.txt").write_text("# nothing\n")
    monkeypatch.setattr(cap, "detect_pads", lambda *a, **k: [("054c", "09cc", "Pad")])
    monkeypatch.setattr(cap, "_pad_nodes",
                        lambda v, p: ("84:30", {"/dev/input/event9": cap.sdl_layout(FACE, [])}))
    monkeypatch.setattr(cap, "sdl_guids", lambda *a, **k: [GUID])
    monkeypatch.setattr(cap, "display_name", lambda *a: "Pad")

    cap.start()
    result = cap.commit({"a": "b0", "b": "b1", "x": "b2", "y": "b3",
                         "dpup": "h0.1", "dpdown": "h0.4",
                         "dpleft": "h0.8", "dpright": "h0.2",
                         "leftshoulder": "b4", "rightshoulder": "b5",
                         "back": "b6", "leftx": "a0", "lefty": "a1"})

    assert result["missing"] == ["start"], result["missing"]
    assert "guide" not in result["missing"], "the guide button is optional"


def test_every_step_is_a_field_sdl_understands():
    """A typo in STEPS would produce a line SDL parses and silently drops the
    field from — the wizard would ask for a button and record it nowhere."""
    known = {
        "a", "b", "x", "y", "back", "guide", "start", "leftstick", "rightstick",
        "leftshoulder", "rightshoulder", "dpup", "dpdown", "dpleft", "dpright",
        "leftx", "lefty", "rightx", "righty", "lefttrigger", "righttrigger",
        "misc1", "paddle1", "paddle2", "paddle3", "paddle4", "touchpad",
    }
    fields = [field for field, _kind, _label in cap.STEPS]

    assert set(fields) <= known, set(fields) - known
    assert len(fields) == len(set(fields)), "a step is listed twice"
    assert cap.OPTIONAL <= set(fields), "an optional field is not a step"
