"""melonDS local multiplayer: decide, then write each instance's pad.

`launch_command` runs in the backend just before the spawn, inside the
launch's 3 s budget, so it only decides: with two to four pads it writes a
job file and returns the command that runs launcher.py around melonDS.
The launcher calls `prepare` before starting melonDS: per player N,
`[Instance{N-1}] JoystickID` (the pad's SDL index as melonDS's own SDL sees
it), hotkey and screen windows, and for players 2-4 the
`[Instance{N-1}.Joystick]` bindings. Those need SDL probes of about a second
each; in the budget, three pads overran it and melonDS started solo.
One pad: nothing is written, nothing changes.
"""
from __future__ import annotations

import importlib.util
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
from backend.utils import atomic_write_bytes

log = logging.getLogger(__name__)

MAX_PLAYERS = 4
LAUNCHER = Path(__file__).resolve().parent / "launcher.py"
A11Y_FLAG = "--env=QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1"
FULLSCREEN_FLAGS = {"-f", "--fullscreen"}
# Measured 1.1 s warm; runs in the launcher, outside the launch budget.
PROBE_TIMEOUT = 10.0
# Instance 1 keeps its solo settings outside multiplayer; the values replaced
# for a session are parked here and put back at the next solo launch.
STATE_FILE = ".local/share/gamecore/melonds-multiplayer/instance0-solo.json"
# What the backend hands the launcher: config path, pads, where snapshots live.
JOB_FILE = ".local/share/gamecore/melonds-multiplayer/job.json"
GENERATOR = Path(__file__).resolve().parent.parent / "generator.py"
# melonDS hides its menu bar only when it toggles fullscreen itself; the
# launcher sends this key (Qt::Key_F11) to every instance. F12 is the L3 daemon's.
FULLSCREEN_KEY = "16777274"
# One window per DS screen, each stretched to fill its half of the column:
# melonDS cannot stretch two stacked screens in one window. Values from
# ScreenLayout.h (TopOnly = 4, BotOnly = 5) and Screen.h (aspect "window" = 3).
SCREEN_WINDOWS = (("Window0", "4"), ("Window1", "5"))
ASPECT_WINDOW = "3"
# What melonDS assumes for a key absent from the file: restored when solo
# put back a key multiplayer added.
MELONDS_DEFAULTS = {"JoystickID": "0", "HK_FullscreenToggle": "-1", "Enabled": "false",
                    "ScreenSizing": "0", "ScreenAspectTop": "0", "ScreenAspectBot": "0"}

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


def command(exec_path: str, exec_args: str, players: int,
            job: Path | None = None) -> tuple[str, str]:
    """The launcher around melonDS. No fullscreen: the windows share the screen.
    `job` given: the launcher runs `prepare` on it first.
    The ROM is appended by the process manager, last, as for any launch."""
    args = [a for a in shlex.split(exec_args) if a not in FULLSCREEN_FLAGS]
    if exec_path == "flatpak":
        cmd = ["flatpak"] + args
        if "run" in cmd:
            cmd.insert(cmd.index("run") + 1, A11Y_FLAG)
    else:
        cmd = [exec_path] + args
    prepare_args = [f"--prepare={job}"] if job is not None else []
    return sys.executable, shlex.join([str(LAUNCHER), "--players", str(players),
                                       *prepare_args, "--", *cmd])


def _generator():
    spec = importlib.util.spec_from_file_location("gamecore_melonds_generator", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare(job_path: Path, synth=None, set_keys=None) -> dict[int, int]:
    """Write every instance's settings from the backend's job file, before
    melonDS starts. Returns player → SDL index."""
    job = json.loads(job_path.read_text())
    if synth is None or set_keys is None:
        generator = _generator()
        synth, set_keys = generator.synth_for(job["app_id"]), generator.set_joystick_keys
    target, players = Path(job["target"]), job["players"]
    _park_instance0(target, Path(job["state"]))
    indices = assign_joysticks(players, sdl_joysticks(job["app_id"]))
    write_instances(target, players, indices, Path(job["snap_dir"]), synth, set_keys)
    return indices


def _set(text: str, header: str, key: str, value: str) -> str:
    if section(text, header) is None:
        return set_section(text, header, f"{key} = {value}\n")
    return set_key(text, header, key, value)[0]


def _instance_settings(instance: int, joystick: int | None) -> list[tuple[str, str, str]]:
    """(section, key, value) multiplayer sets on one instance."""
    out = [(f"Instance{instance}.Keyboard", "HK_FullscreenToggle", FULLSCREEN_KEY)]
    for window, sizing in SCREEN_WINDOWS:
        header = f"Instance{instance}.{window}"
        out += [(header, "Enabled", "true"), (header, "ScreenSizing", sizing),
                (header, "ScreenAspectTop", ASPECT_WINDOW),
                (header, "ScreenAspectBot", ASPECT_WINDOW)]
    if joystick is not None:
        out.append((f"Instance{instance}", "JoystickID", str(joystick)))
    return out


def write_instances(target: Path, players: list[dict], indices: dict[int, int],
                    snap_dir: Path, synth, set_keys) -> None:
    """Pad, hotkey and screen-window settings for every instance, bindings for
    players 2-4, one atomic write."""
    text = target.read_text()
    base = section(text, "Instance0.Joystick") or ""
    for p in players:
        n = p["player"]
        for header, key, value in _instance_settings(n - 1, indices.get(n)):
            text = _set(text, header, key, value)
        if n > 1:
            pad = Pad(vendor=p["vendor"], product=p["product"], evdev_name=p["name"])
            header = f"Instance{n - 1}.Joystick"
            text = set_section(text, header, joystick_block(pad, header, base, snap_dir,
                                                            synth, set_keys))
    backup(target)
    atomic_write(target, text)


def _park_instance0(target: Path, state: Path) -> None:
    """Remember instance 1's solo values before multiplayer replaces them."""
    if state.exists():
        return
    text = target.read_text()
    parked = []
    for header, key, _value in _instance_settings(0, 0):
        m = re.search(rf"^{key} = (.*)$", section(text, header) or "", re.M)
        parked.append([header, key, m.group(1) if m else MELONDS_DEFAULTS[key]])
    state.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(state, json.dumps(parked))


def restore_instance0(target: Path, state: Path) -> None:
    """Solo launch after multiplayer: give instance 1 its own values back."""
    try:
        parked = json.loads(state.read_text())
    except (OSError, ValueError):
        return
    text = target.read_text()
    for header, key, value in parked:
        text = _set(text, header, key, value)
    atomic_write(target, text)
    state.unlink(missing_ok=True)


# An erased DS save chip reads 0xFF: what a game takes for "no save yet".
ERASED_BYTE = b"\xff"


def _save_dir(config_text: str, instance: int, rom: Path) -> Path:
    """Where melonDS keeps this instance's saves: its SaveFilePath, else the ROM's."""
    m = re.search(r'^SaveFilePath = "(.*)"$', section(config_text, f"Instance{instance}") or "", re.M)
    return Path(m.group(1)) if m and m.group(1) else rom.parent


def blank_player_saves(rom_path: str, players: int, config_text: str = "") -> list[Path]:
    """Give players 2-4 a blank save where they have none yet. Returns the new files.

    melonDS opens <rom>.sav.N for instance N and, when that is missing, loads
    player 1's <rom>.sav instead: player 2 started on a copy of the owner's
    progress (Pokemon Platinum, measured). A blank file the size of player 1's
    save makes the game offer a new one. Player 1's save and an existing
    player save are never touched; no player 1 save means melonDS starts every
    player fresh by itself. Archives are skipped: melonDS names their saves
    after the file inside.
    """
    rom = Path(rom_path)
    if rom.suffix.lower() != ".nds":
        return []
    made = []
    for player in range(2, players + 1):
        folder = _save_dir(config_text, player - 1, rom)
        base = folder / f"{rom.stem}.sav"
        mine = folder / f"{rom.stem}.sav.{player}"
        if mine.exists() or not base.is_file():
            continue
        atomic_write_bytes(mine, ERASED_BYTE * base.stat().st_size)
        made.append(mine)
    return made


def launch_command(*, rom_path: str, exec_path: str, exec_args: str,
                   players: list[dict], opts: dict | None) -> tuple[str, str] | None:
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
    configured = bool(target and target.is_file())
    for made in blank_player_saves(rom_path, count, target.read_text() if configured else ""):
        log.info("melonds multiplayer: blank save for a new player: %s", made.name)
    if not configured:
        return command(exec_path, exec_args, count)
    job = Path(opts["home"]) / JOB_FILE
    job.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(job, json.dumps({
        "target": str(target), "state": str(state), "snap_dir": str(opts["snap_dir"]),
        "app_id": opts.get("app_id", ""), "players": players}, default=str))
    log.info("melonds multiplayer: %d players", count)
    return command(exec_path, exec_args, count, job)
