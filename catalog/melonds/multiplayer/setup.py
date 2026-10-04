"""melonDS local multiplayer, backend side: decide, write each instance's pad.

Runs in the backend just before the spawn (generator.launch_command). With
two to four pads it writes, for every player N, `[Instance{N-1}] JoystickID`
(the pad's SDL index as melonDS's own SDL sees it) and, for players 2-4, the
`[Instance{N-1}.Joystick]` bindings; then it returns the command that runs
launcher.py around melonDS. One pad: nothing is written, nothing changes.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shlex
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from backend.services.configgen import snapshots
from backend.services.configgen.controllers import Pad
from backend.services.configgen.helpers.base import atomic_write, backup
from backend.services.configgen.helpers.ini import section, set_key, set_section
from backend.services.controller_registry import normalize_mac

log = logging.getLogger(__name__)

MAX_PLAYERS = 4
LAUNCHER = Path(__file__).resolve().parent / "launcher.py"
A11Y_FLAG = "--env=QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1"
FULLSCREEN_FLAGS = {"-f", "--fullscreen"}
# Measured 1.1 s warm; the whole hook must fit the launch's 3 s budget.
PROBE_TIMEOUT = 2.0
# Instance 1 keeps its solo JoystickID outside multiplayer; the value replaced
# for a session is parked here and put back at the next solo launch.
STATE_FILE = ".local/share/gamecore/melonds-multiplayer/instance0-joystick.json"

# Asks the SDL2 melonDS links (inside its sandbox) for its joystick order.
# melonDS sets no hint that changes enumeration (main.cpp), so neither do we.
_SDL_PROBE = (
    "import ctypes,os\n"
    "os.environ['SDL_VIDEODRIVER']='dummy'\n"
    "s=ctypes.CDLL('libSDL2-2.0.so.0')\n"
    "s.SDL_JoystickPathForIndex.restype=ctypes.c_char_p\n"
    "s.SDL_JoystickPathForIndex.argtypes=[ctypes.c_int]\n"
    "if s.SDL_Init(0x200)!=0: raise SystemExit(1)\n"
    "for i in range(s.SDL_NumJoysticks()):\n"
    " print(i,(s.SDL_JoystickPathForIndex(i) or b'').decode(),sep='\\t')\n"
)


def probe_command(app_id: str) -> list[str]:
    if app_id:
        return ["flatpak", "run", "--command=python3", app_id, "-c", _SDL_PROBE]
    return [sys.executable, "-c", _SDL_PROBE]


def sdl_joysticks(app_id: str) -> list[tuple[int, str]]:
    """[(SDL index, device path)] in melonDS's own SDL; [] when it cannot say."""
    try:
        out = subprocess.run(probe_command(app_id), capture_output=True, text=True,
                             timeout=PROBE_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired):
        log.warning("melonds multiplayer: SDL probe failed", exc_info=True)
        return []
    found = []
    for line in out.stdout.splitlines():
        index, _, path = line.partition("\t")
        if index.isdigit() and path:
            found.append((int(index), path))
    return found


def _read(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def device_ids(path: str, sys_root: Path = Path("/sys")) -> set[str]:
    """Everything that names the physical pad behind a device node: the node,
    its HID device directory, its MAC. A DS4 is /dev/input/eventN to GameCore
    and /dev/hidrawM to SDL's HIDAPI driver; both lead to one HID directory."""
    ids = {path}
    name = os.path.basename(path)
    if name.startswith("hidraw"):
        hid = sys_root / "class/hidraw" / name / "device"
        uevent = _read(hid / "uevent")
        m = re.search(r"^HID_UNIQ=(.*)$", uevent, re.M)
        mac = normalize_mac(m.group(1)) if m else ""
    elif name.startswith("event"):
        node = sys_root / "class/input" / name / "device"
        hid = node / "device"
        mac = normalize_mac(_read(node / "uniq"))
    else:
        return ids
    if hid.exists():
        ids.add(os.path.realpath(hid))
    if mac:
        ids.add(mac)
    return ids


def assign_joysticks(players: list[dict], sdl: list[tuple[int, str]],
                     ids_of: Callable[[str], set[str]] | None = None) -> dict[int, int]:
    """player → SDL index, for every player whose pad SDL lists.

    A registry key is a MAC or an event node; `ids_of` turns both sides into
    comparable identities."""
    ids_of = ids_of or device_ids
    sdl_ids = [(index, ids_of(path)) for index, path in sdl]
    out: dict[int, int] = {}
    for p in players:
        key = p["key"]
        wanted = {key} if normalize_mac(key) == key else ids_of(key)
        hit = next((i for i, ids in sdl_ids if ids & wanted and i not in out.values()), None)
        if hit is not None:
            out[p["player"]] = hit
    return out


def joystick_block(pad: Pad, header: str, base: str, snap_dir: Path,
                   synth, set_keys) -> str:
    """`[header]` bindings for `pad`: its saved mapping when the owner captured
    one, else the base section with the shoulders, Start/Select and D-pad
    derived for this pad (what slot 1 gets on connect)."""
    snap = snapshots.snap_path(snap_dir, "melonds", pad.vendor, pad.product)
    if snap.is_file() and not snapshots.block_disagrees(snap.read_text(), pad.vendor, pad.product):
        body = section(snap.read_text(), "Instance0.Joystick")
        if body is not None:
            return body
    text = f"[{header}]\n{base}"
    found = synth(pad)
    if found:
        text, _n = set_keys(text, header, found[0])
    return section(text, header) or base


def command(exec_path: str, exec_args: str, players: int) -> tuple[str, str]:
    """The launcher around melonDS. No fullscreen: the windows share the screen.
    The ROM is appended by the process manager, last, as for any launch."""
    args = [a for a in shlex.split(exec_args) if a not in FULLSCREEN_FLAGS]
    if exec_path == "flatpak":
        cmd = ["flatpak"] + args
        if "run" in cmd:
            cmd.insert(cmd.index("run") + 1, A11Y_FLAG)
    else:
        cmd = [exec_path] + args
    return sys.executable, shlex.join([str(LAUNCHER), "--players", str(players), "--", *cmd])


def _set_joystick_id(text: str, instance: int, index: int) -> str:
    header = f"Instance{instance}"
    if section(text, header) is None:
        return set_section(text, header, f"JoystickID = {index}\n")
    return set_key(text, header, "JoystickID", str(index))[0]


def write_instances(target: Path, players: list[dict], indices: dict[int, int],
                    snap_dir: Path, synth, set_keys) -> None:
    """JoystickID for every player, bindings for players 2-4, one atomic write."""
    text = target.read_text()
    base = section(text, "Instance0.Joystick") or ""
    for p in players:
        n = p["player"]
        if n in indices:
            text = _set_joystick_id(text, n - 1, indices[n])
        if n > 1:
            pad = Pad(vendor=p["vendor"], product=p["product"], evdev_name=p["name"])
            header = f"Instance{n - 1}.Joystick"
            text = set_section(text, header, joystick_block(pad, header, base, snap_dir,
                                                            synth, set_keys))
    backup(target)
    atomic_write(target, text)


def _park_instance0(target: Path, state: Path) -> None:
    """Remember instance 1's solo JoystickID before multiplayer replaces it."""
    if state.exists():
        return
    m = re.search(r"^JoystickID = (-?\d+)$", section(target.read_text(), "Instance0") or "", re.M)
    if m:
        state.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(state, json.dumps({"JoystickID": int(m.group(1))}))


def restore_instance0(target: Path, state: Path) -> None:
    """Solo launch after multiplayer: give instance 1 its own JoystickID back."""
    try:
        value = json.loads(state.read_text())["JoystickID"]
    except (OSError, ValueError, KeyError):
        return
    text = target.read_text()
    atomic_write(target, _set_joystick_id(text, 0, int(value)))
    state.unlink(missing_ok=True)


def launch_command(*, rom_path: str, exec_path: str, exec_args: str,
                   players: list[dict], opts: dict | None,
                   synth, set_keys) -> tuple[str, str] | None:
    """(exec_path, exec_args) for 2-4 pads, None for the solo launch.
    `opts` None (autoconfig off): the command changes, the config does not."""
    target = Path(opts["target"]) if opts else None
    state = Path(opts["home"]) / STATE_FILE if opts else None
    count = min(len(players), MAX_PLAYERS)
    if count < 2 or not rom_path:
        if target and target.is_file() and state and state.exists():
            restore_instance0(target, state)
        return None
    # Instance N is the Nth pad by slot: a gap in the slots (players 1 and 3)
    # must not open a window nobody controls.
    players = [{**p, "player": rank} for rank, p in enumerate(
        sorted(players, key=lambda p: p["player"])[:MAX_PLAYERS], start=1)]
    if target and target.is_file():
        indices = assign_joysticks(players, sdl_joysticks(opts.get("app_id", "")))
        log.info("melonds multiplayer: %d players, SDL indices %s", count, indices)
        _park_instance0(target, state)
        write_instances(target, players, indices, Path(opts["snap_dir"]), synth, set_keys)
    return command(exec_path, exec_args, count)
