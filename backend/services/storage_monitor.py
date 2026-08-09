"""Reacting to a disk being plugged in, and to one being pulled out.

`storage.py` answers "what is attached and where did it land". This decides
what to DO about a change: mount an arrival, re-point its stable link, and tell
the frontend — so a disk full of ROMs appears on the grid without anyone
restarting anything.

Nothing is invalidated on the way, and that is not an omission. A system's
games are scanned per request from its `romsPath`, and `romsPath` points at the
stable link rather than at a mount point — so the moment the link is re-pointed
the next scan already reads the new disk. There is no cached library to clear,
and adding a hook for one that does not exist would be a line nobody could ever
prove still works.

Polled, at STORAGE_POLL seconds. udev would be event-driven and is the obvious
alternative; it is not used here for one reason worth writing down: reaching
udev events from the backend means either a netlink socket the process must
hold open with the right group membership, or a rule in `/etc/udev/rules.d`
that runs something as root on every device change. Both are a privilege the
box does not currently need, to save a few seconds on an event that happens
when a human walks across a room. `lsblk` costs one short-lived subprocess and
needs nothing.

**Departure is the normal case, not the error case.** A living-room box gets
its disk pulled mid-game sooner or later, and pulled without warning is the
default rather than the exception. So every branch here assumes the path may
already be gone: nothing stats a mount to decide whether it left, nothing
raises when it has, and the scanner is told to forget rather than asked to
re-read.
"""
from __future__ import annotations

import asyncio
import logging

from . import storage

log = logging.getLogger(__name__)

# A human plugging a disk in will wait a couple of seconds without noticing.
# Shorter buys nothing and spends a subprocess; longer reads as "it did not
# work" and gets the cable pulled and re-inserted, which is the one thing that
# actually confuses udisks.
STORAGE_POLL = 3.0


def _index(volumes: list[storage.Volume]) -> dict[str, storage.Volume]:
    """Device path → volume. Keyed on `/dev/...` because that is what survives
    a mount point changing, which is exactly what this loop is watching for."""
    return {v.path: v for v in volumes}


async def _announce(ws, event: str, payload: dict) -> None:
    """Broadcasting must never take the loop down: a websocket layer that is
    momentarily unhappy would otherwise stop the box noticing disks at all."""
    try:
        await ws.broadcast(event, payload)
    except Exception:
        log.exception("storage_monitor: could not broadcast %s", event)


async def _on_arrival(volume: storage.Volume, ws, runner=None) -> storage.Volume:
    """Mount it if it is not mounted, then give it its stable path."""
    if not volume.is_mounted:
        ok, detail = await asyncio.to_thread(storage.mount, volume, runner)
        if not ok:
            log.warning("storage_monitor: could not mount %s (%s) — %s",
                        volume.path, volume.label or "no label", detail)
            await _announce(ws, "storage:failed",
                            {"device": volume.path, "label": volume.label,
                             "detail": detail})
            return volume
        # Re-read rather than assume: the mount point is udisks's choice, and
        # guessing it is precisely the mistake the stable link exists to undo.
        for fresh in await asyncio.to_thread(storage.list_volumes, runner):
            if fresh.path == volume.path:
                volume = fresh
                break

    link = await asyncio.to_thread(storage.link_volume, volume)
    log.info("storage_monitor: %s (%s) mounted at %s",
             volume.path, volume.label or "no label", volume.mountpoint)
    payload = storage.describe(volume)
    payload["stable_path"] = str(link) if link else ""
    await _announce(ws, "storage:mounted", payload)
    return volume


async def _on_departure(volume: storage.Volume, ws) -> None:
    """A disk that is no longer attached, or no longer mounted.

    The order matters: the running game is checked BEFORE the link is dropped,
    because a player whose disk has just gone mid-session needs to be told what
    happened more than the box needs its symlink tidy.
    """
    running = _running_game()
    if running and storage.path_is_under(running.get("rom_path", ""), volume.mountpoint):
        # The one case that is genuinely bad and cannot be repaired from here.
        # The emulator holds an open file descriptor on a device that is gone:
        # it will fail on its next read, and — the part that costs something —
        # its next save will not land. Saying so beats a freeze with no
        # explanation, which is what this looked like before.
        log.error("storage_monitor: %s was removed while %s was running from it",
                  volume.mountpoint, running.get("game_key") or "a game")
        await _announce(ws, "storage:lost", {
            "device": volume.path,
            "label": volume.label,
            "mountpoint": volume.mountpoint,
            "game_key": running.get("game_key", ""),
            "system_id": running.get("system_id", ""),
            "detail": (f"{volume.label or volume.path} was removed while a game "
                       "was running from it. Progress since the last save is "
                       "very likely lost — plug the disk back in before saving "
                       "again."),
        })

    await asyncio.to_thread(storage.unlink_volume, volume)
    log.info("storage_monitor: %s (%s) is gone", volume.path, volume.label or "no label")
    await _announce(ws, "storage:removed",
                    {"device": volume.path, "label": volume.label,
                     "mountpoint": volume.mountpoint})


def _running_game() -> dict | None:
    """The game that is up, or None. Never raises — this is a question asked
    while a disk is disappearing, and it must not be able to make that worse."""
    try:
        from . import process_manager
        return process_manager.process_manager.current_game
    except Exception:
        return None


async def poll_once(was: dict[str, storage.Volume], ws, runner=None
                    ) -> dict[str, storage.Volume]:
    """One comparison pass. Returns the new state.

    Split out of `run()` so the whole behaviour is reachable from a test
    without a sleep loop, a real disk or a real subprocess — `runner` is a
    double, and what is asserted is the argv and the broadcasts.
    """
    live = _index(await asyncio.to_thread(storage.list_volumes, runner))

    # list() because _on_arrival re-reads the volume after mounting it and the
    # result is written back into `live` — rebinding a value mid-iteration is
    # legal today and one refactor away from being a RuntimeError.
    for path, volume in list(live.items()):
        previous = was.get(path)
        # An arrival is a device that is new, OR one that was here and has just
        # been mounted. Treating only the first as an arrival is why a disk
        # mounted by hand from a file manager never got its stable link.
        if previous is None or (volume.is_mounted and not previous.is_mounted):
            live[path] = await _on_arrival(volume, ws, runner)

    for path, volume in was.items():
        gone = path not in live
        unmounted = not gone and volume.is_mounted and not live[path].is_mounted
        if (gone or unmounted) and volume.is_mounted:
            await _on_departure(volume, ws)

    return live


async def run() -> None:
    """Watch for disks arriving and leaving, for as long as the box is up."""
    from .. import ws

    log.info("storage_monitor: started (every %.0fs)", STORAGE_POLL)

    # Links left over from a session that ended with the disk attached: the box
    # was powered off and came up without it, so nothing generated a departure.
    # The link still resolves, is still a directory, and scans zero games —
    # which reads exactly like a library that has lost its contents.
    live: dict[str, storage.Volume] = {}
    try:
        attached = await asyncio.to_thread(storage.list_volumes)
        for stale in await asyncio.to_thread(storage.stale_links, attached):
            try:
                stale.unlink()
                log.info("storage_monitor: dropped stale link %s", stale)
            except OSError:
                log.warning("storage_monitor: could not drop stale link %s", stale)

        # Only the ALREADY-MOUNTED disks are adopted into the starting state,
        # and that asymmetry is the point. Adopting an unmounted one too would
        # make it identical to itself on the first poll — no arrival, so never
        # mounted — and a disk left plugged in across a reboot would come back
        # invisible until someone unplugged and replugged it.
        for volume in attached:
            if volume.is_mounted:
                # Re-linked but NOT announced: a box coming up with its disk in
                # is not news, and a toast at every boot is how a player learns
                # to ignore the one that matters.
                await asyncio.to_thread(storage.link_volume, volume)
                live[volume.path] = volume
    except Exception:
        log.exception("storage_monitor: startup sweep failed")

    while True:
        try:
            live = await poll_once(live, ws)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("storage_monitor: poll failed — retrying")
        await asyncio.sleep(STORAGE_POLL)
