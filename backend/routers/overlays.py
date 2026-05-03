"""Overlay bezel management — upload/serve per-system PNG."""
import shutil
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from ..config import ASSETS_DIR

router = APIRouter(tags=["overlays"])

OVERLAYS_DIR = ASSETS_DIR / "overlays"


def _overlay_path(system_id: str) -> Path:
    OVERLAYS_DIR.mkdir(parents=True, exist_ok=True)
    return OVERLAYS_DIR / f"{system_id}.png"


@router.get("/overlays/{system_id}")
async def get_overlay(system_id: str):
    p = _overlay_path(system_id)
    if not p.exists():
        raise HTTPException(404, "No overlay for this system")
    return FileResponse(p, media_type="image/png")


@router.post("/overlays/{system_id}")
async def upload_overlay(system_id: str, file: UploadFile = File(...)):
    if file.content_type not in ("image/png", "image/jpeg", "image/webp"):
        raise HTTPException(400, "Only PNG/JPEG/WebP images are accepted")
    p = _overlay_path(system_id)
    with p.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"ok": True, "path": str(p)}


@router.delete("/overlays/{system_id}")
async def delete_overlay(system_id: str):
    p = _overlay_path(system_id)
    if not p.exists():
        raise HTTPException(404, "No overlay to delete")
    p.unlink()
    return {"ok": True}
