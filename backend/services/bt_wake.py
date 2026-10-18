"""Bluetooth and sleep: pads wake the box, are turned off before it sleeps,
and nothing else wakes it.

BlueZ only arms a device for wake when its `WakeAllowed` property is true, and
on the reference box it was false for the pad until set by hand. Any user may
set it over the system bus (the same policy that lets `bluetoothctl trust`
work unprivileged), so this lives in the backend, next to the pad monitor that
sees new pads arrive. The adapter's own USB wakeup is root's job:
`install/bin/gamecore-wake-setup`.

Which devices: paired ones BlueZ draws as a gamepad (`Icon` input-gaming), or
whose address is a pad on GameCore's own roster. Keyboards and mice get
`WakeAllowed` false: BlueZ allows it by default for HID, and a moved mouse
woke the box.

Before a sleep, connected pads are disconnected over Device1.Disconnect, which
ends the link with "remote user terminated" (0x13): the pad turns itself off.
Left to the kernel, the link ends with "power off" (0x15) as the box suspends,
and an Xbox pad answers that by paging straight back, which wakes the box.
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


def _paired(objects: dict):
    """(path, Device1 properties) of every paired device."""
    for path, ifaces in objects.items():
        props = ifaces.get(_DEVICE_IFACE) if isinstance(ifaces, dict) else None
        if isinstance(props, dict) and _value(props, "Paired") is True:
            yield path, props


def _is_pad(props: dict, roster_macs: set[str]) -> bool:
    icon = _value(props, "Icon") or ""
    mac = normalize_mac(_value(props, "Address") or "")
    return icon not in NOT_PADS and (icon == GAMEPAD_ICON or mac in roster_macs)


def pads_to_arm(objects: dict, roster_macs: set[str]) -> list[str]:
    """Object paths of paired pads whose WakeAllowed is false.

    `objects` is the `data[0]` of busctl's JSON GetManagedObjects reply. A pad
    without the property cannot wake anything and is left alone.
    """
    return sorted(p for p, props in _paired(objects)
                  if _is_pad(props, roster_macs) and _value(props, "WakeAllowed") is False)


def others_to_disarm(objects: dict) -> list[str]:
    """Paired keyboards and mice (NOT_PADS) still allowed to wake the box."""
    return sorted(p for p, props in _paired(objects)
                  if (_value(props, "Icon") or "") in NOT_PADS
                  and _value(props, "WakeAllowed") is True)


def pads_to_turn_off(objects: dict, roster_macs: set[str]) -> list[str]:
    """Paired pads connected right now. Audio and input devices that are not pads stay."""
    return sorted(p for p, props in _paired(objects)
                  if _is_pad(props, roster_macs) and _value(props, "Connected") is True)


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


async def _devices() -> dict | None:
    """BlueZ's managed objects, or None when it could not be asked."""
    code, out = await _busctl("--json=short", "call", "org.bluez", "/",
                              "org.freedesktop.DBus.ObjectManager", "GetManagedObjects")
    if code != 0:
        log.debug("bt_wake: BlueZ did not answer: %s", out.strip()[:200])
        return None
    try:
        return json.loads(out)["data"][0]
    except (ValueError, KeyError, IndexError, TypeError):
        log.warning("bt_wake: unreadable GetManagedObjects reply")
        return None


async def _set_wake(path: str, allowed: bool) -> None:
    value = "true" if allowed else "false"
    code, detail = await _busctl("set-property", "org.bluez", path,
                                 _DEVICE_IFACE, "WakeAllowed", "b", value)
    name = path.rsplit("/", 1)[-1]
    if code == 0:
        log.info("bt_wake: %s %s wake the box", name, "may now" if allowed else "can no longer")
    else:
        log.warning("bt_wake: could not set WakeAllowed=%s on %s: %s", value, path, detail.strip())


async def set_wake_permissions() -> bool | None:
    """One pass: arm pads, disarm keyboards and mice.

    True when BlueZ answered, None when it could not be asked.
    """
    objects = await _devices()
    if objects is None:
        return None
    for path in pads_to_arm(objects, roster_macs()):
        await _set_wake(path, True)
    for path in others_to_disarm(objects):
        await _set_wake(path, False)
    return True


async def _disconnect(path: str) -> None:
    # BlueZ answers once the link is down, so awaiting this is awaiting the pad off.
    code, detail = await _busctl("call", "org.bluez", path, _DEVICE_IFACE, "Disconnect")
    name = path.rsplit("/", 1)[-1]
    if code == 0:
        log.info("bt_wake: %s turned off for the sleep", name)
    else:
        log.warning("bt_wake: could not disconnect %s: %s", name, detail.strip()[:200])


async def turn_off_pads() -> int:
    """Disconnect every connected pad, all at once. Returns how many were asked.

    Each call is bounded by BUSCTL_SECS; WakeAllowed is left as it is, so the
    pad's home button still wakes the box.
    """
    objects = await _devices()
    if objects is None:
        return 0
    paths = pads_to_turn_off(objects, roster_macs())
    await asyncio.gather(*(_disconnect(p) for p in paths))
    return len(paths)


async def run() -> None:
    """A pass at start, then one whenever a pad not seen before connects."""
    seen: set[str] | None = None
    retry_at = 0.0
    loop = asyncio.get_running_loop()
    while True:
        macs = roster_macs()
        new_pad = seen is None or not macs <= seen
        if new_pad or (retry_at and loop.time() >= retry_at):
            answered = await set_wake_permissions()
            retry_at = 0.0 if answered else loop.time() + RETRY_SECS
            seen = (seen or set()) | macs
        await asyncio.sleep(ROSTER_POLL_SECS)
