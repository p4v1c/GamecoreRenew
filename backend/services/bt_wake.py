"""Let paired Bluetooth pads wake the box from Rest mode.

BlueZ only arms a device for wake when its `WakeAllowed` property is true, and
on the reference box it was false for the pad until set by hand. Any user may
set it over the system bus (the same policy that lets `bluetoothctl trust`
work unprivileged), so this lives in the backend, next to the pad monitor that
sees new pads arrive. The adapter's own USB wakeup is root's job:
`install/bin/gamecore-wake-setup`.

Which devices: paired ones BlueZ draws as a gamepad (`Icon` input-gaming), or
whose address is a pad on GameCore's own roster. Never a keyboard or a mouse.
"""
import asyncio
import json
import logging

from . import gamepad_monitor
from .controller_registry import normalize_mac

log = logging.getLogger(__name__)

BUSCTL_SECS = 5.0
GAMEPAD_ICON = "input-gaming"
#: Never armed, even if some roster entry claimed the address.
NOT_PADS = frozenset({"input-keyboard", "input-mouse", "input-tablet"})
#: How often the roster is checked for a pad not seen before.
ROSTER_POLL_SECS = 5.0
#: How soon a pass that could not reach BlueZ (not started yet) is retried.
RETRY_SECS = 30.0

_DEVICE_IFACE = "org.bluez.Device1"


def _value(props: dict, name: str):
    entry = props.get(name)
    return entry.get("data") if isinstance(entry, dict) else None


def pads_to_arm(objects: dict, roster_macs: set[str]) -> list[str]:
    """Object paths of paired pads whose WakeAllowed is false.

    `objects` is the `data[0]` of busctl's JSON GetManagedObjects reply. A pad
    without the property cannot wake anything and is left alone.
    """
    out = []
    for path, ifaces in objects.items():
        props = ifaces.get(_DEVICE_IFACE) if isinstance(ifaces, dict) else None
        if not isinstance(props, dict) or _value(props, "Paired") is not True:
            continue
        icon = _value(props, "Icon") or ""
        mac = normalize_mac(_value(props, "Address") or "")
        if icon in NOT_PADS or not (icon == GAMEPAD_ICON or mac in roster_macs):
            continue
        if _value(props, "WakeAllowed") is False:
            out.append(path)
    return sorted(out)


def roster_macs() -> set[str]:
    """MACs of the pads the monitor sees; other keys are device paths."""
    return {m for m in (normalize_mac(k) for k in gamepad_monitor.roster()) if m}


async def _busctl(*args: str) -> tuple[int, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            "busctl", "--system", *args, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT)
        out, _ = await asyncio.wait_for(proc.communicate(), BUSCTL_SECS)
    except (OSError, asyncio.TimeoutError) as e:
        return 1, str(e) or type(e).__name__
    return proc.returncode, (out or b"").decode(errors="replace")


async def allow_paired_pads() -> bool | None:
    """One pass. True when BlueZ answered, None when it could not be asked."""
    code, out = await _busctl("--json=short", "call", "org.bluez", "/",
                              "org.freedesktop.DBus.ObjectManager", "GetManagedObjects")
    if code != 0:
        log.debug("bt_wake: BlueZ did not answer: %s", out.strip()[:200])
        return None
    try:
        objects = json.loads(out)["data"][0]
    except (ValueError, KeyError, IndexError, TypeError):
        log.warning("bt_wake: unreadable GetManagedObjects reply")
        return None
    for path in pads_to_arm(objects, roster_macs()):
        code, detail = await _busctl("set-property", "org.bluez", path,
                                     _DEVICE_IFACE, "WakeAllowed", "b", "true")
        if code == 0:
            log.info("bt_wake: %s may now wake the box", path.rsplit("/", 1)[-1])
        else:
            log.warning("bt_wake: could not allow wake on %s: %s", path, detail.strip())
    return True


async def run() -> None:
    """A pass at start, then one whenever a pad not seen before connects."""
    seen: set[str] | None = None
    retry_at = 0.0
    loop = asyncio.get_running_loop()
    while True:
        macs = roster_macs()
        new_pad = seen is None or not macs <= seen
        if new_pad or (retry_at and loop.time() >= retry_at):
            answered = await allow_paired_pads()
            retry_at = 0.0 if answered else loop.time() + RETRY_SECS
            seen = (seen or set()) | macs
        await asyncio.sleep(ROSTER_POLL_SECS)
