"""Who plays on this box: list, create, edit, delete profiles; read and set the active one."""
from fastapi import APIRouter
from pydantic import BaseModel, Field

from .. import ws
from ..services import profile_saves, profiles
from ..services.catalog import load_catalog

router = APIRouter(tags=["profiles"])

# Name caps are generous on purpose: the service trims, then enforces NAME_MAX
# with a sentence the UI can show.
class NewProfile(BaseModel):
    name: str = Field(max_length=200)
    color: str | None = None
    avatar: str | None = None


class ProfileEdit(BaseModel):
    name: str | None = Field(None, max_length=200)
    color: str | None = None
    avatar: str | None = None


class ActiveProfile(BaseModel):
    id: str = Field(max_length=64)


async def _changed() -> None:
    # Player 1 is shown by the active profile's name: every write may change it.
    await ws.broadcast("profiles:changed", {"active": profiles.active()})


@router.get("/profiles")
def list_profiles():
    return {**profiles.list_profiles(),
            "separate_saves": profile_saves.separate_systems(load_catalog())}


@router.post("/profiles")
async def create_profile(body: NewProfile):
    made = profiles.create(body.name, body.color, body.avatar)
    await _changed()
    return made


@router.get("/profiles/active")
def get_active_profile():
    return profiles.active()


@router.put("/profiles/active")
async def set_active_profile(body: ActiveProfile):
    profile = profiles.set_active(body.id)
    await _changed()
    return profile


@router.patch("/profiles/{profile_id}")
async def update_profile(profile_id: str, body: ProfileEdit):
    # Only the fields the caller sent: `avatar: null` clears, absent keeps.
    profile = profiles.update(profile_id, body.model_dump(exclude_unset=True))
    await _changed()
    return profile


@router.delete("/profiles/{profile_id}")
async def delete_profile(profile_id: str):
    out = profiles.delete(profile_id)
    await _changed()
    return out
