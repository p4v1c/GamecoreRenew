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
from pathlib import Path

from .. import ws
from .paths import config_dir
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
#
# The path now comes from mapping_db.served(), not from the vendored file
# directly: what an emulator must read is the community database WITH the
# owner's own captures appended. Naming the vendored file here would have made
# the mapping wizard write to a database nothing loads.


def _controller_db():
    """Path for SDL_GAMECONTROLLERCONFIG_FILE, or None.

    Imported inside the call rather than at module scope: `configgen` pulls in
    the catalogue loader, and this module is imported from `main` before the
    app has decided anything. Never raises — a database that cannot be built
    must cost the captured mappings, not the launch.
    """
    try:
        from .configgen import mapping_db
        return mapping_db.served()
    except Exception:
        log.warning("process_manager: no controller database to hand to SDL",
                    exc_info=True)
        return None


# The pgid of the running game, so a restarted backend can find it again.
# config/ survives the OTA rsync, and this file is state rather than settings —
# it is removed as soon as the game exits.
SESSION_FILE = config_dir() / "session.json"


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


def session_env_file(uid: int | None = None) -> Path:
    """Where the graphical session writes down what it is.

    `install/bin/gamecore-session` creates this at login and removes it at
    logout, in the user's own runtime directory. Its absence is meaningful: no
    session, which is exactly what a headless box or an SSH install looks like.
    """
    uid = os.getuid() if uid is None else uid
    runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{uid}"
    return Path(runtime) / "gamecore" / "session.env"


def _session_display(uid: int) -> tuple[str, str] | None:
    """(DISPLAY, XAUTHORITY) as the session itself declared them, or None.

    The backend is a system unit — deliberately, so the API and the web
    interface survive without a graphical session — and a system unit sees
    nothing of one. Which left it probing: every X socket against every cookie
    location, on every launch and every standby transition, with a 20 s bound
    in its own unit for the cold-boot case.

    A session that knows its own DISPLAY writing it down is both cheaper and
    more truthful than this process guessing. The probe below stays for every
    box that has not migrated, for a desktop session that is not ours, and for
    the window between a backend restart and the next login.
    """
    try:
        text = session_env_file(uid).read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None
    values: dict[str, str] = {}
    for line in text.splitlines():
        key, _, value = line.partition("=")
        if key and value:
            values[key.strip()] = value.strip()
    display = values.get("DISPLAY")
    if not display:
        return None
    return display, values.get("XAUTHORITY", "")


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
    if not env.get("SDL_GAMECONTROLLERCONFIG_FILE"):
        db = _controller_db()
        if db:
            env["SDL_GAMECONTROLLERCONFIG_FILE"] = str(db)
    if not env.get("DISPLAY") or not env.get("XAUTHORITY"):
        # Asked first, and it costs a file read. Only if there is no session
        # file does this fall back to looking for a display by hand.
        declared = _session_display(uid)
        if declared:
            env["DISPLAY"] = declared[0]
            if declared[1]:
                env["XAUTHORITY"] = declared[1]
            else:
                env.pop("XAUTHORITY", None)
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
    # GameCore is hosted on the machine's own X11 desktop session — remove
    # Wayland to prevent Qt apps from trying WAYLAND_DISPLAY and failing
    # silently under the systemd service.
    #
    # This said "an X11 openbox session" long after openbox stopped being
    # installed (arch.sh lays down plasma-desktop and plasma-x11-session). The
    # line below is still right — the whole stack is X11-only — but a reader who
    # knew openbox was gone would conclude the comment was dead and therefore
    # that the line was too. The session changed; X11-only did not.
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


class SessionConflict(RuntimeError):
    """A lifecycle request the box cannot honour in the state it is in.

    Carries the sentence the player should read. Every raise site here is a
    409 at the router, and the router does not invent the wording: the manager
    is the only thing that knows *which* session is in the way.
    """


class Session:
    """One launched thing — a game or an app — and everything needed to
    describe it, suspend it, resume it, kill it and bill it for playtime.

    It exists because a session outlived the fields that described it. The
    manager used to keep `_proc`, `_game_key`, `_start_time` and the rest as
    its own attributes, which is exactly one session's worth of room. Putting
    a game in the background and starting something else then overwrote the
    first one's identity in place: a frozen emulator with nothing left holding
    its pgid, unkillable and invisible, holding its RAM until the box was
    restarted. Two slots need two objects.
    """

    __slots__ = ("proc", "orphan_pgid", "game_key", "system_id", "rom_path",
                 "exec_path", "launch_args", "start_time", "session_id",
                 "state", "bg_since", "bg_total")

    def __init__(self, *, proc=None, orphan_pgid: int = 0, game_key: str = "",
                 system_id: str = "", rom_path: str = "", exec_path: str = "",
                 launch_args: list[str] | None = None, start_time: float = 0.0,
                 session_id: int = 0, state: str = "foreground",
                 bg_since: float = 0.0, bg_total: float = 0.0):
        self.proc = proc
        # Set only for a session adopted from a previous backend: we cannot
        # await() something that is not our child, so it is polled by pgid.
        self.orphan_pgid = orphan_pgid
        self.game_key = game_key
        self.system_id = system_id
        self.rom_path = rom_path
        self.exec_path = exec_path
        self.launch_args = launch_args or []
        self.start_time = start_time
        self.session_id = session_id
        self.state = state
        #: When the current suspended stretch began, 0.0 while in the foreground.
        self.bg_since = bg_since
        #: Seconds already spent suspended, over every stretch that has ended.
        self.bg_total = bg_total

    # ── identity ─────────────────────────────────────────────────────────────

    @property
    def pgid(self) -> int:
        """The process GROUP, which is what every signal here is aimed at.

        Never the bare pid. Measured on the reference box: a Flatpak emulator
        is five processes — the outer bwrap, a second bwrap wrapping
        xdg-dbus-proxy, the proxy, the inner bwrap and the application — and
        they share one group because `start_new_session=True` made it and
        nothing inside bwrap calls setsid. Signalling the group moves all five;
        signalling the pid moves the wrapper and leaves the game running.
        """
        if self.orphan_pgid:
            return self.orphan_pgid
        if self.proc is None:
            return 0
        try:
            return os.getpgid(self.proc.pid)
        except OSError:
            return 0

    def alive(self) -> bool:
        if self.orphan_pgid:
            return _pgid_alive(self.orphan_pgid)
        return self.proc is not None and self.proc.returncode is None

    @property
    def is_app(self) -> bool:
        """An application tile rather than a game.

        A tile carrying no ROM launches with `game_key == system_id` — see
        routers/games.py — and that identity is the only thing that tells the
        two apart once the session exists. Themes need it to say "Close app"
        rather than "Close game", so it is computed here and not in each of
        them.
        """
        return bool(self.game_key) and self.game_key == self.system_id

    # ── time ─────────────────────────────────────────────────────────────────

    def background_secs(self, now: float) -> float:
        """Suspended seconds, including the stretch still open."""
        open_stretch = (now - self.bg_since
                        if self.state == "background" and self.bg_since else 0.0)
        return self.bg_total + max(0.0, open_stretch)

    def played_secs(self, now: float) -> int:
        """Wall time minus every second the process was frozen.

        A SIGSTOPped emulator is not being played, and counting it would make
        the box's own statistics reward leaving a game suspended overnight —
        eight hours of "playtime" for a game nobody touched. Clamped at zero:
        a clock that moved backwards must not subtract from a player's hours.
        """
        return max(0, int(now - self.start_time - self.background_secs(now)))

    # ── how it is described to everyone else ─────────────────────────────────

    def describe(self) -> dict:
        return {
            "game_key": self.game_key,
            "system_id": self.system_id,
            "rom_path": self.rom_path,
            "session": self.session_id,
            "state": self.state,
            "kind": "app" if self.is_app else "game",
        }

    def to_disk(self) -> dict:
        return {
            "pgid": self.pgid,
            "game_key": self.game_key,
            "system_id": self.system_id,
            "exec_path": self.exec_path,
            "rom_path": self.rom_path,
            "launch_args": self.launch_args,
            "started_at": self.start_time,
            "state": self.state,
            "bg_since": self.bg_since,
            "bg_total": self.bg_total,
        }


#: How many launched things may be resident at once, suspended or not.
#:
#: **Two, and the limit is memory rather than bookkeeping.** A suspended
#: emulator has given back its CPU and nothing else: RPCS3 holds several
#: gigabytes of RAM and its VRAM for as long as it is stopped. A third resident
#: emulator on a fixed-memory box is the OOM killer, and the OOM killer takes
#: whichever process it likes — which is to say, sooner or later, the player's
#: suspended game. A feature sold as "your game is safe while you do something
#: else" must not contain a path that ends in the kernel destroying it.
MAX_SESSIONS = 2


class ProcessManager:
    """Two slots, one screen.

    At most `MAX_SESSIONS` launched things exist at once, and at most one of
    them is in front of the player. Every other combination is legal: two
    suspended, one suspended and one playing, one playing, nothing.

    **Suspending is never refused, and that is a rule rather than an
    accident.** An earlier draft of this kept a single background slot and
    refused a second, which reads as reasonable until the double-Home gesture
    meets it: a player inside game B with game A already suspended asks to get
    out, the suspend is refused, and the only way off that screen is to quit
    the game they were playing. Moving a session from the screen to the
    background does not create a session — the resident count is identical
    either side of it — so there was never a memory argument for that refusal,
    only a data-structure one. The cap belongs on launching, which really does
    create one.
    """

    def __init__(self):
        #: Every resident session, in the order they were launched. At most one
        #: carries `state == "foreground"`; see the class docstring.
        self._sessions: list[Session] = []
        self._launching: bool = False  # claimed before the first await in launch()
        # Which run is current. Every launch and every adoption takes the next
        # number; a watcher keeps the one it was started with, and compares
        # before touching anything shared. See _watch().
        self._seq: int = 0
        #: Named while a launch is in flight, so `current_game` is not None
        #: during the window `_launching` covers. Cleared by launch()'s finally.
        self._pending_key: str = ""
        self._pending_system: str = ""

    # ── what the box is doing ────────────────────────────────────────────────

    def _reap(self) -> bool:
        """Drop slots whose process has gone, and say whether anything changed.

        Every dead session, not only the adopted ones. A child of ours is also
        cleared by its own watcher, but the watcher only runs when the event
        loop gets back to it, and `is_running` frees a child the instant it has
        a return code — a window wide enough to hold a whole launch. A slot
        still holding a game that has already exited would refuse the next
        launch with "the box is already holding suspended sessions", naming
        games that are gone.

        Safe to remove one from under its watcher: the watcher holds the
        `Session` object directly, so it still records that game's playtime and
        still announces its finish under its own number. It merely finds the
        list has moved on without it, which is exactly what it should do.
        """
        keep = [s for s in self._sessions if s.alive()]
        if len(keep) == len(self._sessions):
            return False
        self._sessions = keep
        self._save_state()
        self._publish()
        return True

    @property
    def is_running(self) -> bool:
        """A session EXISTS — on the screen or frozen behind it.

        Deliberately still true for a suspended game: it is still a process,
        still on that disk, still holding that RAM. The question "may I start
        something" is `is_foreground`, and separating the two is the whole of
        this feature.
        """
        self._reap()
        return self._launching or any(s.alive() for s in self._sessions)

    @property
    def is_foreground(self) -> bool:
        """Something owns the screen.

        This is what gates a launch, holds the standby clock and defers the
        cover prefetcher — every question that is really "is the player in a
        game right now", which a frozen one is not.
        """
        self._reap()
        return self._launching or self._fg is not None

    @property
    def _fg(self) -> Session | None:
        """The one session on the screen, if there is one. Not reaped: callers
        that need liveness go through the public properties below."""
        return next((s for s in self._sessions
                     if s.state == "foreground" and s.alive()), None)

    @property
    def foreground_session(self) -> Session | None:
        self._reap()
        return self._fg

    @property
    def background_sessions(self) -> list[Session]:
        """Every suspended session, oldest first."""
        self._reap()
        return [s for s in self._sessions if s.state == "background" and s.alive()]

    @property
    def background_session(self) -> Session | None:
        """The suspended session a bare "resume" means: the most recent one."""
        held = self.background_sessions
        return held[-1] if held else None

    @property
    def current_game(self) -> dict | None:
        """The session on the screen, or None.

        Unchanged in meaning: every caller that reads this is asking about the
        game in front of the player. A suspended one answers None here and is
        found through `session_state()`.
        """
        s = self.foreground_session
        if s is None:
            return {"game_key": self._pending_key, "system_id": self._pending_system,
                    "rom_path": "", "session": self._seq} if self._launching else None
        return {"game_key": s.game_key, "system_id": s.system_id,
                "rom_path": s.rom_path, "session": s.session_id}

    def session_state(self) -> dict:
        """The whole of what the box is running, in one shape.

        Flat fields describe the FOREGROUND session, which is exactly what
        `/api/games/session` has always returned — so a client that predates
        this feature keeps reading it correctly, and reads a box whose only
        session is suspended as "nothing in front of me", which is true and is
        the answer that unblocks its pad.

        `background` carries the other slot when there is one.
        """
        state: dict = {}
        fg = self.foreground_session
        if fg is not None:
            state.update(fg.describe())
        held = self.background_sessions
        if held:
            state["background"] = [s.describe() for s in held]
        return state

    # ── the session on disk ───────────────────────────────────────────────────

    def _save_state(self) -> None:
        """Remember the pgids so a restarted backend can still reach them.

        Without it, a backend restart — OTA, crash, `systemctl restart` — left
        the emulator fullscreen and untouchable: the new process came up with
        no session, so `is_running` was false, kill() returned at its first
        line and the double-PS shortcut could never close the game again. The
        UI keeps its own session state (it is a separate service and does not
        restart with the backend), so it still asked; nothing answered.

        Both slots are written. A suspended game is the one that most needs
        finding again: it cannot exit on its own to clear itself.
        """
        sessions = [s.to_disk() for s in self._sessions if s.pgid]
        try:
            if not sessions:
                SESSION_FILE.unlink(missing_ok=True)
                return
            SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = SESSION_FILE.with_name(SESSION_FILE.name + ".tmp")
            # `sessions` is the shape this build writes; the top-level keys of
            # the first one are kept beside it so a DOWNGRADE — an OTA rolled
            # back onto a box with a game running — still finds a session to
            # adopt instead of leaving an unkillable emulator on the screen.
            payload = dict(sessions[0])
            payload["sessions"] = sessions
            tmp.write_text(json.dumps(payload))
            os.replace(tmp, SESSION_FILE)
        except OSError:
            log.warning("could not record the running session in %s", SESSION_FILE)

    def _clear_session(self) -> None:
        """Forget both slots on disk. Kept for the tests that stub it out."""
        try:
            SESSION_FILE.unlink(missing_ok=True)
        except OSError:
            pass

    async def adopt_orphan(self) -> None:
        """Re-attach at startup to sessions a previous backend left behind."""
        try:
            data = json.loads(SESSION_FILE.read_text())
        except (OSError, ValueError):
            return

        raw = data.get("sessions")
        if not isinstance(raw, list) or not raw:
            raw = [data]          # written by a build before the second slot

        adopted: list[Session] = []
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            try:
                pgid = int(entry.get("pgid") or 0)
            except (TypeError, ValueError):
                continue
            if not _pgid_alive(pgid):
                continue
            try:
                started = float(entry.get("started_at") or time.time())
            except (TypeError, ValueError):
                started = time.time()
            state = entry.get("state")
            state = state if state in ("foreground", "background") else "foreground"
            self._seq += 1
            adopted.append(Session(
                orphan_pgid=pgid,
                game_key=str(entry.get("game_key") or ""),
                system_id=str(entry.get("system_id") or ""),
                exec_path=str(entry.get("exec_path") or ""),
                rom_path=str(entry.get("rom_path") or ""),
                launch_args=[str(a) for a in (entry.get("launch_args") or [])],
                start_time=started,
                session_id=self._seq,
                state=state,
                bg_since=_as_float(entry.get("bg_since")),
                bg_total=_as_float(entry.get("bg_total")),
            ))

        if not adopted:
            self._clear_session()
            return

        seen_foreground = False
        for s in adopted:
            if len(self._sessions) >= MAX_SESSIONS:
                log.warning("session file named more sessions than there are "
                            "slots — ignoring %s", s.game_key or "?")
                continue
            if s.state == "background":
                # It is still frozen: SIGSTOP outlives the backend that sent it.
                if not s.bg_since:
                    s.bg_since = time.time()
            elif seen_foreground:
                # Two foregrounds cannot both be true. The later one keeps the
                # screen; the first is recorded as suspended rather than
                # dropped, so it stays killable instead of becoming a leak.
                s.state = "background"
                s.bg_since = time.time()
            else:
                seen_foreground = True
            self._sessions.append(s)

        self._save_state()
        self._publish()
        for s in self._sessions:
            log.warning("adopted a session left by a previous backend: %s "
                        "(pgid %d, %s)", s.game_key or "?", s.orphan_pgid, s.state)

    # ── announcing ───────────────────────────────────────────────────────────

    def _publish(self) -> None:
        """Refresh what a newly connected websocket client is told."""
        ws.set_current_game(self.session_state() or None)

    async def _announce(self, event: str, session: Session) -> None:
        """One lifecycle event, carrying the WHOLE state.

        The run number alone is not enough for these two. A resume that swaps
        the two slots moves both of them at once, and a client rebuilding its
        picture from "run 3 came forward" cannot know what happened to run 2 —
        it would drop the session that is still frozen and leave the player
        with a game the interface no longer shows. So each event carries the
        transition (`game_key`, `system_id`, `session`) *and* the state the box
        is in once it has happened.
        """
        payload = dict(session.describe())
        payload["state_snapshot"] = self.session_state()
        try:
            await ws.broadcast(event, payload)
        except Exception:
            log.exception("failed to broadcast %s", event)

    # ── launching ────────────────────────────────────────────────────────────

    async def launch(self, exec_path: str, exec_args: str, rom_path: str = "",
                     game_key: str = "", system_id: str = "") -> None:
        if self.is_foreground:
            raise SessionConflict("A game is already running")
        self._reap()
        if len(self._sessions) >= MAX_SESSIONS:
            held = ", ".join(s.game_key or "?" for s in self._sessions)
            raise SessionConflict(
                f"The box is already holding {len(self._sessions)} suspended "
                f"sessions ({held}) — close one before starting another")
        # Claim the slot synchronously — two concurrent launch() calls both
        # pass the check above otherwise (the subprocess spawn awaits below).
        self._launching = True
        self._pending_key = game_key
        self._pending_system = system_id

        try:
            args = shlex.split(exec_args) if exec_args else []
            if rom_path:
                args.append(rom_path)

            if exec_path == "flatpak":
                cmd = ["flatpak"] + args
            else:
                cmd = [exec_path] + args

            env = await display_env()
            log.info("launch: %s (DISPLAY=%s)", " ".join(cmd), env.get("DISPLAY", ""))

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                start_new_session=True,  # isolates child into its own process group so killpg doesn't hit the backend
                env=env,
            )
        finally:
            self._launching = False
            self._pending_key = ""
            self._pending_system = ""

        self._seq += 1
        session = Session(
            proc=proc,
            game_key=game_key or (rom_path.split("/")[-1] if rom_path
                                  else exec_path.split("/")[-1]),
            system_id=system_id,
            rom_path=rom_path,
            exec_path=exec_path,
            launch_args=args,
            start_time=time.time(),
            session_id=self._seq,
        )
        self._sessions.append(session)

        self._save_state()
        self._publish()
        await ws.broadcast("game:started", {
            "game_key": session.game_key,
            "system_id": session.system_id,
            "session": session.session_id,
        })

        # Its own process and its own session, so that resuming after this game
        # ends says nothing about whatever is running by then.
        watch_task = asyncio.create_task(self._watch(session))

        def _log_err(t: asyncio.Task) -> None:
            if t.cancelled():
                return
            exc = t.exception()
            if exc:
                log.warning("watch task failed: %s", exc)
        watch_task.add_done_callback(_log_err)

    # ── suspend and resume ───────────────────────────────────────────────────

    def _signal(self, session: Session, sig: int) -> bool:
        """Signal the whole group, and say whether it landed.

        The group and never the pid: see `Session.pgid`. A failure here is
        reported rather than raised into the caller's face — the session may
        have exited between the check and the signal, which is not an error,
        it is the game having ended.
        """
        pgid = session.pgid
        if not pgid:
            return False
        try:
            os.killpg(pgid, sig)
            return True
        except (OSError, ProcessLookupError):
            return False

    async def background(self) -> dict:
        """Freeze the session on the screen and give the interface back.

        SIGSTOP to the process group, which is what makes this work at all for
        the Flatpak emulators: measured on the reference box, all five
        processes of a sandbox — both bwraps, the dbus proxy and the
        application — take the signal together and all five report `T`.
        """
        if self._launching:
            raise SessionConflict("A game is still starting")
        s = self.foreground_session
        if s is None:
            raise SessionConflict("Nothing is running")

        if not self._signal(s, signal.SIGSTOP):
            raise SessionConflict("That session could not be suspended")

        s.state = "background"
        s.bg_since = time.time()
        self._save_state()
        self._publish()
        log.info("session %s (%s) suspended", s.game_key or "?", s.system_id)
        await self._announce("game:backgrounded", s)
        await self._raise_interface(s)
        return self.session_state()

    async def foreground(self, session_id: int | None = None) -> dict:
        """Wake a frozen session, and put whatever holds the screen behind it.

        The swap is one operation rather than two on purpose. Only one thing
        can own the screen, so resuming a game while an application is up
        already implies suspending the application — making the player close it
        first would be the interface asking them to do arithmetic the box can do
        itself. The resident count is unchanged by a swap.

        With no number this resumes the most recent suspended session, which is
        what a session bar with one entry on it means.
        """
        if session_id is None:
            s = self.background_session
        else:
            s = next((x for x in self.background_sessions
                      if x.session_id == session_id), None)
        if s is None:
            raise SessionConflict("Nothing is in the background")

        outgoing = self.foreground_session
        if outgoing is not None:
            if not self._signal(outgoing, signal.SIGSTOP):
                raise SessionConflict("The running session could not be suspended")
            outgoing.state = "background"
            outgoing.bg_since = time.time()

        if not self._signal(s, signal.SIGCONT):
            # Put the screen back the way it was rather than leaving nothing
            # in front of the player.
            if outgoing is not None:
                self._signal(outgoing, signal.SIGCONT)
                outgoing.state = "foreground"
                outgoing.bg_since = 0.0
            raise SessionConflict("That session could not be resumed")

        now = time.time()
        if s.bg_since:
            s.bg_total += max(0.0, now - s.bg_since)
        s.bg_since = 0.0
        s.state = "foreground"
        self._save_state()
        self._publish()
        log.info("session %s (%s) resumed", s.game_key or "?", s.system_id)
        if outgoing is not None:
            await self._announce("game:backgrounded", outgoing)
        await self._announce("game:foregrounded", s)
        await self._give_back_the_screen(s)
        return self.session_state()

    async def _give_back_the_screen(self, session: Session) -> None:
        """Raise and re-fullscreen the window of a session coming forward.

        Best effort by design, and never fatal: this is X11 through a library
        that may not be installed, on a display the backend does not own. A
        resumed game whose window is merely behind the interface is a game the
        player can still reach; an exception here would be a resume that
        reported failure after having already succeeded.
        """
        try:
            from . import window_focus
            await window_focus.activate(session.system_id, session.pgid)
        except Exception:
            log.debug("could not raise the resumed session's window",
                      exc_info=True)

    async def _raise_interface(self, session: Session) -> None:
        """Put the interface in front of a session that has just been frozen.

        Same contract as `_give_back_the_screen`, and the same reason it cannot
        raise: the game IS suspended by the time this runs. Failing here would
        report a suspend that did not happen, and the player would be looking at
        a frozen picture with the interface telling them nothing had changed.
        """
        try:
            from . import window_focus
            await window_focus.hide(session.system_id, session.pgid)
        except Exception:
            log.debug("could not raise the interface over the frozen session",
                      exc_info=True)

    # ── killing ──────────────────────────────────────────────────────────────

    async def kill(self, session_id: int | None = None) -> None:
        """End a session. The one on the screen unless another is named.

        With nothing on the screen this ends the suspended one, which is what
        "close it" means from a session bar: the player is looking at a game
        that is not in front of them and asking for it to be gone.
        """
        if session_id is None:
            target = self.foreground_session or self.background_session
        else:
            target = next((s for s in self._sessions
                           if s.session_id == session_id), None)
        if target is None:
            return

        # A stopped process cannot run its own exit path: `flatpak kill` sends
        # SIGTERM inside the sandbox and a frozen process never handles it, so
        # the sandbox would be torn down by SIGKILL alone with its files still
        # open. Thawed first, killed immediately after.
        if target.state == "background":
            self._signal(target, signal.SIGCONT)

        if "flatpak" in target.exec_path or target.launch_args[:1] == ["run"]:
            await self._flatpak_kill(target)

        if target.orphan_pgid:
            await self._kill_orphan(target)
            return
        await kill_process_group(target.proc)

    async def _kill_orphan(self, target: Session) -> None:
        """Kill a session adopted from a previous backend — no child handle."""
        pgid = target.orphan_pgid
        target.orphan_pgid = 0
        log.info("killing adopted session %s (pgid %d)", target.game_key or "?", pgid)
        try:
            os.killpg(pgid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass

        self._sessions = [s for s in self._sessions if s is not target]
        self._save_state()
        self._publish()
        # Playtime is deliberately not recorded: `start_time` came off disk from
        # a process that may have died long ago, so the elapsed figure would be
        # a guess written into the player's stats.
        try:
            await ws.broadcast("game:finished", {
                "game_key": target.game_key, "system_id": target.system_id,
                "elapsed": target.played_secs(time.time()),
                "session": target.session_id,
            })
        except Exception:
            log.exception("_kill_orphan: failed to broadcast game:finished")

    async def _flatpak_kill(self, target: Session) -> None:
        """Run 'flatpak kill <app-id>' non-blockingly, like the C++ startDetached."""
        # Read by tiles.py: the id is the first NON-OPTION argument after
        # `run`, not the token after it. This used to take args[idx + 1] and so
        # ran `flatpak kill --nosocket=wayland` for any tile carrying a flag —
        # killing nothing, warning about nothing, and leaving the sandbox up.
        from .catalog.tiles import flatpak_app_id
        app_id = flatpak_app_id(" ".join(target.launch_args))
        if not app_id:
            log.warning("flatpak_kill: could not find app-id in args %s",
                        target.launch_args)
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

    # ── the end of a session ─────────────────────────────────────────────────

    async def _watch(self, session: Session | None = None) -> None:
        """Wait for one session to end, and speak only for that session.

        Everything this needs is on the object it was handed, and nothing it
        writes back touches a slot unless that slot still holds the session it
        watched.

        It used to read the manager's own fields after its `await`, which is a
        window wide enough to hold a whole launch: `is_running` frees the slot
        the moment the child has a return code, so a second game can start
        while the first watcher is still suspended. When it resumed it read
        fields describing the *new* game, set `_proc = None` on a process that
        was running, deleted its session file and announced the wrong game as
        finished. The player's game was then untrackable and unkillable.
        """
        session = session or self._fg
        if session is None or session.proc is None:
            return

        await session.proc.wait()
        elapsed = session.played_secs(time.time())

        # Only the slot that still holds this session may be cleared by it.
        if session in self._sessions:
            self._sessions = [s for s in self._sessions if s is not session]
            self._save_state()
            self._publish()

        if elapsed > 5:
            try:
                db = await get_db()
                now = datetime.now(timezone.utc).isoformat()
                await db.execute("""
                    INSERT INTO playtime (game_key, system_id, total_secs, session_count, last_played)
                    VALUES (?, ?, ?, 1, ?)
                    ON CONFLICT(system_id, game_key) DO UPDATE SET
                        total_secs    = total_secs + excluded.total_secs,
                        session_count = session_count + 1,
                        last_played   = excluded.last_played
                """, (session.game_key, session.system_id, elapsed, now))
                await db.commit()
            except Exception:
                log.exception("_watch: failed to save playtime for %s",
                              session.game_key)

        try:
            await ws.broadcast("game:finished", {
                "game_key": session.game_key,
                "system_id": session.system_id,
                "elapsed": elapsed,
                # Which run ended. A finish belonging to a game the player has
                # already left behind must not unlock the screen over the one
                # they are playing now.
                "session": session.session_id,
            })
        except Exception:
            log.exception("_watch: failed to broadcast game:finished")


def _as_float(value) -> float:
    try:
        return max(0.0, float(value or 0.0))
    except (TypeError, ValueError):
        return 0.0


process_manager = ProcessManager()
