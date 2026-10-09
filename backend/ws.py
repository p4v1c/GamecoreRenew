"""WebSocket broadcast manager."""
import asyncio
import json
import logging
from fastapi import WebSocket

log = logging.getLogger(__name__)

# A client whose socket stopped draining would otherwise hold up every
# broadcast: launches, addon CLI output, the OTA log pump.
SEND_TIMEOUT = 2.0

_clients: list[WebSocket] = []
_closing: set[asyncio.Task] = set()
_current_game: dict | None = None


def set_current_game(game: dict | None) -> None:
    global _current_game
    _current_game = game


async def connect(ws: WebSocket) -> None:
    """Accept a client and tell it what the box is playing — including nothing.

    The empty case is the one that mattered. This used to announce a running
    game and stay silent otherwise, so a front end that lost the socket while a
    game was up, and reconnected after the emulator had quit, never heard the
    `game:finished` it missed: nothing contradicted what it still believed. The
    session guard then blocked the pad on a dashboard with no game behind it,
    until a reload.

    `{}` is the whole state, not the absence of one, and the client reads it as
    such.
    """
    await ws.accept()
    _clients.append(ws)
    try:
        payload = json.dumps({"event": "game:running", "data": _current_game or {}})
        await ws.send_text(payload)
    except Exception as e:
        log.warning("ws initial send failed: %s", e)


def disconnect(ws: WebSocket) -> None:
    if ws in _clients:
        _clients.remove(ws)


async def _send(ws: WebSocket, payload: str) -> bool:
    try:
        await asyncio.wait_for(ws.send_text(payload), SEND_TIMEOUT)
        return True
    except Exception as e:
        log.debug("ws broadcast failed (client will be dropped): %r", e)
        return False


async def broadcast(event: str, data: dict | None = None) -> None:
    """Send to every client at once; drop those that fail or stall."""
    payload = json.dumps({"event": event, "data": data or {}})
    # A snapshot: connect()/disconnect() may change the list while we await.
    clients = list(_clients)
    sent = await asyncio.gather(*(_send(ws, payload) for ws in clients))
    for ws, ok in zip(clients, sent):
        if not ok:
            disconnect(ws)
            # Closed, not just forgotten: the UI reconnects on close and resyncs.
            task = asyncio.create_task(_close(ws))
            _closing.add(task)          # the loop holds tasks only weakly
            task.add_done_callback(_closing.discard)


async def _close(ws: WebSocket) -> None:
    try:
        await asyncio.wait_for(ws.close(), SEND_TIMEOUT)
    except Exception:
        pass
