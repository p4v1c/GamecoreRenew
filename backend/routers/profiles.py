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


async def _changed(switched: bool = False) -> None:
    # Player 1 is shown by the active profile's name: every write may change it.
    await ws.broadcast("profiles:changed", {"active": profiles.active()})
    if switched:
        # Playtime and recents are the active profile's: what reloads them
        # after the playtime repair reloads them here too.
        await ws.broadcast("playtime:rekeyed", {"moved": 0})


@router.get("/profiles")
def list_profiles():
    packs = load_catalog()
    return {**profiles.list_profiles(),
            "separate_saves": profile_saves.separate_systems(packs),
            "shared_saves": profile_saves.shared_systems(packs)}


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
    before = profiles.active()["id"]
    profile = profiles.set_active(body.id)
    await _changed(switched=profile["id"] != before)
    return profile


@router.patch("/profiles/{profile_id}")
async def update_profile(profile_id: str, body: ProfileEdit):
    # Only the fields the caller sent: `avatar: null` clears, absent keeps.
    profile = profiles.update(profile_id, body.model_dump(exclude_unset=True))
    await _changed()
    return profile


@router.delete("/profiles/{profile_id}")
async def delete_profile(profile_id: str):
    before = profiles.active()["id"]
    out = profiles.delete(profile_id)
    await _changed(switched=out["active"] != before)
    return out
