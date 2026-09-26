"""Launching a game or app: every gate and preparation step before the spawn.

The router looks the system up; `LaunchRefused` becomes the HTTP error in main.py;
everything else — conflicts, BIOS/USB gates, controller and per-game config,
the spawn itself — is decided here.
"""
import asyncio
import logging
import time
from pathlib import Path

from .. import ws
from ..config import resolve_path
from . import (
    bios,
    configgen,
    controller_profiles,
    controller_registry,
    fullscreen_enforcer,
    gamepad_monitor,
    pergame,
    session,
    standby,
    usb_devices,
)
from .catalog import launch as catalog_launch
from .errors import ServiceError
from .catalog import load_catalog
from .process_manager import SessionConflict, process_manager

log = logging.getLogger(__name__)

# Budget for config housekeeping in front of a launch. A stalled disk must cost
# a slightly stale config, never a game that will not start.
RECONCILE_BUDGET = 0.2

# How long a launch waits for a connected but not-yet-profiled pad. A cold
# apply_profile measured 6.36 s on the reference box; emulators read input
# config once at startup, so a shorter wait loses the race (pad dead in game).
PROFILE_BUDGET = 8.0

# prepare_launch hooks (RPCS3 settings + patches) take ~100 ms warm, far more
# cold. The hook gets a deadline and writes nothing it cannot finish.
PACK_PREPARE_BUDGET = 3.0


class LaunchRefused(ServiceError):
    """The launch did not happen."""


def _is_app(system: dict) -> bool:
    return system.get("kind") == "app" or system.get("type") == "application"


async def _broadcast(event: str, game_key: str, system_id: str, detail: str) -> None:
    try:
        await ws.broadcast(event, {
            "game_key": game_key, "system_id": system_id, "detail": detail,
        })
    except Exception:
        log.exception("launch: failed to broadcast %s", event)


async def _gamepad_trigger(rounds: int = 3, delay: float = 3.0) -> None:
    """Re-fire udev a few times so a sandboxed app sees devices plugged in late.

    Runs for `launch.gamepadTrigger` and for any pack declaring `usb`.
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


async def _await_controller_profiles(system_id: str, game_key: str) -> None:
    """Wait (up to PROFILE_BUDGET) until every connected pad has its config.

    Waits, never profiles: SDL probes carry an 8 s timeout each. Costs nothing
    once the roster is settled. Never raises; a timeout launches anyway and
    tells the player via `game:notice`.
    """
    try:
        started = asyncio.get_running_loop().time()
        pending = await gamepad_monitor.await_profiled(PROFILE_BUDGET)
        waited = asyncio.get_running_loop().time() - started
        if not pending:
            if waited > 0.05:
                log.info("launch: %s — waited %.1f s for the controller to be "
                         "profiled", system_id, waited)
            return
        detail = (f"{', '.join(sorted(set(pending)))} was not configured in "
                  f"time — if it does not work in game, quit and start again")
        log.warning("launch: %s — %s (waited %.1f s)", system_id, detail, waited)
        await _broadcast("game:notice", game_key, system_id, detail)
    except Exception:
        log.exception("launch: %s — could not check controller profiling, "
                      "launching anyway", system_id)


async def _free_stale_slots(system_id: str) -> None:
    """Release slots no pad holds, for the pack about to start only.

    Release only (pure file I/O, no SDL); profiling a present pad stays the
    monitor's job. Never raises: a failure leaves a playable config.
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
        # Not retried: the monitor comes back within three seconds.
        log.warning("launch: %s — slot cleanup exceeded %.0f ms, launching "
                    "with the config as it is", system_id, RECONCILE_BUDGET * 1000)
    except Exception:
        log.exception("launch: %s — slot cleanup failed, launching anyway",
                      system_id)


async def _place_per_game_config(system_id: str, rom_path: str) -> None:
    """Write this game's own settings before the emulator reads them.

    Bounded by RECONCILE_BUDGET: identifying the game may hit a cold disc or
    NFS. A missing per-game tweak is fine; a game that will not start is not.
    """
    try:
        placed = await asyncio.wait_for(
            asyncio.to_thread(pergame.materialise, system_id, rom_path,
                              configgen.HOME),
            timeout=RECONCILE_BUDGET)
        if placed:
            log.info("launch: %s", placed)
    except TimeoutError:
        log.warning("launch: %s — per-game config exceeded %.0f ms, launching "
                    "with the config as it is", system_id, RECONCILE_BUDGET * 1000)
    except Exception:
        log.exception("launch: %s — per-game config failed, launching anyway",
                      system_id)


async def _prepare_pack_launch(system_id: str, rom_path: str, exec_path: str,
                               exec_args: str, game_key: str) -> None:
    """Call the pack's `prepare_launch(...)` hook in generator.py, if any.

    Pack-specific logic stays in catalog/<id>/. Its `notice` goes out as
    `game:notice`.
    """
    try:
        pack = load_catalog().get(system_id.lower())
        module = configgen.load_generator(pack) if pack else None
        hook = getattr(module, "prepare_launch", None)
        if hook is None:
            return
        deadline = time.monotonic() + PACK_PREPARE_BUDGET
        result = await asyncio.wait_for(
            asyncio.to_thread(hook, rom_path=rom_path, home=configgen.HOME,
                              exec_path=exec_path, exec_args=exec_args,
                              deadline=deadline),
            timeout=PACK_PREPARE_BUDGET + 0.5)
        detail = (result or {}).get("notice")
        if detail:
            log.info("launch: %s", detail)
            await _broadcast("game:notice", game_key, system_id, detail)
    except TimeoutError:
        log.warning("launch: %s — pack preparation exceeded %.1f s, launching "
                    "as things are", system_id, PACK_PREPARE_BUDGET)
    except Exception:
        log.exception("launch: %s — pack preparation failed, launching anyway",
                      system_id)


def _check_rom_path(system: dict, rom_path: str) -> None:
    """The ROM must sit inside the system's ROMs directory (no arbitrary exec)."""
    roms_root = resolve_path(system.get("romsPath", ""))
    if not roms_root:
        raise LaunchRefused(400, "System has no ROMs path configured")
    try:
        Path(rom_path).resolve().relative_to(roms_root.resolve())
    except ValueError:
        raise LaunchRefused(403, "ROM path is outside the system's ROMs directory")


async def _resume_or_refuse(system: dict, system_id: str, game_key: str) -> dict | None:
    """One game at a time: the same suspended game resumes, another is refused.

    Runs before any launch side effect. Apps may coexist with a suspended game.
    """
    if _is_app(system):
        return None
    held_games = [s for s in process_manager.background_sessions if not s.is_app]
    same = next((s for s in held_games
                 if s.game_key == game_key and s.system_id == system_id), None)
    if same is not None:
        try:
            state = await process_manager.foreground(same.session_id)
        except SessionConflict as e:
            raise LaunchRefused(409, str(e)) from e
        return {"ok": True, "game_key": game_key, "resumed": True, **state}
    if held_games:
        title = held_games[0].game_key or "another game"
        raise LaunchRefused(
            409,
            f"Another game is still running ({title}). Close it before "
            "starting a different game",
        )
    return None


async def _gates(system: dict, system_id: str, exec_args: str, game_key: str) -> str:
    """Resolve launch args and run the refuse/notify gates. Returns final args."""
    # The tile defers its Flatpak app id to the catalogue, resolved now.
    try:
        exec_args = await asyncio.to_thread(catalog_launch.resolve_args, system["id"], exec_args)
    except LookupError as e:
        log.warning("launch refused — %s", e)
        await _broadcast("game:failed", game_key, system_id, str(e))
        raise LaunchRefused(424, str(e))

    # A missing required BIOS = black screen that looks like a broken dump.
    # Only ABSENT blocks, never a hash mismatch.
    if blocker := bios.launch_blocker(system_id):
        log.warning("launch refused — %s", blocker)
        await _broadcast("game:failed", game_key, system_id, blocker)
        raise LaunchRefused(424, blocker)

    # A missing USB accessory is announced, never blocking.
    if notice := usb_devices.launch_notice(system_id):
        log.info("launch: %s", notice)
        await _broadcast("game:notice", game_key, system_id, notice)
    return exec_args


async def _prepare(system_id: str, rom_path: str, exec_path: str,
                   exec_args: str, game_key: str) -> None:
    """Everything the emulator must find on disk when it starts."""
    # A launch may come from the LAN while the box sleeps; a dark screen with
    # standby still armed swallows gp:guide, the only way out of a game.
    await standby.exit_standby()
    # Emulators read input config once at startup: the profile write must have
    # landed before the stale-slot sweep and before the spawn.
    await _await_controller_profiles(system_id, game_key)
    await _free_stale_slots(system_id)
    if rom_path:
        await _place_per_game_config(system_id, rom_path)
        await _prepare_pack_launch(system_id, rom_path, exec_path, exec_args, game_key)


async def _spawn(system: dict, system_id: str, rom_path: str, exec_path: str,
                 exec_args: str, game_key: str) -> bool:
    try:
        return await process_manager.launch(
            exec_path=exec_path,
            exec_args=exec_args,
            rom_path=rom_path,
            game_key=game_key,
            system_id=system_id,
        )
    except SessionConflict as e:
        # The resident cap; the manager's message names what to close.
        log.info("launch refused — %s", e)
        raise LaunchRefused(409, str(e)) from e
    except (FileNotFoundError, PermissionError) as e:
        detail = (f"{system['id']}: cannot start {exec_path!r} — "
                  + ("not installed" if isinstance(e, FileNotFoundError) else "not executable"))
        log.warning("launch failed — %s", detail)
        # X may have moved; force the next launch to re-probe the display.
        session.invalidate_display_cache()
        await _broadcast("game:failed", game_key, system_id, detail)
        raise LaunchRefused(503, detail)


def _start_background_tasks(system: dict, system_id: str) -> None:
    # One trigger loop, not two: `or`.
    if system.get("gamepadTrigger") or system.get("usb"):
        task = asyncio.create_task(_gamepad_trigger())
        task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
    fs_cfg = system.get("fullscreen")
    if fs_cfg:
        fs_task = asyncio.create_task(fullscreen_enforcer.enforce(system_id, fs_cfg))
        fs_task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)


async def launch(system: dict, system_id: str, rom_path: str, game_key: str) -> dict:
    """Launch `rom_path` (or the app) for `system`. Raises LaunchRefused."""
    # A second thing on the screen is always refused.
    if process_manager.is_foreground:
        raise LaunchRefused(409, "A game is already running")
    if rom_path:
        _check_rom_path(system, rom_path)

    exec_path = system.get("path", "")
    game_key = game_key or (Path(rom_path).name if rom_path else system["id"])

    resumed = await _resume_or_refuse(system, system_id, game_key)
    if resumed is not None:
        return resumed

    exec_args = await _gates(system, system_id, system.get("args", ""), game_key)
    await _prepare(system_id, rom_path, exec_path, exec_args, game_key)
    resumed_flag = await _spawn(system, system_id, rom_path, exec_path, exec_args, game_key)
    _start_background_tasks(system, system_id)
    return {"ok": True, "game_key": game_key, "resumed": resumed_flag}
