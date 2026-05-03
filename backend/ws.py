"""WebSocket broadcast manager."""
import json
from fastapi import WebSocket

_clients: list[WebSocket] = []
_current_game: dict | None = None


def set_current_game(game: dict | None) -> None:
    global _current_game
    _current_game = game


async def connect(ws: WebSocket) -> None:
    await ws.accept()
    _clients.append(ws)
    if _current_game:
        try:
            payload = json.dumps({"event": "game:running", "data": _current_game})
            await ws.send_text(payload)
        except Exception:
            pass


def disconnect(ws: WebSocket) -> None:
    if ws in _clients:
        _clients.remove(ws)


async def broadcast(event: str, data: dict | None = None) -> None:
    payload = json.dumps({"event": event, "data": data or {}})
    dead = []
    for ws in _clients:
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        disconnect(ws)
