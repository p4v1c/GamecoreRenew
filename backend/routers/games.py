"""Game scanning, launching, and session management."""
import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import ws
from ..config import resolve_path
from ..services import (
    bios,
    controller_profiles,
    controller_registry,
    fullscreen_enforcer,
    local_media,
    usb_devices,
)
from ..services import process_manager as process_manager_module
from ..services.catalog import launch as catalog_launch
from ..services.process_manager import process_manager
from ..services.rom_scanner import clean_name, iter_rom_files
from .systems import list_all

log = logging.getLogger(__name__)


async def _gamepad_trigger(rounds: int = 3, delay: float = 3.0) -> None:
    """Run 'sudo udevadm trigger' several times so Flatpak apps detect the gamepad.

    Named for pads because pads were all it ever ran for, and that was the hole:
    the flag is `launch.gamepadTrigger`, only Stremio set it, and every reason
    it exists applies word for word to a GameCube adapter. A device plugged in
    after the sandbox started stayed invisible until the game was quit and
    relaunched — which from a sofa is an accessory that does not work.

    `udevadm trigger` with no filter re-fires the whole tree, so nothing about
    the command had to change. What changed is WHO gets to ask for it: any pack
    that declares `usb` does now, without having to claim to be about gamepads.
    """
    for i in range(rounds):
        await asyncio.sleep(delay)
        try:
            proc = await asyncio.create_subprocess_exec(
                "sudo", "udevadm", "trigger",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            log.info("gamepad_trigger: round %d/%d done", i + 1, rounds)
        except Exception:
            log.warning("gamepad_trigger: round %d failed", i + 1, exc_info=True)

# A launch must never wait on config housekeeping. The work below is a few
# small file reads and at most one rewrite per emulator, so it lands in
# milliseconds — but a stalled NFS home or a flatpak directory that has gone
# away must cost the player a slightly stale config, never a game that will not
# start. Generous next to the real cost, tight next to a player's patience.
RECONCILE_BUDGET = 0.2


async def _free_stale_slots(system_id: str) -> None:
    """Drop slots no pad holds, for the emulator about to start.

    Launch is the one moment where the inventory is certainly complete and the
    emulator is about to re-read its config, so it catches whatever the hotplug
    events missed — a pad that died between two scans, a scan that failed, a
    box that came up with `evdev` briefly unreadable.

    Deliberately the RELEASE half only, and not a full re-profile:

      · writing a profile means asking SDL for names and GUIDs, and those probes
        carry an 8 s timeout apiece. That does not belong in front of a launch,
        and the monitor already retries them on its own budget.
      · reading the registry is a pure lookup with no SDL in it at all, so this
        pass is file I/O and nothing else.

    So this fixes a slot that names a pad which is NOT there. It does not create
    one for a pad that is there and was never profiled — that stays the
    monitor's job, on its three-second loop.

    Scoped to the one pack being launched: rewriting Cemu because someone
    started PCSX2 is a side effect nobody asked for.

    Never raises. Every failure here is a config left as it was, which is a
    playable game; an exception would be a game that does not start.
    """
    try:
        occupied = {c["player"] for c in controller_registry.snapshot()}

        def sweep() -> list[str]:
            done: list[str] = []
            for slot in range(1, controller_profiles.MAX_PLAYERS + 1):
                if slot not in occupied:
                    done += controller_profiles.release_profile(
                        slot, occupied, pack_ids=(system_id,))
            return done

        freed = await asyncio.wait_for(asyncio.to_thread(sweep),
                                       timeout=RECONCILE_BUDGET)
        if freed:
            log.info("launch: %s — freed stale slots: %s",
                     system_id, "; ".join(freed))
    except TimeoutError:
        # Abandoned, not retried: the launch is what matters, and the monitor
        # will come back to it within three seconds anyway.
        log.warning("launch: %s — slot cleanup exceeded %.0f ms, launching "
                    "with the config as it is", system_id, RECONCILE_BUDGET * 1000)
    except Exception:
        log.exception("launch: %s — slot cleanup failed, launching anyway",
                      system_id)


router = APIRouter(tags=["games"])


def scan_roms(roms_path: Path, extensions: list[str], scan_dirs: bool = False,
              system_id: str = "") -> list[dict]:
    files = []
    for f in iter_rom_files(roms_path, extensions, scan_dirs=scan_dirs):
        try:
            stat = f.stat()
        except OSError:
            # Broken symlink or vanished file — skip it instead of turning
            # the whole library listing into a 500.
            continue
        # Folder-based games (PS3/PS4) embed their real title — prefer it over
        # the folder name, which is often just a serial like BLES01234.
        title = local_media.get_title(system_id, f) if scan_dirs and system_id else None
        files.append({
            "filename": f.name,
            "display_name": title or clean_name(f.name),
            "path": str(f),
            "size": stat.st_size,
            "ext": "FOLDER" if f.is_dir() else f.suffix.lstrip(".").upper(),
        })
    return files


@router.get("/systems/{system_id}/games")
def list_games(system_id: str):
    system = next((s for s in list_all() if s["id"].lower() == system_id.lower()), None)
    if not system:
        raise HTTPException(404, "System not found")

    if system.get("kind") == "app" or system.get("type") == "application":
        return []

    roms_raw = system.get("romsPath", "")
    if not roms_raw:
        return []

    roms_path = resolve_path(roms_raw)
    if not roms_path:
        return []

    return scan_roms(roms_path, system.get("extensions", []),
                     scan_dirs=system.get("scanDirs", False), system_id=system["id"])


class LaunchRequest(BaseModel):
    system_id: str
    rom_path: str = ""
    game_key: str = ""


@router.post("/games/launch")
async def launch_game(req: LaunchRequest):
    system = next((s for s in list_all() if s["id"].lower() == req.system_id.lower()), None)
    if not system:
        raise HTTPException(404, "System not found")

    if process_manager.is_running:
        raise HTTPException(409, "A game is already running")

    # Validate rom_path stays inside the system's configured ROMs directory.
    # Prevents launching arbitrary executables via crafted relative/absolute paths.
    if req.rom_path:
        roms_root = resolve_path(system.get("romsPath", ""))
        if not roms_root:
            raise HTTPException(400, "System has no ROMs path configured")
        try:
            Path(req.rom_path).resolve().relative_to(roms_root.resolve())
        except ValueError:
            raise HTTPException(403, "ROM path is outside the system's ROMs directory")

    exec_path = system.get("path", "")
    exec_args = system.get("args", "")
    game_key = req.game_key or (Path(req.rom_path).name if req.rom_path else system["id"])

    # The tile names no Flatpak app id — it defers to the catalogue, which is
    # what lets a dead upstream be corrected without rewriting every box's
    # systems.json. Resolved here, against what is installed right now.
    try:
        exec_args = catalog_launch.resolve_args(system["id"], exec_args)
    except LookupError as e:
        log.warning("launch refused — %s", e)
        try:
            await ws.broadcast("game:failed", {
                "game_key": game_key, "system_id": req.system_id, "detail": str(e),
            })
        except Exception:
            log.exception("launch: failed to broadcast game:failed")
        raise HTTPException(424, str(e))

    # Before the emulator, not after. Without a required BIOS, PCSX2 starts and
    # sits on a black screen: the player sees a game that launched and did
    # nothing, which is indistinguishable from a broken dump, a broken pad or a
    # broken box. Refusing here costs the same second and names the file.
    #
    # Only ABSENT stops a launch — never a hash. An owner running a dump this
    # catalogue does not record has a working emulator, and blocking them would
    # be GameCore inventing a fault. `bios.launch_blocker` never raises: a
    # check that cannot run is a game that starts.
    if blocker := bios.launch_blocker(req.system_id):
        log.warning("launch refused — %s", blocker)
        try:
            await ws.broadcast("game:failed", {
                "game_key": game_key, "system_id": req.system_id, "detail": blocker,
            })
        except Exception:
            log.exception("launch: failed to broadcast game:failed")
        raise HTTPException(424, blocker)

    # Beside the BIOS gate, and deliberately NOT one of them: a declared USB
    # accessory that is absent is said out loud and the game starts anyway.
    #
    # An accessory is optional by nature — Dolphin plays perfectly with a
    # DualShock 4 and no GameCube adapter — so refusing here would be GameCore
    # inventing a fault, which is the mistake `bios.required: false` exists to
    # avoid. But saying nothing is how "my adapter does not work" becomes a
    # phone call: the owner cannot tell an adapter that is unplugged from one
    # the sandbox cannot see, and both look like a game that ignores it.
    #
    # Before the launch attempt rather than after, so an emulator that then
    # fails to start does not swallow the one sentence that explains the box.
    if notice := usb_devices.launch_notice(req.system_id):
        log.info("launch: %s", notice)
        try:
            await ws.broadcast("game:notice", {
                "game_key": game_key, "system_id": req.system_id, "detail": notice,
            })
        except Exception:
            log.exception("launch: failed to broadcast game:notice")

    # Before launch, not after: the emulator reads its input config at startup,
    # so a slot freed a moment later is a slot the running game still sees.
    await _free_stale_slots(req.system_id)

    try:
        await process_manager.launch(
            exec_path=exec_path,
            exec_args=exec_args,
            rom_path=req.rom_path,
            game_key=game_key,
            system_id=req.system_id,
        )
    except (FileNotFoundError, PermissionError) as e:
        # The emulator is not installed, or is not executable. This used to
        # escape as a bare 500 with an empty body: no reason on screen, and no
        # WebSocket event either, so the UI sat on its loading screen until
        # someone pressed Back. _launching is released by launch()'s finally,
        # so retrying works — the player just had no idea what happened.
        detail = (f"{system['id']}: cannot start {exec_path!r} — "
                  + ("not installed" if isinstance(e, FileNotFoundError) else "not executable"))
        log.warning("launch failed — %s", detail)
        # X may have moved under us; make the next launch re-probe rather than
        # reuse a display that no longer answers.
        process_manager_module.invalidate_display_cache()
        try:
            await ws.broadcast("game:failed", {
                "game_key": game_key, "system_id": req.system_id, "detail": detail,
            })
        except Exception:
            log.exception("launch: failed to broadcast game:failed")
        raise HTTPException(503, detail)

    # A pack declaring `usb` wants the same re-fire, for the same reason — see
    # _gamepad_trigger. `or`, not a second task: two overlapping trigger loops
    # would be six `udevadm trigger` calls on a box that asked for three.
    if system.get("gamepadTrigger") or system.get("usb"):
        task = asyncio.create_task(_gamepad_trigger())
        task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)

    fs_cfg = system.get("fullscreen")
    if fs_cfg:
        fs_task = asyncio.create_task(fullscreen_enforcer.enforce(req.system_id, fs_cfg))
        fs_task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)

    return {"ok": True, "game_key": game_key}


@router.post("/games/kill")
async def kill_game():
    await process_manager.kill()
    return {"ok": True}


@router.get("/games/session")
def get_session():
    return process_manager.current_game or {}
