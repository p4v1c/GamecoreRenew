"""The N64 pack writing a profile of its own, and taking one back.

gopher64 was the last red system on the 15 August 2026 bench: at its zero point
the game says "connect a controller to socket 1", and the only way out was to
map the pad by hand inside RMG. These tests pin the two halves of the fix — a
synthesised profile that RMG will actually match, and an inverse that puts a
port back to the socket-nobody-assigned shape.

Everything asserted here about RMG's own file was MEASURED, not derived: the
binding values come from upstream's `Data/InputProfileDB.json`, the empty-socket
shape from the reference box's own `mupen64plus.cfg`, and the identity strings
from libSDL3 with the pad connected. Where the brief that commissioned this work
and the measurement disagreed, the measurement is what is pinned — see
`test_an_empty_socket_is_device_type_zero` and
`test_the_n64_b_button_is_sdl_x_not_sdl_b`.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

from backend.services.configgen.controllers import ResolvedName
from backend.services.configgen.helpers.base import Skip

ROOT = Path(__file__).resolve().parents[2]

P = "Rosalie's Mupen GUI - Input Plugin"

# The pad that was connected while this was measured.
VENDOR, PRODUCT = "054c", "09cc"
SDL_NAME = "PS4 Controller"
SDL_PATH = "/dev/hidraw0"
SDL_SERIAL = "40:1b:5f:b9:ea:8d"


@pytest.fixture(scope="module")
def gen():
    spec = importlib.util.spec_from_file_location(
        "gopher64_generator_synth", ROOT / "catalog" / "gopher64" / "generator.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ── the file RMG writes for itself on first run ──────────────────────────────
#
# Trimmed to the keys that matter plus enough neighbours to prove nothing else
# moves. The key ORDER and the quoting are RMG's.

_GLOBALS = ("Deadzone = 9\n"
            "Sensitivity = 100\n"
            "Pak = 0\n"
            "RemoveDuplicateMappings = True\n"
            "FilterEventsForButtons = True\n"
            "FilterEventsForAxis = True\n")

_CONTROLS = ("A", "B", "Start", "DpadUp", "DpadDown", "DpadLeft", "DpadRight",
             "LeftTrigger", "RightTrigger", "ZTrigger",
             "CButtonUp", "CButtonDown", "CButtonLeft", "CButtonRight",
             "AnalogStickUp", "AnalogStickDown", "AnalogStickLeft",
             "AnalogStickRight")


def empty_profile(port: int) -> str:
    body = "".join(f'{c}_{f} = ""\n' for c in _CONTROLS
                   for f in ("InputType", "Name", "Data", "ExtraData"))
    return (f"[{P} Profile {port}]\n\n"
            "PluggedIn = False\n"
            'DeviceName = "None"\n'
            "DeviceType = 0\n"
            'DevicePath = ""\n'
            'DeviceSerial = ""\n'
            + _GLOBALS + body
            + 'UseProfile = ""\n'
            + 'Hotkey_Exit_Name = ""\n\n')


@pytest.fixture
def cfg(tmp_path):
    """RMG's own zero point: four sockets, none assigned."""
    p = tmp_path / "mupen64plus.cfg"
    p.write_text(f"[{P}]\n\nProfiles = \"\"\nControllerMode = 0\n\n"
                 + "".join(empty_profile(n) for n in range(4))
                 + "[Rosalie's Mupen GUI Core]\n\nRandomizeInterrupt = True\n")
    return p


class FakePad:
    """What a generator receives, minus everything gopher64 does not read."""

    def __init__(self, source="sdl3_live", name=SDL_NAME):
        self.vendor, self.product = VENDOR, PRODUCT
        self._name = ResolvedName(name, source)

    @property
    def name(self):
        return self._name


@pytest.fixture
def opts(cfg, tmp_path):
    return {"target": cfg, "snap_dir": tmp_path / "snaps",
            "config_dir": cfg.parent, "app_id": "com.github.Rosalie241.RMG",
            "controllers": {}, "home": tmp_path}


@pytest.fixture(autouse=True)
def sdl3(gen, monkeypatch):
    """SDL3 answers about the pad that was connected when this was measured.

    Patched for every test in the file: a probe that shells out to the real
    libSDL3 is green on a box with a pad plugged in and red on a runner, which
    is the failure `_hidraw_for`'s injectable root already exists to prevent.
    """
    seen: list[tuple] = []

    def identity(vendor, product, lib=""):
        seen.append((vendor, product, lib))
        return {"path": SDL_PATH, "serial": SDL_SERIAL}

    monkeypatch.setattr(gen.controllers, "sdl3_identity", identity)
    monkeypatch.setattr(gen.controllers, "bundled_sdl3",
                        lambda app_id: f"/runtime/{app_id}/libSDL3.so.0")
    return seen


def body(text: str, port: int) -> str:
    m = re.search(rf"(?ms)^\[{re.escape(P)} Profile {port}\]\n(.*?)(?=^\[|\Z)",
                  text)
    assert m, f"no profile {port} in the file"
    return m.group(1)


def keys(section: str) -> dict[str, str]:
    return {k.strip(): v.strip()
            for k, _s, v in (l.partition("=") for l in section.splitlines())
            if _s}


# ── synthesis ────────────────────────────────────────────────────────────────

def test_the_socket_is_plugged_in(gen, opts, cfg):
    """The zero-point symptom, in one key. Without `PluggedIn` the game asks for
    a controller on socket 1 however complete the rest of the profile is."""
    assert gen.generate(1, FakePad(), opts)
    assert keys(body(cfg.read_text(), 0))["PluggedIn"] == "True"


def test_all_three_identity_fields_come_from_sdl(gen, opts, cfg):
    """RMG-Input compares name, path and serial SIMULTANEOUSLY (main.cpp:647).
    One of the three wrong and the profile does not attach, in silence."""
    gen.generate(1, FakePad(), opts)
    k = keys(body(cfg.read_text(), 0))
    assert k["DeviceName"] == f'"{SDL_NAME}"'
    assert k["DevicePath"] == f'"{SDL_PATH}"'
    assert k["DeviceSerial"] == f'"{SDL_SERIAL}"'
    assert k["DeviceType"] == "4"          # InputDeviceType::Joystick


def test_the_emulators_own_sdl3_is_the_one_asked(gen, opts, sdl3):
    """RMG ships no SDL and links the runtime's. Asking some other SDL for a
    device path is how Ryujinx's slot got disposed by a bus byte."""
    gen.generate(1, FakePad(), opts)
    assert sdl3 == [(VENDOR, PRODUCT,
                     "/runtime/com.github.Rosalie241.RMG/libSDL3.so.0")]


def test_the_whole_binding_table_is_written(gen, opts, cfg):
    assert all(v == '""' for k, v in keys(body(cfg.read_text(), 0)).items()
               if k.endswith("_Data")), "the fixture is not a zero point"
    gen.generate(1, FakePad(), opts)
    k = keys(body(cfg.read_text(), 0))
    for control in _CONTROLS:
        assert k[f"{control}_Data"] != '""', f"{control} left unbound"
        assert k[f"{control}_InputType"] != '""'


def test_the_n64_b_button_is_sdl_x_not_sdl_b(gen, opts, cfg):
    """The one value the brief and the reference box disagreed about.

    Upstream's `fallback_profile` binds N64 `B` to SDL `x` (button 2) — the face
    button LEFT of `a`, which is where B sits on an N64 pad. The box's own file
    says `b`/1, and that is the OWNER's hand-mapping for an Xbox controller,
    which is exactly the work `snapshots.exists()` protects.
    """
    gen.generate(1, FakePad(), opts)
    k = keys(body(cfg.read_text(), 0))
    assert k["B_Data"] == '"2"'
    assert k["B_Name"] == '"x"'
    assert k["A_Data"] == '"0"'


def test_the_c_buttons_are_the_right_stick(gen, opts, cfg):
    """No modern pad has a C cluster, so this is where a plausible-looking
    mistake would hide. Four axis halves, two axes."""
    gen.generate(1, FakePad(), opts)
    k = keys(body(cfg.read_text(), 0))
    assert (k["CButtonUp_Data"], k["CButtonUp_ExtraData"]) == ('"3"', '"0"')
    assert (k["CButtonDown_Data"], k["CButtonDown_ExtraData"]) == ('"3"', '"1"')
    assert (k["CButtonLeft_Data"], k["CButtonLeft_ExtraData"]) == ('"2"', '"0"')
    assert (k["CButtonRight_Data"], k["CButtonRight_ExtraData"]) == ('"2"', '"1"')


def test_z_is_the_left_analog_trigger(gen, opts, cfg):
    """The N64's other control with no modern equivalent."""
    gen.generate(1, FakePad(), opts)
    k = keys(body(cfg.read_text(), 0))
    assert k["ZTrigger_InputType"] == '"1"'          # an AXIS, not a button
    assert (k["ZTrigger_Data"], k["ZTrigger_ExtraData"]) == ('"4"', '"1"')


def test_nothing_is_ever_written_in_the_raw_index_space(gen, opts, cfg):
    """InputType 0 and 1 are SDL_GameController CONSTANTS and are the same on
    every pad. 2, 3 and 4 are `JoystickButton/Axis/Hat` — raw indices, which
    differ per pad AND per driver. Writing those is the failure that broke mGBA
    and azahar on the morning of the bench, reached from the other side."""
    gen.generate(1, FakePad(), opts)
    k = keys(body(cfg.read_text(), 0))
    written = {v for key, v in k.items() if key.endswith("_InputType")}
    assert written <= {'"0"', '"1"'}, f"raw joystick index space used: {written}"


def test_a_second_pad_lands_on_its_own_port(gen, opts, cfg):
    gen.generate(1, FakePad(), opts)
    gen.generate(2, FakePad(), opts)
    text = cfg.read_text()
    assert keys(body(text, 1))["PluggedIn"] == "True"
    assert keys(body(text, 2))["DeviceName"] == '"None"'
    assert keys(body(text, 3))["DeviceName"] == '"None"'


def test_the_global_defaults_are_not_ours_to_write(gen, opts, cfg):
    """Deadzone, Sensitivity, Pak and the three filters are identical between an
    assigned profile and an empty one, and they are the owner's to tune."""
    gen.generate(1, FakePad(), opts)
    k = keys(body(cfg.read_text(), 0))
    assert k["Deadzone"] == "9" and k["Sensitivity"] == "100"
    assert k["Pak"] == "0" and k["FilterEventsForAxis"] == "True"
    assert k["UseProfile"] == '""'


def test_the_sections_that_are_not_ports_survive(gen, opts, cfg):
    """34 KB of Core, Video and Audio sit in this file. Surgery, not rewriting."""
    gen.generate(1, FakePad(), opts)
    text = cfg.read_text()
    assert "RandomizeInterrupt = True" in text
    assert "ControllerMode = 0" in text


def test_writing_the_same_profile_twice_changes_nothing(gen, opts, cfg):
    """The monitor reprofiles on every roster change. A file rewritten each time
    has an mtime that says something happened when nothing did."""
    assert gen.generate(1, FakePad(), opts)
    once = cfg.read_text()
    assert gen.generate(1, FakePad(), opts) is None
    assert cfg.read_text() == once


def test_four_ports_and_no_more(gen, opts):
    assert gen.generate(0, FakePad(), opts) is None
    assert gen.generate(5, FakePad(), opts) is None


# ── the two refusals ─────────────────────────────────────────────────────────

def test_a_pad_sdl3_cannot_name_is_left_alone(gen, opts, cfg):
    """`resolve_name` falling through to the kernel's name is the case that
    writes "SDL: Adding empty device" into an emulator's log. RMG matches by
    name, so an unsure name is a profile that binds nothing."""
    before = cfg.read_text()
    got = gen.generate(1, FakePad(source="unknown", name="Wireless Controller"),
                       opts)
    assert isinstance(got, Skip)
    assert cfg.read_text() == before


def test_the_hosts_sdl3_is_never_substituted_for_the_emulators(gen, opts, cfg,
                                                               monkeypatch):
    """The DualSense bug, in one assertion.

    This used to fall through to the host's libSDL3 when the emulator's could
    not be located. Measured, same box, same instant: the host spells a
    DualSense's serial `50-ee-32-32-88-2d` and the library RMG actually links
    spells it `50:ee:32:32:88:2d`. RMG compares that field by equality, so the
    pad got a complete, plausible, permanently unmatched profile — the right
    name, the right path, `PluggedIn = True`, and nothing in game.

    A DualShock 4 answers identically from both builds, which is exactly why
    one pad was not enough to establish the rule.
    """
    asked = []
    monkeypatch.setattr(gen.controllers, "bundled_sdl3", lambda app_id: "")

    def identity(vendor, product, lib=""):
        asked.append(lib)
        return {"path": "/dev/hidraw0", "serial": "50-ee-32-32-88-2d"}

    monkeypatch.setattr(gen.controllers, "sdl3_identity", identity)
    before = cfg.read_text()

    got = gen.generate(1, FakePad(), opts)

    assert asked == [], "the host's SDL3 was asked on the emulator's behalf"
    assert isinstance(got, Skip)
    assert cfg.read_text() == before


def test_a_native_emulator_is_still_answered_by_the_host(gen, opts, cfg,
                                                         monkeypatch):
    """The refusal is about a flatpak whose own library is out of reach. With
    no app id the box runs a native binary, and then the host's SDL3 IS its
    SDL3 — the same reasoning `generator_opts` uses to leave the id empty."""
    seen = []
    monkeypatch.setattr(gen.controllers, "sdl3_identity",
                        lambda v, p, lib="": seen.append(lib) or
                        {"path": SDL_PATH, "serial": SDL_SERIAL})
    monkeypatch.setattr(gen.controllers, "bundled_sdl3",
                        lambda app_id: pytest.fail("asked for a native install"))

    assert gen.generate(1, FakePad(), {**opts, "app_id": ""})
    assert seen == [""]


def test_no_device_path_is_a_refusal_not_a_guess(gen, opts, cfg, monkeypatch):
    """`{}` is "SDL was never asked", which is not a finding about the pad. An
    invented path is compared by equality and matches nothing."""
    monkeypatch.setattr(gen.controllers, "sdl3_identity",
                        lambda v, p, lib="": {})
    before = cfg.read_text()
    got = gen.generate(1, FakePad(), opts)
    assert isinstance(got, Skip)
    assert cfg.read_text() == before


def test_an_empty_serial_is_an_answer_and_not_an_absence(gen, opts, cfg,
                                                         monkeypatch):
    """Measured on the Xbox Wireless pad: SDL reads it through the evdev node
    and gives it NO serial, and RMG's own file for it says `DeviceSerial = ""`.
    Refusing to write that would leave the one pad this fix is for unbindable."""
    monkeypatch.setattr(gen.controllers, "sdl3_identity",
                        lambda v, p, lib="": {"path": "/dev/input/event14",
                                              "serial": ""})
    assert gen.generate(1, FakePad(), opts)
    k = keys(body(cfg.read_text(), 0))
    assert k["DevicePath"] == '"/dev/input/event14"'
    assert k["DeviceSerial"] == '""'
    assert k["PluggedIn"] == "True"


def test_no_config_file_yet_is_silence_not_a_skip(gen, opts, cfg):
    """RMG writes this file itself on first run. Never started is not a failure
    to report every three seconds."""
    cfg.unlink()
    assert gen.generate(1, FakePad(), opts) is None


# ── a hand-made snapshot always wins ─────────────────────────────────────────

def snapshot_for(snap_dir: Path, block: str) -> Path:
    p = snap_dir / "gopher64" / f"{VENDOR}_{PRODUCT}.snap"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(block)
    return p


OWNERS_PROFILE = (f"[{P} Profile 0]\n\n"
                  "PluggedIn = True\n"
                  f'DeviceName = "{SDL_NAME}"\n'
                  "DeviceType = 4\n"
                  'DevicePath = "/dev/hidraw7"\n'
                  'DeviceSerial = "40:1b:5f:b9:ea:8d"\n'
                  'B_InputType = "0"\n'
                  'B_Name = "circle"\n'
                  'B_Data = "1"\n'
                  'B_ExtraData = "0"\n\n')


def test_a_saved_mapping_is_not_overwritten_by_the_generic_one(gen, opts, cfg):
    """The owner mapped this pad inside RMG. `B` on SDL `b` is their decision,
    and the generic profile's `x` must not replace it."""
    snapshot_for(opts["snap_dir"], OWNERS_PROFILE)
    assert gen.generate(1, FakePad(), opts)
    k = keys(body(cfg.read_text(), 0))
    assert k["B_Data"] == '"1"'
    assert k["B_Name"] == '"circle"'


def test_the_snapshot_test_is_exists_and_not_a_falsy_return(gen, opts, cfg):
    """`restore()` answers None both for "no snapshot" and for "already
    applied". Conflating them is what made melonDS's synthesis overwrite the
    owner's captured mapping every OTHER connection — so the second call must
    not fall through to the generic profile."""
    snapshot_for(opts["snap_dir"], OWNERS_PROFILE)
    gen.generate(1, FakePad(), opts)
    after_first = cfg.read_text()
    assert gen.generate(1, FakePad(), opts) is None
    assert cfg.read_text() == after_first
    assert keys(body(cfg.read_text(), 0))["B_Data"] == '"1"'


def test_a_restored_profile_gets_this_boot_s_device_path(gen, opts, cfg):
    """hidraw numbering follows connection order, so the saved path pins the
    number the pad held the day it was captured — and the path is one of the
    three fields RMG compares by equality."""
    snapshot_for(opts["snap_dir"], OWNERS_PROFILE)   # saved on hidraw7
    gen.generate(1, FakePad(), opts)
    assert keys(body(cfg.read_text(), 0))["DevicePath"] == f'"{SDL_PATH}"'


# ── the inverse ──────────────────────────────────────────────────────────────

def test_release_unplugs_the_socket(gen, opts, cfg):
    gen.generate(2, FakePad(), opts)
    assert gen.release(2, opts) == ["gopher64: port 2 released (socket unassigned)"]
    k = keys(body(cfg.read_text(), 1))
    assert k["PluggedIn"] == "False"
    assert k["DeviceName"] == '"None"'
    assert k["DevicePath"] == '""'
    assert k["DeviceSerial"] == '""'


def test_an_empty_socket_is_device_type_zero(gen, opts, cfg):
    """Measured, and NOT the assigned type with PluggedIn flipped: RMG writes
    `DeviceType = 0` — `InputDeviceType::None` — for a socket nobody assigned."""
    gen.generate(1, FakePad(), opts)
    gen.release(1, opts)
    assert keys(body(cfg.read_text(), 0))["DeviceType"] == "0"


def test_release_blanks_all_four_fields_of_every_control(gen, opts, cfg):
    """Not only the labels. A released port that kept `A_Data = "0"` is not the
    shape RMG writes, and the shape is the whole point of an inverse."""
    gen.generate(1, FakePad(), opts)
    gen.release(1, opts)
    k = keys(body(cfg.read_text(), 0))
    for control in _CONTROLS:
        for field in ("InputType", "Name", "Data", "ExtraData"):
            assert k[f"{control}_{field}"] == '""', f"{control}_{field} kept"


def test_release_leaves_the_other_ports_and_the_defaults(gen, opts, cfg):
    gen.generate(1, FakePad(), opts)
    gen.generate(2, FakePad(), opts)
    gen.release(1, opts)
    text = cfg.read_text()
    assert keys(body(text, 1))["PluggedIn"] == "True"
    assert keys(body(text, 0))["Deadzone"] == "9"
    assert "RandomizeInterrupt = True" in text


def test_releasing_an_unassigned_socket_writes_nothing(gen, opts, cfg):
    before = cfg.read_text()
    assert gen.release(3, opts) == []
    assert cfg.read_text() == before


def test_release_stops_at_four_ports(gen, opts, cfg):
    before = cfg.read_text()
    assert gen.release(0, opts) == [] and gen.release(5, opts) == []
    assert cfg.read_text() == before


def test_release_survives_a_missing_file(gen, opts, cfg):
    cfg.unlink()
    assert gen.release(1, opts) == []
