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
async def get_game_playtime(game_key: str):
    db = await get_db()
    # aiosqlite has no execute_fetchone — go through a cursor explicitly
    cur = await db.execute(
        "SELECT * FROM playtime WHERE game_key = ?", (game_key,)
    )
    row = await cur.fetchone()
    await cur.close()
    if not row:
        return {"game_key": game_key, "total_secs": 0, "session_count": 0, "last_played": None}
    return dict(row)
