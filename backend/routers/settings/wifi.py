"""WiFi management via nmcli."""
import asyncio
import contextlib
import logging
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/settings/wifi", tags=["wifi"])
log = logging.getLogger(__name__)

# Long enough for a join that is merely slow — a 5 GHz association plus DHCP on
# a busy access point runs past 30s — and short enough that the screen is not
# left saying nothing. Whatever is still running when it expires is killed, so
# overshooting costs a wait rather than a process nobody owns; see `_run`.
CONNECT_TIMEOUT = 45.0

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


async def _run(*args: str, stdin: str | None = None,
               timeout: float | None = None) -> tuple[int, str, str]:
    """Spawn nmcli, wait for it, and kill it if `timeout` expires.

    The kill is the point of the timeout being here rather than around the
    call. `asyncio.wait_for` cancels the *await*, not the process: nmcli lives
    on holding the secret agent it registered with NetworkManager, which then
    keeps asking it for a password nobody is left to type. Two minutes later
    the desktop's own agent inherits that request and puts a Wi-Fi password
    dialog on screen — long after this box told the player the attempt had
    failed, and with nothing on it naming GameCore. It reads as the system
    demanding administrator rights out of nowhere.
    """
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.PIPE if stdin is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    payload = stdin.encode() if stdin is not None else None
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(payload), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        # Reap it too, so a timeout leaves neither an agent nor a zombie.
        with contextlib.suppress(Exception):
            await proc.wait()
        raise
    return proc.returncode or 0, stdout.decode(), stderr.decode()


async def _saved_profiles_for(ssid: str) -> list[str]:
    """The UUIDs of every saved connection whose Wi-Fi SSID is `ssid`.

    Matched on the SSID and never on the profile's name, because the names are
    exactly what cannot be trusted here: nmcli calls its second profile for one
    network `<SSID> 1`, and those near-misses are the ones this has to find.
    """
    _, out, _ = await _run("nmcli", "-t", "-f", "UUID,TYPE", "con", "show")
    uuids: list[str] = []
    for line in out.splitlines():
        # UUID first and colon-free, so the type is what follows the last one.
        parts = line.rsplit(":", 1)
        if len(parts) != 2 or parts[1].strip() != "802-11-wireless":
            continue
        uuid = parts[0].strip()
        if uuid:
            uuids.append(uuid)

    # nmcli only reports a profile's SSID one profile at a time, so this is a
    # spawn each. Run in one round rather than in series: a box with a dozen
    # saved networks would otherwise spend most of a second here, twice, on
    # every attempt to join anything.
    async def _ssid_of(uuid: str) -> str:
        _, info, _ = await _run(
            "nmcli", "-t", "-f", "802-11-wireless.ssid", "con", "show", uuid)
        for row in info.splitlines():
            key, sep, value = row.partition(":")
            if sep and key.strip() == "802-11-wireless.ssid":
                return _unescape(value.strip())
        return ""

    names = await asyncio.gather(*(_ssid_of(u) for u in uuids))
    return [u for u, name in zip(uuids, names) if name == ssid]


async def _forget(ssid: str) -> None:
    """Delete every saved profile for `ssid`. Only ever called with a password.

    Two separate things go wrong when one is left in place, and this box hit
    both in the same sitting.

    A saved profile holding the *old* key shadows the new one. `nmcli dev wifi
    connect` reuses the profile it finds, NetworkManager answers its own secret
    request with "secrets exist. No new secrets needed", and the password just
    typed is never consulted — the box retries the stale key until the
    supplicant gives up, thirteen times in one minute in the case that prompted
    this.

    And `nmcli dev wifi connect` will not overwrite a profile it did not
    create: it adds `<SSID> 1`, then `<SSID> 2`, one per attempt, each carrying
    a wrong secret of its own for the next attempt to trip over.

    Deleting is confined to the case where a password was supplied, i.e. where
    the player has just said what the key is and anything saved is out of date
    by definition. A reconnect with no password — an open network, or rejoining
    something the box already knows — keeps what it has.
    """
    for uuid in await _saved_profiles_for(ssid):
        code, _, err = await _run("nmcli", "con", "delete", "uuid", uuid)
        if code != 0:
            log.warning("wifi: could not delete stale profile %s: %s",
                        uuid, err.strip())


async def _fail(ssid: str, password: str) -> None:
    """Leave nothing behind after a password attempt that did not work.

    The profile nmcli just created carries the key that was refused. Kept, it
    shadows the next attempt exactly as the previous one shadowed this — and
    NetworkManager holds the activation open for two more minutes asking any
    agent it can find for a better key, which is what raises the desktop's own
    password dialog after GameCore has already given up and said so.

    A failure with no password to blame is left alone: there is nothing there
    the player supplied, and the profile may be one they want.
    """
    if password:
        await _forget(ssid)


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

    # A password means the player has just told the box what the key for this
    # network is, so whatever is saved for it can only get in the way. See
    # `_forget` for the two ways it does.
    if req.password:
        await _forget(req.ssid)

    args = ["nmcli", "dev", "wifi", "connect", req.ssid]
    stdin = None
    if req.password:
        # --ask makes nmcli prompt for the secret and read it from stdin. It
        # used to go in argv, where /proc/<pid>/cmdline exposed the Wi-Fi
        # password to every local user for as long as the connect took.
        args.insert(1, "--ask")
        stdin = req.password + "\n"
    try:
        code, out, err = await _run(*args, stdin=stdin, timeout=CONNECT_TIMEOUT)
    except asyncio.TimeoutError:
        # nmcli is dead by the time this runs, but the profile it made on the
        # way is not, and NetworkManager will go on retrying the key in it.
        await _fail(req.ssid, req.password)
        log.warning("wifi: connect to %r timed out after %ss",
                    req.ssid, CONNECT_TIMEOUT)
        return {"ok": False, "wrong_password": False, "error": "Connection timed out"}

    if code != 0:
        combined = (err + out).lower()
        wrong_pass = any(kw in combined for kw in (
            "secrets", "incorrect", "wrong", "authentication",
            "802-11-wireless-security.psk", "invalid password",
        ))
        error = ("Wrong password" if wrong_pass
                 else (err.strip() or out.strip() or "Connection failed"))
        await _fail(req.ssid, req.password)
        # This endpoint answers 200 with `ok: false` — the shape the default UI
        # and two shipped themes already parse — so a failed join is invisible
        # in the journal unless it is written there. Five in a row read as five
        # `200 OK` lines while the player was getting nowhere.
        log.warning("wifi: connect to %r failed: %s", req.ssid, error)
        return {"ok": False, "wrong_password": wrong_pass, "error": error}
    return {"ok": True, "wrong_password": False}


@router.delete("/connect")
async def disconnect_wifi():
    iface = await _wifi_iface()
    code, _, err = await _run("nmcli", "dev", "disconnect", iface)
    return {"ok": code == 0, "error": err.strip() if code != 0 else ""}
