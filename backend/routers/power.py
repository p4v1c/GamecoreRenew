"""Rest mode, and what the interface needs to know about a wake."""
from fastapi import APIRouter

from ..services import rest_mode, resume

router = APIRouter(prefix="/power", tags=["power"])


@router.post("/rest")
async def rest():
    """Close every game and app, then suspend. Answers after the wake, or on refusal."""
    return await rest_mode.enter()


@router.get("/state")
def state():
    """`resumes` grows by one per wake (once the TV is back); `sleeping` is true
    from the sleep announcement until then. A client reads both after reconnecting."""
    return {"resting": rest_mode.is_resting(), "resumes": resume.resume_count(),
            "sleeping": resume.is_sleeping()}
