"""Debug helpers — manual triggers and state dumps for hard-to-reproduce
events (LAN-only box, no auth needed).

POST /api/debug/battery-toast?level=25  → broadcast a fake low-battery
    alert exactly like the watcher would: in the UI it pops the React
    toast, in-game it pops the native always-on-top HUD.
GET  /api/debug/battery → what the watcher actually sees: sysfs readings
    (level/charging per pad) and which thresholds have already fired.
"""
from fastapi import APIRouter

from .. import ws
from ..services import battery

router = APIRouter(tags=["debug"])


@router.post("/debug/battery-toast")
async def fake_battery_toast(level: int = 15):
    await ws.broadcast("gp:battery", {"name": "Debug controller", "level": level, "threshold": level})
    return {"ok": True, "level": level}


@router.get("/debug/battery")
def battery_state():
    return {
        "batteries": battery.read_batteries(),
        "thresholds": list(battery.THRESHOLDS),
        "fired": {name: sorted(t) for name, t in battery._fired.items()},
    }
