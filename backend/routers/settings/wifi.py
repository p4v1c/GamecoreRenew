"""WiFi management via nmcli."""
import asyncio
import logging
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/settings/wifi", tags=["wifi"])
log = logging.getLogger(__name__)

CONNECT_TIMEOUT = 30.0

# Keep references to fire-and-forget background tasks so they aren't GC'd
# mid-flight and so any exception is logged instead of swallowed.
_bg_tasks: set[asyncio.Task] = set()


def _spawn_bg(coro, label: str) -> None:
    task = asyncio.create_task(coro)
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)

    def _log_err(t: asyncio.Task) -> None:
        if t.cancelled():
            return
        exc = t.exception()
        if exc:
            log.warning("bg task %s failed: %s", label, exc)
    task.add_done_callback(_log_err)


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
    async def _rescan() -> None:
        proc = await asyncio.create_subprocess_exec(
            "nmcli", "dev", "wifi", "rescan",
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()

    _spawn_bg(_rescan(), "wifi-rescan")

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


async def _iface_ip(iface: str) -> str:
    if not iface:
        return ""
    _, info, _ = await _run("nmcli", "-t", "-f", "IP4.ADDRESS", "dev", "show", iface)
    for line in info.splitlines():
        if line.startswith("IP4.ADDRESS"):
            return line.split(":", 1)[-1].split("/")[0].strip()
    return ""


async def _ethernet_status() -> dict:
    """Whether a wired (ethernet) connection is active — lets the UI skip the
    Wi-Fi list when the box is plugged in."""
    _, out, _ = await _run("nmcli", "-t", "-f", "TYPE,STATE,DEVICE", "con", "show", "--active")
    for line in out.splitlines():
        parts = line.split(":")
        if len(parts) >= 2 and parts[0] == "802-3-ethernet" and parts[1] == "activated":
            iface = parts[2] if len(parts) > 2 else ""
            return {"connected": True, "iface": iface, "ip": await _iface_ip(iface)}
    return {"connected": False, "iface": "", "ip": ""}


@router.get("/status")
async def wifi_status():
    """Return currently connected SSID + IP, plus wired (ethernet) status."""
    ethernet = await _ethernet_status()
    _, out, _ = await _run(
        "nmcli", "-t", "-f", "NAME,TYPE,STATE,DEVICE", "con", "show", "--active"
    )
    for line in out.splitlines():
        parts = line.split(":")
        if len(parts) >= 3 and parts[1] in ("802-11-wireless",) and parts[2] == "activated":
            ssid = parts[0]
            iface = parts[3] if len(parts) > 3 else ""
            return {"connected": True, "ssid": ssid, "ip": await _iface_ip(iface),
                    "iface": iface, "ethernet": ethernet}
    return {"connected": False, "ssid": "", "ip": "", "iface": "", "ethernet": ethernet}


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
