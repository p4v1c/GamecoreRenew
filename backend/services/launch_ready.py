"""The launch cover: when the game behind it is really running.

A pack's `launch.ready` (a port's `# gamecore-ready-*` lines) names the signal:
a line in the emulator's log, or its window appearing. `announce()` runs
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
from . import configgen, fullscreen_enforcer, native_ports
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
    ready = (pack.data.get("launch") or {}).get("ready") if pack else None
    if not ready:
        return None
    if "log" in ready:
        return {**ready, "log": str(pack.expand(ready["log"], configgen.HOME))}
    return dict(ready)


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
        else:
            found = await asyncio.to_thread(fullscreen_enforcer.wait_for_window,
                                            w.spec["wmClass"], 1.0)
        if found:
            return "signal"
        await asyncio.sleep(POLL_S)
    return "timeout"


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
