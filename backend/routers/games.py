"""Game scanning, launching, and session management."""
import fnmatch
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import resolve_path
from ..services.process_manager import process_manager
from ..utils import TAG_RE
from .systems import list_all

router = APIRouter(tags=["games"])


def clean_name(filename: str) -> str:
    name = Path(filename).stem
    return TAG_RE.sub("", name).strip()


def matches_ext(filename: str, extensions: list[str]) -> bool:
    name = filename.lower()
    return any(fnmatch.fnmatch(name, p.lower()) for p in extensions)


def scan_roms(roms_path: Path, extensions: list[str]) -> list[dict]:
    if not roms_path.exists():
        return []
    files = []
    for f in sorted(roms_path.iterdir(), key=lambda x: x.name.lower()):
        if not f.is_file() or f.name.startswith(".") or "example" in f.name.lower():
            continue
        if extensions and not matches_ext(f.name, extensions):
            continue
        stat = f.stat()
        files.append({
            "filename": f.name,
            "display_name": clean_name(f.name),
            "path": str(f),
            "size": stat.st_size,
            "ext": f.suffix.lstrip(".").upper(),
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

    return scan_roms(roms_path, system.get("extensions", []))


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

    exec_path = system.get("path", "")
    exec_args = system.get("args", "")
    game_key = req.game_key or (Path(req.rom_path).name if req.rom_path else system["id"])

    await process_manager.launch(
        exec_path=exec_path,
        exec_args=exec_args,
        rom_path=req.rom_path,
        game_key=game_key,
        system_id=req.system_id,
    )
    return {"ok": True, "game_key": game_key}


@router.post("/games/kill")
async def kill_game():
    await process_manager.kill()
    return {"ok": True}


@router.get("/games/session")
def get_session():
    return process_manager.current_game or {}
