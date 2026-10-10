#!/usr/bin/env python3
"""Keep the Flatpak Lutris ready for GameCore: GE-Proton and fast defaults.

Run by `gamecore-lutris-setup.timer` shortly after login and once a day:

1. the latest GE-Proton release into `<runners>/wine/` (once per release);
2. the defaults of `lutris_defaults.py`, with that build as the Wine version;
3. our builds beyond the newest two removed, unless a game is pinned to one.

What it installed is recorded in ~/.local/share/gamecore/lutris/state.json.
Exit status 1 when a step failed; the next run tries again.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterator

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lutris_defaults  # noqa: E402
import lutris_paths  # noqa: E402
import lutris_proton  # noqa: E402

KEEP_BUILDS = 2


def _log(message: str) -> None:
    print(f"[gamecore-lutris-setup] {message}", flush=True)


def state_dir(home: Path) -> Path:
    return home / ".local" / "share" / "gamecore" / "lutris"


def load_state(home: Path) -> dict:
    try:
        data = json.loads((state_dir(home) / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"proton": []}
    builds = data.get("proton") if isinstance(data, dict) else None
    return {"proton": [b for b in builds or [] if isinstance(b, str)]}


def save_state(home: Path, state: dict) -> None:
    path = state_dir(home) / "state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, path)


@contextlib.contextmanager
def locked(home: Path) -> Iterator[bool]:
    """One run at a time: a timer and a manual run must not unpack twice."""
    state_dir(home).mkdir(parents=True, exist_ok=True)
    with (state_dir(home) / "setup.lock").open("w") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False
            return
        yield True


def lutris_installed(app_id: str) -> bool:
    try:
        return subprocess.run(["flatpak", "info", app_id], capture_output=True,
                              timeout=30).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def ensure_proton(wine_dir: Path, state: dict) -> tuple[str | None, bool]:
    """(the build to use, whether everything went well)."""
    ours = [t for t in state["proton"] if lutris_proton.is_installed(wine_dir, t)]
    newest_ours = max(ours, key=lutris_proton.version_key, default=None)
    tag = lutris_proton.latest_tag(_log)
    if tag is None:
        return newest_ours, False
    if lutris_proton.is_installed(wine_dir, tag):
        if tag not in ours and tag not in state["proton"]:
            _log(f"{tag} is already there (not ours, kept as it is)")
        return tag, True
    if not lutris_proton.fetch(wine_dir, tag, _log):
        return newest_ours, False
    state["proton"] = sorted(set(ours) | {tag}, key=lutris_proton.version_key)
    return tag, True


def run(home: Path, app_id: str, games_dir: Path | None) -> int:
    wine_dir = lutris_paths.wine_dir(home, app_id)
    config_dir = lutris_paths.config_dir(home, app_id)
    state = load_state(home)
    proton, ok = ensure_proton(wine_dir, state)
    save_state(home, state)
    ours = set(state["proton"])
    for line in lutris_defaults.apply(config_dir, proton=proton, ours=ours, games_dir=games_dir):
        _log(line)
    removed = lutris_proton.prune(wine_dir, list(ours), KEEP_BUILDS, config_dir)
    if removed:
        state["proton"] = [t for t in state["proton"] if t not in removed]
        save_state(home, state)
        _log(f"removed older builds: {', '.join(removed)}")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--app-id", required=True)
    parser.add_argument("--games-dir", type=Path,
                        help="Lutris's default install folder, set when it has none")
    parser.add_argument("--home", type=Path, default=Path.home())
    args = parser.parse_args(argv)
    if not lutris_installed(args.app_id):
        _log(f"{args.app_id} is not installed; nothing to do")
        return 0
    with locked(args.home) as mine:
        if not mine:
            _log("another run is in progress")
            return 0
        return run(args.home, args.app_id, args.games_dir)


if __name__ == "__main__":
    sys.exit(main())
