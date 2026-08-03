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


def current_game() -> dict | None:
    """What is running, or None. The overlay router asks, to pick a bezel."""
    return _current_game


async def connect(ws: WebSocket) -> None:
    await ws.accept()
    _clients.append(ws)
    if _current_game:
        try:
            payload = json.dumps({"event": "game:running", "data": _current_game})
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
