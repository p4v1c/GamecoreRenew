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
async def set_config(cfg: StandbyConfig):
    saved = standby.save_config({k: v for k, v in cfg.model_dump().items() if v is not None})
    # Switching standby OFF has to be able to end the standby it is switching
    # off. The watcher's first line is "not enabled → nothing to do", so nothing
    # ever undid what the last tick had done: the box answered "standby
    # disabled" and stayed asleep, screen and all. Somebody reaching for that
    # switch from a phone is doing it precisely because the television is dark.
    #
    # Only OFF. Turning it on is not a reason to light the screen, and waking on
    # any config write would mean the box could never settle while somebody was
    # adjusting the timings.
    if cfg.enabled is False:
        await standby.exit_standby()
    return {"ok": True, **saved}


@router.post("/standby/exit")
async def wake():
    await standby.exit_standby()
    return {"ok": True}
