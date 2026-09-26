"""Game scanning, launching, and session management."""
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import resolve_path
from ..services import launch as launch_service
from ..services import local_media, prefetch
from ..services.process_manager import SessionConflict, process_manager
from ..services.rom_scanner import clean_name, iter_rom_files
from ..services.systems import find

log = logging.getLogger(__name__)

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
    system = find(system_id)
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

    games = scan_roms(roms_path, system.get("extensions", []),
                      scan_dirs=system.get("scanDirs", False), system_id=system["id"])

    # This listing IS the box's ROM scan, and it runs whenever the grid opens.
    # It is therefore the one place that learns a game was added since boot —
    # which used to be learned by nobody, so a game added mid-session had no
    # cover and no box-back until the next restart.
    #
    # Costs one set lookup per game and returns immediately; the fetching is a
    # background worker's problem, and it defers itself while a game is running.
    try:
        prefetch.note_scan(system, [g["filename"] for g in games])
    except Exception:
        log.debug("prefetch: could not queue %s", system_id, exc_info=True)

    return games


class LaunchRequest(BaseModel):
    system_id: str
    rom_path: str = ""
    game_key: str = ""


@router.post("/games/launch")
async def launch_game(req: LaunchRequest):
    system = find(req.system_id)
    if not system:
        raise HTTPException(404, "System not found")
    return await launch_service.launch(system, req.system_id, req.rom_path, req.game_key)


class KillRequest(BaseModel):
    """Which run to end.

    Optional, and omitted by everything that predates the second slot: with no
    number this ends the session on the screen, exactly as it always has. A
    number is how a session bar closes the suspended one while something else
    is in front of it.
    """
    session: int | None = None


@router.post("/games/kill")
async def kill_game(req: KillRequest | None = None):
    await process_manager.kill(req.session if req else None)
    return {"ok": True}


@router.post("/games/background")
async def background_game():
    """Freeze the session on the screen and give the interface back.

    The process GROUP is suspended, not the process — an emulator is a tree,
    and a Flatpak one is five processes deep. See ProcessManager.background().
    """
    try:
        state = await process_manager.background()
    except SessionConflict as e:
        raise HTTPException(409, str(e)) from e
    return {"ok": True, **state}


class ResumeRequest(BaseModel):
    """Which suspended run to bring forward. Omitted means the most recent."""
    session: int | None = None


@router.post("/games/foreground")
async def foreground_game(req: ResumeRequest | None = None):
    """Resume a frozen session, putting whatever holds the screen behind it."""
    try:
        state = await process_manager.foreground(req.session if req else None)
    except SessionConflict as e:
        raise HTTPException(409, str(e)) from e
    return {"ok": True, **state}


@router.get("/games/session")
def get_session():
    """What the box is running, in one shape.

    The flat fields describe the session on the SCREEN, which is what this
    endpoint has always returned — so a front end that predates the second slot
    reads a box whose only session is suspended as "nothing in front of me".
    That is true, and it is the answer that leaves its pad unblocked.
    """
    return process_manager.session_state()
