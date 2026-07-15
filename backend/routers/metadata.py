"""Game metadata — resolved by services.metadata (TheGamesDB), disk-cached."""
from fastapi import APIRouter, HTTPException

from ..services import metadata
from .systems import list_all

router = APIRouter(tags=["metadata"])


@router.get("/metadata/{system_id}/{filename:path}")
async def get_metadata(system_id: str, filename: str):
    system = next((s for s in list_all() if s["id"].lower() == system_id.lower()), None)
    if not system:
        raise HTTPException(404, "System not found")

    meta = await metadata.resolve(system, filename)
    if not meta:
        raise HTTPException(404, "No metadata")
    return meta
