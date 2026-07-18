"""Console-style player slots for connected controllers.

gamepad_monitor calls connect()/disconnect() as pads come and go; each pad
gets the lowest free slot (1-based), like on a console — plug a second pad
while the first is connected and it becomes player 2; unplug player 1 and
the next pad to arrive takes slot 1 back.

battery.py joins the sysfs power supplies back to a slot through the pad's
MAC address (evdev `uniq`, also embedded in the supply directory name), so
alerts and the TopBar pills can say "Controller 2" instead of a device name.

Pure logic, no evdev/sysfs access — unit-testable (see
tests/test_controller_registry.py).
"""
import logging
import re

log = logging.getLogger(__name__)

_MAC_RE = re.compile(r"([0-9a-f]{2}(?::[0-9a-f]{2}){5})")

# registry key (normalized MAC, else device path) → player slot (1-based)
_slots: dict[str, int] = {}
_labels: dict[str, str] = {}


def normalize_mac(value: str | None) -> str:
    """Extract a lowercased aa:bb:cc:dd:ee:ff from any MAC-ish string.

    Handles evdev `uniq` ("84:30:95:07:C8:1C") as well as sysfs power-supply
    names ("ps-controller-battery-84:30:95:07:c8:1c",
    "sony_controller_battery_84:30:95:07:c8:1c"). Returns '' when no MAC is
    present.
    """
    if not value:
        return ""
    m = _MAC_RE.search(value.lower())
    return m.group(1) if m else ""


def key_for(uniq: str | None, path: str) -> str:
    """Stable registry key for a pad: its MAC when known, else the devnode."""
    return normalize_mac(uniq) or path


def has(key: str) -> bool:
    return key in _slots


def connect(key: str, label: str = "") -> int:
    """Assign the lowest free slot to `key`; idempotent for a known key."""
    if key in _slots:
        if label:
            _labels[key] = label
        return _slots[key]
    used = set(_slots.values())
    player = next(n for n in range(1, len(used) + 2) if n not in used)
    _slots[key] = player
    if label:
        _labels[key] = label
    log.info("controller_registry: player %d ← %s (%s)", player, key, label or "?")
    return player


def disconnect(key: str) -> int | None:
    """Free `key`'s slot and return the player number it had, if any."""
    _labels.pop(key, None)
    player = _slots.pop(key, None)
    if player is not None:
        log.info("controller_registry: player %d freed (%s)", player, key)
    return player


def label_for(key: str) -> str:
    return _labels.get(key, "")


def player_for_mac(value: str | None) -> int | None:
    """Player slot for any MAC-bearing string (e.g. a power-supply name)."""
    mac = normalize_mac(value)
    return _slots.get(mac) if mac else None


def snapshot() -> list[dict]:
    """Connected pads ordered by slot: [{player, label}]."""
    return [
        {"player": player, "label": _labels.get(key, "")}
        for key, player in sorted(_slots.items(), key=lambda kv: kv[1])
    ]
