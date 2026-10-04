"""Controller battery reading (sysfs) + low-battery watcher.

read_batteries() is the single source of truth — sysinfo uses it for the
TopBar pills, and run() watches thresholds (25/15/10/5 %) and broadcasts
"gp:battery" over the WebSocket so the UI can pop a toast.
"""
import asyncio
import glob
import logging
from pathlib import Path

from . import controller_registry
from .gamepad_devices import BTN_SOUTH

log = logging.getLogger(__name__)

# Power supply name prefixes that are NOT controllers (laptop/UPS/USB-PD...)
_SKIP = ("BAT", "AC", "USB", "UCSI", "ADP", "MACSMC", "axp", "bq")

# Warn when the level crosses each threshold going down, once per crossing
THRESHOLDS = (25, 15, 10, 5)
# The kernel value itself is fresh — hid-playstation updates power_supply on
# every HID report — it just changes rarely, because a battery drains slowly.
# What this interval really governs is how fast a *charging* change or a pad
# appearing/disappearing reaches the UI. Reading a handful of files from a
# virtual filesystem costs microseconds, so 10s is free; the broadcast below
# only fires when something actually changed, so the socket stays quiet.
_POLL_SECS = 10
# Re-arm a threshold once the level climbs back above it by this margin
# (avoids toast spam when a reading oscillates around the threshold)
_REARM_MARGIN = 5


POWER_SUPPLY_ROOT = Path("/sys/class/power_supply")


def _has_bit(bitmap: str, bit: int) -> bool:
    """A sysfs capability bitmap: 64-bit hex words, most significant first."""
    words = bitmap.split()
    index = len(words) - 1 - bit // 64
    return 0 <= index < len(words) and bool(int(words[index], 16) >> (bit % 64) & 1)


def _is_gamepad(supply: Path) -> bool:
    """Whether the device behind a battery has a gamepad button.

    Mice and keyboards report batteries too (Logitech's hidpp_battery_N):
    shown as controllers, a mouse took the pill "P2", numbered by the themes
    from its place in the list. A supply whose device lists no input node
    is kept, as before.
    """
    keys = sorted((supply / "device" / "input").glob("input*/capabilities/key"))
    if not keys:
        return True
    for key in keys:
        try:
            if _has_bit(key.read_text(), BTN_SOUTH):
                return True
        except (OSError, ValueError):
            continue
    return False


def read_batteries(root: Path = POWER_SUPPLY_ROOT) -> list[dict]:
    """Controller batteries from sysfs: [{name, level, charging}]."""
    result = []
    for supply in sorted(glob.glob(str(root / "*"))):
        p = Path(supply)
        name = p.name
        if any(name.upper().startswith(s.upper()) for s in _SKIP):
            continue
        if not _is_gamepad(p):
            continue
        cap_path = p / "capacity"
        if not cap_path.exists():
            continue
        try:
            level = int(cap_path.read_text().strip())
        except (ValueError, OSError):
            continue
        try:
            status = (p / "status").read_text().strip()
        except OSError:
            status = ""
        # model_name is friendlier than the supply dir name when present
        try:
            label = (p / "model_name").read_text().strip() or name
        except OSError:
            label = name
        result.append({
            "name": name,
            "label": label,
            # Supply dir names embed the pad's MAC — join it back to the
            # console-style slot assigned by gamepad_monitor (None if unknown)
            "player": controller_registry.player_for_mac(name),
            "level": level,
            "charging": status in ("Charging", "Full"),
        })
    return result


# supply name → set of thresholds already fired
_fired: dict[str, set[int]] = {}


def _check(batteries: list[dict]) -> list[dict]:
    """Return the alerts to send for this poll (pure logic — unit-testable)."""
    alerts = []
    seen = set()
    for b in batteries:
        name, level, charging = b["name"], b["level"], b["charging"]
        seen.add(name)
        fired = _fired.setdefault(name, set())
        if charging:
            # Charging resets everything — a later discharge should warn again
            fired.clear()
            continue
        # Ascending: report the tightest crossed threshold (a pad plugged in
        # at 4% is a "5%" alert, not a "15%" one)
        for t in sorted(THRESHOLDS):
            if level <= t and t not in fired:
                fired.add(t)
                # Also mark higher thresholds: connecting a pad at 4% must
                # yield ONE toast (5%), not three
                fired.update(x for x in THRESHOLDS if x >= t)
                alerts.append({"name": b["label"], "player": b.get("player"), "level": level, "threshold": t})
                break
        # Re-arm thresholds the level has climbed well above
        for t in list(fired):
            if level > t + _REARM_MARGIN:
                fired.discard(t)
    # Forget disconnected pads so a reconnect starts fresh
    for name in list(_fired):
        if name not in seen:
            del _fired[name]
    return alerts


def _signature(batteries: list[dict]) -> str:
    """What the UI actually renders — so an unchanged poll broadcasts nothing."""
    return "|".join(f"{b['name']}:{b['level']}:{b['charging']}:{b['player']}"
                    for b in batteries)


async def run() -> None:
    """Poll sysfs, push controller status on change, broadcast low-battery alerts."""
    from .. import ws

    log.info("battery: watcher started (thresholds=%s, poll=%ss)", THRESHOLDS, _POLL_SECS)
    last = None
    while True:
        # Sleep FIRST: at backend startup the UI isn't connected to the
        # WebSocket yet — checking immediately would broadcast a crossed
        # threshold to zero clients and mark it fired, losing the alert
        # (seen after every OTA restart with a pad already below 25%).
        await asyncio.sleep(_POLL_SECS)
        try:
            batteries = read_batteries()

            # Push the whole picture when it moves. The TopBar used to poll
            # /api/sysinfo every 15s for this, which meant the battery pill
            # could contradict the connection toast for a quarter of a minute.
            sig = _signature(batteries)
            if sig != last:
                last = sig
                await ws.broadcast("gp:controllers", {"controllers": batteries})

            for alert in _check(batteries):
                log.info("battery: %(name)s at %(level)d%% (threshold %(threshold)d%%)", alert)
                await ws.broadcast("gp:battery", alert)
        except Exception:
            log.exception("battery: poll failed")
