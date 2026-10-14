"""After a wake: wait until the screen can actually show something.

The kernel's DRM connectors say when the link is back: `status` reads
`connected` once amdgpu has re-sensed the TV, `enabled` once a mode is set on
it again, `dpms` is `On` once the screen is lit. Read from sysfs because it
needs no X connection (the backend's X access is the slowest thing to come
back) and no privilege, and a 200 ms poll costs nothing for 10 s.

The link being up is not the picture being up: a TV keeps "no signal" on
screen for a moment after it, which is what the settle delay is for
(`standby.json` `wake_settle_secs`, Settings → System).
"""
import asyncio
import logging
from pathlib import Path

log = logging.getLogger(__name__)

DRM = Path("/sys/class/drm")
POLL_SECS = 0.2
#: Past this the splash starts anyway: a box with no screen must still wake.
WAIT_MAX_SECS = 10.0


def _read(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def connector_ready(status: str, enabled: str, dpms: str) -> bool:
    """One connector carrying a picture. `dpms` may be "" (file absent)."""
    return status == "connected" and enabled == "enabled" and dpms in ("On", "")


def display_ready(root: Path | None = None) -> bool:
    """True when any card*-* connector is connected, has a mode and is lit."""
    root = root or DRM
    for conn in sorted(root.glob("card*-*")):
        if connector_ready(_read(conn / "status"), _read(conn / "enabled"),
                           _read(conn / "dpms")):
            return True
    return False


def has_connectors(root: Path | None = None) -> bool:
    return any((root or DRM).glob("card*-*/status"))


async def wait_for_display(settle: float = 0.0, root: Path | None = None,
                           max_wait: float = WAIT_MAX_SECS) -> bool:
    """Wait for a lit connector (at most `max_wait`), then `settle` more.

    Returns False when it gave up waiting; the caller starts anyway.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max_wait
    ready = not has_connectors(root)        # no DRM (a VM): nothing to wait for
    while not ready and loop.time() < deadline:
        ready = display_ready(root)
        if not ready:
            await asyncio.sleep(POLL_SECS)
    if not ready:
        log.warning("display_ready: no lit connector after %ss; waking the UI anyway",
                    max_wait)
    if settle > 0:
        await asyncio.sleep(settle)
    return ready
