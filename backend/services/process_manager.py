"""Manages the currently running emulator/app process."""
import asyncio
import glob
import json
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
# which is not a variable SDL has ever read — the DB was silently ignored.)
#
# The flatpak'd emulators DO read /opt: five carry an explicit
# `filesystems=/opt/GameCore` override and the rest have `host:ro` in their
# manifest. A comment here used to claim the opposite, which would send the
# next maintainer hunting a sandbox problem that does not exist.
_CONTROLLER_DB = GAMECORE_ROOT / "backend" / "data" / "gamecontrollerdb.txt"

# The pgid of the running game, so a restarted backend can find it again.
# config/ survives the OTA rsync, and this file is state rather than settings —
# it is removed as soon as the game exits.
SESSION_FILE = GAMECORE_ROOT / "config" / "session.json"


async def kill_process_group(proc) -> None:
    """SIGKILL a process and everything it started.

    Killing the process alone leaves its children behind — for a shell script
    that means the rsync, pip and npm it spawned keep writing while the caller
    has already given up on it. Needs start_new_session=True at spawn time, so
    the group is the child's own and never the backend's.
    """
    if proc is None or proc.returncode is not None:
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (OSError, ProcessLookupError):
        try:
            proc.kill()
        except (ProcessLookupError, OSError):
            pass


def _pgid_alive(pgid: int) -> bool:
    if pgid <= 1:
        return False
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True          # the group exists; we merely may not signal it
    except OSError:
        return False
    return True


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


# Result of the last SUCCESSFUL _probe_display. The display does not move while
# the session is up, and probing costs up to 5 s of blocked event loop per call
# (see _display_env), so a success is kept for the life of the process.
_probe_cache: tuple[str, str] | None = None

# A failure is NOT kept the same way, and that distinction is the whole point.
#
# The backend wins the boot race against X, every cold boot. Measured on the
# reference box: systemd starts the backend at 14:56:19, main.py's lifespan
# calls standby.resume_after_restart() → xset → display_env() at 14:56:20 —
# and /tmp/.X11-unix/ is still empty. SDDM only starts X at 14:56:22, the
# first socket appears at 14:56:22.8, and :1 — the only display that answers
# on that box — at 14:56:24.3. The probe therefore ran 4.3 s too early.
#
# Latching that failure the way a success is latched left _probe_cache at None
# for the life of the process, _display_env fell through to DISPLAY=":0", and
# every emulator started against a display that does not answer and died
# instantly — stdout to DEVNULL, so the UI just flashed game:started →
# game:finished. Restarting the backend was the only cure, and it worked only
# because by then X had been up for minutes.
#
# A failed probe means "X could not be asked yet", never "there is no display".
# So it is retried; the delay only stops a genuinely headless box from paying
# xdpyinfo's timeout on every call.
_probe_retry_at: float = 0.0
_PROBE_RETRY_SECS = 5.0


def _probe_due() -> bool:
    """True when _display_env() would actually run the probe — and so may block."""
    return _probe_cache is None and time.monotonic() >= _probe_retry_at


def invalidate_display_cache() -> None:
    """Forget the probed display — call when a launch fails and X may have moved."""
    global _probe_cache, _probe_retry_at
    _probe_cache, _probe_retry_at = None, 0.0


def _display_env() -> dict:
    """Build an env dict for launching GUI apps from systemd (DISPLAY, XDG_RUNTIME_DIR, DBUS, XAUTHORITY).

    Synchronous, and it may run xdpyinfo — so callers on the event loop must go
    through _display_env_async(). Under systemd neither DISPLAY nor XAUTHORITY
    is set, so the probe ran on *every* game launch and *every* standby
    transition; with X slow to answer (cold boot, stale xauth cookie, the TV
    resyncing HDMI) each subprocess.run sat there up to its 5 s timeout with the
    whole loop blocked behind it — no WebSocket, no API, no pad events.
    Measured at 4.7 s on an unrelated GET /api/systems during one launch.
    """
    global _probe_cache, _probe_retry_at
    env = os.environ.copy()
    uid = os.getuid()
    if not env.get("SDL_GAMECONTROLLERCONFIG_FILE") and _CONTROLLER_DB.is_file():
        env["SDL_GAMECONTROLLERCONFIG_FILE"] = str(_CONTROLLER_DB)
    if not env.get("DISPLAY") or not env.get("XAUTHORITY"):
        if _probe_due():
            found = _probe_display(uid)
            if found:
                _probe_cache = found
            else:
                _probe_retry_at = time.monotonic() + _PROBE_RETRY_SECS
        probed = _probe_cache
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


async def display_env() -> dict:
    """_display_env() for callers on the event loop.

    The first call may probe X and can take seconds; every later one is served
    from the cache and never leaves the loop. Off-thread even so, because the
    first launch after a cold boot is exactly when the probe is slowest and
    exactly when the UI most needs to stay responsive.
    """
    if os.environ.get("DISPLAY") or not _probe_due():
        return _display_env()
    return await asyncio.to_thread(_display_env)


class ProcessManager:
    def __init__(self):
        self._proc: asyncio.subprocess.Process | None = None
        self._launching: bool = False  # claimed before the first await in launch()
        self._game_key: str = ""
        self._system_id: str = ""
        self._start_time: float = 0.0
        self._exec_path: str = ""   # "flatpak" or absolute path
        self._launch_args: list[str] = []  # args passed after exec_path
        # A game started by a previous backend process and still running. We
        # cannot await() something that is not our child, so it is tracked by
        # pgid and polled for liveness.
        self._orphan_pgid: int = 0

    # ── the session on disk ───────────────────────────────────────────────────

    def _save_session(self) -> None:
        """Remember the pgid so a restarted backend can still reach this game.

        Without it, a backend restart — OTA, crash, `systemctl restart` — left
        the emulator fullscreen and untouchable: the new process came up with
        _proc = None, so is_running was false, kill() returned at its first line
        and the double-PS shortcut could never close the game again. The UI
        keeps its own session state (it is a separate service and does not
        restart with the backend), so it still asked; nothing answered.
        """
        if not self._proc:
            return
        try:
            pgid = os.getpgid(self._proc.pid)
        except OSError:
            return
        payload = {
            "pgid": pgid,
            "game_key": self._game_key,
            "system_id": self._system_id,
            "exec_path": self._exec_path,
            "launch_args": self._launch_args,
            "started_at": self._start_time,
        }
        try:
            SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = SESSION_FILE.with_name(SESSION_FILE.name + ".tmp")
            tmp.write_text(json.dumps(payload))
            os.replace(tmp, SESSION_FILE)
        except OSError:
            log.warning("could not record the running session in %s", SESSION_FILE)

    def _clear_session(self) -> None:
        self._orphan_pgid = 0
        try:
            SESSION_FILE.unlink(missing_ok=True)
        except OSError:
            pass

    async def adopt_orphan(self) -> None:
        """Re-attach at startup to a game a previous backend left running."""
        try:
            data = json.loads(SESSION_FILE.read_text())
        except (OSError, ValueError):
            return
        try:
            pgid = int(data.get("pgid") or 0)
        except (TypeError, ValueError):
            pgid = 0
        if not _pgid_alive(pgid):
            self._clear_session()
            return

        self._orphan_pgid = pgid
        self._game_key = str(data.get("game_key") or "")
        self._system_id = str(data.get("system_id") or "")
        self._exec_path = str(data.get("exec_path") or "")
        self._launch_args = [str(a) for a in (data.get("launch_args") or [])]
        try:
            self._start_time = float(data.get("started_at") or time.time())
        except (TypeError, ValueError):
            self._start_time = time.time()

        ws.set_current_game({"game_key": self._game_key, "system_id": self._system_id})
        log.warning("adopted a game left running by a previous backend: %s (pgid %d)",
                    self._game_key or "?", pgid)

    def _orphan_alive(self) -> bool:
        if not self._orphan_pgid:
            return False
        if _pgid_alive(self._orphan_pgid):
            return True
        # It exited by itself since we adopted it.
        self._clear_session()
        ws.set_current_game(None)
        return False

    @property
    def is_running(self) -> bool:
        return (self._launching
                or (self._proc is not None and self._proc.returncode is None)
                or self._orphan_alive())

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

            env = await display_env()
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

        self._save_session()
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
        if self._orphan_pgid:
            await self._kill_orphan()
            return
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

    async def _kill_orphan(self) -> None:
        """Kill a game adopted from a previous backend — no child handle, just the pgid."""
        pgid, self._orphan_pgid = self._orphan_pgid, 0
        game_key, system_id = self._game_key, self._system_id
        elapsed = int(time.time() - self._start_time)
        log.info("killing adopted game %s (pgid %d)", game_key or "?", pgid)

        if "flatpak" in self._exec_path or self._launch_args[:1] == ["run"]:
            await self._flatpak_kill()
        try:
            os.killpg(pgid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass

        self._clear_session()
        ws.set_current_game(None)
        # Playtime is deliberately not recorded: _start_time came off disk from
        # a process that may have died long ago, so the elapsed figure would be
        # a guess written into the player's stats.
        try:
            await ws.broadcast("game:finished", {
                "game_key": game_key, "system_id": system_id, "elapsed": elapsed,
            })
        except Exception:
            log.exception("_kill_orphan: failed to broadcast game:finished")

    async def _flatpak_kill(self) -> None:
        """Run 'flatpak kill <app-id>' non-blockingly, like the C++ startDetached."""
        # Read by tiles.py: the id is the first NON-OPTION argument after
        # `run`, not the token after it. This used to take args[idx + 1] and so
        # ran `flatpak kill --nosocket=wayland` for any tile carrying a flag —
        # killing nothing, warning about nothing, and leaving the sandbox up.
        from .catalog.tiles import flatpak_app_id
        app_id = flatpak_app_id(" ".join(self._launch_args))
        if not app_id:
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
        await kill_process_group(self._proc)

    async def _watch(self) -> None:
        if not self._proc:
            return
        await self._proc.wait()
        elapsed = int(time.time() - self._start_time)
        game_key = self._game_key
        system_id = self._system_id
        self._proc = None
        self._clear_session()
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
