"""Addon registry + lifecycle.

The core stays minimal: it reads the registry written by the `gamecore-addon`
CLI (config/addons.json — excluded from OTA rsync, so it survives updates),
and drives that same CLI for one-click install/remove from the Addons screen.
It knows nothing about addon contents.
"""
import asyncio
import json
import logging
import re
import shutil
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import GAMECORE_ROOT
from .. import ws

router = APIRouter(prefix="/addons", tags=["addons"])
log = logging.getLogger(__name__)

ADDONS_FILE = GAMECORE_ROOT / "config" / "addons.json"
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_CLI_TIMEOUT = 600.0
_busy_lock = asyncio.Lock()  # one CLI action at a time


def _cli() -> str:
    path = shutil.which("gamecore-addon") or str(GAMECORE_ROOT / "install" / "gamecore-addon")
    return path


def _registry() -> dict:
    try:
        return json.loads(ADDONS_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


@router.get("")
def list_installed():
    """Installed addons, as a list — consumed by the shared nav of every addon UI."""
    return [{"name": name, **entry} for name, entry in sorted(_registry().items())]


@router.get("/available")
async def list_available():
    """Available + installed state, from `gamecore-addon list --json` (may clone the repo)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            _cli(), "list", "--json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await asyncio.wait_for(proc.communicate(), timeout=60.0)
    except (FileNotFoundError, asyncio.TimeoutError) as e:
        raise HTTPException(503, f"gamecore-addon CLI unavailable: {e}")
    if proc.returncode != 0:
        raise HTTPException(503, f"gamecore-addon list failed: {err.decode().strip()}")
    return json.loads(out.decode())


class NotifyBody(BaseModel):
    event: str
    data: dict = {}


@router.post("/notify")
async def notify(body: NotifyBody):
    """Generic hook for addons to reach the TV UI over the core WebSocket
    (e.g. the ROM Manager addon broadcasts rom_uploaded after an upload)."""
    if not body.event or len(body.event) > 64:
        raise HTTPException(400, "invalid event name")
    await ws.broadcast(body.event, body.data)
    return {"ok": True}


async def _run_cli(action: str, name: str) -> None:
    async with _busy_lock:
        proc = await asyncio.create_subprocess_exec(
            _cli(), action, name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            if proc.stdout:
                async for line in proc.stdout:
                    await ws.broadcast("addon:log", {"line": line.decode().rstrip()})
            await asyncio.wait_for(proc.wait(), timeout=_CLI_TIMEOUT)
            code = proc.returncode or 0
        except asyncio.TimeoutError:
            log.warning("gamecore-addon %s %s timed out — killing", action, name)
            try:
                proc.kill()
                await proc.wait()
            except ProcessLookupError:
                pass
            await ws.broadcast("addon:log", {"line": f"[ERROR] {action} timed out."})
            code = -1
        await ws.broadcast("addon:done", {"action": action, "name": name, "success": code == 0})


def _start(action: str, name: str) -> dict:
    if not _NAME_RE.fullmatch(name):
        raise HTTPException(400, "invalid addon name")
    if _busy_lock.locked():
        raise HTTPException(409, "another addon operation is running")
    task = asyncio.get_event_loop().create_task(_run_cli(action, name))
    task.add_done_callback(lambda t: t.cancelled() or (t.exception() and log.warning("addon task failed: %s", t.exception())))
    return {"ok": True, "message": f"{action} {name} started"}


@router.post("/{name}/install")
async def install_addon(name: str):
    return _start("install", name)


@router.post("/{name}/update")
async def update_addon(name: str):
    return _start("update", name)


@router.delete("/{name}")
async def remove_addon(name: str):
    return _start("remove", name)
