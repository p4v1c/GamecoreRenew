"""Game metadata — resolved by services.metadata (TheGamesDB), disk-cached."""
from fastapi import APIRouter, HTTPException

from ..services import metadata
from ..services.systems import find

router = APIRouter(tags=["metadata"])


@router.get("/metadata/{system_id}/{filename:path}")
async def get_metadata(system_id: str, filename: str):
    system = find(system_id)
    if not system:
        raise HTTPException(404, "System not found")

    meta = await metadata.resolve(system, filename)
    if not meta:
        raise HTTPException(404, "No metadata")
    return meta
