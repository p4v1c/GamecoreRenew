"""Game scanning, launching, and session management."""
import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import ws
from ..config import resolve_path
from ..services import fullscreen_enforcer, local_media
from ..services import process_manager as process_manager_module
from ..services.process_manager import process_manager
from ..services.rom_scanner import clean_name, iter_rom_files
from .systems import list_all

log = logging.getLogger(__name__)


async def _gamepad_trigger(rounds: int = 3, delay: float = 3.0) -> None:
    """Run 'sudo udevadm trigger' several times so Flatpak apps detect the gamepad."""
    for i in range(rounds):
        await asyncio.sleep(delay)
        try:
            proc = await asyncio.create_subprocess_exec(
                "sudo", "udevadm", "trigger",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            log.info("gamepad_trigger: round %d/%d done", i + 1, rounds)
        except Exception:
            log.warning("gamepad_trigger: round %d failed", i + 1, exc_info=True)

router = APIRouter(tags=["games"])


def scan_roms(roms_path: Path, extensions: list[str], scan_dirs: bool = False,
              system_id: str = "") -> list[dict]:
    files = []
    for f in iter_rom_files(roms_path, extensions, scan_dirs=scan_dirs):
        try:
            stat = f.stat()
        except OSError:
            # Broken symlink or vanished file — skip it instead of turning
            # the whole library listing into a 500.
            continue
        # Folder-based games (PS3/PS4) embed their real title — prefer it over
        # the folder name, which is often just a serial like BLES01234.
        title = local_media.get_title(system_id, f) if scan_dirs and system_id else None
        files.append({
            "filename": f.name,
            "display_name": title or clean_name(f.name),
            "path": str(f),
            "size": stat.st_size,
            "ext": "FOLDER" if f.is_dir() else f.suffix.lstrip(".").upper(),
        })
    return files


@router.get("/systems/{system_id}/games")
def list_games(system_id: str):
    system = next((s for s in list_all() if s["id"].lower() == system_id.lower()), None)
    if not system:
        raise HTTPException(404, "System not found")

    if system.get("kind") == "app" or system.get("type") == "application":
        return []

    roms_raw = system.get("romsPath", "")
    if not roms_raw:
        return []

    roms_path = resolve_path(roms_raw)
    if not roms_path:
        return []

    return scan_roms(roms_path, system.get("extensions", []),
                     scan_dirs=system.get("scanDirs", False), system_id=system["id"])


class LaunchRequest(BaseModel):
    system_id: str
    rom_path: str = ""
    game_key: str = ""


@router.post("/games/launch")
async def launch_game(req: LaunchRequest):
    system = next((s for s in list_all() if s["id"].lower() == req.system_id.lower()), None)
    if not system:
        raise HTTPException(404, "System not found")

    if process_manager.is_running:
        raise HTTPException(409, "A game is already running")

    # Validate rom_path stays inside the system's configured ROMs directory.
    # Prevents launching arbitrary executables via crafted relative/absolute paths.
    if req.rom_path:
        roms_root = resolve_path(system.get("romsPath", ""))
        if not roms_root:
            raise HTTPException(400, "System has no ROMs path configured")
        try:
            Path(req.rom_path).resolve().relative_to(roms_root.resolve())
        except ValueError:
            raise HTTPException(403, "ROM path is outside the system's ROMs directory")

    exec_path = system.get("path", "")
    exec_args = system.get("args", "")
    game_key = req.game_key or (Path(req.rom_path).name if req.rom_path else system["id"])

    try:
        await process_manager.launch(
            exec_path=exec_path,
            exec_args=exec_args,
            rom_path=req.rom_path,
            game_key=game_key,
            system_id=req.system_id,
        )
    except (FileNotFoundError, PermissionError) as e:
        # The emulator is not installed, or is not executable. This used to
        # escape as a bare 500 with an empty body: no reason on screen, and no
        # WebSocket event either, so the UI sat on its loading screen until
        # someone pressed Back. _launching is released by launch()'s finally,
        # so retrying works — the player just had no idea what happened.
        detail = (f"{system['id']}: cannot start {exec_path!r} — "
                  + ("not installed" if isinstance(e, FileNotFoundError) else "not executable"))
        log.warning("launch failed — %s", detail)
        # X may have moved under us; make the next launch re-probe rather than
        # reuse a display that no longer answers.
        process_manager_module.invalidate_display_cache()
        try:
            await ws.broadcast("game:failed", {
                "game_key": game_key, "system_id": req.system_id, "detail": detail,
            })
        except Exception:
            log.exception("launch: failed to broadcast game:failed")
        raise HTTPException(503, detail)

    if system.get("gamepadTrigger"):
        task = asyncio.create_task(_gamepad_trigger())
        task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)

    fs_cfg = system.get("fullscreen")
    if fs_cfg:
        fs_task = asyncio.create_task(fullscreen_enforcer.enforce(req.system_id, fs_cfg))
        fs_task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)

    return {"ok": True, "game_key": game_key}


@router.post("/games/kill")
async def kill_game():
    await process_manager.kill()
    return {"ok": True}


@router.get("/games/session")
def get_session():
    return process_manager.current_game or {}
