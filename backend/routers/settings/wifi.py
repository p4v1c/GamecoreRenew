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


async def _run(*args: str, stdin: str | None = None) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.PIPE if stdin is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate(stdin.encode() if stdin is not None else None)
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


def _unescape(value: str) -> str:
    r"""nmcli -t escapes ':' inside a value as '\:'.

    A MAC address is the case that matters: `GENERAL.HWADDR` arrives as
    `DC\:A6\:32\:11\:8F\:04`, and handing that to a UI shows the backslashes to
    the player.
    """
    return value.replace("\\:", ":")


def _parse_dev_show(text: str) -> dict:
    """Gateway, DNS servers and MAC out of `nmcli -t ... dev show <iface>`.

    Split on the FIRST colon, never the last: the key is fixed and the value is
    not. `IP4.DNS[1]:9.9.9.9` and a MAC full of colons both parse correctly this
    way and neither does the other way round.

    Every field is optional. A box on DHCP with no DNS advertised, or a driver
    that does not report a hardware address, answers with what it has — the
    screen omits the rows it gets nothing for rather than printing a blank one,
    which would read as "this network has no gateway".
    """
    gateway, dns, mac = "", [], ""
    for line in text.splitlines():
        key, sep, value = line.partition(":")
        if not sep:
            continue
        value = _unescape(value.strip())
        # nmcli prints the key with an empty value for anything it cannot
        # answer, so emptiness is the absence test, not a missing line.
        if not value or value == "--":
            continue
        if key == "IP4.GATEWAY":
            gateway = value
        elif key.startswith("IP4.DNS"):
            dns.append(value)
        elif key == "GENERAL.HWADDR":
            mac = value
    return {"gateway": gateway, "dns": dns, "mac": mac}


def _band(freq: str) -> str:
    """`5180 MHz` → `5 GHz`. Empty when the frequency is not a number.

    Ranges rather than an exact table: a channel map would need updating for
    every regulatory domain, and the only thing being answered here is which
    of the three radios the player is on.
    """
    digits = "".join(ch for ch in freq if ch.isdigit())
    if not digits:
        return ""
    mhz = int(digits)
    if mhz >= 5925:
        return "6 GHz"
    if mhz >= 4900:
        return "5 GHz"
    if mhz >= 2400:
        return "2.4 GHz"
    return ""


def _parse_wifi_details(text: str) -> list[dict]:
    """`SSID,SECURITY,CHAN,FREQ,RATE` per network, from `nmcli -t dev wifi`.

    `rsplit` on the four fixed trailing fields for the same reason
    `scan_networks` does it: the SSID comes first and may itself contain a
    colon, and it is the one field nobody here controls.

    Kept apart from `/networks` deliberately. That endpoint's shape is what the
    default UI and two shipped themes already read; widening its field list
    would change how every one of them parses a scan, to add detail only one
    screen wants.
    """
    out: dict[str, dict] = {}
    for line in text.splitlines():
        parts = line.rsplit(":", 4)
        if len(parts) < 5:
            continue
        ssid = _unescape(parts[0]).strip()
        if not ssid:
            continue
        security = parts[1].strip()
        rate = parts[4].strip().replace("Mbit/s", "Mb/s")
        try:
            channel = int(parts[2].strip())
        except ValueError:
            channel = 0
        # First entry wins: a scan lists one row per BSSID, so a mesh with three
        # access points on one SSID appears three times. The strongest is first
        # in nmcli's own ordering, which is the one the box would associate to.
        out.setdefault(ssid, {
            "ssid": ssid,
            "security": "Open" if security in ("", "--") else security,
            "channel": channel,
            "band": _band(parts[3]),
            "rate": rate,
        })
    return list(out.values())


@router.get("/details")
async def wifi_details():
    """The radio detail behind each SSID: security, channel, band, link rate.

    Additive on purpose — `/networks` keeps the exact shape it has always had.
    A screen that wants to say "5 GHz · channel 44" asks for this as well; one
    that does not is unaffected, and nothing that reads the scan today has to
    change.
    """
    _, out, _ = await _run(
        "nmcli", "-t", "-f", "SSID,SECURITY,CHAN,FREQ,RATE", "dev", "wifi"
    )
    return _parse_wifi_details(out)


async def _iface_ip(iface: str) -> str:
    if not iface:
        return ""
    _, info, _ = await _run("nmcli", "-t", "-f", "IP4.ADDRESS", "dev", "show", iface)
    for line in info.splitlines():
        if line.startswith("IP4.ADDRESS"):
            return line.split(":", 1)[-1].split("/")[0].strip()
    return ""


async def _link_info(iface: str) -> dict:
    """Gateway, DNS and MAC for the interface currently carrying the box."""
    if not iface:
        return {"gateway": "", "dns": [], "mac": ""}
    _, out, _ = await _run(
        "nmcli", "-t", "-f", "IP4.GATEWAY,IP4.DNS,GENERAL.HWADDR", "dev", "show", iface
    )
    return _parse_dev_show(out)


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
        # NAME comes first and may contain ':' (escaped '\:' by nmcli -t) —
        # split from the right on the 3 fixed fields, like scan_networks does.
        parts = line.rsplit(":", 3)
        if len(parts) >= 3 and parts[1] in ("802-11-wireless",) and parts[2] == "activated":
            ssid = parts[0].replace("\\:", ":")
            iface = parts[3] if len(parts) > 3 else ""
            return {"connected": True, "ssid": ssid, "ip": await _iface_ip(iface),
                    "iface": iface, "ethernet": ethernet,
                    **await _link_info(iface)}
    # The same keys either way. A screen that reads `body.gateway` must not
    # have to know whether the box happened to be connected when it asked —
    # that is how a disconnected box renders `undefined` into a table row.
    return {"connected": False, "ssid": "", "ip": "", "iface": "", "ethernet": ethernet,
            "gateway": "", "dns": [], "mac": ""}


class ConnectRequest(BaseModel):
    ssid: str
    password: str = ""


@router.post("/connect")
async def connect_wifi(req: ConnectRequest):
    # The SSID is positional and nothing marks the end of the options, so an
    # SSID starting with '-' would be read as one by nmcli. Refused rather than
    # escaped: such a network is vanishingly rare, and guessing at nmcli's
    # option parsing is not something to be clever about.
    if req.ssid.startswith("-"):
        return {"ok": False, "wrong_password": False,
                "error": "SSIDs starting with '-' are not supported"}

    args = ["nmcli", "dev", "wifi", "connect", req.ssid]
    stdin = None
    if req.password:
        # --ask makes nmcli prompt for the secret and read it from stdin. It
        # used to go in argv, where /proc/<pid>/cmdline exposed the Wi-Fi
        # password to every local user for as long as the connect took.
        args.insert(1, "--ask")
        stdin = req.password + "\n"
    try:
        code, out, err = await asyncio.wait_for(_run(*args, stdin=stdin), timeout=CONNECT_TIMEOUT)
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
