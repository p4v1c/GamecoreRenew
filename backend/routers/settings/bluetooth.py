"""Bluetooth management via bluetoothctl (5.x direct subcommand mode).

── Pairing, and why it works without a D-Bus binding ──────────────────────────
This screen used to be a *reconnection* screen wearing a scan button. `/devices`
asked bluetoothctl for `devices Paired`, so a controller in pairing mode could
never appear in it; `/scan` ran `scan on` for eight seconds with its output sent
to DEVNULL, so whatever it discovered was thrown away; and there was no `pair`
anywhere. A new pad had to be paired from a terminal before the box could see it.

Pairing needs an *agent* — the object BlueZ calls back to confirm a request.
`--agent <capability>` does not register one in direct subcommand mode
(bluetoothctl 5.87, measured): bluetoothd refused a mouse's passkey
confirmation and a DualSense's authorization with "No agent available", and
only the desktop session's KDE agent could pair them. So pairing runs one short
*interactive* bluetoothctl (`_pair_with_agent`), where `--agent` does
register: default-agent, pair, answer its prompts, quit. Everything else stays a direct subcommand.

Measured on the reference box before writing any of this, because the D-Bus
policy shipped by BlueZ reads as though it should forbid it:

    <policy user="root">      <allow send_interface="org.bluez.Agent1"/>
    <policy context="default"> <allow send_destination="org.bluez"/>

Any user may CALL BlueZ; only root is listed for the Agent1 interface. In
practice `bluetoothctl --timeout 4 -- agent NoInputNoOutput` run as the backend's
own unprivileged user answers "Agent registered". The rule governs messages a
client sends bearing that interface, not the replies an agent makes.

`NoInputNoOutput` is the right capability for a living-room box and not merely
the convenient one: it means "just works" pairing, which is exactly what pads and
headsets implement. A confirmation prompt is answered yes: the player picked
this device on screen. A device that insists on a typed passkey cannot be
served — that is reported as its own failure rather than a silent hang.

Nothing is ever paired automatically. The scan lists what is in range and the
player picks: a box that paired with whatever was discoverable would happily
adopt the neighbours' headphones.
"""
import asyncio
import logging
import os
import re
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...services.logs import mask_mac

router = APIRouter(prefix="/settings/bluetooth", tags=["bluetooth"])
log = logging.getLogger(__name__)

_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[mK]|\r')
_MAC_RE = re.compile(r'^(?:[0-9A-F]{2}:){5}[0-9A-F]{2}$', re.I)
_DEVICE_RE = re.compile(r'^Device\s+((?:[0-9A-F]{2}:){5}[0-9A-F]{2})\s+(.+)$', re.I)

# How long the adapter looks around. Long enough for a pad that has just been
# put into pairing mode to advertise, short enough that the screen is not dead
# while it runs — the UI says how long it will be.
SCAN_SECS = 10

# Pairing is a negotiation with a device that may be asleep, out of range or
# waiting for its own button. Bounded so a failure is an error message rather
# than a page that never comes back.
PAIR_SECS = 25

# "Just works" pairing: the box has no keypad to type a passkey into, and pads
# and headsets implement exactly this. A device that insists on one is reported
# as such rather than left hanging.
AGENT = "NoInputNoOutput"
# bluetoothctl's agent asks "(yes/no):" without a newline, so output is read in
# chunks, not lines; the session ends at the first of these.
_CONFIRM = "(yes/no)"
_PAIR_DONE = re.compile(
    r"pairing successful|failed to pair|already exists|already paired|not available", re.I)


def _session_env() -> dict:
    env = os.environ.copy()
    uid = os.getuid()
    if not env.get("XDG_RUNTIME_DIR"):
        env["XDG_RUNTIME_DIR"] = f"/run/user/{uid}"
    if not env.get("DBUS_SESSION_BUS_ADDRESS"):
        env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path=/run/user/{uid}/bus"
    return env


async def _run(*args: str, timeout: float = 30.0) -> tuple[int, str]:
    """Run bluetoothctl and return (code, clean output).

    Every call goes through here, environment included. The scan used to build
    its subprocess by hand and skip `_session_env()` — either that environment
    matters, in which case the scan was the fragile one, or it does not, in
    which case every other call carried it for nothing. Both cannot be true.
    """
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=_session_env(),
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        # A bluetoothctl that will not exit must not hold the request open.
        for kill in (proc.terminate, proc.kill):
            try:
                kill()
            except ProcessLookupError:
                break
            try:
                await asyncio.wait_for(proc.wait(), timeout=2.0)
                break
            except asyncio.TimeoutError:
                continue
        return 1, ""
    out = _ANSI_RE.sub("", stdout.decode(errors="replace"))
    return proc.returncode or 0, out


async def _pair_with_agent(mac: str, timeout: float = PAIR_SECS) -> str:
    """Pair `mac` from one interactive bluetoothctl holding the default agent.
    Returns everything it printed (ANSI stripped)."""
    proc = await asyncio.create_subprocess_exec(
        # Interactive mode registers its agent at start-up, with --agent's
        # capability; a later `agent X` only answers "already registered".
        "bluetoothctl", f"--agent={AGENT}", stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, env=_session_env())
    proc.stdin.write(f"default-agent\npair {mac}\n".encode())
    out, answered = "", 0
    deadline = asyncio.get_running_loop().time() + timeout
    try:
        while not _PAIR_DONE.search(out):
            left = deadline - asyncio.get_running_loop().time()
            chunk = await asyncio.wait_for(proc.stdout.read(4096), timeout=max(left, 0.01))
            if not chunk:
                break
            out += _ANSI_RE.sub("", chunk.decode(errors="replace"))
            while answered < out.count(_CONFIRM):       # a prompt may span two chunks
                proc.stdin.write(b"yes\n")
                answered += 1
    except asyncio.TimeoutError:
        pass
    finally:
        try:
            proc.stdin.write(b"quit\n")
            await asyncio.wait_for(proc.wait(), timeout=3.0)
        except (asyncio.TimeoutError, BrokenPipeError, ConnectionResetError):
            proc.kill()
            await proc.wait()
    return out


def parse_devices(out: str) -> list[tuple[str, str]]:
    """[(mac, name)] from `bluetoothctl devices` output.

    A regex rather than the `split(" ", 2)` this replaces. That split was
    correct about names — its maxsplit already kept "JBL Charge 2" whole — but
    it decided a line was a device by testing `parts[0] == "Device"`, and the
    scan path now feeds this output that the paired path never contained: agent
    chatter, controller banners, and discovery events. Matching the shape of an
    address is what tells a device line from a sentence that begins with the
    same word.
    """
    found = []
    for line in out.splitlines():
        m = _DEVICE_RE.match(line.strip())
        if m:
            found.append((m.group(1).upper(), m.group(2).strip()))
    return found


def unnamed(name: str, mac: str) -> bool:
    """A device BlueZ has no name for yet, so it lists its address instead.

    `bluetoothctl` writes that address with dashes (`AA-BB-…`), not the colons
    of the MAC, so both separators are dropped before comparing.
    """
    bare = lambda v: v.replace(":", "").replace("-", "").strip().upper()  # noqa: E731
    return not name.strip() or bare(name) == bare(mac)


def named_first(devices: list[dict]) -> list[dict]:
    """Devices with a real name first — those are the ones anybody recognises —
    then the bare addresses, each group alphabetical."""
    return sorted(devices, key=lambda d: (unnamed(d["name"], d["mac"]), d["name"].lower()))


async def _known(kind: str = "") -> list[tuple[str, str]]:
    args = ["bluetoothctl", "--", "devices"] + ([kind] if kind else [])
    _, out = await _run(*args)
    return parse_devices(out)


@router.get("/devices")
async def list_devices():
    """Every paired device, with whether it is connected right now.

    The `info` calls go out together rather than one after another. Each one is
    a `bluetoothctl` process and the wait is entirely the round trip, so a box
    with a pad, a second pad and a headset paid three of them end to end — long
    enough that the settings screen drew its empty state first and "nothing is
    paired yet" was the first thing the owner read. They do not depend on each
    other, so there was never a reason to queue them.
    """
    known = await _known("Paired")
    infos = await asyncio.gather(
        *(_run("bluetoothctl", "--", "info", mac) for mac, _ in known)
    )
    return named_first([
        {
            "mac": mac,
            "name": name,
            "connected": "Connected: yes" in info,
            "paired": True,
        }
        for (mac, name), (_, info) in zip(known, infos)
    ])


@router.post("/scan")
async def start_scan():
    """Look around for SCAN_SECS, then answer with what is NOT already paired.

    `--timeout` makes bluetoothctl run the scan and exit on its own, which is
    the whole reason this no longer needs a background task, a sleep and a
    terminate dance — and the reason its results can be returned at all. The
    previous version discarded them into DEVNULL and returned `{"ok": true}`
    immediately, so the button spun for eight seconds and could surface nothing
    that was not already in the paired list.

    Discovered-and-unpaired is a set difference, not a parse of the live scan
    stream: BlueZ remembers what it saw, so asking it twice afterwards is
    steadier than reading a firehose of ANSI-coloured event lines.
    """
    await _run("bluetoothctl", f"--timeout={SCAN_SECS}", "--", "scan", "on",
               timeout=SCAN_SECS + 10)

    paired = {mac for mac, _ in await _known("Paired")}
    found = [
        {"mac": mac, "name": name, "connected": False, "paired": False}
        for mac, name in await _known()
        if mac not in paired
    ]
    # A device whose name has not resolved yet shows up as its own address.
    # Keep it — it may be the pad you just woke — but put the named ones first,
    # because those are the ones anybody can recognise.
    return {"ok": True, "found": named_first(found), "seconds": SCAN_SECS}


class DeviceRequest(BaseModel):
    mac: str


@router.post("/pair")
async def pair_device(req: DeviceRequest):
    """Pair, trust, connect — in that order, on the device the player chose.

    Trust after pairing rather than before: trusting an unpaired address tells
    BlueZ to accept a future connection from something that has not yet proved
    who it is. The old `/connect` did it in that order because it could assume
    the pairing had already happened elsewhere.
    """
    # The address is typed into an interactive session: a newline in it would
    # be a second bluetoothctl command.
    if not _MAC_RE.fullmatch(req.mac):
        raise HTTPException(status_code=400, detail="Not a Bluetooth address")
    out = await _pair_with_agent(req.mac.upper())
    low = out.lower()
    ok = "pairing successful" in low or "already exists" in low or "already paired" in low
    if not ok:
        log.warning("bluetooth: pairing %s failed: %s", mask_mac(req.mac), _failure(out, "no answer"))
        return {"ok": False, "message": _failure(out, "Pairing failed")}

    await _run("bluetoothctl", "--", "trust", req.mac)
    _, cout = await _run("bluetoothctl", "--", "connect", req.mac, timeout=25.0)
    connected = "connection successful" in cout.lower()
    log.info("bluetooth: paired %s, %s", mask_mac(req.mac),
             "connected" if connected else "not connected yet")
    if connected:
        return {"ok": True, "message": "Paired and connected"}
    # Paired but not connected is a real, useful state: the device is known now
    # and the Connect button will work. Saying "failed" here would be a lie.
    return {"ok": True, "message": "Paired — press Connect when it is awake"}


def _failure(out: str, fallback: str) -> str:
    """The line bluetoothctl actually complained on, or a usable fallback."""
    for pat in (r"Failed to pair:\s*(.+)", r"Failed to connect:\s*(.+)"):
        m = re.search(pat, out)
        if m:
            reason = m.group(1).strip()
            if "authentication" in reason.lower():
                # The one failure NoInputNoOutput cannot fix, said plainly.
                return f"{reason} — this device asks for a passkey, which the box cannot type"
            return reason
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    return lines[-1] if lines else fallback


@router.post("/connect")
async def connect_device(req: DeviceRequest):
    await _run("bluetoothctl", "--", "trust", req.mac)
    _, out = await _run("bluetoothctl", "--", "connect", req.mac, timeout=25.0)
    if "connection successful" in out.lower():
        log.info("bluetooth: connected %s", mask_mac(req.mac))
        return {"ok": True, "message": "Connected"}
    log.warning("bluetooth: connecting %s failed: %s", mask_mac(req.mac), _failure(out, "no answer"))
    return {"ok": False, "message": _failure(out, "Failed")}


@router.post("/disconnect")
async def disconnect_device(req: DeviceRequest):
    _, out = await _run("bluetoothctl", "--", "disconnect", req.mac)
    ok = "successful disconnected" in out.lower() or "not connected" in out.lower()
    return {"ok": ok}


@router.delete("/devices/{mac}")
async def remove_device(mac: str):
    """Unpair and forget: disconnect, drop the pairing, and prove it went.

    This is the settings screen's "Unpair and forget", and the promise on that
    button is that the device has to be paired again before it reconnects. So
    the answer is not bluetoothctl's exit code — `remove` of an address BlueZ
    does not know exits 0 on some versions and 1 on others — but the paired
    list read back afterwards. A device still in it was not forgotten, whatever
    the tool printed.

    Disconnect first although `remove` implies it: a headset mid-stream
    answers the implicit disconnect late, and the removal then races it.
    Asking explicitly costs one short process and orders the two.

    The address is checked before it reaches argv. It is not a shell, so
    nothing is injected, but `bluetoothctl -- remove --help` is still a
    different command from the one this route exists to run.
    """
    mac = mac.upper()
    if not _MAC_RE.match(mac):
        raise HTTPException(status_code=400, detail="Not a Bluetooth address")

    await _run("bluetoothctl", "--", "disconnect", mac)
    _, out = await _run("bluetoothctl", "--", "remove", mac)

    still = {m for m, _ in await _known("Paired")}
    if mac in still:
        log.warning("bluetooth: %s is still paired after remove", mask_mac(mac))
        return {"ok": False, "message": _failure(out, "The device is still paired")}
    log.info("bluetooth: forgot %s", mask_mac(mac))
    # "not available" is BlueZ saying it has no record of the address — which
    # is the state this route exists to reach, so it is not an error.
    return {"ok": True, "message": "Forgotten — pair it again to reconnect"}
