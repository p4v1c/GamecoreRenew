#!/usr/bin/env python3
"""Run one Lutris game as a GameCore session, and end when the game ends.

GameCore's session is this process. Lutris alone is not a reliable stand-in:

- A Lutris already running receives the command over D-Bus and the new
  process exits at once: the session would end before the game starts.
- Lutris can outlive the game (a dialog, a tray icon): the session would
  never end.

So an idle Lutris is closed first, the game is followed through its
`lutris-wrapper` process (Lutris runs every game under one and retitles it
"lutris-wrapper: <name>"), and once that is gone Lutris gets a few seconds to
quit before it is closed. Everything runs in this process group, so
GameCore's suspend and kill reach the whole tree.

    lutris_session.py --app-id net.lutris.Lutris [/path/Game.lutris]

Without a stub it opens Lutris's own window and ends when that closes.
Stdlib only: runs on the system python3.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lutris_library import game_id_of  # noqa: E402

PROC = Path("/proc")
WRAPPER_TITLE = b"lutris-wrapper:"
WRAPPER_SCRIPT = b"/lutris-wrapper"
POLL_S = 0.5
# How long Lutris may stay up after its game before it is closed.
LINGER_S = 10.0
CLOSE_WAIT_S = 5.0


def _log(message: str) -> None:
    print(f"[gamecore-lutris] {message}", flush=True)


def is_game_cmdline(cmdline: bytes) -> bool:
    """A lutris-wrapper process, by its retitled name or its script path."""
    if cmdline.startswith(WRAPPER_TITLE):
        return True
    return any(arg.endswith(WRAPPER_SCRIPT) for arg in cmdline.split(b"\0")[:3])


def game_running(proc: Path = PROC, uid: int | None = None) -> bool:
    """True while a Lutris game of this user runs, in any Lutris instance."""
    uid = os.getuid() if uid is None else uid
    try:
        entries = list(proc.iterdir())
    except OSError:
        return False
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            if entry.stat().st_uid != uid:
                continue
            cmdline = (entry / "cmdline").read_bytes()
        except OSError:
            continue                    # exited while we looked
        if is_game_cmdline(cmdline):
            return True
    return False


def instance_running(app_id: str) -> bool:
    try:
        out = subprocess.run(["flatpak", "ps", "--columns=application"],
                             capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return app_id in {line.strip() for line in out.splitlines()}


def close_instance(app_id: str) -> None:
    try:
        subprocess.run(["flatpak", "kill", app_id], capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as e:
        _log(f"could not close Lutris: {e}")


def follow(child: subprocess.Popen, *, running: Callable[[], bool],
           close: Callable[[], None], sleep: Callable[[float], None] = time.sleep,
           clock: Callable[[], float] = time.monotonic, linger: float = LINGER_S) -> int:
    """Wait for the game to start and end, then for Lutris. Returns the exit code."""
    seen = False
    while True:
        if running():
            seen = True
        elif seen:
            break
        else:
            code = child.poll()
            if code is not None:
                _log(f"Lutris exited ({code}) without starting a game")
                return code or 1
        sleep(POLL_S)
    _log("the game has ended")
    deadline = clock() + linger
    while child.poll() is None and clock() < deadline:
        sleep(POLL_S)
    if child.poll() is None:
        _log("Lutris is still up after the game; closing it")
        close()
        try:
            child.wait(timeout=CLOSE_WAIT_S)
        except subprocess.TimeoutExpired:
            child.kill()
    return 0


def _clear_idle_instance(app_id: str) -> None:
    """Close a Lutris that runs no game, or our command would be forwarded to it."""
    if not instance_running(app_id):
        return
    _log("closing an idle Lutris first")
    close_instance(app_id)
    deadline = time.monotonic() + CLOSE_WAIT_S
    while instance_running(app_id) and time.monotonic() < deadline:
        time.sleep(POLL_S)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--app-id", required=True)
    parser.add_argument("stub", nargs="?", type=Path)
    args = parser.parse_args(argv)

    command = ["flatpak", "run", args.app_id]
    if args.stub is None:
        return subprocess.call(command)
    game_id = game_id_of(args.stub)
    if game_id is None:
        _log(f"{args.stub.name} is not a Lutris entry")
        return 2
    if game_running():
        _log("Lutris is already running a game or an installer; close it first")
        return 1
    _clear_idle_instance(args.app_id)
    command.append(f"lutris:rungameid/{game_id}")
    _log(" ".join(command))
    child = subprocess.Popen(command)
    return follow(child, running=game_running, close=lambda: close_instance(args.app_id))


if __name__ == "__main__":
    sys.exit(main())
