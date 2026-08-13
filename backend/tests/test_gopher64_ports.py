"""The N64 pack's four ports, and the two defects that made a second pad useless.

RMG keeps one profile per N64 socket. The pack used to restore all four from a
single snapshot and refuse any player but the first, so a second controller was
never configured — and restoring the first one wrote `PluggedIn = False` over
the other three, undoing by hand-binding the owner had done in RMG.

These tests pin the shape of the fix: one profile per snapshot, replayed into
the connecting player's port, neighbours untouched.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

P = "Rosalie's Mupen GUI - Input Plugin"


@pytest.fixture(scope="module")
def gen():
    spec = importlib.util.spec_from_file_location(
        "gopher64_generator", ROOT / "catalog" / "gopher64" / "generator.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def profile(port, name="PS4 Controller", serial="40:1b:5f:b9:ea:8d",
            path="/dev/hidraw0", plugged="True", a_name="cross"):
    return (f"[{P} Profile {port}]\n\n"
            f"PluggedIn = {plugged}\n"
            f'DeviceName = "{name}"\n'
            f"DeviceType = 4\n"
            f'DevicePath = "{path}"\n'
            f'DeviceSerial = "{serial}"\n'
            f'A_Name = "{a_name}"\n\n')


EMPTY = dict(name="None", serial="", path="", plugged="False", a_name="a")


@pytest.fixture
def live():
    """A one-pad RMG config: port 1 mapped, ports 2-4 empty."""
    return (f"[{P}]\n\nProfiles = \"\"\nControllerMode = 0\n\n"
            + profile(0)
            + profile(1, **EMPTY) + profile(2, **EMPTY) + profile(3, **EMPTY)
            + "[Rosalie's Mupen GUI Core]\n\nRandomizeInterrupt = True\n")


XBOX = profile(0, "Xbox Wireless Controller", "5c:ba:37:63:ee:62",
               "/dev/hidraw9", a_name="a")


def port_body(text, port):
    return text.split(f"[{P} Profile {port}]")[1].split("[")[0]


def test_a_second_pad_lands_on_its_own_port(gen, live):
    out = gen._replace_port(1)(live, XBOX)
    assert "Xbox Wireless Controller" in port_body(out, 1)


def test_it_does_not_disturb_the_first_pad(gen, live):
    """The defect that made hand-binding pointless: restoring one pad wrote
    `PluggedIn = False` over every other port."""
    out = gen._replace_port(1)(live, XBOX)
    assert "PS4 Controller" in port_body(out, 0)
    assert "PluggedIn = True" in port_body(out, 0)
    assert '"None"' in port_body(out, 2)      # untouched, still empty
    assert '"None"' in port_body(out, 3)


def test_it_keeps_the_sections_that_are_not_ports(gen, live):
    out = gen._replace_port(1)(live, XBOX)
    assert "ControllerMode" in out            # the plugin's own section
    assert "RandomizeInterrupt" in out        # RMG's core section


def test_a_port_is_written_once(gen, live):
    out = gen._replace_port(1)(live, XBOX)
    assert out.count(f"[{P} Profile 1]") == 1


def test_the_legacy_four_section_snapshot_is_still_readable(gen):
    """Every box that ever pressed "Scan mapping" has one of these on disk."""
    legacy = (f"[{P}]\n\nProfiles = \"\"\n\n" + profile(0)
              + profile(1, **EMPTY) + profile(2, **EMPTY) + profile(3, **EMPTY))
    got = gen._snapshot_profile(legacy)
    assert got.count("[") == 1                # one profile, not four
    assert "PS4 Controller" in got
    assert '"None"' not in got                # the empty sockets are dropped


def test_a_snapshot_is_stored_port_agnostic(gen, live):
    """Captured on port 1, replayable anywhere — so the header is normalised."""
    assert gen._extract_port(1)(live).startswith(f"[{P} Profile 0]")
    assert gen._extract_port(0)(live).startswith(f"[{P} Profile 0]")


def test_an_empty_snapshot_overwrites_nothing(gen, live):
    assert gen._replace_port(1)(live, "") == live


def test_generate_covers_four_players_and_stops_there(gen):
    assert gen.generate(0, None, {}) is None
    assert gen.generate(5, None, {}) is None
    # 1..4 get past the guard and reach restore(), which needs real opts
    with pytest.raises((KeyError, TypeError)):
        gen.generate(2, None, {})


def _fake_sysfs(tmp_path, nodes):
    for name, uniq in nodes.items():
        d = tmp_path / name / "device"
        d.mkdir(parents=True)
        (d / "uevent").write_text(f"DRIVER=hid-generic\nHID_UNIQ={uniq}\n")
    return str(tmp_path)


def test_devicepath_follows_the_serial_not_the_saved_number(gen, tmp_path):
    """hidraw numbering follows connection order: a Bluetooth mouse connecting
    first takes hidraw0 and the pad lands on hidraw1. The saved path is stale;
    the serial is not."""
    root = _fake_sysfs(tmp_path, {"hidraw0": "00:00:13:08:05:04",
                                  "hidraw1": "40:1b:5f:b9:ea:8d"})
    assert gen._hidraw_for("40:1b:5f:b9:ea:8d", root) == "/dev/hidraw1"


def test_the_serial_match_ignores_case(gen, tmp_path):
    """bluetoothctl prints a MAC upper-case, the kernel lower-case."""
    root = _fake_sysfs(tmp_path, {"hidraw3": "40:1b:5f:b9:ea:8d"})
    assert gen._hidraw_for("40:1B:5F:B9:EA:8D", root) == "/dev/hidraw3"


def test_an_unknown_serial_leaves_the_path_alone(gen, tmp_path):
    """An invented path is worse than a stale one, and a pad RMG drives through
    SDL rather than hidraw has no node to name."""
    root = _fake_sysfs(tmp_path, {"hidraw0": "aa:bb:cc:dd:ee:ff"})
    assert gen._hidraw_for("00:00:00:00:00:00", root) is None


def test_no_serial_at_all_is_not_a_lookup(gen, tmp_path):
    assert gen._hidraw_for("", _fake_sysfs(tmp_path, {})) is None
