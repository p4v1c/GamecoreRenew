#!/usr/bin/env python3
"""Start melonDS for 2-4 local players: one process, one instance per player.

    launcher.py --players N [--prepare JOB] -- <melonDS command ...> <rom>

With --prepare, first writes every instance's pad and windows (setup.prepare:
SDL probes too slow for the backend's launch budget). Starts melonDS with
the ROM (instance 1), then presses melonDS's own
"Launch new instance" and "Open recent > 1." for each other player, exactly
what a player does by hand. Every instance then boots its DS firmware with the
cart inserted ("Boot firmware" keeps the cart), so each player lands on the DS
menu: the game for multi-card play, DS Download Play for single-card games.
The windows are laid out side by side. melonDS links its instances itself
(local multiplayer inside one process). Once a second mouse is used, each
mouse drives its own player's arrow and touch screen (mouse_touch.py).

Runs in the game's process group, so GameCore's suspend and kill reach melonDS
through it. Never exits before melonDS does: an early exit would end the
session while the game is still on screen. A failed step leaves the players
started so far running. Stdlib only, except that pad step (setup.py, run by
the backend's interpreter).
"""
from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import atspi
import mouse_touch
import windows

MAX_PLAYERS = 4
A11Y_ENV = "QT_LINUX_ACCESSIBILITY_ALWAYS_ON"
# Read back by the L3 layout daemon (files/melonds_config.py), which must leave
# the per-screen windows alone.
PLAYERS_ENV = "GAMECORE_MELONDS_PLAYERS"
# A cold flatpak start plus firmware boot measured ~5 s; Qt registers its
# accessible tree a little later.
APP_TIMEOUT = 40.0
INSTANCE_TIMEOUT = 15.0
POLL = 0.25
# melonDS restores each window's saved geometry when it shows it, and the
# fullscreen round trip moves it again; re-place for a short while so the
# layout is the last word.
TILE_PASSES = 8
MENU_KEY_ATTEMPTS = 3
# The mouse loop polls every 0.5 s, then gives the arrows back.
MICE_STOP_TIMEOUT = 3.0
MENU_KEY_TIMEOUT = 2.0
LOG_PATH = Path.home() / ".cache/gamecore/melonds-multiplayer.log"

log = logging.getLogger("melonds-multiplayer")


class MelonDSExited(RuntimeError):
    """melonDS is gone; there is nothing left to set up."""


def _wait(predicate, timeout: float, what: str, alive=lambda: True):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not alive():
            raise MelonDSExited(f"melonDS exited while waiting for {what}")
        try:
            value = predicate()
        except atspi.AtspiError:
            value = None
        if value:
            return value
        time.sleep(POLL)
    raise TimeoutError(f"timed out waiting for {what}")


def _all_frames(address: str) -> dict[tuple[int, int], atspi.Node]:
    """(player, window) → frame, for every melonDS window."""
    app = atspi.find_app(address)
    if app is None:
        return {}
    frames = {}
    for node in app.children():
        if node.role() == "frame" and (ids := windows.title_ids(node.name())):
            frames[ids] = node
    return frames


def _frames(address: str) -> dict[int, atspi.Node]:
    """player → that instance's first window, the one menus are pressed in."""
    return {p: f for (p, w), f in _all_frames(address).items() if w == 1}


def recent_rom_matcher(rom: str):
    """Predicate for the ROM just started: entry 1 of Open recent, whose
    label keeps the file name even when melonDS shortens the path. An archive
    is listed as "<file>.zip|<member>"."""
    tail = "/" + atspi.strip_mnemonic(os.path.basename(rom))
    return lambda label: label.startswith("1.") and (
        label.endswith(tail) or tail + "|" in label)


def add_instance(address: str, player: int, rom: str, alive) -> None:
    """Open instance `player` and boot the ROM in it."""
    first = _wait(lambda: _frames(address).get(1), INSTANCE_TIMEOUT, "instance 1", alive)
    item = atspi.find_menu_item(first, ["System", "Multiplayer", "Launch new instance"])
    if item is None:
        raise atspi.AtspiError("no 'Launch new instance' menu item")
    item.press()
    frame = _wait(lambda: _frames(address).get(player), INSTANCE_TIMEOUT,
                  f"instance {player}", alive)
    recent = atspi.find_menu_item(frame, ["File", "Open recent", recent_rom_matcher(rom)])
    if recent is None:
        raise atspi.AtspiError(f"{rom} is not entry 1 of Open recent")
    recent.press()
    log.info("player %d: instance opened, ROM loaded", player)


def boot_firmware(frame: atspi.Node, player: int, alive) -> None:
    """Restart this instance on its DS menu, cart still inserted."""
    _wait(lambda: atspi.find_menu_item(frame, ["File", has_cart]), INSTANCE_TIMEOUT,
          f"the cart in instance {player}", alive)
    item = atspi.find_menu_item(frame, ["File", "Boot firmware"])
    if item is None:
        raise atspi.AtspiError("no 'Boot firmware' menu item")
    item.press()
    log.info("player %d: DS firmware booted", player)


def has_cart(label: str) -> bool:
    """melonDS names the inserted cart in File: "DS slot: <name>"."""
    return label.startswith("DS slot:") and "(none)" not in label


def hide_menu_bar(address: str, player: int, alive) -> None:
    """Have melonDS hide the menu bars of this player's windows; checked,
    because a key that lands while the instance restarts its firmware is lost."""
    bars = [b for (p, _w), f in _all_frames(address).items()
            if p == player and (b := atspi.menu_bar(f)) is not None]
    for _attempt in range(MENU_KEY_ATTEMPTS):
        if not bars or not windows.press_fullscreen_key(player):
            break
        try:
            _wait(lambda: all(b.extents()[3] == 0 for b in bars), MENU_KEY_TIMEOUT,
                  "the menu bars", alive)
            log.info("player %d: menu bars hidden", player)
            return
        except TimeoutError:
            continue
    log.warning("player %d: menu bar still shown", player)


def tile(players: int) -> None:
    for _ in range(TILE_PASSES):
        try:
            placed = windows.tile(players)
        except OSError:
            log.exception("window layout failed")
            return
        log.debug("layout pass: %d/%d windows", placed, players)
        time.sleep(0.5)


def orchestrate(players: int, rom: str, alive) -> None:
    address = atspi.bus_address()
    _wait(lambda: _frames(address).get(1), APP_TIMEOUT, "melonDS to start", alive)
    for player in range(2, players + 1):
        add_instance(address, player, rom, alive)
    frames = _frames(address)
    for player in range(1, players + 1):
        boot_firmware(frames[player], player, alive)
    for player in range(1, players + 1):
        hide_menu_bar(address, player, alive)
    tile(players)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--players", type=int, required=True)
    parser.add_argument("--prepare", type=Path)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("no melonDS command")
    players = max(1, min(MAX_PLAYERS, args.players))
    rom = command[-1]

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=LOG_PATH, filemode="w", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    log.info("%d players: %s", players, " ".join(command))
    if args.prepare:
        _prepare(args.prepare)
    proc = subprocess.Popen(command, env={**os.environ, A11Y_ENV: "1",
                                            PLAYERS_ENV: str(players)})
    try:
        orchestrate(players, rom, alive=lambda: proc.poll() is None)
        log.info("all %d players started", players)
    except Exception:
        log.exception("multiplayer setup stopped; the players started so far keep playing")
    mice = threading.Thread(target=_route_mice, args=(players, proc), daemon=True)
    mice.start()
    code = proc.wait()
    mice.join(timeout=MICE_STOP_TIMEOUT)
    return code


def _prepare(job: Path) -> None:
    """Each player's pad and windows in its instance. A failure costs the
    per-player settings, never the game."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # GameCore root
        import setup
        log.info("instances written, SDL index per player: %s", setup.prepare(job))
    except Exception:
        log.exception("instance settings skipped; melonDS keeps the ones it had")


def _route_mice(players: int, proc: subprocess.Popen) -> None:
    """One mouse per player while melonDS runs; never fatal to the game."""
    try:
        mouse_touch.MouseRouter(players).run(keep_going=lambda: proc.poll() is None)
    except Exception:
        log.exception("per-player mice stopped; the shared pointer is back")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
