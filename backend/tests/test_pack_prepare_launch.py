"""A pack's `prepare_launch`: called with what the launch will run, never fatal.

The hook is how RPCS3's per-game settings and patch activations get written
before the emulator reads them. What this suite pins is the contract the core
owns — the arguments, the deadline, the notice, and that no failure of the
hook can cost the player the game.
"""
from __future__ import annotations

import asyncio
import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.routers import games as games_router          # noqa: E402
from backend.services import configgen                       # noqa: E402


class _Pack:
    id = "testpack"


def _wire(monkeypatch, module):
    sent = []

    async def broadcast(event, data):
        sent.append((event, data))

    monkeypatch.setattr(games_router, "load_catalog", lambda *a, **k: {"testpack": _Pack()})
    monkeypatch.setattr(configgen, "load_generator", lambda pack: module)
    monkeypatch.setattr(games_router.ws, "broadcast", broadcast)
    return sent


def _run(**kw):
    asyncio.run(games_router._prepare_pack_launch(
        "testpack", "/roms/game", "flatpak", "run net.rpcs3.RPCS3 --no-gui", "game", **kw))


def test_the_hook_gets_the_launch_and_its_notice_is_broadcast(monkeypatch):
    seen = {}

    def prepare_launch(**kw):
        seen.update(kw)
        return {"notice": "PS3 · Game: 1 validated patch(es) on"}

    sent = _wire(monkeypatch, types.SimpleNamespace(prepare_launch=prepare_launch))
    _run()
    assert seen["rom_path"] == "/roms/game"
    assert (seen["exec_path"], seen["exec_args"]) == ("flatpak", "run net.rpcs3.RPCS3 --no-gui")
    assert 0 < seen["deadline"] - time.monotonic() <= games_router.PACK_PREPARE_BUDGET
    assert sent == [("game:notice", {"game_key": "game", "system_id": "testpack",
                                     "detail": "PS3 · Game: 1 validated patch(es) on"})]


def test_a_pack_without_a_hook_is_left_alone(monkeypatch):
    sent = _wire(monkeypatch, types.SimpleNamespace())
    _run()
    assert sent == []


def test_a_failing_hook_does_not_stop_the_launch(monkeypatch):
    def prepare_launch(**kw):
        raise RuntimeError("boom")

    sent = _wire(monkeypatch, types.SimpleNamespace(prepare_launch=prepare_launch))
    _run()
    assert sent == []


def test_a_slow_hook_is_abandoned(monkeypatch):
    monkeypatch.setattr(games_router, "PACK_PREPARE_BUDGET", 0.05)

    def prepare_launch(**kw):
        time.sleep(1.2)
        return {"notice": "late"}

    sent = _wire(monkeypatch, types.SimpleNamespace(prepare_launch=prepare_launch))
    waited = []

    async def scenario():
        started = time.monotonic()
        await games_router._prepare_pack_launch("testpack", "/roms/game", "flatpak", "",
                                                "game")
        waited.append(time.monotonic() - started)

    asyncio.run(scenario())
    assert waited[0] < 0.05 + 0.5 + 0.3      # budget + grace, not the hook's 1.2 s
    assert sent == []


def test_the_rpcs3_pack_provides_the_hook():
    from backend.services.catalog import load_catalog
    module = configgen.load_generator(load_catalog()["rpcs3"])
    assert callable(getattr(module, "prepare_launch", None))
