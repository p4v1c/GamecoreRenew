"""Name what woke the box: the wakeup sources whose count moved across a sleep.

Every device allowed to wake the machine has a `/sys/class/wakeup/wakeupN`
entry whose `event_count` grows when it signals. A snapshot when logind
announces the sleep, another first thing after the wake, and the difference is
the culprit: the USB port of the Bluetooth adapter (a pad or a mouse paging),
the power button, the RTC. World-readable, so the backend needs no privilege.
`/sys/power/pm_wakeup_irq` adds the IRQ when the kernel kept it (s2idle).
"""
import logging
from pathlib import Path

log = logging.getLogger(__name__)

WAKEUP = Path("/sys/class/wakeup")
WAKEUP_IRQ = Path("/sys/power/pm_wakeup_irq")

_before: dict[str, tuple[str, int]] | None = None


def _read(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def _label(entry: Path) -> str:
    """`name`, plus the USB product when the device has one ("3-3 (Bluetooth)")."""
    name = _read(entry / "name") or entry.name
    product = _read(entry / "device" / "product")
    return f"{name} ({product})" if product else name


def snapshot(root: Path | None = None) -> dict[str, tuple[str, int]]:
    """{wakeupN: (label, event_count)} for every source the kernel lists."""
    out = {}
    for entry in sorted((root or WAKEUP).glob("wakeup*")):
        count = _read(entry / "event_count")
        if count.isdigit():
            out[entry.name] = (_label(entry), int(count))
    return out


def moved(before: dict[str, tuple[str, int]], after: dict[str, tuple[str, int]]) -> list[str]:
    """Labels of the sources that signalled in between, most events first."""
    # A source born after the wake (a device plugged in since) proves nothing.
    deltas = [(count - before[key][1], label)
              for key, (label, count) in after.items() if key in before]
    return [f"{label} +{d}" for d, label in sorted(deltas, key=lambda x: -x[0]) if d > 0]


def remember(root: Path | None = None) -> None:
    """PrepareForSleep(true): keep the counts from before the sleep."""
    global _before
    _before = snapshot(root)


def report(root: Path | None = None, irq_path: Path = WAKEUP_IRQ) -> list[str]:
    """After the wake: log the sources that moved and return them."""
    global _before
    before, _before = _before, None
    if before is None:
        log.info("wake_source: no snapshot from before the sleep")
        return []
    sources = moved(before, snapshot(root))
    irq = _read(irq_path)
    log.info("wake_source: woken by %s%s", ", ".join(sources) or "no listed source",
             f" (irq {irq})" if irq else "")
    return sources
