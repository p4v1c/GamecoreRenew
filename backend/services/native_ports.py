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


def declared_saves(script: Path, home: Path) -> list[Path]:
    """The save folders the script's header declares, absolute, in order."""
    try:
        with script.open(encoding="utf-8", errors="replace") as f:
            head = [next(f, "") for _ in range(HEADER_LINES)]
    except OSError:
        return []
    out: list[Path] = []
    for line in head:
        text = line.strip().lstrip("#").strip()
        if not line.lstrip().startswith("#") or not text.startswith(SAVES_TAG):
            continue
        raw = text[len(SAVES_TAG):].strip().replace("@HOME@", str(home))
        if not raw:
            continue
        if raw == "~" or raw.startswith("~/"):
            raw = str(home) + raw[1:]
        path = Path(os.path.normpath(script.parent / raw))
        if path not in out:
            out.append(path)
    return out


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
