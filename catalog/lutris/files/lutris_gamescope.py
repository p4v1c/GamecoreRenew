"""Gamescope on by default for Lutris games, fullscreen at the TV's own mode.

Lutris 0.5.22 system options (`lutris/sysoptions.py`, `runner_interpreter.py`):

    gamescope              bool, default False; used only when `gamescope` is
                           on PATH (the VulkanLayer.gamescope extension)
    gamescope_window_mode  "-f" fullscreen (default), "" windowed, "-b" borderless
    gamescope_output_res   "WxH" -> -W/-H
    gamescope_game_res     "WxH" -> -w/-h

Both resolutions are needed. Nested gamescope (SDL backend) opens at 1280x720
when -W/-H are absent and sizes the game from that before going fullscreen,
so the game would render at 720p and be stretched (`src/Backends/SDLBackend.cpp`,
`src/main.cpp`).

Written just before each launch, from `xrandr` on the session's display, in
system.yml: `gamescope` and the window mode only where absent; the two
resolutions where absent or still holding the mode this file wrote last, so
a new TV is followed and an owner's own value is not. A game set otherwise
in Lutris (System options) keeps its own values.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import lutris_defaults
import lutris_paths

GAMESCOPE_DEFAULTS = {"gamescope": True, "gamescope_window_mode": "-f"}
RES_KEYS = ("gamescope_output_res", "gamescope_game_res")
STATE_FILE = "gamescope.json"
XRANDR_TIMEOUT_S = 5
# "HDMI-A-0 connected primary 3840x2160+0+0 (normal left …"
_OUTPUT_RE = re.compile(r"^\S+ connected (primary )?(\d+)x(\d+)\+\d+\+\d+")


def parse_mode(xrandr: str) -> str | None:
    """The primary output's current mode, else the first active one, as WxH."""
    modes = []
    for line in xrandr.splitlines():
        if m := _OUTPUT_RE.match(line):
            modes.append((bool(m.group(1)), f"{m.group(2)}x{m.group(3)}"))
    primary = [mode for is_primary, mode in modes if is_primary]
    return (primary or [mode for _, mode in modes] or [None])[0]


def current_mode() -> str | None:
    """The mode of the display this process was started on, None without one."""
    if not os.environ.get("DISPLAY"):
        return None
    try:
        r = subprocess.run(["xrandr", "--query"], capture_output=True, text=True,
                           timeout=XRANDR_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_mode(r.stdout) if r.returncode == 0 else None


def plan(system: dict, mode: str, ours: str | None) -> dict:
    """The keys to set in system.yml's `system` block. Pure."""
    changes = {k: v for k, v in GAMESCOPE_DEFAULTS.items() if k not in system}
    for key in RES_KEYS:
        current = system.get(key)
        if current in (None, "") or (ours and current == ours and current != mode):
            changes[key] = mode
    return changes


def _load_ours(home: Path) -> str | None:
    try:
        value = json.loads((lutris_paths.state_dir(home) / STATE_FILE).read_text())["res"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return value if isinstance(value, str) else None


def _save_ours(home: Path, mode: str) -> None:
    path = lutris_paths.state_dir(home) / STATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"res": mode}) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def apply(home: Path, app_id: str, mode: str | None) -> str:
    """Write the defaults for `mode`. Returns one line for the log."""
    if mode is None:
        return "no display mode read; gamescope settings left as they are"
    if lutris_defaults.yaml is None:
        return "python-yaml is missing; gamescope settings not written"
    path = lutris_paths.config_dir(home, app_id) / "system.yml"
    doc = lutris_defaults.load(path)
    if doc is None:
        return f"{path} is not readable YAML: left alone"
    system = doc.get("system") if isinstance(doc.get("system"), dict) else {}
    changes = plan(system, mode, _load_ours(home))
    if changes:
        doc["system"] = {**system, **changes}
        lutris_defaults.save(path, doc)
    if any(key in changes for key in RES_KEYS):
        _save_ours(home, mode)
    return (f"gamescope: {', '.join(f'{k}={v}' for k, v in changes.items())}" if changes
            else f"gamescope settings already set ({mode} on this display)")
