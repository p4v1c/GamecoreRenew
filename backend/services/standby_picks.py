"""Which games the standby TV shows first: the ones people actually play.

Value is hours played plus how recently, summed over every profile, so the box
spends its video budget on the games of the people who use it. Unplayed games
come after, in a fixed mix across consoles rather than alphabetically (an
alphabetical tail would be all of one system's "A" games).

Favourites are not here: they live in each theme's localStorage, which the
backend never sees. The playlist accepts them as a hint instead
(`standby_videos.playlist(favourites=...)`).
"""
from __future__ import annotations

import hashlib
import math
import random
from datetime import datetime, timezone

from ..config import resolve_path
from ..db import get_db
from . import local_media
from .rom_scanner import clean_name, iter_rom_files
from .systems import list_all

# Points, not units: 50 h played or a game played today both score 10.
HOURS_CAP = 50
RECENT_DAYS = 30


def value(total_secs: int, last_played: str | None, now: datetime) -> float:
    """How much a game deserves a video. 0 for a game nobody has played."""
    hours = min((total_secs or 0) / 3600, HOURS_CAP)
    score = hours / HOURS_CAP * 10
    days = days_since(last_played, now)
    if days is not None:
        score += max(0.0, RECENT_DAYS - days) / RECENT_DAYS * 10
    return score


def days_since(stamp: str | None, now: datetime) -> float | None:
    """Days between an ISO timestamp from the playtime table and `now`."""
    if not stamp:
        return None
    try:
        when = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    if when.tzinfo is None:
        # The table stores local wall-clock time without an offset.
        when = when.replace(tzinfo=now.tzinfo)
    return max(0.0, (now - when).total_seconds() / 86400)


def _mix_key(game: dict) -> str:
    """Stable but scattered order for the unplayed tail."""
    return hashlib.sha1(f"{game['system_id']}/{game['filename']}".encode()).hexdigest()


def rank(games: list[dict], played: dict[tuple[str, str], dict],
         now: datetime | None = None) -> list[dict]:
    """`games` most valuable first, each with `value` and `last_played` filled in.

    `played` maps (system_id, filename), lowercased system, to
    {total_secs, last_played}. Pure: no disk, no clock unless `now` is None.
    """
    now = now or datetime.now(timezone.utc).astimezone()
    out = []
    for g in games:
        row = played.get((g["system_id"].lower(), g["filename"])) or {}
        out.append({**g, "last_played": row.get("last_played"),
                    "value": value(row.get("total_secs", 0), row.get("last_played"), now)})
    out.sort(key=lambda g: (-g["value"], _mix_key(g)))
    return out


def weighted_shuffle(items: list[dict], rng: random.Random,
                     favourites: set[tuple[str, str]] = frozenset()) -> list[dict]:
    """Random order where valuable games tend to come first.

    Efraimidis-Spirakis: key = u^(1/w). Weight 1 + value, doubled for a
    favourite, so an unplayed game still turns up now and then.
    """
    def key(item: dict) -> float:
        weight = 1 + item.get("value", 0)
        if (item["system_id"].lower(), item["filename"]) in favourites:
            weight *= 2
        return math.log(rng.random() or 1e-12) / weight

    return sorted(items, key=key, reverse=True)


async def played_rows() -> dict[tuple[str, str], dict]:
    """Playtime of every profile, merged per game: hours summed, latest date kept."""
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT system_id, game_key, total_secs, last_played FROM playtime "
        "UNION ALL SELECT system_id, game_key, total_secs, last_played FROM profile_playtime")
    merged: dict[tuple[str, str], dict] = {}
    for r in rows:
        key = (str(r["system_id"]).lower(), r["game_key"])
        cur = merged.setdefault(key, {"total_secs": 0, "last_played": None})
        cur["total_secs"] += r["total_secs"] or 0
        if r["last_played"] and (cur["last_played"] or "") < r["last_played"]:
            cur["last_played"] = r["last_played"]
    return merged


def library() -> list[dict]:
    """Every ROM on the box: system_id, filename, display_name, system_name, target.

    `target` is the ROM's path, what gamemedia identifies a game by. Same scan
    and same names as the library listing (routers/games.scan_roms).
    """
    games = []
    for system in list_all():
        if system.get("kind") != "emulator":
            continue
        roms = resolve_path(system.get("romsPath", ""))
        if not roms:
            continue
        scan_dirs = system.get("scanDirs", False)
        for f in iter_rom_files(roms, system.get("extensions", []), scan_dirs=scan_dirs):
            title = local_media.get_title(system["id"], f) if scan_dirs else None
            games.append({
                "system_id": system["id"].lower(),
                "filename": f.name,
                "display_name": title or clean_name(f.name),
                "system_name": system.get("label") or system["id"],
                "target": str(f),
            })
    return games
