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

# How many scan passes a pad gets to be profiled completely before the monitor
# stops trying. A pass that leaves an emulator unconfigured is retried on the
# next scan (3 s apart) rather than remembered as done.
#
# Bounded, because some give-ups are permanent — an emulator with no gamepad
# slot to clone from will never succeed — and each retry pays for SDL probes
# with an 8 s timeout apiece. Five passes is ~15 s, which covers the case this
# exists for: SDL not yet seeing a Bluetooth pad that has just connected. A
# DualShock 4's Ryujinx slot was lost exactly that way, and never recreated.
PROFILE_RETRIES = 5

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

# Both evdev failure modes return the SAME empty dict a box with nothing
# plugged in returns, and the scan loop below runs every three seconds forever.
# So each one gets a WARNING the first time and on every change after that,
# never once per pass — a line repeated 1200 times an hour is how the one line
# that names the cause gets buried. The unconditional debug line underneath
# stays available when someone is actually looking.
_logged_no_evdev = False
_last_denied: tuple[int, int] | None = None


def _report_denied(denied: int, total: int) -> None:
    """Say that input devices are being refused, without saying it every pass.

    A box with no controller plugged in is a legitimate state and MUST stay
    silent. That is the whole difficulty: it produces the same `{}` as a box
    whose every device was refused. `denied` is the only thing that tells the
    two apart, so nothing is written unless something was actually refused.
    """
    global _last_denied
    if not denied:
        _last_denied = None          # cleared, so a later failure reports again
        return
    log.debug("gamepad_monitor: %d/%d input devices refused", denied, total)
    if _last_denied == (denied, total):
        return
    _last_denied = (denied, total)
    log.warning(
        "gamepad_monitor: %d of %d input devices refused (permission denied) — "
        "is the account running the backend outside the `input` group? A pad "
        "refused here is invisible everywhere: no player slot, no emulator "
        "config, and no guide shortcut, in the menu as well as in games.",
        denied, total)


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


def _find_gamepad_devices() -> dict[str, tuple[str, str, bool, str, str, int]]:
    """
    Map path → (name, uniq, is_pad, vendor, product) for event devices that
    declare the guide button. Scans /dev/input/event* directly instead of
    relying on evdev.list_devices(), which reads /proc/bus/input/devices and
    may be inaccessible without input group.

    `bustype` is the transport (0x03 USB, 0x05 Bluetooth). It is part of what
    a config is written FOR, not just how the pad is reached: an SDL GUID
    encodes the bus, so the same Xbox pad is 0x05... over Bluetooth and
    0x03... over USB, and Ryujinx binds by that GUID. Without it in the
    footprint, moving a pad from Bluetooth to a cable left every GUID-bound
    emulator pointing at a device that no longer exists — silently, because
    the MAC, the vendor and the product are all unchanged.

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
    global _logged_no_evdev
    try:
        import evdev
    except ImportError:
        # Not a crash: the rest of the box works without a pad. But it is not
        # the absence of a controller either — it is the guarantee that no
        # controller will EVER be seen, which the empty dict below cannot say.
        log.debug("gamepad_monitor: python-evdev is not importable")
        if not _logged_no_evdev:
            _logged_no_evdev = True
            log.error("gamepad_monitor: python-evdev is not importable — no "
                      "controller can be detected on this box at all. Install "
                      "python-evdev in the backend's environment.")
        return {}

    candidate_paths: set[str] = set(glob.glob("/dev/input/event*"))
    try:
        candidate_paths |= set(evdev.list_devices())
    except Exception:
        pass

    found: dict[str, tuple[str, str, bool, str, str, int]] = {}
    denied = 0
    for path in sorted(candidate_paths):
        try:
            dev = evdev.InputDevice(path)
            caps = dev.capabilities()
            keys = caps.get(EV_KEY, [])
            name, uniq = dev.name, (dev.uniq or "")
            info = dev.info
            vendor, product = f"{info.vendor:04x}", f"{info.product:04x}"
            bustype = getattr(info, "bustype", 0)
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
                found[path] = (name, uniq, is_pad, vendor, product, bustype)
                if is_pad and not has_guide and path not in _logged_no_guide:
                    _logged_no_guide.add(path)
                    log.info("gamepad_monitor: %s (%s) has no Guide button — taking a "
                             "player slot, but it cannot trigger the guide shortcut",
                             name, path)
        except PermissionError:
            # Counted, not reported here: one line per device would be four
            # lines a pass on a box that simply lacks the group. Must come
            # before OSError — it is a subclass, so the wide clause would
            # swallow it and the count would always be zero.
            denied += 1
        except OSError:
            # A device that vanished between the glob and the open — a pad
            # being unplugged right now. Routine, and not a permission problem.
            pass
    _report_denied(denied, len(candidate_paths))
    _logged_no_guide.intersection_update(found)
    return found


def _event_sort_key(path: str) -> tuple[str, int]:
    """Sort /dev/input/event10 after event2, not before it. Player slots are
    handed out in this order on the first scan, so a lexicographic sort quietly
    made the numbering depend on how many input devices the box happens to
    have."""
    head = path.rstrip("0123456789")
    tail = path[len(head):]
    return head, int(tail) if tail else -1


def pads_by_key(devices: dict[str, tuple[str, str, bool, str, str, int]]
                ) -> dict[str, tuple[str, str, str, int]]:
    """registry key → (vendor, product, evdev name, bustype), one entry per
    PHYSICAL controller.

    A pad owns several event nodes (a DualShock 4 adds a touchpad and a motion
    node) and key_for() collapses them onto its MAC, so the same controller
    must not be counted — or slotted — twice. Pads whose ids are still zero are
    left out entirely: uhid can expose a Bluetooth pad before the kernel fills
    them in, and a slot handed out then used to be held for ever by a pad we
    refused to profile, because `known` blocked every later attempt.
    """
    out: dict[str, tuple[str, str, str, int]] = {}
    for path in sorted(devices, key=_event_sort_key):
        name, uniq, is_pad, vendor, product, bustype = devices[path]
        if not is_pad or vendor == "0000" or product == "0000":
            continue
        key = controller_registry.key_for(uniq, path)
        out.setdefault(key, (vendor, product, name, bustype))
    return out


def dup_indexes(roster: dict[str, tuple[int, str]]) -> dict[str, int]:
    """key → how many pads sharing the same RESOLVED NAME hold a lower slot.

    It used to count by vendor:product, but every consumer counts by name:
    Dolphin writes `SDL/<dup>/<name>` and RPCS3 `<name> <dup+1>`, both per-name
    counters. SDL3_FALLBACK_NAMES alone collapses 054c:05c4, 054c:09cc and
    054c:0ba0 onto "PS4 Controller", so a DualShock 4 v1 and a v2 both got
    dup 0 — GCPad1 and GCPad2 pointed at `SDL/0/PS4 Controller`, one pad drove
    two ports and the other was dead. Ryujinx counts by GUID, where the name is
    at least as fine-grained, so counting by name is safe for it too.
    """
    return {key: sum(1 for k2, (slot2, name2) in roster.items()
                     if k2 != key and name2 == name and slot2 < slot)
            for key, (slot, name) in roster.items()}



def _game_running() -> bool:
    """True while an emulator is up. Imported late: process_manager pulls in the
    database and the websocket layer, and this module is imported at startup."""
    try:
        from . import process_manager
        return process_manager.process_manager.is_running
    except Exception:      # never let a bookkeeping question break reconciliation
        return False

async def _reconcile(was: dict[str, tuple[str, str, str, int]],
                     live: dict[str, tuple[str, str, str, int]],
                     applied: dict[str, tuple[tuple[str, str, str, int] | None, int]],
                     first_scan: bool, ws) -> None:
    """Bring every player slot in line with the pads that are actually here.

    Only the arriving pad used to be profiled, and only the leaving pad's slot
    was released. But the strings these emulators store are relative to the
    whole roster — Dolphin's `SDL/<dup>/<name>`, RPCS3's `<name> <dup+1>`,
    Ryujinx's `<dup>-<GUID>` — so a departure silently invalidates the
    survivors' configs. Player 1's pad running out of battery mid-session left
    player 2 holding a `dup` that no longer described anything, and the next
    launch of Dolphin found port 1 pinned to a controller that had left.

    Reconciling the whole roster whenever it changes fixes that class of bug
    rather than its instances, and it is the only way a slot ever gets a second
    chance: the old code profiled a pad exactly once, when `known` was False.
    """
    # Departures first: their slots must be free before dup indexes are recomputed.
    #
    # No release_profile() here any more. It used to hang off this loop, which
    # meant a slot was only ever freed for a departure this process WITNESSED —
    # and worse, it named the slot the pad held before compact() moved anyone.
    # The sweep below decides from the roster instead, which is the thing that
    # actually says whether a slot is occupied.
    for key in [k for k in was if k not in live]:
        applied.pop(key, None)
        label = controller_registry.label_for(key)
        player = controller_registry.disconnect(key)
        if player is None:
            continue
        log.info("gamepad_monitor: controller %d disconnected (%s)", player, label)
        try:
            await ws.broadcast("gp:disconnected", {"player": player, "label": label})
        except Exception:
            log.exception("gamepad_monitor: error broadcasting gp:disconnected")

    # Close up the gap a departure leaves, but only between games. Slots are
    # never taken back from a connected pad, so unplugging player 1 during
    # co-op left the survivor on slot 2 for good — and a Switch game asking for
    # Player 1 then found nobody. Doing it mid-session would be worse: the
    # remaining player would silently become someone else.
    #
    # The pads that move are re-profiled on their own, because the player
    # number is part of the footprint.
    if not _game_running():
        for key, (old_slot, new_slot) in controller_registry.compact().items():
            log.info("gamepad_monitor: player %d → %d (%s)", old_slot, new_slot,
                     controller_registry.label_for(key))

    arrivals = [k for k in live if not controller_registry.has(k)]
    roster: dict[str, tuple[int, str]] = {}
    for key, (vendor, product, evdev_name, _bus) in live.items():
        player = controller_registry.connect(key, evdev_name)
        roster[key] = (player, controller_profiles.resolve_name(vendor, product, evdev_name))

    # Free every slot no pad holds, on EVERY inventory change — not only on a
    # departure. This is the reboot hole, and it is the one the reference box
    # was sitting in: someone plays at four, powers the box off, unplugs three
    # pads, powers it back on. `was` is empty at startup, so those three
    # departures produce no event at all and their slots were never released.
    # With one DualShock 4 connected the box showed RPCS3 players 2-4 naming
    # Xbox pads, Ryujinx holding indexes 2 and 3, and Dolphin's GCPad4 on
    # SDL/3 — four players, three of them ghosts.
    #
    # Before the profiling loop, so a slot is freed before anything claims it,
    # and passing the whole remaining roster because some of what was written
    # is not per-slot: the PS1/PS2 multitap is on while ANY player at or above
    # slot 3 is here, which no single index can answer.
    occupied = {player for player, _name in roster.values()}
    for slot in range(1, controller_profiles.MAX_PLAYERS + 1):
        if slot in occupied:
            continue
        try:
            released = await asyncio.to_thread(
                controller_profiles.release_profile, slot, occupied)
            if released:
                log.info("gamepad_monitor: slot %d freed — %s",
                         slot, "; ".join(released))
        except Exception:
            log.exception("gamepad_monitor: release_profile failed for slot %d", slot)

    # Which systems this pass gave up on, per pad, for the arrival toast below.
    # The profiling loop is the only place that knows, and it runs before the
    # loop that speaks to the player — so the answer has to be carried, not
    # recomputed. Re-profiling to find out would double every SDL probe.
    unconfigured: dict[str, list[str]] = {}

    for key, dup in dup_indexes(roster).items():
        vendor, product, evdev_name, bustype = live[key]
        player, name = roster[key]
        # Everything that decides what gets written. The player number belongs
        # here — a pad moving slot rewrites different sections — and so does
        # the transport, which an SDL GUID encodes.
        footprint = (player, vendor, product, name, dup, bustype)
        prev, retries = applied.get(key, (None, 0))
        # Settled: this exact footprint was configured cleanly, or it failed
        # often enough that retrying is just burning SDL probes every 3 s.
        if prev == footprint and retries <= 0:
            continue
        if prev != footprint:
            retries = PROFILE_RETRIES   # new pad, or it moved slot — full budget
        # Claimed before the attempt so a raise cannot loop forever, but with
        # one retry spent rather than the whole thing marked done.
        applied[key] = (footprint, retries - 1)
        try:
            results = await asyncio.to_thread(
                controller_profiles.apply_profile, player, vendor, product, evdev_name, dup)
            # Log both outcomes. `if results:` alone meant a pass that
            # configured nothing looked exactly like one that never ran —
            # apply_profile details the give-ups itself, but the "0 emulators"
            # headline belongs here.
            log.info("gamepad_monitor: player %d profiled (%s, %s:%s, dup %d) — %s",
                     player, name, vendor, product, dup,
                     "; ".join(results) if results else "no emulator configured")
            unconfigured[key] = list(getattr(results, "skipped_labels", ()))
            if getattr(results, "complete", True):
                applied[key] = (footprint, 0)          # done, stop asking
            elif retries - 1 <= 0:
                # Out of budget. Say so once, here, rather than leaving the
                # owner to notice months later that one emulator never got a
                # slot — apply_profile has already logged which ones and why.
                log.warning("gamepad_monitor: player %d (%s) still incomplete after "
                            "%d attempts — giving up until it reconnects",
                            player, name, PROFILE_RETRIES)
        except Exception:
            log.exception("gamepad_monitor: controller_profiles failed for player %d", player)

    if not first_scan:
        for key in arrivals:
            player, _name = roster[key]
            vendor, product, label, _bus = live[key]
            log.info("gamepad_monitor: controller %d connected (%s)", player, label)
            # P1 made the give-up visible in the journal and at "Scan mapping".
            # Neither is where the player is standing: they have just plugged a
            # pad in and it does not work. The toast is, and until now it said
            # "Controller 2 connected" in green for a controller that is dead in
            # every emulator matching a device by name.
            #
            # Asked through P1's own `identification`, not by matching the skip
            # strings: one source of truth for "can this pad be named", and it
            # is the exact condition the wizard answers.
            unmapped = False
            try:
                unmapped = not (await asyncio.to_thread(
                    controller_profiles.identification, vendor, product, label)
                )["identified"]
            except Exception:
                # A pad arriving is news whatever we can work out about it.
                # Letting this question take the toast down with it would
                # silence precisely the pad we understand least.
                log.exception("gamepad_monitor: could not tell whether %s:%s "
                              "is identified", vendor, product)
            # A pad can be perfectly identified and STILL be left out of one
            # emulator — the reference box's Xbox pad was, on the Switch alone,
            # while every other system bound it. `unmapped` cannot say so: it
            # answers "can this pad be named", which was true. So the toast was
            # the green "Controller 1 connected" and the only trace of the
            # give-up was a journal line nobody reads from a sofa.
            #
            # A system missing from one console out of thirteen is exactly the
            # fault that is undiagnosable from the couch, and it is silent by
            # construction: the game simply does not answer the pad.
            try:
                await ws.broadcast("gp:connected",
                                   {"player": player, "label": label,
                                    "vendor": vendor, "product": product,
                                    "unmapped": unmapped,
                                    "unconfigured": unconfigured.get(key, [])})
            except Exception:
                log.exception("gamepad_monitor: error broadcasting gp:connected")


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
    # registry key → the (vendor, product, resolved name, dup) an emulator
    # config was last written for, and how many attempts that footprint has
    # left. A slot is re-profiled when its footprint changes, which is what
    # makes the roster self-correcting — and now also when the last pass left
    # an emulator unconfigured, until the budget runs out.
    applied: dict[str, tuple[tuple[str, str, str, int] | None, int]] = {}
    live: dict[str, tuple[str, str, str]] = {}
    # Pads already plugged in when the backend starts get their slots
    # silently — a console doesn't toast for pads that were always there.
    first_scan = True

    while True:
        devices = _find_gamepad_devices()
        current = set(devices)

        # Watch every device that declares a Guide button or is a pad. This is
        # about the guide shortcut only; player slots are decided below, from
        # the device list rather than from which watchers happen to be alive.
        for path in sorted(current - set(watched), key=_event_sort_key):
            watched[path] = asyncio.create_task(_watch_device(path), name=f"gpad:{path}")
        for path in [p for p, t in watched.items() if t.done()]:
            del watched[path]      # gone, or errored: re-watched next pass if still there

        was, live = live, pads_by_key(devices)
        # `was != live` alone would never give a failed pass its retry: nothing
        # about the pad changes when SDL merely has not caught up with it yet.
        pending = any(retries > 0 for _, retries in applied.values())
        if was != live or pending:
            await _reconcile(was, live, applied, first_scan, ws)
        first_scan = False
        await asyncio.sleep(3)


def _can_read(path: str) -> bool:
    try:
        import os
        return os.access(path, os.R_OK)
    except Exception:
        return False
