"""Who plays on this box: list, create, edit, delete profiles; read and set the active one."""
from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..services import profiles

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


@router.get("/profiles")
def list_profiles():
    return profiles.list_profiles()


@router.post("/profiles")
def create_profile(body: NewProfile):
    return profiles.create(body.name, body.color, body.avatar)


@router.get("/profiles/active")
def get_active_profile():
    return profiles.active()


@router.put("/profiles/active")
def set_active_profile(body: ActiveProfile):
    return profiles.set_active(body.id)


@router.patch("/profiles/{profile_id}")
def update_profile(profile_id: str, body: ProfileEdit):
    # Only the fields the caller sent: `avatar: null` clears, absent keeps.
    return profiles.update(profile_id, body.model_dump(exclude_unset=True))


@router.delete("/profiles/{profile_id}")
def delete_profile(profile_id: str):
    return profiles.delete(profile_id)
