"""Who a finished game belongs to, and which console a played hour belongs to.

Two defects from the 2026-09-04 audit (findings 3 and 9) and the reconnection
half of finding 2. They are one file because they are one mistake made in three
places: state that outlives the thing it describes.

  · `_watch()` read the manager's fields *after* its await, so the watcher of a
    game that had exited could describe — and erase — the game started since.
  · `playtime` was keyed by filename alone, so two consoles holding a file of
    the same name shared a row.
  · `ws.connect()` announced a running game and said nothing otherwise, so a
    client that missed `game:finished` during an outage had nothing to correct
    it.

Nothing here starts a process, opens a socket or touches a real database: the
children are fakes with a `wait()` this file resolves by hand, and the database
is `:memory:`.
"""
import asyncio
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import aiosqlite

from backend import db
from backend import ws
from backend.services import process_manager as pm


class FakeProcess:
    """A child that exits when the test says so."""

    def __init__(self):
        self.returncode = None
        self.done = asyncio.Event()

    async def wait(self):
        await self.done.wait()
        return self.returncode


def _silence(monkeypatch, manager=None):
    monkeypatch.setattr(pm, "display_env", AsyncMock(return_value={}))
    monkeypatch.setattr(pm.ws, "broadcast", AsyncMock())
    monkeypatch.setattr(pm.ws, "set_current_game", lambda data: None)
    if manager is not None:
        monkeypatch.setattr(manager, "_save_session", lambda: None)
        monkeypatch.setattr(manager, "_clear_session", lambda: None)


# ── the watcher and the game it is watching ──────────────────────────────────

def test_an_old_watcher_does_not_clear_the_game_that_replaced_it(monkeypatch):
    """The race is narrow and its result is a box that cannot be rescued.

    `is_running` frees the slot as soon as the child has a return code, which
    happens before the watcher's `await` resumes. A second launch can therefore
    complete inside that window — and the first watcher then woke up holding
    the manager's fields, which by now described the second game.
    """
    async def scenario():
        manager = pm.ProcessManager()
        first, second = FakeProcess(), FakeProcess()
        _silence(monkeypatch, manager)
        monkeypatch.setattr(pm.asyncio, "create_subprocess_exec",
                            AsyncMock(side_effect=[first, second]))

        await manager.launch("fake", "", game_key="old.rom", system_id="gc")
        await asyncio.sleep(0)          # the watcher is inside first.wait()
        first.returncode = 0            # the child is gone; the watcher is not
        await manager.launch("fake", "", game_key="new.rom", system_id="ps2")
        first.done.set()
        await asyncio.sleep(0)

        assert manager._proc is second, "the old watcher cleared the new process"
        assert manager.is_running
        assert manager._game_key == "new.rom"

    asyncio.run(scenario())


def test_each_launch_is_announced_under_its_own_number(monkeypatch):
    """The number is what lets a client refuse a finish it has moved on from."""
    async def scenario():
        manager = pm.ProcessManager()
        first, second = FakeProcess(), FakeProcess()
        broadcast = AsyncMock()
        _silence(monkeypatch, manager)
        monkeypatch.setattr(pm.ws, "broadcast", broadcast)
        monkeypatch.setattr(pm.asyncio, "create_subprocess_exec",
                            AsyncMock(side_effect=[first, second]))

        await manager.launch("fake", "", game_key="old.rom", system_id="gc")
        await asyncio.sleep(0)
        first.returncode = 0
        await manager.launch("fake", "", game_key="new.rom", system_id="ps2")

        started = [c.args[1] for c in broadcast.await_args_list if c.args[0] == "game:started"]
        assert [s["game_key"] for s in started] == ["old.rom", "new.rom"]
        assert started[0]["session"] != started[1]["session"]
        assert manager.current_game["session"] == started[1]["session"]

        # And the finish of the first run carries the first run's number.
        first.done.set()
        await asyncio.sleep(0)
        finished = [c.args[1] for c in broadcast.await_args_list if c.args[0] == "game:finished"]
        assert finished and finished[0]["session"] == started[0]["session"]

    asyncio.run(scenario())


# ── the console a played hour belongs to ─────────────────────────────────────

async def _memory_db(monkeypatch):
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    monkeypatch.setattr(db, "_DB", conn)
    monkeypatch.setattr(pm, "get_db", AsyncMock(return_value=conn))
    return conn


async def _play(monkeypatch, manager_system: str, game_key: str, seconds: int) -> None:
    """One finished session of `seconds`, recorded the way _watch() records it."""
    manager = pm.ProcessManager()
    proc = FakeProcess()
    proc.returncode = 0
    proc.done.set()
    manager._proc = proc
    manager._game_key = game_key
    manager._system_id = manager_system
    manager._start_time = time.time() - seconds
    monkeypatch.setattr(manager, "_clear_session", lambda: None)
    await manager._watch()


def test_two_consoles_holding_the_same_filename_keep_their_own_hours(monkeypatch):
    """`Same name.chd` under DuckStation is not the game under PCSX2.

    Before the composite key, the second console's hour was added to the first
    console's row: one line, 120 seconds, two sessions, and PCSX2 reporting a
    game it had run for a minute as never played.
    """
    async def scenario():
        conn = await _memory_db(monkeypatch)
        _silence(monkeypatch)
        try:
            await db.init_db()
            await _play(monkeypatch, "duckstation", "Same name.chd", 60)
            await _play(monkeypatch, "pcsx2", "Same name.chd", 60)

            rows = await conn.execute_fetchall(
                "SELECT * FROM playtime ORDER BY system_id")
            assert [(r["system_id"], r["total_secs"], r["session_count"]) for r in rows] == [
                ("duckstation", 60, 1), ("pcsx2", 60, 1)]
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_the_same_game_on_one_console_still_accumulates(monkeypatch):
    """The conflict clause still has to fire where it always did."""
    async def scenario():
        conn = await _memory_db(monkeypatch)
        _silence(monkeypatch)
        try:
            await db.init_db()
            await _play(monkeypatch, "duckstation", "Crash.bin", 60)
            await _play(monkeypatch, "duckstation", "Crash.bin", 30)

            rows = await conn.execute_fetchall("SELECT * FROM playtime")
            assert len(rows) == 1
            assert rows[0]["total_secs"] == 90
            assert rows[0]["session_count"] == 2
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_an_existing_database_is_widened_without_losing_or_inventing_hours(monkeypatch):
    """The migration carries rows across; it does not try to split them.

    A row that already merged two consoles cannot be divided again — nothing
    recorded which session belonged to which — so it keeps the console it is
    labelled with, and only what happens afterwards is kept apart.
    """
    async def scenario():
        conn = await aiosqlite.connect(":memory:")
        conn.row_factory = aiosqlite.Row
        monkeypatch.setattr(db, "_DB", conn)
        monkeypatch.setattr(pm, "get_db", AsyncMock(return_value=conn))
        _silence(monkeypatch)
        try:
            # v1 shape, and a row with the merge already in it.
            await conn.executescript("""
                CREATE TABLE playtime (
                    game_key    TEXT PRIMARY KEY,
                    system_id   TEXT NOT NULL,
                    total_secs  INTEGER NOT NULL DEFAULT 0,
                    session_count INTEGER NOT NULL DEFAULT 0,
                    last_played TEXT
                );
                INSERT INTO playtime VALUES ('Same name.chd', 'duckstation', 120, 2, '2026-09-01T10:00:00');
                INSERT INTO playtime VALUES ('Crash.bin', 'duckstation', 900, 21, '2026-09-02T10:00:00');
            """)
            await conn.commit()

            await db.init_db()

            rows = await conn.execute_fetchall("SELECT * FROM playtime ORDER BY game_key")
            assert [(r["game_key"], r["system_id"], r["total_secs"], r["session_count"])
                    for r in rows] == [
                ("Crash.bin", "duckstation", 900, 21),
                ("Same name.chd", "duckstation", 120, 2)]

            # From here on the second console gets its own line.
            await _play(monkeypatch, "pcsx2", "Same name.chd", 60)
            rows = await conn.execute_fetchall(
                "SELECT * FROM playtime WHERE game_key = 'Same name.chd' ORDER BY system_id")
            assert [(r["system_id"], r["total_secs"]) for r in rows] == [
                ("duckstation", 120), ("pcsx2", 60)]

            # And running it again does not create a third.
            await db.init_db()
            rows = await conn.execute_fetchall("SELECT * FROM playtime")
            assert len(rows) == 3
        finally:
            await conn.close()

    asyncio.run(scenario())


# ── what a reconnecting client is told ───────────────────────────────────────

class FakeSocket:
    def __init__(self):
        self.sent: list[str] = []

    async def accept(self):
        pass

    async def send_text(self, payload: str):
        self.sent.append(payload)


def test_connecting_is_told_about_the_empty_session_too():
    """Silence used to mean two different things.

    A client that lost the socket with a game running, and reconnected after
    the emulator had quit, never heard the `game:finished` it missed. Nothing
    contradicted what it still believed, and its session guard blocked the pad
    on every screen until a reload.
    """
    async def scenario():
        before = list(ws._clients)
        try:
            ws.set_current_game(None)
            empty = FakeSocket()
            await ws.connect(empty)
            assert empty.sent == ['{"event": "game:running", "data": {}}']

            ws.set_current_game({"game_key": "live.iso", "system_id": "ps2", "session": 4})
            live = FakeSocket()
            await ws.connect(live)
            assert '"live.iso"' in live.sent[0]
        finally:
            ws._clients[:] = before
            ws.set_current_game(None)

    asyncio.run(scenario())
