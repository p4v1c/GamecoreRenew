"""WiFi management via nmcli."""
import asyncio
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/settings/wifi", tags=["wifi"])

CONNECT_TIMEOUT = 30.0


async def _run(*args: str) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode or 0, stdout.decode(), stderr.decode()


async def _wifi_iface() -> str:
    """Return the active WiFi interface name (e.g. wlp0s20f3)."""
    _, out, _ = await _run("nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "dev")
    for line in out.splitlines():
        parts = line.split(":")
        if len(parts) >= 3 and parts[1] in ("wifi", "wireless") and parts[2] == "connected":
            return parts[0]
    # Fallback: any wifi device
    for line in out.splitlines():
        parts = line.split(":")
        if len(parts) >= 2 and parts[1] in ("wifi", "wireless"):
            return parts[0]
    return "wlan0"


@router.get("/networks")
async def scan_networks():
    # Rescan first (non-blocking, best-effort)
    asyncio.create_task(asyncio.create_subprocess_exec(
        "nmcli", "dev", "wifi", "rescan",
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
    ))

    _, out, _ = await _run(
        "nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY,ACTIVE", "dev", "wifi"
    )

    # Use rsplit(max 3) so SSIDs containing ':' are handled correctly.
    # Priority: if an SSID appears multiple times, prefer the connected entry,
    # then the strongest signal.
    best: dict[str, dict] = {}
    for line in out.splitlines():
        parts = line.rsplit(":", 3)
        if len(parts) < 4:
            continue
        ssid = parts[0].replace("\\:", ":").strip()
        if not ssid:
            continue
        try:
            signal = int(parts[1])
        except ValueError:
            signal = 0
        security = parts[2].strip()
        connected = parts[3].strip() == "yes"

        existing = best.get(ssid)
        if existing is None:
            best[ssid] = {"ssid": ssid, "signal": signal,
                          "secured": bool(security and security != "--"),
                          "connected": connected}
        else:
            # Always prefer the connected entry; otherwise keep strongest signal
            if connected and not existing["connected"]:
                best[ssid] = {"ssid": ssid, "signal": signal,
                              "secured": bool(security and security != "--"),
                              "connected": True}
            elif not connected and not existing["connected"] and signal > existing["signal"]:
                existing["signal"] = signal

    networks = list(best.values())
    networks.sort(key=lambda n: (not n["connected"], -n["signal"]))
    return networks


@router.get("/status")
async def wifi_status():
    """Return currently connected SSID + IP, or null."""
    _, out, _ = await _run(
        "nmcli", "-t", "-f", "NAME,TYPE,STATE,DEVICE", "con", "show", "--active"
    )
    for line in out.splitlines():
        parts = line.split(":")
        if len(parts) >= 3 and parts[1] in ("802-11-wireless",) and parts[2] == "activated":
            ssid = parts[0]
            iface = parts[3] if len(parts) > 3 else ""
            # Get IP
            ip = ""
            if iface:
                _, info, _ = await _run("nmcli", "-t", "-f", "IP4.ADDRESS", "dev", "show", iface)
                for line in info.splitlines():
                    if line.startswith("IP4.ADDRESS"):
                        ip = line.split(":", 1)[-1].split("/")[0].strip()
                        break
            return {"connected": True, "ssid": ssid, "ip": ip, "iface": iface}
    return {"connected": False, "ssid": "", "ip": "", "iface": ""}


class ConnectRequest(BaseModel):
    ssid: str
    password: str = ""


@router.post("/connect")
async def connect_wifi(req: ConnectRequest):
    args = ["nmcli", "dev", "wifi", "connect", req.ssid]
    if req.password:
        args += ["password", req.password]
    try:
        code, out, err = await asyncio.wait_for(_run(*args), timeout=CONNECT_TIMEOUT)
    except asyncio.TimeoutError:
        return {"ok": False, "wrong_password": False, "error": "Connection timed out"}

    if code != 0:
        combined = (err + out).lower()
        wrong_pass = any(kw in combined for kw in (
            "secrets", "incorrect", "wrong", "authentication",
            "802-11-wireless-security.psk", "invalid password",
        ))
        return {
            "ok": False,
            "wrong_password": wrong_pass,
            "error": "Wrong password" if wrong_pass else (err.strip() or out.strip() or "Connection failed"),
        }
    return {"ok": True, "wrong_password": False}


@router.delete("/connect")
async def disconnect_wifi():
    iface = await _wifi_iface()
    code, _, err = await _run("nmcli", "dev", "disconnect", iface)
    return {"ok": code == 0, "error": err.strip() if code != 0 else ""}
