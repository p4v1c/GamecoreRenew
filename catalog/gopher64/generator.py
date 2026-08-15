"""The N64 slot — Rosalie's Mupen GUI. A saved snapshot, else RMG's own profile.

The id stays `gopher64` even though it launches RMG: gopher64 sets no WM_CLASS
on its window, so the bezel overlay could never find it.

**This module used to synthesise nothing, and that was the last red system on
the 15 August 2026 bench.** At its zero point the game itself says "connect a
controller to socket 1", and the only way out was to map the pad by hand inside
RMG and press "Scan mapping". Two earlier attempts failed against what RMG
actually writes; what they were missing is written down below rather than left
as folklore, because both failures are still the ways this can break.

  1. `PluggedIn` is what attaches a controller to the port. Without it the game
     says "connect a controller to socket 1" however complete the rest looks —
     the exact symptom measured at the zero point.

  2. **The identity is three strings compared at once.**
     `Source/RMG-Input/main.cpp:647` matches a profile with

         deviceName == DeviceName && devicePath == DevicePath
                                  && deviceSerial == DeviceSerial

     read from SDL_GetGamepadName / Path / Serial. One field wrong and the
     profile does not attach, in silence, the way a wrong GUID silently
     disposes Ryujinx's slot. `controllers.sdl3_identity()` takes the path and
     the serial from ONE SDL3 probe and `resolve_name()` answers the name — the
     same source every other SDL3-name consumer uses.

     Neither of the two is derivable from the pad's ids. Measured, same instant:

         054c:09cc DualShock 4    /dev/hidraw0        40:1b:5f:b9:ea:8d
         045e:02fd Xbox Wireless  /dev/input/event14  ""

     SDL names the node of whichever driver reads the pad, and only a
     HIDAPI-driven pad has a serial at all.

**Why a fixed binding table is right here, where it would be wrong elsewhere.**
mgba, melonDS and azahar bind RAW joystick indices, which differ per pad and
per driver — a seed of one pad's numbers is what put Zelda's map on Y for an
Xbox. RMG does not. Its `InputType` 0 and 1 carry SDL_GameControllerButton and
SDL_GameControllerAxis CONSTANTS (`Source/RMG-Input/common.hpp`):

    enum class InputType { Keyboard = -1, GamepadButton = 0, GamepadAxis = 1,
                           JoystickButton = 2, JoystickAxis = 3,
                           JoystickHat = 4, Invalid };

`a` is 0 on every pad SDL has a mapping for. Types 2/3/4 ARE the raw index
space and nothing here ever writes them. That distinction is the one that broke
mGBA and azahar on the morning of the bench, reached from the other side.

The values are RMG's own `fallback_profile`, from `Data/InputProfileDB.json`
upstream, and its database holds only three entries — that profile, a real N64
controller and a GameCube controller. For any other pad RMG's own answer IS the
generic profile, so writing it is not an invention.

**A hand-made snapshot always wins.** That is the owner's work, done in RMG's
own UI, and the reference box carries one: an Xbox profile whose N64 `B` sits
on SDL `b` rather than the generic profile's `x`. Synthesis only fills a void,
and the test is `snapshots.exists()` — never a falsy return from `restore()`,
which answers None both for "no snapshot" and for "already applied". Conflating
those is what made melonDS overwrite the owner's mapping every other session.

**Four ports, one profile per port.** RMG keeps four, `Profile 0` to
`Profile 3`, one per N64 socket. The pack used to restore all four at once from
a single snapshot and refuse any player but the first. Two consequences, both
measured on the reference box:

  * a second pad was never configured — `maxPlayers` said 1 and `generate()`
    returned None for every player but 1, silently, with no log line;
  * restoring player 1 wrote `PluggedIn = False` over ports 2-4, because the
    snapshot had captured those empty profiles too. Binding a second pad by
    hand in RMG survived exactly until the first pad reconnected.

So a snapshot holds ONE profile, stored as if it were port 1, and is replayed
into whichever port the connecting player owns. Other ports are never touched.
`scan_mapping()` refuses to run unless exactly one pad is connected, which is
what makes "stored as port 1" safe: the pad being captured is the only one RMG
can have put there.

`DevicePath` is a host path that MOVES — hidraw numbering follows connection
order, so a Bluetooth mouse connecting first takes /dev/hidraw0 and the pad
lands on hidraw1, and evdev numbering drifts the same way. A restored path
pinned the number the pad happened to hold the day it was captured, which is
one of the three fields that must match. So the identity is refreshed from the
live SDL3 on the way in, for a restore exactly as for a synthesis; only the
BINDINGS come from the snapshot.
"""
from __future__ import annotations

import glob
import logging
import os
import re
from collections.abc import Collection
from pathlib import Path

from backend.services.configgen import controllers, snapshots
from backend.services.configgen.controllers import SDL3_TRUSTED
from backend.services.configgen.helpers.base import Skip, atomic_write, backup
from backend.services.configgen.helpers.ini import iter_sections, replace_section

log = logging.getLogger(__name__)

EMU_ID = "gopher64"

PORTS = 4
_PREFIX = "Rosalie's Mupen GUI - Input Plugin"
# A snapshot is stored as if the pad sat in port 1. Restoring re-heads it.
_CANON_PORT = 0

# `InputDeviceType::Joystick`, common.hpp. The value RMG writes for any pad it
# drives through SDL, and constant across every profile the reference box has.
_DEVICE_TYPE_JOYSTICK = "4"
# `InputDeviceType::None` — what an unassigned socket carries. Measured, and
# NOT the same as the assigned value with PluggedIn flipped: RMG writes 0.
_DEVICE_TYPE_NONE = "0"


def _header(port: int) -> str:
    return f"{_PREFIX} Profile {port}"


# ── what RMG binds an N64 pad to, for every controller ───────────────────────
#
# RMG's `fallback_profile`, verbatim. `Data` is an SDL_GameControllerButton for
# InputType 0 and an SDL_GameControllerAxis for InputType 1, where `ExtraData`
# is the axis half — 0 negative, 1 positive.
#
# The `*_Name` values are COSMETIC: RMG shows them in its settings dialog and
# rewrites them to the pad's own vocabulary when the owner maps by hand ("cross"
# for a DualShock 4's `a`). They are the generic profile's here and are not
# guessed per controller family — a wrong label is a display defect, a guessed
# one is a claim about a pad nobody measured.
_BINDINGS: tuple[tuple[str, str, str, str, str], ...] = (
    # control              InputType  Name            Data  ExtraData
    ("A",                  "0", "a",              "0",  "0"),
    # N64 `B` is the generic profile's SDL `x`, not `b` — measured against
    # upstream's InputProfileDB.json. The reference box's own file says `b`,
    # and that is the OWNER's hand-mapping for an Xbox pad, which is precisely
    # the work a snapshot exists to keep.
    ("B",                  "0", "x",              "2",  "0"),
    ("Start",              "0", "start",          "6",  "0"),
    ("DpadUp",             "0", "dpup",           "11", "0"),
    ("DpadDown",           "0", "dpdown",         "12", "0"),
    ("DpadLeft",           "0", "dpleft",         "13", "0"),
    ("DpadRight",          "0", "dpright",        "14", "0"),
    # The N64's shoulder buttons. LEFTSHOULDER / RIGHTSHOULDER, not the analog
    # triggers: those are axes and Z already owns one of them.
    ("LeftTrigger",        "0", "leftshoulder",   "9",  "0"),
    ("RightTrigger",       "0", "rightshoulder",  "10", "0"),
    # Z is the pad's LEFT analog trigger, positive half. It has no obvious
    # equivalent on a modern controller, which makes it one of the two controls
    # worth pressing first when checking this by hand.
    ("ZTrigger",           "1", "lefttrigger+",   "4",  "1"),
    # The four C buttons are the RIGHT STICK's four directions — the other
    # control with no modern equivalent.
    ("CButtonUp",          "1", "righty-",        "3",  "0"),
    ("CButtonDown",        "1", "righty+",        "3",  "1"),
    ("CButtonLeft",        "1", "rightx-",        "2",  "0"),
    ("CButtonRight",       "1", "rightx+",        "2",  "1"),
    ("AnalogStickUp",      "1", "lefty-",         "1",  "0"),
    ("AnalogStickDown",    "1", "lefty+",         "1",  "1"),
    ("AnalogStickLeft",    "1", "leftx-",         "0",  "0"),
    ("AnalogStickRight",   "1", "leftx+",         "0",  "1"),
)

_FIELDS = ("InputType", "Name", "Data", "ExtraData")


def _bound_keys() -> dict[str, str]:
    out: dict[str, str] = {}
    for control, input_type, name, data, extra in _BINDINGS:
        for field, value in zip(_FIELDS, (input_type, name, data, extra)):
            out[f"{control}_{field}"] = f'"{value}"'
    return out


# An unassigned socket blanks all FOUR fields of every control, not just the
# label. Measured on the reference box's own empty profiles — a released port
# that kept `A_Data = "0"` would not be the shape RMG writes, and the shape is
# the whole point of an inverse.
_UNBOUND_KEYS: dict[str, str] = {f"{control}_{field}": '""'
                                 for control, *_ in _BINDINGS
                                 for field in _FIELDS}

# The socket-not-assigned identity, as RMG writes it three times over on a
# one-pad box.
_RELEASED_IDENTITY: dict[str, str] = {
    "PluggedIn": "False",
    "DeviceName": '"None"',
    "DeviceType": _DEVICE_TYPE_NONE,
    "DevicePath": '""',
    "DeviceSerial": '""',
}

# Deliberately absent from both tables: Deadzone, Sensitivity, Pak,
# RemoveDuplicateMappings, FilterEventsForButtons, FilterEventsForAxis. They are
# identical between an assigned profile and an empty one, they are the owner's
# to tune, and a generator writes only what it owns.


def _identity_keys(name: str, path: str, serial: str) -> dict[str, str]:
    return {
        # Without this the game asks for a controller on socket 1 whatever else
        # the profile says. It is the zero-point symptom, and it is one line.
        "PluggedIn": "True",
        "DeviceName": f'"{name}"',
        "DeviceType": _DEVICE_TYPE_JOYSTICK,
        "DevicePath": f'"{path}"',
        "DeviceSerial": f'"{serial}"',
    }


def _set_keys(section_text: str, values: dict[str, str]) -> str:
    """Set `key = value` for each entry of `values`, in place.

    Surgical like everything else in this package: lines that are not named are
    copied byte for byte, and a key RMG does not have is appended rather than
    silently dropped — a future RMG that renames a control must leave a trace,
    not a config missing a button.
    """
    out: list[str] = []
    seen: set[str] = set()
    for line in section_text.splitlines(keepends=True):
        key = line.partition("=")[0].strip()
        if "=" in line and key in values:
            out.append(f"{key} = {values[key]}\n")
            seen.add(key)
        else:
            out.append(line)
    missing = [k for k in values if k not in seen]
    if missing:
        at = max((n for n, l in enumerate(out) if l.strip()), default=-1) + 1
        out[at:at] = [f"{k} = {values[k]}\n" for k in missing]
    return "".join(out)


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


def _section_of(text: str, port: int) -> str:
    """This port's profile section as it stands in `text`, or ""."""
    for header, body in iter_sections(text):
        if header == _header(port):
            return body
    return ""


def _profile_of(text: str, port: int) -> str:
    """The one profile section for `port`, re-headed to the canonical port."""
    body = _section_of(text, port)
    return _retarget(body, _CANON_PORT) if body else ""


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


def _with_live_identity(section_text: str, ident: dict[str, str] | None) -> str:
    """Point a restored profile's DevicePath / DeviceSerial at this boot.

    A snapshot carries the owner's BINDINGS; where the pad sits is machine state
    that changed the moment something else connected first. Both fields are
    compared by equality, so a stale one is a profile that does not attach.

    `ident` is what SDL3 says right now, and it is authoritative when present —
    including when it says the serial is empty, which is the true answer for a
    pad SDL does not read through HIDAPI.

    Falls back to resolving the SAVED serial against sysfs when SDL could not be
    asked, which is what this function did before it had a second source. That
    path is left untouched when the serial resolves to nothing: an empty or
    invented path is worse than a stale one.
    """
    if ident and "path" in ident:
        section_text = _sub_quoted(section_text, "DevicePath", ident["path"])
        if "serial" in ident:
            section_text = _sub_quoted(section_text, "DeviceSerial",
                                       ident["serial"])
        return section_text
    m = re.search(r'^DeviceSerial\s*=\s*"([^"]*)"', section_text, re.M)
    if not m:
        return section_text
    node = _hidraw_for(m.group(1))
    if not node:
        return section_text
    return _sub_quoted(section_text, "DevicePath", node)


def _sub_quoted(section_text: str, key: str, value: str) -> str:
    return re.sub(rf'^{key}\s*=\s*"[^"]*"', f'{key} = "{value}"',
                  section_text, count=1, flags=re.M)


def _extract_port(port: int):
    def f(text: str) -> str:
        return _profile_of(text, port)
    return f


def _replace_port(port: int, ident: dict[str, str] | None = None):
    def f(text: str, block: str) -> str:
        body = _snapshot_profile(block)
        if not body:
            return text                      # nothing worth writing; leave it
        body = _with_live_identity(_retarget(body, port), ident)
        return replace_section(_header(port))(text, body)
    return f


# What the dispatcher and "Scan mapping" read off the module by name. Capture
# reads port 1 because scan_mapping() runs only with a single pad connected.
# No identity is passed here: this pair is the file-to-file one, and asking SDL
# for a live path belongs to a profiling pass that knows which pad it is for.
extract = _extract_port(_CANON_PORT)
replace = _replace_port(_CANON_PORT)


def _live_identity(pad, opts: dict) -> dict[str, str]:
    """What RMG's own SDL3 will call this pad's node and serial, or `{}`.

    RMG ships no SDL and links `org.kde.Platform`'s; `bundled_sdl3` finds it,
    and answering "" there is not a refusal — measured on the reference box, the
    runtime's SDL3 3.2.30 and the host's 3.4.12 return the same three strings
    for the same pad, byte for byte. See `controllers.bundled_sdl3`.
    """
    app_id = opts.get("app_id") or ""
    lib = controllers.bundled_sdl3(app_id) if app_id else ""
    return controllers.sdl3_identity(pad.vendor, pad.product, lib)


def _synthesise(port: int, pad, opts: dict) -> str | Skip | None:
    """Write RMG's generic profile into `port`, for the pad in hand."""
    target = opts["target"]
    if not target.is_file():
        # RMG writes this file itself on first run. No file means it has never
        # started, and there is no key set to write into.
        return None

    # The same guard rpcs3 and dolphin make, for the same reason: RMG matches
    # DeviceName by string equality against its own SDL3 enumeration, so a name
    # we are not sure of is a profile that will not attach.
    if pad.name.source not in SDL3_TRUSTED:
        return Skip(f"gopher64: no SDL3 name for {pad.vendor}:{pad.product} — "
                    f"RMG matches a profile by name, path and serial at once, "
                    f"so port {port + 1} is left as it is")

    ident = _live_identity(pad, opts)
    if "path" not in ident:
        return Skip(f"gopher64: SDL3 did not report a device path for "
                    f"{pad.vendor}:{pad.product} — RMG compares it by equality "
                    f"and an invented one binds nothing")

    text = target.read_text()
    body = _section_of(text, port)
    if not body:
        return Skip(f"gopher64: {target.name} has no "
                    f"'{_header(port)}' section to write into")

    body = _set_keys(body, {**_identity_keys(str(pad.name), ident["path"],
                                             ident.get("serial", "")),
                            **_bound_keys()})
    out = replace_section(_header(port))(text, body)
    if out == text:
        # Idempotent by comparison rather than by hope: the monitor reprofiles
        # on every roster change, and a file rewritten each time is a file whose
        # mtime says something happened when nothing did.
        return None
    backup(target)
    atomic_write(target, out)
    return (f"gopher64: port {port + 1} bound to {pad.name} "
            f"(RMG generic profile)")


def generate(player_index: int, pad, opts: dict) -> str | Skip | None:
    if not 1 <= player_index <= PORTS:
        return None
    port = player_index - 1
    snap_dir, target = opts["snap_dir"], opts["target"]

    # `exists()` and never a falsy return from restore(): it answers None both
    # for "no snapshot" and for "already applied", and conflating those is what
    # made melonDS's synthesis overwrite the owner's captured mapping every
    # other connection.
    if snapshots.exists(snap_dir, EMU_ID, pad.vendor, pad.product):
        return snapshots.restore(snap_dir, EMU_ID, target,
                                 _extract_port(port),
                                 _replace_port(port, _live_identity(pad, opts)),
                                 pad.vendor, pad.product)
    return _synthesise(port, pad, opts)


def release(player_index: int, opts: dict,
            occupied: Collection[int] = ()) -> list[str]:
    """Put a port back to the socket-nobody-assigned shape when its pad leaves.

    Without this a departed pad keeps its port `PluggedIn = True` and an N64
    game still presents that player — the same phantom `release_profile`
    documents for RPCS3 and Ryujinx, spelled in RMG's vocabulary. It matters
    more here than elsewhere because the identity is a path that gets REUSED:
    the next pad to connect can take /dev/hidraw0, and a stale profile naming
    it would attach a departed player's port to somebody else's controller.

    The shape written is RMG's own, measured rather than derived — an empty
    socket carries `DeviceType = 0`, not the joystick type with PluggedIn
    flipped, and blanks all four fields of every control and not only the
    labels.

    `occupied` is unused: RMG stores nothing about the roster. Each of the four
    profiles is independent, which is exactly what the four-port fix
    established.
    """
    if not 1 <= player_index <= PORTS:
        return []
    port = player_index - 1
    target = opts["target"]
    if not target.is_file():
        return []
    text = target.read_text()
    body = _section_of(text, port)
    if not body or _is_empty_profile(body):
        return []
    out = replace_section(_header(port))(
        text, _set_keys(body, {**_RELEASED_IDENTITY, **_UNBOUND_KEYS}))
    if out == text:
        return []
    backup(target)
    atomic_write(target, out)
    return [f"gopher64: port {player_index} released (socket unassigned)"]
