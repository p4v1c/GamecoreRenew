"""SQLite database — playtime, and the Store's acquisition queue.

One database, `<DATA>/config/playtime.db`, and it holds both. A second store —
a JSON file of jobs beside it, or a `store.db` of its own — would be a second
schema to migrate, a second handle to keep alive across the box's suspend
cycles, and a second answer to "is this file the player's data" for the
uninstaller and the OTA to disagree about.

**What that inherits, stated once here and again in
`docs/architecture/07-config-and-data.md`:** `config/` is excluded from the OTA
rsync and kept by `install/uninstall.sh` unless `--purge` is given — and on a
box with separate roots the uninstaller does not touch the data root at all. So
a download history survives an uninstall exactly as the play history does. That
is the behaviour this product already has for `playtime`; the Store's queue
joins it rather than inventing a second rule, and it is written down so that
nobody has to discover it.
"""
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
        CREATE TABLE IF NOT EXISTS store_jobs (
            id          TEXT PRIMARY KEY,
            system_id   TEXT NOT NULL,
            roms_dir    TEXT NOT NULL DEFAULT '',
            title       TEXT NOT NULL,
            filename    TEXT NOT NULL,
            format      TEXT NOT NULL DEFAULT '',
            size        INTEGER NOT NULL DEFAULT 0,
            provider    TEXT NOT NULL,
            source      TEXT NOT NULL,
            state       TEXT NOT NULL,
            reason      TEXT NOT NULL DEFAULT '',
            queued_at   TEXT NOT NULL,
            started_at  TEXT,
            ended_at    TEXT,
            downloaded_bytes INTEGER NOT NULL DEFAULT 0,
            download_total   INTEGER NOT NULL DEFAULT 0,
            ingestion_class  TEXT NOT NULL DEFAULT '',
            transformed_bytes INTEGER NOT NULL DEFAULT 0,
            transform_total   INTEGER NOT NULL DEFAULT 0,
            validation        TEXT NOT NULL DEFAULT '',
            bios_warning      TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS store_jobs_by_state
            ON store_jobs (state, queued_at);
    """)
    await _widen_playtime_key(db)
    await _widen_store_jobs(db)
    await db.commit()


async def _widen_store_jobs(db: aiosqlite.Connection) -> None:
    """Add later Store-job facts to databases made before they existed.

    SQLite has no ``ADD COLUMN IF NOT EXISTS``. Inspect first so this remains
    idempotent on every boot, like the table creation around it.
    """
    cur = await db.execute("PRAGMA table_info(store_jobs)")
    columns = {row["name"] for row in await cur.fetchall()}
    await cur.close()
    if "downloaded_bytes" not in columns:
        await db.execute(
            "ALTER TABLE store_jobs ADD COLUMN downloaded_bytes INTEGER NOT NULL DEFAULT 0")
    if "download_total" not in columns:
        await db.execute(
            "ALTER TABLE store_jobs ADD COLUMN download_total INTEGER NOT NULL DEFAULT 0")
    if "ingestion_class" not in columns:
        await db.execute(
            "ALTER TABLE store_jobs ADD COLUMN ingestion_class TEXT NOT NULL DEFAULT ''")
    # Transformation progress is its own pair and not a second writer of the
    # download's: one bar that means "downloading" for a while and then
    # "unpacking" is a bar nobody can read, and a test asserting how many
    # bytes arrived would start asserting how many were produced.
    if "transformed_bytes" not in columns:
        await db.execute(
            "ALTER TABLE store_jobs ADD COLUMN transformed_bytes INTEGER NOT NULL DEFAULT 0")
    if "transform_total" not in columns:
        await db.execute(
            "ALTER TABLE store_jobs ADD COLUMN transform_total INTEGER NOT NULL DEFAULT 0")
    # The validation verdict is its own fact and not a spelling of `reason`:
    # a job can be `verified` and still fail (nothing imports it yet), and a
    # row that only carried the sentence could not be asked "which downloads
    # on this box were never proven to be what they claimed".
    if "validation" not in columns:
        await db.execute(
            "ALTER TABLE store_jobs ADD COLUMN validation TEXT NOT NULL DEFAULT ''")
    # And the BIOS warning is a third fact again — about the box, not about
    # the download. Folded into the verdict it would read as a fault of the
    # file; folded into `reason` it would vanish the moment a later step
    # rewrote the sentence (matrix §5.3 rule 4).
    if "bios_warning" not in columns:
        await db.execute(
            "ALTER TABLE store_jobs ADD COLUMN bios_warning TEXT NOT NULL DEFAULT ''")


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
