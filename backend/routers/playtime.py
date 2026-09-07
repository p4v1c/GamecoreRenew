"""Playtime queries."""
from fastapi import APIRouter
from ..db import get_db

router = APIRouter(tags=["playtime"])


@router.get("/playtime")
async def get_all_playtime():
    db = await get_db()
    rows = await db.execute_fetchall("SELECT * FROM playtime ORDER BY last_played DESC")
    return [dict(r) for r in rows]


@router.get("/playtime/system/{system_id}")
async def get_system_playtime(system_id: str):
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT * FROM playtime WHERE system_id = ? ORDER BY total_secs DESC",
        (system_id,)
    )
    return [dict(r) for r in rows]


@router.get("/playtime/game/{game_key:path}")
async def get_game_playtime(game_key: str, system_id: str | None = None):
    """One game's playtime — for one console, or across all of them.

    A filename does not identify a game: `Same name.chd` exists under
    DuckStation and under PCSX2, and the table is keyed by the pair. Callers
    that know which console they mean should say so; the total is what is left
    to answer when they do not, and summing is at least true, where returning
    whichever row came first was not.
    """
    db = await get_db()
    # aiosqlite has no execute_fetchone — go through a cursor explicitly
    if system_id is not None:
        cur = await db.execute(
            "SELECT * FROM playtime WHERE system_id = ? AND game_key = ?",
            (system_id, game_key))
        row = await cur.fetchone()
        await cur.close()
        if not row:
            return {"game_key": game_key, "system_id": system_id,
                    "total_secs": 0, "session_count": 0, "last_played": None}
        return dict(row)

    rows = await db.execute_fetchall(
        "SELECT * FROM playtime WHERE game_key = ?", (game_key,))
    if not rows:
        return {"game_key": game_key, "total_secs": 0, "session_count": 0, "last_played": None}
    played = [r["last_played"] for r in rows if r["last_played"]]
    return {
        "game_key": game_key,
        "total_secs": sum(r["total_secs"] or 0 for r in rows),
        "session_count": sum(r["session_count"] or 0 for r in rows),
        "last_played": max(played) if played else None,
    }
