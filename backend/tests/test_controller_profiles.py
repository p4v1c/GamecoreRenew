"""Unit tests for the emulator profilers (services.controller_profiles).

Focused on _dolphin's "is this section already a real pad config?" decision,
which is what decides between retargeting a section and rewriting it. Getting
that wrong is invisible until someone plays: the pad connects, the emulator
launches, and only the D-Pad is dead.

Run under pytest:  pytest backend/tests/test_controller_profiles.py
Or directly:       python backend/tests/test_controller_profiles.py
"""
import json
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



# ── the donor must be a healthy section, not GCPad1 on faith ─────────────────

def test_a_contaminated_gcpad1_repairs_itself(dolphin_dir):
    """The bug that shipped: GCPad1 was the donor AND the broken section.

    Only its Device line was rewritten, so the D-Pad and Z stayed on keyboard
    keys for player 1 in every GameCube game, while player 2 — the one section
    that happened to be correct — worked fine.
    """
    write_ini(dolphin_dir, {"GCPad1": KEYBOARD_PAD, "GCPad2": GOOD_PAD})

    msg = cp._dolphin(1, 0, "054c", "09cc", "PS4 Controller")

    body = cp.section((dolphin_dir / "GCPadNew.ini").read_text(), "GCPad1")
    assert "`T`" not in body and "`D`" not in body, "keyboard keys must be gone"
    assert "D-Pad/Up = `Pad N`" in body and "Buttons/Z = Back" in body
    assert "Device = SDL/0/PS4 Controller" in body
    assert "GCPad2" in (msg or ""), "it should say where the bindings came from"


def test_every_section_broken_falls_back_to_the_template(dolphin_dir):
    """No healthy donor anywhere — the canonical body lives in the code."""
    write_ini(dolphin_dir, {f"GCPad{n}": KEYBOARD_PAD for n in (1, 2, 3, 4)})

    cp._dolphin(3, 0, "054c", "09cc", "PS4 Controller")

    body = cp.section((dolphin_dir / "GCPadNew.ini").read_text(), "GCPad3")
    assert cp._gcpad_is_real(body)
    assert "Main Stick/Up = `Left Y+`" in body and "Triggers/L = `Shoulder L`" in body


def test_a_keyboard_modifier_does_not_survive(dolphin_dir):
    """`Main Stick/Modifier = `Shift`` passed the old blacklist, and a keyboard
    held down shrank three players' stick range."""
    write_ini(dolphin_dir, {"GCPad1": GOOD_PAD + "Main Stick/Modifier = `Shift`\n"})

    cp._dolphin(1, 0, "054c", "09cc", "PS4 Controller")

    body = cp.section((dolphin_dir / "GCPadNew.ini").read_text(), "GCPad1")
    assert "Modifier" not in body


def test_one_pad_cannot_hold_two_ports(dolphin_dir):
    """GCPad2 and GCPad3 both held `SDL/0/Xbox One Controller` on the box, and
    Mario Party moved two characters together."""
    write_ini(dolphin_dir, {"GCPad1": GOOD_PAD,
                            "GCPad3": GOOD_PAD.replace("SDL/0/", "SDL/0/")})

    cp._dolphin(1, 0, "054c", "09cc", "PS4 Controller")

    t = (dolphin_dir / "GCPadNew.ini").read_text()
    assert "Device = SDL/0/PS4 Controller" in cp.section(t, "GCPad1")
    assert "Device =\n" in cp.section(t, "GCPad3"), "the stale duplicate is unbound"


def test_profiling_twice_changes_nothing(dolphin_dir):
    """The scan runs every three seconds for the whole session."""
    write_ini(dolphin_dir, {"GCPad1": KEYBOARD_PAD, "GCPad2": GOOD_PAD})
    cp._dolphin(1, 0, "054c", "09cc", "PS4 Controller")

    before = (dolphin_dir / "GCPadNew.ini").read_text()
    assert cp._dolphin(1, 0, "054c", "09cc", "PS4 Controller") is None
    assert (dolphin_dir / "GCPadNew.ini").read_text() == before


# ── release_profile must neutralise Source, not delete it ────────────────────

def test_releasing_a_wiimote_writes_source_zero(dolphin_dir):
    """Dolphin's compiled-in default for Wiimote1 is Emulated, so a block with
    no Source key at all presents a connected remote bound to a pointer with no
    buttons: the game asks for A and nothing on the box can answer."""
    (dolphin_dir / "WiimoteNew.ini").write_text(
        "[Wiimote1]\nSource = 1\nDevice = SDL/0/PS4 Controller\nButtons/A = `Button S`\n")

    cp.release_profile(1)

    body = cp.section((dolphin_dir / "WiimoteNew.ini").read_text(), "Wiimote1")
    assert "Source = 0" in body, "the emulated remote must be switched off, not orphaned"


def test_releasing_unbinds_the_gamecube_port(dolphin_dir):
    """Otherwise the port stays pinned to a pad that has left, and the next pad
    to take a lower slot is written next to it."""
    write_ini(dolphin_dir, {"GCPad1": GOOD_PAD})

    cp.release_profile(1)

    body = cp.section((dolphin_dir / "GCPadNew.ini").read_text(), "GCPad1")
    assert "Device = SDL/" not in body
    assert "Buttons/A = `Button S`" in body, "only the device goes, not the mapping"


# ── Ryujinx: the GUID is a conversion, not a guess ───────────────────────────

def test_the_ryujinx_guid_is_dotnets_rendering_of_the_sdl_bytes():
    """Ryujinx hands SDL2's 16 GUID bytes to System.Guid, whose string form
    reverses the first three fields. Both cases below are byte-for-byte what
    the reference box's Config.json holds."""
    assert cp.ryu_guid_from_sdl2("030000004c050000cc09000000006800") == \
        "00000003-054c-0000-cc09-000000006800"      # DualShock 4, USB/HIDAPI
    assert cp.ryu_guid_from_sdl2("050000005e040000fd02000003090000") == \
        "00000005-045e-0000-fd02-000003090000"      # Xbox One, Bluetooth


def test_a_guid_is_never_fabricated_from_another_one():
    """The old best-effort swapped vendor/product into a reference GUID and
    kept its bus and driver bytes, so a DualShock 4 GUID with Xbox vendor bytes
    came out as bus 0x0003 with a HIDAPI tail — a device that has never
    existed. The two real GUIDs differ in far more than vendor:product."""
    ds4 = cp.ryu_guid_from_sdl2("030000004c050000cc09000000006800")
    xbox = cp.ryu_guid_from_sdl2("050000005e040000fd02000003090000")
    assert ds4.split("-")[0] != xbox.split("-")[0], "bus type differs"
    assert ds4.split("-")[-1] != xbox.split("-")[-1], "driver/version tail differs"


def test_a_malformed_guid_yields_nothing():
    """A wrong id disposes the Ryujinx slot in silence, so anything short of a
    real answer must be no answer."""
    assert cp.ryu_guid_from_sdl2("") is None
    assert cp.ryu_guid_from_sdl2("0300") is None
    assert cp.ryu_guid_from_sdl2("zzzz00004c050000cc09000000006800") is None


def test_ryujinx_leaves_the_slot_alone_when_sdl_says_nothing(tmp_path, monkeypatch):
    cfg = tmp_path / "Config.json"
    cfg.write_text(json.dumps({"input_config": [
        {"player_index": "Player1", "backend": "GamepadSDL2",
         "id": "0-00000003-054c-0000-cc09-000000006800", "name": "PS4 Controller (0)"}]}))
    monkeypatch.setattr(cp, "RYUJINX_CFG", cfg)
    monkeypatch.setattr(cp, "_sdl2_probe", lambda v, p: {})

    before = cfg.read_text()
    msg = cp._ryujinx(2, 0, "045e", "02fd", "Xbox One Controller")

    assert isinstance(msg, cp.Skip), "a give-up has to be reported, not swallowed"
    assert cfg.read_text() == before, "an invented id is worse than an untouched slot"


def test_ryujinx_does_not_rewrite_a_slot_that_is_already_right(tmp_path, monkeypatch):
    """This was the only writer that rewrote its whole 11 KB config on every
    single connection, battery warnings included."""
    cfg = tmp_path / "Config.json"
    cfg.write_text(json.dumps({"input_config": [
        {"player_index": "Player1", "backend": "GamepadSDL2",
         "id": "0-00000003-054c-0000-cc09-000000006800", "name": "PS4 Controller (0)"}]}, indent=2))
    monkeypatch.setattr(cp, "RYUJINX_CFG", cfg)
    monkeypatch.setattr(cp, "_sdl2_probe",
                        lambda v, p: {"guid": "030000004c050000cc09000000006800"})

    before = cfg.read_text()
    assert cp._ryujinx(1, 0, "054c", "09cc", "PS4 Controller") is None
    assert cfg.read_text() == before


def test_ryujinx_replaces_a_keyboard_slot_instead_of_mutating_it(tmp_path, monkeypatch):
    """Mutating the id of a keyboard config left it claiming to be an SDL
    device: the pad did not work and neither did the keyboard."""
    cfg = tmp_path / "Config.json"
    cfg.write_text(json.dumps({"input_config": [
        {"player_index": "Player1", "backend": "GamepadSDL2", "controller_type": "ProController",
         "id": "0-00000003-054c-0000-cc09-000000006800", "name": "PS4 Controller (0)"},
        {"player_index": "Player2", "backend": "WindowKeyboard", "id": "0"}]}))
    monkeypatch.setattr(cp, "RYUJINX_CFG", cfg)
    monkeypatch.setattr(cp, "_sdl2_probe",
                        lambda v, p: {"guid": "050000005e040000fd02000003090000"})

    cp._ryujinx(2, 0, "045e", "02fd", "Xbox One Controller")

    slot = [e for e in json.loads(cfg.read_text())["input_config"]
            if e["player_index"] == "Player2"][0]
    assert slot["backend"] == "GamepadSDL2"
    assert slot["id"] == "0-00000005-045e-0000-fd02-000003090000"
    assert slot["controller_type"] == "ProController", "cloned from the gamepad slot"


# ── RPCS3: a Null slot is the case that needs repairing ──────────────────────

_RPCS3_BOUND = """\
Player {n} Input:
  Handler: SDL
  Device: PS4 Controller 1
  Config:
    Cross: South
    Circle: East
    Start: Start
"""
_RPCS3_NULL = """\
Player {n} Input:
  Handler: "Null"
  Device: Xbox One Wireless Controller 1
  Config:
    Cross: ""
    Circle: ""
    Start: ""
"""


def test_rpcs3_rebuilds_a_null_slot(tmp_path, monkeypatch):
    """`Handler: "Null"` with blank bindings is exactly what RPCS3 saves when a
    Device matched nothing — and it used to be the one state that returned
    early, so players 2-4 could never come back."""
    yml = tmp_path / "Default.yml"
    yml.write_text(_RPCS3_BOUND.format(n=1) + _RPCS3_NULL.format(n=2))
    monkeypatch.setattr(cp, "rpcs3_default", lambda: yml)

    msg = cp._rpcs3(2, 0, "045e", "02fd", "Xbox One Controller")

    block = cp._rpcs3_block(yml.read_text(), 2).group(1)
    assert cp._rpcs3_is_bound(block), "it has to end up actually bound"
    assert "Device: Xbox One Controller 1" in block
    assert "Cross: South" in block, "the role bindings come from the healthy player"
    assert msg and "rebuilt" in msg


def test_rpcs3_says_so_when_there_is_nothing_to_clone(tmp_path, monkeypatch):
    yml = tmp_path / "Default.yml"
    yml.write_text(_RPCS3_NULL.format(n=1) + _RPCS3_NULL.format(n=2))
    monkeypatch.setattr(cp, "rpcs3_default", lambda: yml)

    assert isinstance(cp._rpcs3(2, 0, "045e", "02fd", "Xbox One Controller"), cp.Skip)


# ── PCSX2 / DuckStation ──────────────────────────────────────────────────────

_DUCK = """\
[ControllerPorts]
MultitapMode = Disabled

[Pad1]
Cross = SDL-0/A
LDown = SDL-0/+LeftY
Type = DigitalController

[Pad2]
Type = None

"""


def test_duckstation_player_one_gets_its_sticks_back(tmp_path):
    """DigitalController declares 14 digital inputs, so every analog binding
    already in [Pad1] was dead: no sticks, no rumble. _tier0_ini returned on
    its first line for i == 1, so nothing could ever fix it."""
    ini = tmp_path / "settings.ini"
    ini.write_text(_DUCK)

    cp._tier0_ini(ini, "duckstation", 1)

    assert "Type = AnalogController" in cp.section(ini.read_text(), "Pad1")


def test_a_third_player_turns_the_multitap_on(tmp_path):
    """PS1 and PS2 have two ports. Writing [Pad3] and reporting success
    promised a third player that could never move."""
    ini = tmp_path / "settings.ini"
    ini.write_text(_DUCK)

    msg = cp._tier0_ini(ini, "duckstation", 3)

    t = ini.read_text()
    assert "MultitapMode = Port1Only" in cp.section(t, "ControllerPorts")
    assert "SDL-2/" in cp.section(t, "Pad3")
    assert msg and "multitap" in msg


def test_two_players_do_not_need_a_multitap(tmp_path):
    ini = tmp_path / "settings.ini"
    ini.write_text(_DUCK)

    cp._tier0_ini(ini, "duckstation", 2)

    assert "MultitapMode = Disabled" in cp.section(ini.read_text(), "ControllerPorts")


def test_an_unusable_pad1_is_reported_not_swallowed(tmp_path):
    """It abandons players 2, 3 and 4 — that deserves a line in the journal."""
    ini = tmp_path / "settings.ini"
    ini.write_text("[ControllerPorts]\nMultitapMode = Disabled\n\n[Pad1]\nType = None\n\n")

    assert isinstance(cp._tier0_ini(ini, "duckstation", 2), cp.Skip)


# ── snapshots ────────────────────────────────────────────────────────────────

def test_a_snapshot_of_the_wrong_controller_is_refused(tmp_path, monkeypatch):
    """cemu/045e_02fd.snap and cemu/054c_09cc.snap on the box are
    byte-identical, both the DualShock 4's config: "Scan mapping" was pressed
    with the Xbox pad connected while the file still held the DS4."""
    xml = tmp_path / "controller0.xml"
    xml.write_text("<emulated_controller>\n"
                   "<uuid>0_05009b514c050000cc09000000810000</uuid>\n"
                   "</emulated_controller>\n")
    monkeypatch.setattr(cp, "SNAP_DIR", tmp_path / "snaps")
    monkeypatch.setitem(cp._SNAP_EMUS, "cemu",
                        (lambda: xml, cp._whole_extract, cp._whole_replace))

    saved, refused = cp.snapshot_capture("045e", "02fd")
    assert "cemu" in refused and "cemu" not in saved

    saved, refused = cp.snapshot_capture("054c", "09cc")
    assert "cemu" in saved and "cemu" not in refused


def test_mgba_captures_the_section_that_binds_buttons(tmp_path, monkeypatch):
    """The old extractor took [gba.input-profile.<GUID>], which holds tilt and
    gyro axes and not one button — 180 bytes of gyroSensitivity, saved and
    restored with a success message, while nothing moved."""
    ini = ("[gba.input.SDLB]\n"
           "keyA=0\nkeyB=1\nkeyL=9\nkeyR=10\n"
           "device0=05008fe54c050000cc09000000006800\n\n"
           "[gba.input-profile.05008fe54c050000cc09000000006800]\n"
           "gyroSensitivity=2,2e+09\n\n"
           "[ports.qt]\nsomething=1\n")

    block = cp._mgba_extract(ini)
    assert "keyA=0" in block and "keyL=9" in block, "the buttons must be in there"
    assert "gyroSensitivity" in block, "and the motion axes alongside"
    assert cp._mgba_replace(ini, block) == ini, "round-trip must not disturb the file"
    assert "something=1" in cp._mgba_replace(ini, block.replace("keyA=0", "keyA=2"))


def test_azahar_follows_the_active_profile(tmp_path):
    """Qt stores the selected index 0-based in `profile=` and writes the array
    1-based, so `profiles\\1\\` is only right while profile=0."""
    one = "[Controls]\nprofile=0\nprofiles\\1\\button_a=\"button:0\"\n"
    two = "[Controls]\nprofile=1\nprofiles\\2\\button_a=\"button:0\"\n"
    assert cp._az_prefix(one) == "profiles\\1\\"
    assert cp._az_prefix(two) == "profiles\\2\\"
    assert cp._az_extract(two).strip() == 'profiles\\2\\button_a="button:0"'


if __name__ == "__main__":
    import tempfile

    class _Monkeypatch:
        """Enough of pytest's monkeypatch for the tests below."""
        def __init__(self):
            self._undo = []

        def setattr(self, obj, name, value):
            self._undo.append(("attr", obj, name, getattr(obj, name)))
            setattr(obj, name, value)

        def setitem(self, mapping, key, value):
            self._undo.append(("item", mapping, key, mapping.get(key)))
            mapping[key] = value

        def undo(self):
            for kind, obj, key, old in reversed(self._undo):
                if kind == "attr":
                    setattr(obj, key, old)
                else:
                    obj[key] = old
            self._undo.clear()

    # (function, which fixtures it wants) — dolphin_dir also patches DOLPHIN_DIR.
    CASES = [
        (test_a_section_with_a_keyboard_dpad_is_rewritten, "dolphin"),
        (test_a_real_section_is_only_retargeted, "dolphin"),
        (test_a_hand_customised_mapping_is_not_thrown_away, "dolphin"),
        (test_an_empty_section_is_created_from_gcpad1, "dolphin"),
        (test_a_contaminated_gcpad1_repairs_itself, "dolphin"),
        (test_every_section_broken_falls_back_to_the_template, "dolphin"),
        (test_a_keyboard_modifier_does_not_survive, "dolphin"),
        (test_one_pad_cannot_hold_two_ports, "dolphin"),
        (test_profiling_twice_changes_nothing, "dolphin"),
        (test_releasing_a_wiimote_writes_source_zero, "dolphin"),
        (test_releasing_unbinds_the_gamecube_port, "dolphin"),
        (test_the_ryujinx_guid_is_dotnets_rendering_of_the_sdl_bytes, ""),
        (test_a_guid_is_never_fabricated_from_another_one, ""),
        (test_a_malformed_guid_yields_nothing, ""),
        (test_ryujinx_leaves_the_slot_alone_when_sdl_says_nothing, "tmp+mp"),
        (test_ryujinx_does_not_rewrite_a_slot_that_is_already_right, "tmp+mp"),
        (test_ryujinx_replaces_a_keyboard_slot_instead_of_mutating_it, "tmp+mp"),
        (test_rpcs3_rebuilds_a_null_slot, "tmp+mp"),
        (test_rpcs3_says_so_when_there_is_nothing_to_clone, "tmp+mp"),
        (test_duckstation_player_one_gets_its_sticks_back, "tmp"),
        (test_a_third_player_turns_the_multitap_on, "tmp"),
        (test_two_players_do_not_need_a_multitap, "tmp"),
        (test_an_unusable_pad1_is_reported_not_swallowed, "tmp"),
        (test_a_snapshot_of_the_wrong_controller_is_refused, "tmp+mp"),
        (test_mgba_captures_the_section_that_binds_buttons, "tmp+mp"),
        (test_azahar_follows_the_active_profile, "tmp"),
        (test_the_shipped_ini_has_no_keyboard_bindings_left, ""),
    ]

    for fn, wants in CASES:
        mp, saved = _Monkeypatch(), cp.DOLPHIN_DIR
        with tempfile.TemporaryDirectory() as tmp:
            args = []
            if wants == "dolphin":
                cp.DOLPHIN_DIR = Path(tmp)
                args = [Path(tmp)]
            elif wants in ("tmp", "tmp+mp"):
                args = [Path(tmp)]
                if wants == "tmp+mp":
                    args.append(mp)
            try:
                fn(*args)
            finally:
                cp.DOLPHIN_DIR = saved
                mp.undo()
        print(f"[OK ] {fn.__name__}")
    print("\nAll tests passed.")
