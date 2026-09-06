"""WebSocket broadcast manager."""
import json
import logging
from fastapi import WebSocket

log = logging.getLogger(__name__)

_clients: list[WebSocket] = []
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


async def broadcast(event: str, data: dict | None = None) -> None:
    payload = json.dumps({"event": event, "data": data or {}})
    dead = []
    for ws in _clients:
        try:
            await ws.send_text(payload)
        except Exception as e:
            log.debug("ws broadcast failed (client will be dropped): %s", e)
            dead.append(ws)
    for ws in dead:
        disconnect(ws)
