"""The catalogue, and installing from it while the box is running.

Same shape as routers/addons.py, deliberately: one CLI action at a time behind
`_busy_lock`, output pumped line by line onto the existing WebSocket, and the
task handle — not the lock — as the busy check.

The core stays thin. It knows the catalogue is a directory of packs and drives
`gamecore-emu`; it knows nothing about what an emulator is.

**Why the ids are validated here and not only in the CLI.** This endpoint is
reachable from the LAN interface (behind forward_auth) and the CLI runs with
enough privilege to install software. `id` goes into an argv, never into a
shell, and it must match a pack the catalogue already declares — there is no
"install this URL". A pack comes from the release or the operator drops it in
config/catalog.d/, and one dropped there is data only.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil

from fastapi import APIRouter, HTTPException

from .. import ws
from ..config import GAMECORE_ROOT
from ..services.catalog import load_catalog

router = APIRouter(prefix="/catalog", tags=["catalog"])
log = logging.getLogger(__name__)

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_CLI_TIMEOUT = 1800.0          # a Flatpak install on a slow line is not a hang
_busy_lock = asyncio.Lock()    # one CLI action at a time
_ACTIONS = ("install", "remove", "reconfigure")


def _cli_argv(action: str, pack_id: str) -> list[str]:
    """The command to run, root-side when it has to be.

    Unlike gamecore-addon — which installs user-level services and needs no
    privilege — this installs Flatpaks and system packages. The backend runs as
    the GameCore user, so it goes through the single narrow sudoers rule
    install/setup-update-permissions.sh writes:

        <user> ALL=(root) NOPASSWD: /usr/local/bin/gamecore-emu

    `sudo -n`: never prompt. There is no terminal here, and a sudo waiting for
    a password would hang until the timeout with _busy_lock held.

    /usr/local/bin first, and that is the point of it: a rule naming a script
    inside GAMECORE_PATH — writable by the very user it grants — would be a
    root shell with extra steps.
    """
    installed = shutil.which("gamecore-emu")
    if installed:
        return ["sudo", "-n", installed, action, pack_id]
    # Development / a box where the permissions were never set up: run it
    # directly and let it fail on its own terms rather than pretend.
    return [str(GAMECORE_ROOT / "install" / "gamecore-emu"), action, pack_id]


def _live_ids() -> set[str]:
    out: set[str] = set()
    for name in ("systems.json", "apps.json"):
        try:
            rows = json.loads((GAMECORE_ROOT / "config" / name).read_text())
            out |= {r["id"] for r in rows if "id" in r}
        except (OSError, ValueError):
            pass
    return out


@router.get("")
def list_catalog():
    """Every pack, with whether its tile is currently on the grid.

    "installed" is about the GRID, which is what the owner sees. Whether the
    Flatpak itself is present is a different question — `gamecore-emu verify`
    answers that one, and it needs the network.
    """
    live = _live_ids()
    packs = load_catalog()
    return [
        {
            "id": p.id,
            "kind": p.kind,
            "label": p.data["label"],
            "platform": p.data["platform"],
            # Who made the hardware. The installer groups by it, so a box with
            # twenty systems reads as four short lists. Empty rather than a
            # guess: a pack that does not say lands under "Other", which is
            # honest, where inferring a maker from the id would be wrong the
            # first time somebody ships a machine nobody here anticipated.
            "family": p.data.get("family", ""),
            "color": p.data["color"],
            "emulatorName": p.data.get("emulatorName", p.data["label"]),
            "description": p.data.get("description", ""),
            "origin": p.origin,
            "installed": p.id in live,
            # A local pack is data only unless the operator opted in; saying so
            # here is what stops "why did my generator not run" being a mystery.
            "restricted": sorted(p.stripped),
        }
        for p in sorted(packs.values(), key=lambda p: (p.kind, p.id))
    ]


async def _run_cli(action: str, pack_id: str) -> None:
    async with _busy_lock:
        try:
            proc = await asyncio.create_subprocess_exec(
                *_cli_argv(action, pack_id),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except OSError as e:
            await ws.broadcast("catalog:log", {"line": f"[ERROR] {e}"})
            await ws.broadcast("catalog:done",
                               {"action": action, "id": pack_id, "success": False})
            return

        async def _pump() -> None:
            # The whole read loop sits under the timeout: a script that blocks
            # never closes stdout, and a timeout on proc.wait() alone would
            # never fire — leaving _busy_lock held for ever.
            if proc.stdout:
                async for line in proc.stdout:
                    await ws.broadcast("catalog:log",
                                       {"line": line.decode(errors="replace").rstrip()})
            await proc.wait()

        try:
            await asyncio.wait_for(_pump(), timeout=_CLI_TIMEOUT)
            code = proc.returncode or 0
        except asyncio.TimeoutError:
            log.warning("gamecore-emu %s %s timed out — killing", action, pack_id)
            try:
                proc.kill()
                await proc.wait()
            except ProcessLookupError:
                pass
            await ws.broadcast("catalog:log", {"line": f"[ERROR] {action} timed out."})
            code = -1
        await ws.broadcast("catalog:done",
                           {"action": action, "id": pack_id, "success": code == 0})


# The task handle, not the lock, is the busy check: two requests arriving in
# the same loop tick both see the lock unlocked (the task has not started yet)
# and the second silently queues instead of getting its 409. Checking and
# assigning _current is atomic — no await in between.
_current: asyncio.Task | None = None


def _start(action: str, pack_id: str) -> dict:
    global _current
    if action not in _ACTIONS:
        raise HTTPException(400, "unknown action")
    if not _ID_RE.fullmatch(pack_id):
        raise HTTPException(400, "invalid pack id")
    if pack_id not in load_catalog():
        # Not "install whatever you name": only what the catalogue declares.
        raise HTTPException(404, f"no pack named {pack_id!r}")
    if _current is not None and not _current.done():
        raise HTTPException(409, "another catalogue operation is running")
    _current = asyncio.create_task(_run_cli(action, pack_id))
    _current.add_done_callback(
        lambda t: t.cancelled() or (t.exception() and
                                    log.warning("catalog task failed: %s", t.exception())))
    return {"ok": True, "message": f"{action} {pack_id} started"}


@router.post("/{pack_id}/install")
async def install_pack(pack_id: str):
    return _start("install", pack_id)


@router.post("/{pack_id}/remove")
async def remove_pack(pack_id: str):
    return _start("remove", pack_id)


@router.post("/{pack_id}/reconfigure")
async def reconfigure_pack(pack_id: str):
    """Re-deploy the seed and re-profile the connected pads.

    The second of the three trigger points the pipeline has: at install, on
    demand (here), and on pad connect (gamepad_monitor).
    """
    return _start("reconfigure", pack_id)


@router.get("/busy")
def busy():
    return {"busy": _current is not None and not _current.done()}
