"""
Background service that reads gamepad events directly from /dev/input via evdev.

This bypasses the Chromium Gamepad API which blocks button 16 (PS/guide button).
When the PS/guide button is detected:
  - If a game is running  → kill it and broadcast gp:guide so the frontend goes home
  - Otherwise             → broadcast gp:guide (frontend can choose to ignore)

Permissions: the process must be able to open /dev/input/event* files.
Either add the user to the 'input' group OR deploy the udev rule from install.sh.
"""
import asyncio
import glob
import logging

from . import controller_registry

log = logging.getLogger(__name__)

# Button codes for PS/Guide/Home across common Linux drivers:
#   BTN_MODE    = 0x13c (316) — hid-sony (DualShock 3/4/5), xpad, most modern drivers
#   KEY_HOMEPAGE = 172        — some older or generic HID mappings
GUIDE_CODES = frozenset({0x13C, 172})

EV_KEY  = 1   # evdev event type for key/button events
KEY_DOWN = 1  # event value for key press


async def _watch_device(path: str) -> None:
    """Read events from one device until it disconnects or is cancelled."""
    try:
        import evdev
    except ImportError:
        return

    try:
        dev = evdev.InputDevice(path)
    except (PermissionError, OSError) as e:
        log.debug("gamepad_monitor: cannot open %s — %s", path, e)
        return

    log.info("gamepad_monitor: watching %s (%s)", path, dev.name)
    try:
        async for event in dev.async_read_loop():
            if event.type != EV_KEY or event.value != KEY_DOWN:
                continue
            # Every button press counts as activity — wakes the box from standby
            from . import standby
            standby.on_input()
            if event.code in GUIDE_CODES:
                log.info("gamepad_monitor: guide/PS button detected (code=%d) on %s",
                         event.code, path)
                await _on_guide_pressed()
            else:
                log.debug("gamepad_monitor: key down code=0x%x (%d) on %s",
                          event.code, event.code, dev.name)
    except asyncio.CancelledError:
        raise
    except Exception:
        log.debug("gamepad_monitor: device %s disconnected or error", path)
    finally:
        try:
            dev.close()
        except Exception:
            pass


async def _on_guide_pressed() -> None:
    from . import process_manager as pm_module
    from .. import ws

    pm = pm_module.process_manager
    if pm.is_running:
        log.info("gamepad_monitor: killing running game")
        try:
            await pm.kill()
        except Exception:
            log.exception("gamepad_monitor: error killing game")

    try:
        await ws.broadcast("gp:guide", {})
    except Exception:
        log.exception("gamepad_monitor: error broadcasting gp:guide")


def _find_gamepad_devices() -> dict[str, tuple[str, str]]:
    """
    Map path → (name, uniq) for event devices that declare the guide button.
    Scans /dev/input/event* directly instead of relying on evdev.list_devices(),
    which reads /proc/bus/input/devices and may be inaccessible without input group.
    `uniq` is the pad's MAC address — the controller registry keys on it, and
    battery.py joins sysfs power supplies back to a player slot through it.
    """
    try:
        import evdev
    except ImportError:
        return {}

    candidate_paths: set[str] = set(glob.glob("/dev/input/event*"))
    try:
        candidate_paths |= set(evdev.list_devices())
    except Exception:
        pass

    found: dict[str, tuple[str, str]] = {}
    for path in sorted(candidate_paths):
        try:
            dev = evdev.InputDevice(path)
            caps = dev.capabilities()
            keys = caps.get(EV_KEY, [])
            name, uniq = dev.name, (dev.uniq or "")
            dev.close()
            if any(code in GUIDE_CODES for code in keys):
                found[path] = (name, uniq)
        except (PermissionError, OSError):
            pass
    return found


async def run() -> None:
    """Main loop: scan for gamepad devices every few seconds and watch them."""
    try:
        import evdev  # noqa: F401
    except ImportError:
        log.warning(
            "gamepad_monitor: evdev not installed — PS/guide button kill disabled. "
            "Fix: pip install evdev"
        )
        return

    log.info("gamepad_monitor: started (GUIDE_CODES=%s)", GUIDE_CODES)

    # Check permissions upfront and warn clearly
    accessible = [p for p in glob.glob("/dev/input/event*")
                  if _can_read(p)]
    if not accessible:
        log.warning(
            "gamepad_monitor: no /dev/input/event* readable. "
            "Fix: sudo usermod -aG input $USER && re-login, "
            "OR deploy the udev rule from install.sh"
        )

    from .. import ws

    watched: dict[str, asyncio.Task] = {}
    reg_keys: dict[str, str] = {}  # device path → controller_registry key
    # Pads already plugged in when the backend starts get their slots
    # silently — a console doesn't toast for pads that were always there.
    first_scan = True

    while True:
        devices = _find_gamepad_devices()
        current = set(devices)
        watching = set(watched.keys())

        for path in sorted(current - watching):
            name, uniq = devices[path]
            key = controller_registry.key_for(uniq, path)
            reg_keys[path] = key
            known = controller_registry.has(key)
            player = controller_registry.connect(key, name)
            task = asyncio.create_task(_watch_device(path), name=f"gpad:{path}")
            watched[path] = task
            # `known` guards against re-announcing a pad whose watcher died
            # transiently while the device never actually left.
            if not first_scan and not known:
                log.info("gamepad_monitor: controller %d connected (%s)", player, name)
                try:
                    await ws.broadcast("gp:connected", {"player": player, "label": name})
                except Exception:
                    log.exception("gamepad_monitor: error broadcasting gp:connected")

        # Clean up finished watchers (device disconnected)
        for path in list(watched):
            if watched[path].done():
                del watched[path]
                if path in current:
                    # Watcher error but the device is still there — it will be
                    # re-watched next pass; keep its player slot.
                    continue
                key = reg_keys.pop(path, None)
                if key is not None:
                    label = controller_registry.label_for(key)
                    player = controller_registry.disconnect(key)
                    if player is not None:
                        log.info("gamepad_monitor: controller %d disconnected (%s)", player, label)
                        try:
                            await ws.broadcast("gp:disconnected", {"player": player, "label": label})
                        except Exception:
                            log.exception("gamepad_monitor: error broadcasting gp:disconnected")

        first_scan = False
        await asyncio.sleep(3)


def _can_read(path: str) -> bool:
    try:
        import os
        return os.access(path, os.R_OK)
    except Exception:
        return False
