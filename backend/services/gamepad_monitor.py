"""
Background service that reads gamepad events directly from /dev/input via evdev.

This bypasses the Chromium Gamepad API which blocks button 16 (PS/guide button).
When the PS/guide button is pressed twice within DOUBLE_PRESS_WINDOW seconds
(a single press is ignored, to avoid accidental exits):
  - If a game is running  → kill it and broadcast gp:guide so the frontend goes home
  - Otherwise             → broadcast gp:guide (frontend can choose to ignore)

Permissions: the process must be able to open /dev/input/event* files.
Either add the user to the 'input' group OR deploy the udev rule from install.sh.
"""
import asyncio
import glob
import logging
import time

from . import controller_profiles, controller_registry

log = logging.getLogger(__name__)

# Button codes for PS/Guide/Home across common Linux drivers:
#   BTN_MODE    = 0x13c (316) — hid-sony (DualShock 3/4/5), xpad, most modern drivers
#   KEY_HOMEPAGE = 172        — some older or generic HID mappings
GUIDE_CODES = frozenset({0x13C, 172})

# BTN_SOUTH (A/Cross) — declared by every real gamepad, by no keyboard/remote.
# Used to decide which guide-capable devices deserve a player slot.
BTN_SOUTH = 0x130

EV_KEY  = 1   # evdev event type for key/button events
KEY_DOWN = 1  # event value for key press

# Guide button must be pressed twice within this window (seconds) to trigger.
DOUBLE_PRESS_WINDOW = 1.0
# Presses closer than this are the same physical press reported twice
# (e.g. a pad exposing both BTN_MODE and KEY_HOMEPAGE) — ignore them.
DEBOUNCE = 0.05

_last_guide_press: float = 0.0

# Paths already reported as "kept, but has no Guide button" — the scan runs
# every few seconds and this should be said once per device, not per pass.
_logged_no_guide: set[str] = set()


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
    global _last_guide_press

    now = time.monotonic()
    elapsed = now - _last_guide_press
    if elapsed < DEBOUNCE:
        return
    if elapsed > DOUBLE_PRESS_WINDOW:
        _last_guide_press = now
        log.info("gamepad_monitor: guide pressed once — press again within %.1fs to exit",
                 DOUBLE_PRESS_WINDOW)
        return
    _last_guide_press = 0.0

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


def _find_gamepad_devices() -> dict[str, tuple[str, str, bool, str, str]]:
    """
    Map path → (name, uniq, is_pad, vendor, product) for event devices that
    declare the guide button. Scans /dev/input/event* directly instead of
    relying on evdev.list_devices(), which reads /proc/bus/input/devices and
    may be inaccessible without input group.

    `uniq` is the pad's MAC address — the controller registry keys on it, and
    battery.py joins sysfs power supplies back to a player slot through it.
    `vendor`/`product` (4-hex USB IDs) drive controller_profiles.apply_profile
    — whichever controller TYPE takes a slot gets that slot's emulator
    configs written for it, live (docs/CONTROLLER_MODELS.md).

    `is_pad` tells actual gamepads apart: KEY_HOMEPAGE (172) is also a plain
    multimedia key, so keyboards and remotes land here too — they must keep
    being watched for the guide/home behavior but must NOT take a player
    slot. Every real pad declares BTN_SOUTH; no keyboard does.
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

    found: dict[str, tuple[str, str, bool, str, str]] = {}
    for path in sorted(candidate_paths):
        try:
            dev = evdev.InputDevice(path)
            caps = dev.capabilities()
            keys = caps.get(EV_KEY, [])
            name, uniq = dev.name, (dev.uniq or "")
            info = dev.info
            vendor, product = f"{info.vendor:04x}", f"{info.product:04x}"
            dev.close()
            has_guide = any(code in GUIDE_CODES for code in keys)
            is_pad = BTN_SOUTH in keys
            # `or is_pad` is the second half of this test, and it was missing:
            # a device had to declare a Guide/Home code to be seen at all. A pad
            # without a Home button — a generic USB pad, an arcade stick, a SNES
            # or N64 clone, an 8BitDo in DInput — never entered this dict, so it
            # was never watched, never registered, never given a player slot, and
            # apply_profile was never called for it. PCSX2 and DuckStation got no
            # [Pad2], Dolphin left Wiimote1 on the virtual pointer, RPCS3 and
            # Ryujinx were never retargeted. It still worked in emulators that
            # read SDL directly, which is what made it look like something else.
            #
            # These pads simply never reach _on_guide_pressed, which is correct.
            # A keyboard cannot arrive this way: is_pad is BTN_SOUTH, which no
            # keyboard declares, so the anti-keyboard rule below is unchanged.
            if has_guide or is_pad:
                found[path] = (name, uniq, is_pad, vendor, product)
                if is_pad and not has_guide and path not in _logged_no_guide:
                    _logged_no_guide.add(path)
                    log.info("gamepad_monitor: %s (%s) has no Guide button — taking a "
                             "player slot, but it cannot trigger the guide shortcut",
                             name, path)
        except (PermissionError, OSError):
            pass
    _logged_no_guide.intersection_update(found)
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
    # registry key → (player, vendor, product) for connected pads — feeds
    # controller_profiles' dup_index (how many same-model pads sit in lower
    # slots), which every per-name/per-GUID emulator counter needs.
    pad_models: dict[str, tuple[int, str, str]] = {}
    # Pads already plugged in when the backend starts get their slots
    # silently — a console doesn't toast for pads that were always there.
    first_scan = True

    while True:
        devices = _find_gamepad_devices()
        current = set(devices)
        watching = set(watched.keys())

        for path in sorted(current - watching):
            name, uniq, is_pad, vendor, product = devices[path]
            task = asyncio.create_task(_watch_device(path), name=f"gpad:{path}")
            watched[path] = task
            # Keyboards/remotes with a Home multimedia key end up here for
            # the guide behavior but are not controllers — no player slot.
            if not is_pad:
                continue
            key = controller_registry.key_for(uniq, path)
            reg_keys[path] = key
            known = controller_registry.has(key)
            player = controller_registry.connect(key, name)
            # `known` guards against re-announcing a pad whose watcher died
            # transiently while the device never actually left. A genuinely
            # new slot always gets its emulator configs written — including
            # on first_scan (pads already plugged in when the backend
            # starts), just without the WS toast a console wouldn't show.
            if not known:
                if vendor == "0000":
                    # uhid may briefly expose a BT pad before its ids are
                    # populated — never write configs from a zero VID/PID.
                    log.warning("gamepad_monitor: %s (%s) has vendor 0000 — "
                                "skipping emulator profiling", name, path)
                else:
                    dup = sum(1 for k2, (pl, v2, p2) in pad_models.items()
                              if k2 != key and (v2, p2) == (vendor, product) and pl < player)
                    try:
                        results = await asyncio.to_thread(
                            controller_profiles.apply_profile, player, vendor, product, name, dup)
                        # Log both outcomes. `if results:` alone meant a pass
                        # that configured nothing looked exactly like one that
                        # never ran — apply_profile now details the give-ups
                        # itself, but the "0 emulators" headline belongs here.
                        log.info("gamepad_monitor: player %d profiled (%s:%s, dup %d) — %s",
                                 player, vendor, product, dup,
                                 "; ".join(results) if results else "no emulator configured")
                    except Exception:
                        log.exception("gamepad_monitor: controller_profiles failed for player %d", player)
            pad_models[key] = (player, vendor, product)
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
                # One pad can own several /dev/input/event* nodes: key_for()
                # returns its MAC, so a DualShock 4 paired over Bluetooth and
                # then plugged in to charge maps two paths to the same key.
                # Unplugging the cable killed that path's watcher and this
                # released the slot outright — gp:disconnected broadcast,
                # release_profile putting Wiimote1 back on the virtual pointer —
                # while the pad was still connected over Bluetooth and still in
                # the player's hands. Only let go once no live path is left.
                if key is not None and key not in reg_keys.values():
                    pad_models.pop(key, None)
                    label = controller_registry.label_for(key)
                    player = controller_registry.disconnect(key)
                    if player is not None:
                        log.info("gamepad_monitor: controller %d disconnected (%s)", player, label)
                        # Free the slot's emulated "connected player" state (else
                        # a Dolphin Wii Remote left on Source=1 haunts solo play).
                        try:
                            released = await asyncio.to_thread(
                                controller_profiles.release_profile, player)
                            if released:
                                log.info("gamepad_monitor: player %d released — %s",
                                         player, "; ".join(released))
                        except Exception:
                            log.exception("gamepad_monitor: release_profile failed for player %d", player)
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
