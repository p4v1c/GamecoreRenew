"""Manages the currently running emulator/app process."""
import asyncio
import logging
import os
import signal
import time
from datetime import datetime, timezone

from .. import ws
from ..db import get_db

log = logging.getLogger(__name__)


class ProcessManager:
    def __init__(self):
        self._proc: asyncio.subprocess.Process | None = None
        self._game_key: str = ""
        self._system_id: str = ""
        self._start_time: float = 0.0
        self._exec_path: str = ""   # "flatpak" or absolute path
        self._launch_args: list[str] = []  # args passed after exec_path

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    @property
    def current_game(self) -> dict | None:
        if not self.is_running:
            return None
        return {"game_key": self._game_key, "system_id": self._system_id}

    async def launch(self, exec_path: str, exec_args: str, rom_path: str = "",
                     game_key: str = "", system_id: str = "") -> None:
        if self.is_running:
            raise RuntimeError("A game is already running")

        args = exec_args.split() if exec_args else []
        if rom_path:
            args.append(rom_path)

        self._exec_path = exec_path
        self._launch_args = args
        self._game_key = game_key or (rom_path.split("/")[-1] if rom_path else exec_path.split("/")[-1])
        self._system_id = system_id
        self._start_time = time.time()

        if exec_path == "flatpak":
            # Force X11/XWayland so the overlay monitor can detect the window.
            # Qt emulators respect QT_QPA_PLATFORM=xcb; SDL emulators SDL_VIDEODRIVER=x11.
            x11_env = [
                "--env=QT_QPA_PLATFORM=xcb",
                "--env=SDL_VIDEODRIVER=x11",
                "--env=GDK_BACKEND=x11",
            ]
            # Insert env flags right after "flatpak run" (args[0] == "run")
            if args and args[0] == "run":
                cmd = ["flatpak", "run"] + x11_env + args[1:]
            else:
                cmd = ["flatpak"] + args
        else:
            cmd = [exec_path] + args

        log.info("launch: %s", " ".join(cmd))

        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,  # isolates child into its own process group so killpg doesn't hit the backend
        )

        ws.set_current_game({"game_key": self._game_key, "system_id": self._system_id})
        await ws.broadcast("game:started", {
            "game_key": self._game_key,
            "system_id": self._system_id,
        })

        asyncio.create_task(self._watch())

    async def kill(self) -> None:
        if not self._proc:
            return

        # ── Flatpak: use 'flatpak kill <app-id>' first ────────────────────────
        # Sending SIGTERM to the flatpak wrapper doesn't reach the sandboxed app.
        # Mirror GameSession::kill() from the old C++ code: find the app-id that
        # follows "run" in the args and run 'flatpak kill <app-id>'.
        if "flatpak" in self._exec_path or (
            self._launch_args and self._launch_args[0] == "run"
        ):
            await self._flatpak_kill()

        # ── Generic kill: terminate process / process group ───────────────────
        await self._proc_kill()

    async def _flatpak_kill(self) -> None:
        """Run 'flatpak kill <app-id>' non-blockingly, like the C++ startDetached."""
        try:
            idx = self._launch_args.index("run")
            app_id = self._launch_args[idx + 1]
        except (ValueError, IndexError):
            log.warning("flatpak_kill: could not find app-id in args %s", self._launch_args)
            return

        log.info("flatpak_kill: flatpak kill %s", app_id)
        try:
            proc = await asyncio.create_subprocess_exec(
                "flatpak", "kill", app_id,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            # Give Flatpak up to 3 s to cleanly shut down the sandbox
            await asyncio.wait_for(proc.wait(), timeout=3.0)
        except (asyncio.TimeoutError, OSError):
            pass

    async def _proc_kill(self) -> None:
        """SIGTERM → wait 3 s → SIGKILL on the wrapper process and its group."""
        if not self._proc:
            return
        pid = self._proc.pid

        # Try process-group kill first (catches child processes)
        try:
            pgid = os.getpgid(pid)
            os.killpg(pgid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            try:
                self._proc.terminate()
            except ProcessLookupError:
                pass

        try:
            await asyncio.wait_for(self._proc.wait(), timeout=3.0)
            return
        except asyncio.TimeoutError:
            pass

        # Still alive — force kill
        log.warning("proc_kill: SIGTERM timed out, sending SIGKILL")
        try:
            pgid = os.getpgid(pid)
            os.killpg(pgid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            try:
                self._proc.kill()
            except ProcessLookupError:
                pass

    async def _watch(self) -> None:
        if not self._proc:
            return
        await self._proc.wait()
        elapsed = int(time.time() - self._start_time)
        game_key = self._game_key
        system_id = self._system_id
        self._proc = None
        ws.set_current_game(None)

        if elapsed > 5:
            try:
                db = await get_db()
                now = datetime.now(timezone.utc).isoformat()
                await db.execute("""
                    INSERT INTO playtime (game_key, system_id, total_secs, session_count, last_played)
                    VALUES (?, ?, ?, 1, ?)
                    ON CONFLICT(game_key) DO UPDATE SET
                        total_secs    = total_secs + excluded.total_secs,
                        session_count = session_count + 1,
                        last_played   = excluded.last_played
                """, (game_key, system_id, elapsed, now))
                await db.commit()
            except Exception:
                log.exception("_watch: failed to save playtime for %s", game_key)

        try:
            await ws.broadcast("game:finished", {
                "game_key": game_key,
                "system_id": system_id,
                "elapsed": elapsed,
            })
        except Exception:
            log.exception("_watch: failed to broadcast game:finished")


process_manager = ProcessManager()
