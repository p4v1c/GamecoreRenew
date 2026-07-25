"""Theme registry — list what is installed, remember what is selected.

The theme's own files are served by the /themes static mount in main.py; the
browser imports the module from there. Nothing in the backend runs theme code.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import ws
from ..services import themes

router = APIRouter(tags=["themes"])


@router.get("/themes")
def list_themes():
    """Installed themes plus the current selection and the SDK version we speak."""
    return {
        "sdk_version": themes.SDK_VERSION,
        "active": themes.get_active(),
        "themes": themes.list_themes(),
    }


class ActiveBody(BaseModel):
    # null selects the built-in default theme.
    id: str | None = None


@router.post("/themes/active")
async def set_active(body: ActiveBody):
    try:
        active = themes.set_active(body.id)
    except ValueError:
        raise HTTPException(400, "invalid theme id")
    except LookupError:
        raise HTTPException(404, "no such theme")
    # Lets a second screen (or the settings page on another client) follow along.
    await ws.broadcast("theme:changed", {"active": active})
    return {"ok": True, "active": active}
