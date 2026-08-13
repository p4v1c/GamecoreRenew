"""The N64 slot — Rosalie's Mupen GUI. Snapshot ONLY, deliberately.

The id stays `gopher64` even though it launches RMG: gopher64 sets no WM_CLASS
on its window, so the bezel overlay could never find it.

Nothing here synthesises an RMG mapping. Two attempts failed against what RMG
actually writes:

    PluggedIn = True
    DeviceName = "PS4 Controller"
    DevicePath = "/dev/hidraw0"
    DeviceSerial = "40:1b:5f:b9:ea:8d"
    A_Name = "cross"   …

`PluggedIn` is what attaches a controller to the port — without it the game
itself says "connect a controller to socket 1", however complete the rest looks.
The button names are per-controller (`cross`, `square` for a DualShock 4, not
the generic `a`, `x` of the fallback_profile RMG ships).

**Four ports, one snapshot per pad.** RMG keeps four profiles, `Profile 0` to
`Profile 3`, one per N64 socket. The pack used to restore all four at once from
a single snapshot, and refused any player but the first. Two consequences, both
measured on the reference box:

  * a second pad was never configured — `maxPlayers` said 1 and `generate()`
    returned None for every player but 1, silently, with no log line;
  * restoring player 1 wrote `PluggedIn = False` over ports 2-4, because the
    snapshot had captured those empty profiles too. Binding a second pad by
    hand in RMG survived exactly until the first pad reconnected.

So a snapshot now holds ONE profile, stored as if it were port 1, and is
replayed into whichever port the connecting player owns. Other ports are never
touched. `scan_mapping()` refuses to run unless exactly one pad is connected,
which is what makes "stored as port 1" safe: the pad being captured is the only
one RMG can have put there.

`DevicePath` is a host path that moves — hidraw numbering follows connection
order, so a Bluetooth mouse connecting first takes /dev/hidraw0 and the pad
lands on hidraw1. Restoring a captured path pinned the number the pad happened
to hold that day. `DeviceSerial` is the pad's MAC and never moves, so the path
is resolved from it at restore time instead.
"""
from __future__ import annotations

import glob
import logging
import os
import re
from pathlib import Path

from backend.services.configgen import snapshots

from backend.services.configgen.helpers.ini import iter_sections, replace_section

log = logging.getLogger(__name__)

EMU_ID = "gopher64"

PORTS = 4
_PREFIX = "Rosalie's Mupen GUI - Input Plugin"
# A snapshot is stored as if the pad sat in port 1. Restoring re-heads it.
_CANON_PORT = 0


def _header(port: int) -> str:
    return f"{_PREFIX} Profile {port}"


def _is_empty_profile(section_text: str) -> bool:
    """RMG's literal for a socket nobody assigned: DeviceName = "None"."""
    m = re.search(r'^DeviceName\s*=\s*"?([^"\n]*)"?\s*$', section_text, re.M)
    return m is None or m.group(1).strip() in ("", "None")


def _retarget(section_text: str, port: int) -> str:
    """Rewrite a profile section's [header] line so it targets `port`."""
    lines = section_text.splitlines(keepends=True)
    if lines and lines[0].strip().startswith("["):
        lines[0] = f"[{_header(port)}]\n"
    return "".join(lines)


def _profile_of(text: str, port: int) -> str:
    """The one profile section for `port`, re-headed to the canonical port."""
    for header, body in iter_sections(text):
        if header == _header(port):
            return _retarget(body, _CANON_PORT)
    return ""


def _snapshot_profile(block: str) -> str:
    """The profile a snapshot means, whatever shape the snapshot is in.

    Tolerates the LEGACY format, which captured every `Input Plugin` section at
    once: four profiles plus the plugin's own global section. Those files are on
    disk on every box that ever pressed "Scan mapping", so reading them is not
    optional. The one profile that names a device is the pad's; the empty ones
    are the sockets nobody assigned.
    """
    sections = [(h, b) for h, b in iter_sections(block) if h.startswith(_PREFIX)]
    for header, body in sections:
        if header.startswith(f"{_PREFIX} Profile") and not _is_empty_profile(body):
            return _retarget(body, _CANON_PORT)
    return ""


# Injectable so a test can describe its own sysfs instead of inheriting the
# machine's: this function is the one thing here that reads live hardware, and
# a fixture that silently depends on which pads happen to be plugged in is
# green on the developer's box and red on a clean runner.
_HIDRAW_ROOT = "/sys/class/hidraw"


def _hidraw_for(serial: str, root: str = "") -> str | None:
    """The /dev/hidraw node whose HID_UNIQ is `serial`, or None.

    Case-insensitive: bluetoothctl prints a MAC upper-case and the kernel
    lower-case, and RMG stores whichever it was handed.
    """
    want = serial.strip().lower()
    if not want:
        return None
    for sysdir in sorted(glob.glob(os.path.join(root or _HIDRAW_ROOT, "hidraw*"))):
        try:
            uevent = Path(sysdir, "device", "uevent").read_text()
        except OSError:
            continue
        for line in uevent.splitlines():
            key, _sep, value = line.partition("=")
            if key == "HID_UNIQ" and value.strip().lower() == want:
                return "/dev/" + os.path.basename(sysdir)
    return None


def _with_live_path(section_text: str) -> str:
    """Point DevicePath at wherever this pad's serial lives right now.

    Left untouched when the serial resolves to nothing: an empty or invented
    path is worse than a stale one, and a pad that is not on hidraw at all
    (a wired pad RMG drives through SDL) has no node to name.
    """
    m = re.search(r'^DeviceSerial\s*=\s*"([^"]*)"', section_text, re.M)
    if not m:
        return section_text
    node = _hidraw_for(m.group(1))
    if not node:
        return section_text
    return re.sub(r'^DevicePath\s*=\s*"[^"]*"',
                  f'DevicePath = "{node}"', section_text, count=1, flags=re.M)


def _extract_port(port: int):
    def f(text: str) -> str:
        return _profile_of(text, port)
    return f


def _replace_port(port: int):
    def f(text: str, block: str) -> str:
        body = _snapshot_profile(block)
        if not body:
            return text                      # nothing worth writing; leave it
        body = _with_live_path(_retarget(body, port))
        return replace_section(_header(port))(text, body)
    return f


# What the dispatcher and "Scan mapping" read off the module by name. Capture
# reads port 1 because scan_mapping() runs only with a single pad connected.
extract = _extract_port(_CANON_PORT)
replace = _replace_port(_CANON_PORT)


def generate(player_index: int, pad, opts: dict) -> str | None:
    if not 1 <= player_index <= PORTS:
        return None
    port = player_index - 1
    return snapshots.restore(opts["snap_dir"], EMU_ID, opts["target"],
                             _extract_port(port), _replace_port(port),
                             pad.vendor, pad.product)
