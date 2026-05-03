"""SQLite database — playtime."""
import aiosqlite
from .config import PLAYTIME_DB

_DB: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    global _DB
    if _DB is not None:
        try:
            await _DB.execute("SELECT 1")
            return _DB
        except Exception:
            _DB = None
    _DB = await aiosqlite.connect(PLAYTIME_DB)
    _DB.row_factory = aiosqlite.Row
    return _DB


async def init_db() -> None:
    db = await get_db()
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS playtime (
            game_key    TEXT PRIMARY KEY,
            system_id   TEXT NOT NULL,
            total_secs  INTEGER NOT NULL DEFAULT 0,
            session_count INTEGER NOT NULL DEFAULT 0,
            last_played TEXT
        );
        CREATE TABLE IF NOT EXISTS sessions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            game_key    TEXT NOT NULL,
            system_id   TEXT NOT NULL,
            started_at  TEXT NOT NULL,
            ended_at    TEXT,
            duration    INTEGER
        );
    """)
    await db.commit()
