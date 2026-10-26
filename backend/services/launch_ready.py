"""The launch cover: when the game behind it is really running.

A pack's `launch.ready` (a port's `# gamecore-ready-*` lines) names the signal:
a line in the emulator's log, or its window appearing (a pack that declares
none is covered until its window fills the screen, and every signal waits for
that too); then, with `handOver:
black`, the game's window going black (window_black.py), which is how RPCS3
and Ryujinx hand their own loading screen over to the game. `announce()` runs
before the spawn: it notes what the log already holds, so a line from the
previous run never counts, and tells the UI to draw the cover
(`game:loading`). `follow()` then waits for the signal, or the ceiling, and
broadcasts `game:ready`. Nothing here may fail a launch.
Contract: docs/architecture/06-electron-and-overlays.md#the-launch-cover.
"""
from __future__ import annotations

import asyncio
import glob
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from .. import ws
from . import configgen, fullscreen_enforcer, native_ports, window_black
from .catalog import load_catalog
from .process_manager import process_manager

log = logging.getLogger(__name__)

# The ceiling when the pack names none. A cold RPCS3 cache takes minutes; the
# pack raises its own, this only bounds the ones that boot in seconds.
DEFAULT_CAP_S = 90
POLL_S = 0.25
# Read per poll. RPCS3 writes ~200 KB/s while it builds its SPU cache.
READ_LIMIT = 4 << 20
# A partial line longer than this is a dump, not a status line.
MAX_TAIL = 64 << 10
# The black between an emulator's loading screen and the game can be short.
HAND_OVER_POLL_S = 0.1
HAND_OVER_CAP_S = 15
# Every launch is covered until the game's window fills the screen: before
# that the player saw a small window jump to fullscreen. The ceiling for a
# pack that declares no signal (its `launch.fullscreen.timeoutSec` wins), and
# the wait for fullscreen after a declared signal.
FULLSCREEN_CAP_S = 30
# A full grab of the window each look: a quarter second is enough.
PAINT_POLL_S = 0.25
FULLSCREEN_AFTER_SIGNAL_S = 10


@dataclass
class _LogCursor:
    """Reads what a log gains after the spawn, across a rotation."""
    pattern: str
    rx: re.Pattern
    # path -> (inode, size) before the spawn: old lines never count.
    before: dict[str, tuple[int, int]]
    path: str = ""
    ino: int = -1
    offset: int = 0
    tail: bytes = b""

    def found(self) -> bool:
        try:
            return self._scan()
        except OSError:
            return False    # rotated between the listing and the read: next poll

    def _scan(self) -> bool:
        newest = _newest(self.pattern)
        if newest is None:
            return False
        st = os.stat(newest)
        if (newest, st.st_ino) != (self.path, self.ino):
            # RPCS3 recreates its log, Ryujinx starts a new file: a file that
            # is not the one seen before the spawn is read from its start.
            seen = self.before.get(newest)
            self.path, self.ino, self.tail = newest, st.st_ino, b""
            self.offset = seen[1] if seen and seen[0] == st.st_ino else 0
        if st.st_size < self.offset:
            self.offset, self.tail = 0, b""
        with open(newest, "rb") as f:
            f.seek(self.offset)
            chunk = f.read(READ_LIMIT)
        self.offset += len(chunk)
        lines = (self.tail + chunk).split(b"\n")
        self.tail = lines.pop()[-MAX_TAIL:]
        return any(self.rx.search(line.decode("utf-8", "replace")) for line in lines)


@dataclass
class Watch:
    game_key: str
    system_id: str
    spec: dict
    cap_s: float
    cursor: _LogCursor | None = field(default=None)


def _newest(pattern: str) -> str | None:
    found = [p for p in glob.glob(pattern) if os.path.isfile(p)]
    return max(found, key=os.path.getmtime) if found else None


def _snapshot(pattern: str) -> dict[str, tuple[int, int]]:
    out = {}
    for p in glob.glob(pattern):
        try:
            st = os.stat(p)
            out[p] = (st.st_ino, st.st_size)
        except OSError:
            continue
    return out


def spec_for(system_id: str, rom_path: str, *, port: bool) -> dict | None:
    """The declared signal, paths resolved, or None for no cover."""
    if port:
        return native_ports.declared_ready(Path(rom_path), configgen.HOME)
    pack = load_catalog().get(system_id.lower())
    if pack is None:
        return None
    launch = pack.data.get("launch") or {}
    forced = launch.get("fullscreen") or {}
    # The windows the pack forces fullscreen are the game's even outside its
    # process group (a Lutris game).
    classes = {"fullscreenClass": list(forced["wmClass"])} if forced.get("wmClass") else {}
    ready = launch.get("ready")
    if not ready:
        return {"timeoutSec": forced.get("timeoutSec") or FULLSCREEN_CAP_S, **classes}
    if "log" in ready:
        return {**ready, "log": str(pack.expand(ready["log"], configgen.HOME)), **classes}
    return {**ready, **classes}


def _watch(game_key: str, system_id: str, rom_path: str, port: bool) -> Watch | None:
    spec = spec_for(system_id, rom_path, port=port)
    if not spec:
        return None
    w = Watch(game_key, system_id, spec, float(spec.get("timeoutSec") or DEFAULT_CAP_S))
    if "log" in spec:
        try:
            rx = re.compile(spec["match"])
        except re.error as e:
            log.warning("launch cover: %s: bad ready pattern %r: %s", system_id, spec["match"], e)
            return None
        w.cursor = _LogCursor(spec["log"], rx, _snapshot(spec["log"]))
    return w


async def _broadcast(event: str, w: Watch, **extra) -> None:
    try:
        await ws.broadcast(event, {"game_key": w.game_key, "system_id": w.system_id, **extra})
    except Exception:
        log.exception("launch cover: could not broadcast %s", event)


async def announce(game_key: str, system_id: str, rom_path: str, *, port: bool = False) -> Watch | None:
    """Before the spawn: note the log, tell the UI to cover the screen."""
    try:
        w = await asyncio.to_thread(_watch, game_key, system_id, rom_path, port)
    except Exception:
        log.exception("launch cover: %s: no cover", system_id)
        return None
    if w is not None:
        await _broadcast("game:loading", w, timeout_s=w.cap_s)
    return w


async def drop(w: Watch | None, reason: str) -> None:
    """Take the cover down now (the spawn failed, the game was resumed)."""
    if w is not None:
        await _broadcast("game:ready", w, reason=reason)


def _still_ours(w: Watch) -> bool:
    cur = process_manager.current_game
    return bool(cur) and cur["game_key"] == w.game_key and cur["system_id"] == w.system_id


async def _wait(w: Watch) -> str:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + w.cap_s
    while loop.time() < deadline:
        if not _still_ours(w):
            return "ended"
        if w.cursor is not None:
            found = await asyncio.to_thread(w.cursor.found)
        elif "wmClass" in w.spec:
            found = await asyncio.to_thread(fullscreen_enforcer.wait_for_window,
                                            w.spec["wmClass"], 1.0)
        else:
            reason = await _until_fullscreen(w, "fullscreen", deadline - loop.time())
            return await _until_painted(w, reason)
        if found:
            reason = await _hand_over(w)
            if reason == "ended":
                return reason
            reason = await _until_fullscreen(w, reason, FULLSCREEN_AFTER_SIGNAL_S)
            return await _until_painted(w, reason)
        await asyncio.sleep(POLL_S)
    return "timeout"


async def _until_painted(w: Watch, reason: str) -> str:
    """With `handOver: painted`, once fullscreen: until the game draws at the
    window's new size (window_black.painted). FIFA 22 under Lutris and Dolphin
    show their old-size frame on an unpainted or stale window for ~3 s after
    going fullscreen (recorded on the box). A window that cannot be read, or
    the `handOverSec` ceiling, leaves `reason` as it was."""
    if reason == "ended" or w.spec.get("handOver") != "painted":
        return reason
    session = process_manager.foreground_session
    pgid = session.pgid if session else 0
    classes = tuple(w.spec.get("fullscreenClass") or ())
    loop = asyncio.get_running_loop()
    deadline = loop.time() + float(w.spec.get("handOverSec") or HAND_OVER_CAP_S)
    while loop.time() < deadline:
        if not _still_ours(w):
            return "ended"
        drawn = await asyncio.to_thread(window_black.is_painted, pgid, classes)
        if drawn is None:
            return reason
        if drawn:
            return "painted"
        await asyncio.sleep(PAINT_POLL_S)
    return reason


async def _until_fullscreen(w: Watch, reason: str, cap_s: float) -> str:
    """Until the game's windows fill the screen (window_black.covers_screen):
    the cover must not drop on a small window about to go fullscreen. A window
    that cannot be read, or the ceiling, leaves `reason` as it was."""
    session = process_manager.foreground_session
    pgid = session.pgid if session else 0
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max(cap_s, 0)
    while loop.time() < deadline:
        if not _still_ours(w):
            return "ended"
        full = await asyncio.to_thread(window_black.covers_screen, pgid,
                                       tuple(w.spec.get("fullscreenClass") or ()))
        if full is None or full:
            return reason
        await asyncio.sleep(HAND_OVER_POLL_S)
    return reason


async def _hand_over(w: Watch) -> str:
    """After the signal, until the game's window goes black: the emulator keeps
    its own loading screen up a moment longer (God of War 3: 0.4 s, Animal
    Crossing: 4 s on the reference box). Its ceiling is a net for a game that
    never shows black; a window that cannot be read leaves the log's word."""
    if w.spec.get("handOver") != "black":
        return "signal"
    session = process_manager.foreground_session
    pgid = session.pgid if session else 0
    loop = asyncio.get_running_loop()
    deadline = loop.time() + float(w.spec.get("handOverSec") or HAND_OVER_CAP_S)
    while loop.time() < deadline:
        if not _still_ours(w):
            return "ended"
        black = await asyncio.to_thread(window_black.is_black, pgid)
        if black is None:
            return "signal"
        if black:
            return "black"
        await asyncio.sleep(HAND_OVER_POLL_S)
    return "signal"


async def _run(w: Watch) -> None:
    reason = "timeout"
    try:
        reason = await _wait(w)
    except Exception:
        log.exception("launch cover: %s: watching failed, dropping the cover", w.system_id)
    log.info("launch cover: %s %s: %s", w.system_id, w.game_key, reason)
    await _broadcast("game:ready", w, reason=reason)


def follow(w: Watch | None, resumed: bool) -> None:
    """After the spawn: wait for the signal in the background."""
    if w is None:
        return
    task = asyncio.create_task(drop(w, "resumed") if resumed else _run(w))
    task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
