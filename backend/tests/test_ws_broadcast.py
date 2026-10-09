"""One stuck WebSocket client must not stall every broadcast.

`broadcast` awaited each `send_text` in turn with no timeout: a client whose
socket stopped draining held up launches, addon CLI output and the OTA log pump.
"""
import asyncio
import json

import pytest

from backend import ws


class FakeClient:
    def __init__(self, *, stuck: bool = False, broken: bool = False):
        self.stuck = stuck
        self.broken = broken
        self.received: list[dict] = []
        self.closed = False

    async def send_text(self, text: str) -> None:
        if self.stuck:
            await asyncio.Event().wait()      # never returns
        if self.broken:
            raise RuntimeError("socket closed")
        self.received.append(json.loads(text))

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def clients(monkeypatch):
    live: list = []
    monkeypatch.setattr(ws, "_clients", live)
    monkeypatch.setattr(ws, "SEND_TIMEOUT", 0.05)
    return live


def test_a_stuck_client_is_dropped_and_the_others_still_get_the_event(clients):
    healthy, stuck = FakeClient(), FakeClient(stuck=True)
    clients.extend([stuck, healthy])

    async def scenario():
        await asyncio.wait_for(ws.broadcast("game:started", {"k": 1}), 5)
        await asyncio.sleep(0)            # let the scheduled close run

    asyncio.run(scenario())
    assert healthy.received == [{"event": "game:started", "data": {"k": 1}}]
    assert clients == [healthy], "the stuck client must be dropped"
    assert stuck.closed, "closed so the UI reconnects instead of going deaf"


def test_a_broken_client_is_dropped(clients):
    healthy, broken = FakeClient(), FakeClient(broken=True)
    clients.extend([broken, healthy])
    asyncio.run(ws.broadcast("x"))
    assert clients == [healthy]
    assert healthy.received == [{"event": "x", "data": {}}]


def test_a_client_that_connects_mid_broadcast_is_kept(clients):
    late = FakeClient()

    class Joiner(FakeClient):
        async def send_text(self, text):
            clients.append(late)
            await super().send_text(text)

    clients.append(Joiner())
    asyncio.run(ws.broadcast("x"))
    assert late in clients
