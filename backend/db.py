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
            game_key    TEXT NOT NULL,
            system_id   TEXT NOT NULL,
            total_secs  INTEGER NOT NULL DEFAULT 0,
            session_count INTEGER NOT NULL DEFAULT 0,
            last_played TEXT,
            PRIMARY KEY (system_id, game_key)
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
    await _widen_playtime_key(db)
    await db.commit()


async def _widen_playtime_key(db: aiosqlite.Connection) -> None:
    """Move an existing playtime table onto (system_id, game_key).

    A game is a filename inside a console, not a filename. The old primary key
    was `game_key` alone, so two consoles holding a file of the same name — the
    multi-disc `Same name.chd`, or the same game dumped for PS1 and PS2 — wrote
    to one row: an hour of DuckStation and an hour of PCSX2 became two hours of
    whichever console got there first, and the second console had no row at all.

    The rows themselves are carried over exactly as they are. What has already
    been merged cannot be split again — nothing records which console each of
    those sessions belonged to — and inventing a division would be worse than
    the wrong total, so each row keeps the system it is labelled with.

    Runs on every start and does nothing after the first: the table it creates
    is already in the shape it tests for.
    """
    cur = await db.execute("PRAGMA table_info(playtime)")
    cols = await cur.fetchall()
    await cur.close()
    # `pk` is the 1-based position in the primary key, 0 for a column outside
    # it. The old table has game_key at 1 and system_id at 0.
    keyed = {row["name"]: row["pk"] for row in cols}
    if keyed.get("system_id"):
        return

    # SAVEPOINT also works when the caller already owns a transaction. Avoid
    # executescript here: it commits an existing transaction before executing.
    await db.execute("SAVEPOINT widen_playtime")
    try:
        await db.execute("""
            CREATE TABLE playtime_new (
                game_key TEXT NOT NULL,
                system_id TEXT NOT NULL,
                total_secs INTEGER NOT NULL DEFAULT 0,
                session_count INTEGER NOT NULL DEFAULT 0,
                last_played TEXT,
                PRIMARY KEY (system_id, game_key)
            )
        """)
        await db.execute("""
            INSERT INTO playtime_new
                (game_key, system_id, total_secs, session_count, last_played)
            SELECT game_key, system_id, total_secs, session_count, last_played FROM playtime
        """)
        await db.execute("DROP TABLE playtime")
        await db.execute("ALTER TABLE playtime_new RENAME TO playtime")
        await db.execute("RELEASE SAVEPOINT widen_playtime")
    except BaseException:
        # Cancellation must roll back too; callers must never observe half a schema.
        await db.execute("ROLLBACK TO SAVEPOINT widen_playtime")
        await db.execute("RELEASE SAVEPOINT widen_playtime")
        raise
