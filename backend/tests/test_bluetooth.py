"""Parsing bluetoothctl output — the part of pairing that can be tested offline.

The subprocess calls need an adapter and a device in the room, so they are not
tested here. The parser is what stands between that output and the screen, and
it is the piece that changed shape: it used to read only `devices Paired`, a
tidy list, and now also reads the output of a scan, which carries agent chatter
and controller banners in the same stream.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.routers.settings.bluetooth import parse_devices  # noqa: E402


# Captured from the reference box: `bluetoothctl -- devices`.
REAL = """Device 5C:BA:37:63:EE:62 Xbox Wireless Controller
Device 00:00:13:08:05:04 Bluetooth mouse
Device 40:1B:5F:B9:EA:8D Wireless Controller
Device 0C:A6:94:AD:5C:5E JBL Charge 2
Device E8:D5:2B:1B:CF:33 Pixel 8a
Device 3C:B0:ED:C5:3C:10 Nothing Ear"""


def test_the_six_devices_on_the_box_parse():
    got = parse_devices(REAL)
    assert len(got) == 6
    assert ("0C:A6:94:AD:5C:5E", "JBL Charge 2") in got
    assert ("5C:BA:37:63:EE:62", "Xbox Wireless Controller") in got


def test_a_name_with_spaces_survives():
    """Three words, and the third is a digit — the shape that a split on
    whitespace loses and that half the speakers in the world are called."""
    assert parse_devices("Device 0C:A6:94:AD:5C:5E JBL Charge 2") == [
        ("0C:A6:94:AD:5C:5E", "JBL Charge 2")]


def test_scan_chatter_is_not_a_device():
    """What the scan path adds to the stream. `parts[0] == "Device"` accepted
    the first of these as a device called "5C:BA:... (random)" and the second
    outright; matching an address rejects both."""
    noisy = """Agent registered
[CHG] Controller 88:F4:DA:9D:2A:37 Discovering: yes
Device Removed 5C:BA:37:63:EE:62 (random)
[NEW] Device AA:BB:CC:DD:EE:FF Pad One
Discovery started"""
    assert parse_devices(noisy) == []


def test_a_new_device_line_is_read_once_the_prefix_is_gone():
    """`[NEW] ` is stripped by the caller's ANSI/CR cleanup on a real terminal;
    what reaches here is the bare line, and that one must parse."""
    assert parse_devices("Device AA:BB:CC:DD:EE:FF Pad One") == [
        ("AA:BB:CC:DD:EE:FF", "Pad One")]


def test_addresses_are_upper_cased_so_the_set_difference_works():
    """The scan compares discovered against paired by address. bluetoothctl is
    consistent in practice, but a case difference would silently list an
    already-paired device as new, and the two lists come from two calls."""
    assert parse_devices("Device aa:bb:cc:dd:ee:ff Pad") == [
        ("AA:BB:CC:DD:EE:FF", "Pad")]


def test_an_unnamed_device_keeps_its_address_as_a_name():
    """A pad whose name has not resolved yet. It has to survive parsing — the
    scan sorts it below the named ones rather than dropping it, because it may
    be the very device the player just woke."""
    assert parse_devices("Device AA:BB:CC:DD:EE:FF AA-BB-CC-DD-EE-FF") == [
        ("AA:BB:CC:DD:EE:FF", "AA-BB-CC-DD-EE-FF")]
