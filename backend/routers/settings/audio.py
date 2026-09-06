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


# `wpctl status` is a tree, and these two are how one reads which part of it a
# line belongs to: a bare word in the first column opens a family (Audio,
# Video), a branch opens a section inside it (Devices, Sinks, Sources, …).
_FAMILY = re.compile(r"^([A-Za-z][A-Za-z ]*?)\s*$")
_SECTION = re.compile(r"(?:├─|└─)\s+([A-Za-z][A-Za-z ]*?):")


@router.get("/sinks")
async def list_sinks():
    """The audio outputs, and only those.

    The section used to be left on one line and one line only — `Sink
    endpoints:` — which is a heading this box's WirePlumber does not print.
    Measured here on PipeWire 1.6.7: `Sinks:` is followed straight by
    `Sources:`, so the loop stayed inside the sinks for the rest of the output
    and the MICROPHONE was offered as a place to send sound to. Video's own
    `Sinks:` was on the far side of the same gate.

    So the tree is read as a tree: any heading ends the previous section, and
    only the `Sinks` of the `Audio` family count. Nothing here depends on which
    optional headings a given WirePlumber emits — the audit that found this
    filed it as conditional for that reason, and the condition holds on the
    box.
    """
    _, out = await _run("wpctl", "status")
    sinks = []
    family = ""
    in_sinks = False
    for line in out.splitlines():
        head = _FAMILY.match(line)
        if head:
            family, in_sinks = head.group(1), False
            continue
        section = _SECTION.search(line)
        if section:
            in_sinks = family == "Audio" and section.group(1) == "Sinks"
            continue
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
