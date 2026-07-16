"""Controller battery reading (sysfs) + low-battery watcher.

read_batteries() is the single source of truth — sysinfo uses it for the
TopBar pills, and run() watches thresholds (15/10/5 %) and broadcasts
"gp:battery" over the WebSocket so the UI can pop a toast.
"""
import asyncio
import glob
import logging
from pathlib import Path

log = logging.getLogger(__name__)

# Power supply name prefixes that are NOT controllers (laptop/UPS/USB-PD...)
_SKIP = ("BAT", "AC", "USB", "UCSI", "ADP", "MACSMC", "axp", "bq")

# Warn when the level crosses each threshold going down, once per crossing
THRESHOLDS = (25, 15, 10, 5)
_POLL_SECS = 30
# Re-arm a threshold once the level climbs back above it by this margin
# (avoids toast spam when a reading oscillates around the threshold)
_REARM_MARGIN = 5


def read_batteries() -> list[dict]:
    """Controller batteries from sysfs: [{name, level, charging}]."""
    result = []
    for supply in sorted(glob.glob("/sys/class/power_supply/*")):
        p = Path(supply)
        name = p.name
        if any(name.upper().startswith(s.upper()) for s in _SKIP):
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
                alerts.append({"name": b["label"], "level": level, "threshold": t})
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


async def run() -> None:
    """Poll sysfs and broadcast low-battery alerts."""
    from .. import ws

    log.info("battery: watcher started (thresholds=%s)", THRESHOLDS)
    while True:
        # Sleep FIRST: at backend startup the UI isn't connected to the
        # WebSocket yet — checking immediately would broadcast a crossed
        # threshold to zero clients and mark it fired, losing the alert
        # (seen after every OTA restart with a pad already below 25%).
        await asyncio.sleep(_POLL_SECS)
        try:
            for alert in _check(read_batteries()):
                log.info("battery: %(name)s at %(level)d%% (threshold %(threshold)d%%)", alert)
                await ws.broadcast("gp:battery", alert)
        except Exception:
            log.exception("battery: poll failed")
