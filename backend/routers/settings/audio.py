"""Audio management via wpctl (PipeWire/WirePlumber)."""
import asyncio
import os
import re
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/settings/audio", tags=["audio"])


def _session_env() -> dict:
    env = os.environ.copy()
    uid = os.getuid()
    if not env.get("XDG_RUNTIME_DIR"):
        env["XDG_RUNTIME_DIR"] = f"/run/user/{uid}"
    if not env.get("DBUS_SESSION_BUS_ADDRESS"):
        env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path=/run/user/{uid}/bus"
    return env


async def _run(*args: str) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=_session_env(),
    )
    stdout, _ = await proc.communicate()
    return proc.returncode or 0, stdout.decode().strip()


@router.get("")
async def get_audio():
    # "Volume: 0.75" or "Volume: 0.75 [MUTED]"
    _, out = await _run("wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@")
    m = re.search(r"Volume:\s*([\d.]+)", out)
    vol_float = float(m.group(1)) if m else 1.0
    muted = "MUTED" in out
    return {"volume": round(min(100, max(0, vol_float * 100))), "muted": muted}


@router.get("/sinks")
async def list_sinks():
    _, out = await _run("wpctl", "status")
    sinks = []
    in_sinks = False
    for line in out.splitlines():
        if re.search(r"(├─|└─)\s+Sinks:", line):
            in_sinks = True
            continue
        if in_sinks and re.search(r"(├─|└─)\s+Sink endpoints:", line):
            break
        if not in_sinks:
            continue
        # Lines look like:  │  *   49. Built-in Audio Analog Stereo  [vol: 0.50]
        m = re.search(r"([*]?)\s*(\d+)\.\s+(.+?)\s+\[vol:", line)
        if not m:
            continue
        is_default = bool(m.group(1))
        node_id = m.group(2)
        name = m.group(3).strip()
        sinks.append({"id": node_id, "name": name, "default": is_default})
    return sinks


class VolumeRequest(BaseModel):
    volume: int


@router.post("/volume")
async def set_volume(req: VolumeRequest):
    vol = max(0, min(100, req.volume))
    code, out = await _run("wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{vol}%")
    if code != 0:
        return {"ok": False, "error": out or "wpctl failed"}
    return {"ok": True, "volume": vol}


class SinkRequest(BaseModel):
    sink: str  # node ID (numeric string)


@router.post("/sink")
async def set_sink(req: SinkRequest):
    code, out = await _run("wpctl", "set-default", req.sink)
    if code != 0:
        return {"ok": False, "error": out}
    return {"ok": True}
