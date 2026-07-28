"""Manages the currently running emulator/app process."""
import asyncio
import glob
import logging
import os
import shlex
import signal
import subprocess
import time
from datetime import datetime, timezone

from .. import ws
from ..config import GAMECORE_ROOT
from ..db import get_db

log = logging.getLogger(__name__)

# Community-maintained button/axis mappings (github.com/mdqinc/SDL_GameControllerDB).
# SDL (2.0.10+ and SDL3 alike) loads the file named by the
# SDL_GAMECONTROLLERCONFIG_FILE hint/env var at init and merges it into its
# built-in database, so any emulator linked against SDL correctly maps a
# controller it doesn't otherwise recognize — no per-emulator manual
# configuration needed. (An earlier revision exported SDL_GAMECONTROLLERDB,
# which is not a variable SDL has ever read — the DB was silently ignored.
# Flatpak'd emulators still can't read /opt inside their sandbox; harmless,
# SDL just skips the file.)
_CONTROLLER_DB = GAMECORE_ROOT / "backend" / "data" / "gamecontrollerdb.txt"


def _xauth_candidates(uid: int) -> list[str]:
    """Cookie files this uid owns, newest first.

    Where the cookie lives depends on who started X:
        SDDM's X11 session  → /tmp/xauth_XXXXXX
        kwin_wayland        → /run/user/<uid>/xauth_XXXXXX
        startx              → ~/.Xauthority
    """
    found = []
    for path in glob.glob("/tmp/xauth_*") + glob.glob(f"/run/user/{uid}/xauth_*"):
        try:
            if os.stat(path).st_uid == uid:
                found.append(path)
        except OSError:
            continue
    found.sort(key=os.path.getmtime, reverse=True)
    home_xauth = os.path.join(os.path.expanduser("~"), ".Xauthority")
    if os.path.exists(home_xauth):
        found.append(home_xauth)
    return found


def _probe_display(uid: int) -> tuple[str, str] | None:
    """(DISPLAY, XAUTHORITY) of a display we can actually open, or None.

    Guessing was the bug: `:1` was hardcoded, and the first socket in sort
    order is no better — this box has both X0 and X1 and only one answers.
    A wrong DISPLAY makes every emulator exit instantly, with stdout going to
    DEVNULL, so the UI just flashes game:started → game:finished.
    """
    displays = [f":{os.path.basename(s)[1:]}" for s in sorted(glob.glob("/tmp/.X11-unix/X*"))]
    if not displays:
        return None
    cookies: list[str | None] = list(_xauth_candidates(uid))
    cookies.append(None)  # some servers accept a local connection with no cookie
    for display in displays:
        for cookie in cookies:
            env = {**os.environ, "DISPLAY": display}
            if cookie:
                env["XAUTHORITY"] = cookie
            else:
                env.pop("XAUTHORITY", None)
            try:
                probe = subprocess.run(
                    ["xdpyinfo"], env=env, timeout=5,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            except (OSError, subprocess.SubprocessError):
                return None  # no xdpyinfo — fall back to the static defaults
            if probe.returncode == 0:
                return display, (cookie or "")
    return None


def _display_env() -> dict:
    """Build an env dict for launching GUI apps from systemd (DISPLAY, XDG_RUNTIME_DIR, DBUS, XAUTHORITY)."""
    env = os.environ.copy()
    uid = os.getuid()
    if not env.get("SDL_GAMECONTROLLERCONFIG_FILE") and _CONTROLLER_DB.is_file():
        env["SDL_GAMECONTROLLERCONFIG_FILE"] = str(_CONTROLLER_DB)
    if not env.get("DISPLAY") or not env.get("XAUTHORITY"):
        probed = _probe_display(uid)
        if probed:
            env["DISPLAY"] = probed[0]
            if probed[1]:
                env["XAUTHORITY"] = probed[1]
            else:
                env.pop("XAUTHORITY", None)
    if not env.get("DISPLAY"):
        env["DISPLAY"] = ":0"
    if not env.get("XDG_RUNTIME_DIR"):
        env["XDG_RUNTIME_DIR"] = f"/run/user/{uid}"
    if not env.get("DBUS_SESSION_BUS_ADDRESS"):
        env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path=/run/user/{uid}/bus"
    if not env.get("XAUTHORITY"):
        for candidate in _xauth_candidates(uid):
            env["XAUTHORITY"] = candidate
            break
    # GameCore runs in an X11 openbox session — remove Wayland to prevent Qt apps
    # from trying WAYLAND_DISPLAY and failing silently under the systemd service.
    env.pop("WAYLAND_DISPLAY", None)
    return env


class ProcessManager:
    def __init__(self):
        self._proc: asyncio.subprocess.Process | None = None
        self._launching: bool = False  # claimed before the first await in launch()
        self._game_key: str = ""
        self._system_id: str = ""
        self._start_time: float = 0.0
        self._exec_path: str = ""   # "flatpak" or absolute path
        self._launch_args: list[str] = []  # args passed after exec_path

    @property
    def is_running(self) -> bool:
        return self._launching or (self._proc is not None and self._proc.returncode is None)

    @property
    def current_game(self) -> dict | None:
        if not self.is_running:
            return None
        return {"game_key": self._game_key, "system_id": self._system_id}

    async def launch(self, exec_path: str, exec_args: str, rom_path: str = "",
                     game_key: str = "", system_id: str = "") -> None:
        if self.is_running:
            raise RuntimeError("A game is already running")
        # Claim the slot synchronously — two concurrent launch() calls both
        # pass the check above otherwise (the subprocess spawn awaits below).
        self._launching = True

        try:
            args = shlex.split(exec_args) if exec_args else []
            if rom_path:
                args.append(rom_path)

            self._exec_path = exec_path
            self._launch_args = args
            self._game_key = game_key or (rom_path.split("/")[-1] if rom_path else exec_path.split("/")[-1])
            self._system_id = system_id
            self._start_time = time.time()

            if exec_path == "flatpak":
                cmd = ["flatpak"] + args
            else:
                cmd = [exec_path] + args

            env = _display_env()
            log.info("launch: %s (DISPLAY=%s)", " ".join(cmd), env.get("DISPLAY", ""))

            self._proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                start_new_session=True,  # isolates child into its own process group so killpg doesn't hit the backend
                env=env,
            )
        finally:
            self._launching = False

        ws.set_current_game({"game_key": self._game_key, "system_id": self._system_id})
        await ws.broadcast("game:started", {
            "game_key": self._game_key,
            "system_id": self._system_id,
        })

        watch_task = asyncio.create_task(self._watch())

        def _log_err(t: asyncio.Task) -> None:
            if t.cancelled():
                return
            exc = t.exception()
            if exc:
                log.warning("watch task failed: %s", exc)
        watch_task.add_done_callback(_log_err)

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
            # Give Flatpak up to 1 s to cleanly shut down the sandbox
            await asyncio.wait_for(proc.wait(), timeout=1.0)
        except (asyncio.TimeoutError, OSError):
            pass

    async def _proc_kill(self) -> None:
        """SIGKILL on the wrapper process and its group — skip SIGTERM to avoid confirm dialogs."""
        if not self._proc:
            return
        pid = self._proc.pid

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
