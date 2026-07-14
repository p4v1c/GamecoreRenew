"""Cover art — resolved by services.cover_pipeline (local icon → disc-ID
lookup → name scraping), cached under emu/covers/<system>/, served here.

?refresh=1 drops the cached cover (and the negative-cache marker) and
resolves again — useful after fixing a filename or adding internet."""
from fastapi import APIRouter, HTTPException

from fastapi.responses import FileResponse

from ..services.cover_pipeline import resolve
from .systems import list_all

router = APIRouter(tags=["covers"])

_MEDIA_TYPES = {".png": "image/png", ".jpg": "image/jpeg"}


@router.get("/covers/{system_id}/{filename:path}")
async def get_cover(system_id: str, filename: str, refresh: bool = False):
    system = next((s for s in list_all() if s["id"].lower() == system_id.lower()), None)
    if not system:
        raise HTTPException(404, "System not found")

    cover = await resolve(system, filename, refresh=refresh)
    if not cover:
        raise HTTPException(404, "Cover not found")

    return FileResponse(cover, media_type=_MEDIA_TYPES.get(cover.suffix, "image/png"))
