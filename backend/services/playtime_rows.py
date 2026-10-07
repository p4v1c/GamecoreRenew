"""Whose playtime a query reads and a finished game adds to.

Playtime and "recently played" follow the profile playing. The primary
profile's rows stay in `playtime`, exactly where every figure from before
profiles is, so nothing is migrated and the playtime repair keeps working on
them. Any other profile's rows are in `profile_playtime`, keyed by its id.

A game is billed to the profile active when it ends. That is the one that
started it: the active profile cannot change while a game is on screen or
suspended (`profiles.set_active`).
"""
from __future__ import annotations

from . import profiles

_COLUMNS = "game_key, system_id, total_secs, session_count, last_played"


def _other_profile() -> str | None:
    """The active profile's id, or None for the primary one."""
    active = profiles.active()
    return None if active.get("primary") else active["id"]


def source() -> tuple[str, tuple]:
    """(`FROM` target, its parameters) for the active profile's rows, with the
    same columns as `playtime`: callers write `SELECT * FROM {target}`."""
    pid = _other_profile()
    if pid is None:
        return "playtime", ()
    return f"(SELECT {_COLUMNS} FROM profile_playtime WHERE profile_id = ?)", (pid,)


async def record(db, game_key: str, system_id: str, elapsed: int, when: str) -> None:
    """Add one finished session to the active profile's row for this game."""
    pid = _other_profile()
    update = """ DO UPDATE SET
            total_secs    = total_secs + excluded.total_secs,
            session_count = session_count + 1,
            last_played   = excluded.last_played"""
    if pid is None:
        await db.execute(f"""
            INSERT INTO playtime ({_COLUMNS}) VALUES (?, ?, ?, 1, ?)
            ON CONFLICT(system_id, game_key){update}""",
            (game_key, system_id, elapsed, when))
    else:
        await db.execute(f"""
            INSERT INTO profile_playtime (profile_id, {_COLUMNS}) VALUES (?, ?, ?, ?, 1, ?)
            ON CONFLICT(profile_id, system_id, game_key){update}""",
            (pid, game_key, system_id, elapsed, when))
    await db.commit()
