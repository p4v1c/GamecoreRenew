"""A pack's `launch_command`: may replace what the launch runs, never fatal.

melonDS uses it for local multiplayer. The core owns the contract: what the
hook receives, that None keeps the command, that autoconfig off withholds the
config, and that a failing or slow hook launches the usual command.
"""
from __future__ import annotations

import asyncio
import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.services import launch as launch_service        # noqa: E402
from backend.services import configgen                       # noqa: E402


class _Pack:
    id = "testpack"


def _wire(monkeypatch, module, *, autoconfig=True):
    pack = _Pack()
    monkeypatch.setattr(launch_service, "load_catalog", lambda *a, **k: {"testpack": pack})
    monkeypatch.setattr(configgen, "load_generator", lambda p: module)
    monkeypatch.setattr(configgen, "autoconfigured_packs",
                        lambda packs: ([pack], []) if autoconfig else ([], [pack]))
    monkeypatch.setattr(configgen, "generator_opts", lambda p, home, snap: {"target": "t"})
    monkeypatch.setattr(launch_service.gamepad_monitor, "roster", lambda: {
        "k2": ("045e", "02fd", "Xbox", 5), "k1": ("054c", "09cc", "DS4", 5)})
    monkeypatch.setattr(launch_service.controller_registry, "player_for",
                        lambda key: {"k1": 1, "k2": 2}[key])


def _run():
    return asyncio.run(launch_service._pack_launch_command(
        "testpack", "/roms/game.nds", "flatpak", "run net.kuribo64.melonDS -f"))


def test_the_hook_sees_the_launch_and_the_players_in_slot_order(monkeypatch):
    seen = {}

    def launch_command(**kw):
        seen.update(kw)
        return "/usr/bin/python3", "launcher.py --players 2 -- flatpak run x"

    _wire(monkeypatch, types.SimpleNamespace(launch_command=launch_command))
    assert _run() == ("/usr/bin/python3", "launcher.py --players 2 -- flatpak run x")
    assert seen["rom_path"] == "/roms/game.nds"
    assert seen["opts"] == {"target": "t"}
    assert [p["player"] for p in seen["players"]] == [1, 2]
    assert seen["players"][0] == {"player": 1, "key": "k1", "vendor": "054c",
                                  "product": "09cc", "name": "DS4"}


def test_none_keeps_the_usual_command(monkeypatch):
    _wire(monkeypatch, types.SimpleNamespace(launch_command=lambda **kw: None))
    assert _run() == ("flatpak", "run net.kuribo64.melonDS -f")


def test_a_pack_without_the_hook_keeps_the_usual_command(monkeypatch):
    _wire(monkeypatch, types.SimpleNamespace())
    assert _run() == ("flatpak", "run net.kuribo64.melonDS -f")


def test_autoconfig_off_gives_the_hook_no_config(monkeypatch):
    seen = {}
    _wire(monkeypatch, types.SimpleNamespace(launch_command=lambda **kw: seen.update(kw)),
          autoconfig=False)
    _run()
    assert seen["opts"] is None


def test_a_failing_hook_keeps_the_usual_command(monkeypatch):
    def launch_command(**kw):
        raise RuntimeError("boom")

    _wire(monkeypatch, types.SimpleNamespace(launch_command=launch_command))
    assert _run() == ("flatpak", "run net.kuribo64.melonDS -f")


def test_a_slow_hook_is_abandoned(monkeypatch):
    monkeypatch.setattr(launch_service, "PACK_PREPARE_BUDGET", 0.05)

    def launch_command(**kw):
        time.sleep(0.5)
        return "late", "late"

    _wire(monkeypatch, types.SimpleNamespace(launch_command=launch_command))
    assert _run() == ("flatpak", "run net.kuribo64.melonDS -f")
