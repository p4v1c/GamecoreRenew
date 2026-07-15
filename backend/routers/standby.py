"""Standby state + configuration."""
from fastapi import APIRouter
from pydantic import BaseModel

from ..services import standby

router = APIRouter(tags=["standby"])


@router.get("/standby")
def get_standby():
    return {"state": standby.get_state(), **standby.load_config()}


class StandbyConfig(BaseModel):
    enabled: bool | None = None
    screensaver_mins: int | None = None
    sleep_mins: int | None = None


@router.post("/standby/config")
def set_config(cfg: StandbyConfig):
    saved = standby.save_config({k: v for k, v in cfg.model_dump().items() if v is not None})
    return {"ok": True, **saved}


@router.post("/standby/exit")
async def wake():
    await standby.exit_standby()
    return {"ok": True}
