"""HTTP surface of the display settings. Logic: services/display.py."""
from fastapi import APIRouter
from pydantic import BaseModel

from ...services import display

router = APIRouter(prefix="/settings/display", tags=["display"])


class ModeRequest(BaseModel):
    width: int
    height: int
    rate: float


class ScaleRequest(BaseModel):
    scale: float


@router.get("")
async def get_display():
    return await display.state()


@router.post("/mode")
async def set_mode(req: ModeRequest):
    return await display.set_mode(req.width, req.height, req.rate)


@router.get("/scale")
async def get_scale():
    return {"scale": display.ui_scale(), "choices": list(display.SCALES)}


@router.post("/scale")
async def set_scale(req: ScaleRequest):
    """The front end applies the zoom itself; nothing to revert."""
    return display.set_scale(req.scale)


@router.post("/confirm")
async def confirm():
    """Keep the mode on screen. Idempotent: nothing pending is not an error."""
    return await display.confirm()


@router.post("/revert")
async def revert_now():
    """Go back now instead of waiting out the timer."""
    return await display.revert_now()
