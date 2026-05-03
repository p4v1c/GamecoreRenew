"""Cover art — scrape from libretro CDN, cache locally, serve."""
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from ..services.scraper import fetch_cover
from ..config import COVERS_DIR

router = APIRouter(tags=["covers"])


@router.get("/covers/{system_id}/{filename:path}")
async def get_cover(system_id: str, filename: str):
    base = Path(filename).stem
    cached = COVERS_DIR / f"{base}.png"

    if not cached.exists():
        result = await fetch_cover(filename, system_id)
        if not result:
            raise HTTPException(404, "Cover not found")
        cached = Path(result)

    return FileResponse(cached, media_type="image/png")
