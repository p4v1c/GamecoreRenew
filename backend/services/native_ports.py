"""Native ports: an executable `*.sh` in a system's ROM folder is a game.

A recompiled or decompiled game runs without the pack's emulator, so the
script itself is the launcher (`Uncharted 2.sh` in `emu/rpcs3/`). It declares
the folders its saves live in with header lines, one per folder:

    # gamecore-saves: ~/.local/share/bbport/user/savedata/1/CUSA00900

`~` and `@HOME@` are the player's home; a relative path is relative to the
script. Contract: docs/architecture/07-config-and-data.md#native-ports--emusystemsh.
Stdlib only: the ROM scanner imports it.
"""
from __future__ import annotations

import hashlib
import os
import shlex
import stat
from pathlib import Path

PORT_SUFFIX = ".sh"
SAVES_TAG = "gamecore-saves:"
READY_LOG_TAG = "gamecore-ready-log:"
READY_MATCH_TAG = "gamecore-ready-match:"
READY_WINDOW_TAG = "gamecore-ready-window:"
# The declarations sit in the header; a script is not read past it.
HEADER_LINES = 40
SAVES_ENV = "GAMECORE_SAVES_DIR"
ENV_BIN = "/usr/bin/env"


def is_port(path: Path) -> bool:
    """A regular `*.sh` file with an executable bit. Uploads land 0644, so a
    file sent over the LAN is never launchable until the owner `chmod +x` it."""
    if path.suffix.lower() != PORT_SUFFIX:
        return False
    try:
        mode = path.stat().st_mode
    except OSError:
        return False
    return stat.S_ISREG(mode) and bool(mode & 0o111)


def _header(script: Path, tag: str) -> list[str]:
    """The values of every `# <tag> <value>` line in the script's header."""
    try:
        with script.open(encoding="utf-8", errors="replace") as f:
            head = [next(f, "") for _ in range(HEADER_LINES)]
    except OSError:
        return []
    out = []
    for line in head:
        text = line.strip().lstrip("#").strip()
        if line.lstrip().startswith("#") and text.startswith(tag):
            if value := text[len(tag):].strip():
                out.append(value)
    return out


def _expand(raw: str, script: Path, home: Path) -> Path:
    raw = raw.replace("@HOME@", str(home))
    if raw == "~" or raw.startswith("~/"):
        raw = str(home) + raw[1:]
    return Path(os.path.normpath(script.parent / raw))


def declared_saves(script: Path, home: Path) -> list[Path]:
    """The save folders the script's header declares, absolute, in order."""
    out: list[Path] = []
    for raw in _header(script, SAVES_TAG):
        path = _expand(raw, script, home)
        if path not in out:
            out.append(path)
    return out


def declared_ready(script: Path, home: Path) -> dict | None:
    """The script's `launch.ready`, in the pack's shape, or None.

    `# gamecore-ready-log:` + `# gamecore-ready-match:` (a line in the
    port's own log), or `# gamecore-ready-window:` (WM_CLASS, comma-separated)."""
    logs, matches = _header(script, READY_LOG_TAG), _header(script, READY_MATCH_TAG)
    if logs and matches:
        return {"log": str(_expand(logs[0], script, home)), "match": matches[0]}
    windows = _header(script, READY_WINDOW_TAG)
    classes = [c.strip() for c in windows[0].split(",") if c.strip()] if windows else []
    return {"wmClass": classes} if classes else None


def profile_folder_name(path: Path) -> str:
    """`<name>-<hash>`: readable, and two ports whose save folders share a name
    (`saves`) still get one folder each. Scripts declaring the same folder
    (Uncharted 1-3: one collection, one save) share it."""
    digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:8]
    return f"{path.name}-{digest}"


def command(saves_dir: Path | None) -> tuple[str, str]:
    """(exec path, args) for the process manager, which appends the script.
    `env` carries `GAMECORE_SAVES_DIR`, unset for the primary profile."""
    args = shlex.join([f"{SAVES_ENV}={saves_dir}"]) if saves_dir is not None else ""
    return ENV_BIN, args
