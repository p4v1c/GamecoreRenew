"""Bluetooth management via bluetoothctl (5.x direct subcommand mode)."""
import asyncio
import re
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/settings/bluetooth", tags=["bluetooth"])

_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[mK]|\r')


async def _run(*args: str) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await proc.communicate()
    out = _ANSI_RE.sub("", stdout.decode())
    return proc.returncode or 0, out


@router.get("/devices")
async def list_devices():
    _, out = await _run("bluetoothctl", "--", "devices", "Paired")
    devices = []
    for line in out.splitlines():
        parts = line.strip().split(" ", 2)
        if len(parts) < 3 or parts[0] != "Device":
            continue
        mac, name = parts[1], parts[2]
        _, info = await _run("bluetoothctl", "--", "info", mac)
        connected = "Connected: yes" in info
        devices.append({"mac": mac, "name": name, "connected": connected})
    return devices


@router.post("/scan")
async def start_scan():
    """Scan for 8 seconds in background — returns immediately."""
    async def _do_scan() -> None:
        proc = await asyncio.create_subprocess_exec(
            "bluetoothctl", "--", "scan", "on",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.sleep(8)
        try:
            proc.terminate()
            await asyncio.wait_for(proc.wait(), timeout=2.0)
        except (asyncio.TimeoutError, ProcessLookupError):
            try:
                proc.kill()
            except ProcessLookupError:
                pass

    asyncio.create_task(_do_scan())
    return {"ok": True}


class DeviceRequest(BaseModel):
    mac: str


@router.post("/connect")
async def connect_device(req: DeviceRequest):
    # Trust first so repeated pairing prompts don't block
    await _run("bluetoothctl", "--", "trust", req.mac)
    code, out = await _run("bluetoothctl", "--", "connect", req.mac)
    ok = "Connection successful" in out
    if ok:
        return {"ok": True, "message": "Connected"}
    # Extract the error reason after the colon
    match = re.search(r"Failed to connect:\s*(.+)", out)
    msg = match.group(1).strip() if match else (out.strip().splitlines()[-1] if out.strip() else "Failed")
    return {"ok": False, "message": msg}


@router.post("/disconnect")
async def disconnect_device(req: DeviceRequest):
    _, out = await _run("bluetoothctl", "--", "disconnect", req.mac)
    ok = "Successful disconnected" in out or "not connected" in out.lower()
    return {"ok": ok}


@router.delete("/devices/{mac}")
async def remove_device(mac: str):
    code, _ = await _run("bluetoothctl", "--", "remove", mac)
    return {"ok": code == 0}
