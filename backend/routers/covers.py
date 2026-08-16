"""Cover art — resolved by services.cover_pipeline (local icon → disc-ID
lookup → name scraping), cached under emu/covers/<system>/, served here.

?refresh=1 drops the cached cover (and the negative-cache marker) and
resolves again — useful after fixing a filename or adding internet."""
from fastapi import APIRouter, HTTPException, Request

from ..services import http_cache
from ..services.cover_pipeline import resolve
from .systems import list_all

router = APIRouter(tags=["covers"])

_MEDIA_TYPES = {".png": "image/png", ".jpg": "image/jpeg",
                ".webp": "image/webp"}


@router.get("/covers/{system_id}/{filename:path}")
async def get_cover(request: Request, system_id: str, filename: str,
                    refresh: bool = False):
    system = next((s for s in list_all() if s["id"].lower() == system_id.lower()), None)
    if not system:
        raise HTTPException(404, "System not found")

    cover = await resolve(system, filename, refresh=refresh)
    if not cover:
        raise HTTPException(404, "Cover not found")

    # Kept by the browser and revalidated, never re-transferred blind: the URL
    # of a cover is the *game's* name and outlives any particular picture, so
    # `?refresh=1` and a re-scrape have to be able to show through. The 304 is
    # what makes that cheap — see services/http_cache.
    return http_cache.conditional_file_response(
        request, cover,
        media_type=_MEDIA_TYPES.get(cover.suffix, "image/png"),
    )
