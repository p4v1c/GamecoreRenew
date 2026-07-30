"""Carry a game's playtime across when the file that represents it changes.

Playtime is keyed by the filename the library listed — `game_key` in the
playtime and sessions tables. So the day the library stops listing a file, the
hours recorded against it stop being reachable: the row is still in the
database, nothing points at it any more, and the player sees a game they have
played for hours reported as never played.

That is exactly what hiding a `.bin` behind its `.cue` does
(rom_scanner.shadowed_by_a_descriptor). Measured on the reference box, one row:

    duckstation | Dragon Ball Z - Ultimate Battle 22 .bin | 15 min | 21 sessions

So the rename is followed here, once, at startup. The covers and metadata
caches need nothing: both are keyed on the *stem*, which `.bin` and `.cue`
share.

Idempotent by construction — after the first pass no row matches a hidden name
any more — and silent when there is nothing to do, which is every start after
the first and every box that owns no disc image.
"""
import logging
from pathlib import Path

from ..config import resolve_path
from ..db import get_db
from ..routers.systems import list_all
from .rom_scanner import shadowed_by_a_descriptor

log = logging.getLogger(__name__)


def _rename_map() -> dict[tuple[str, str], str]:
    """{(system_id, old lowercased filename): the filename now listed}."""
    out: dict[tuple[str, str], str] = {}
    for system in list_all():
        if system.get("kind") != "emulator" or system.get("scanDirs"):
            continue
        roms = resolve_path(system.get("romsPath", ""))
        if not roms or not roms.exists():
            continue
        try:
            entries = sorted(roms.iterdir(), key=lambda x: x.name.lower())
        except OSError:
            continue
        sid = system["id"]
        # The system's own extensions, for the same reason iter_rom_files
        # passes them: a descriptor this system does not scan replaces nothing,
        # so nothing may be re-keyed onto it. Moving playtime onto an entry the
        # library will never list would hide it just as thoroughly as the bug
        # this function exists to prevent.
        for hidden, owner in shadowed_by_a_descriptor(
                entries, system.get("extensions") or []).items():
            out[(sid, hidden)] = owner
    return out


async def rekey_shadowed_entries() -> int:
    """Move playtime from files the library no longer lists onto what replaced
    them. Returns the number of rows moved."""
    try:
        renames = _rename_map()
    except Exception:
        log.exception("playtime repair: could not scan the libraries")
        return 0
    if not renames:
        return 0

    db = await get_db()
    moved = 0
    try:
        rows = await (await db.execute(
            "SELECT game_key, system_id, total_secs, session_count, last_played "
            "FROM playtime")).fetchall()

        for row in rows:
            new_key = renames.get((row["system_id"], row["game_key"].lower()))
            if not new_key or new_key == row["game_key"]:
                continue

            # The destination may already exist — the player launched the .cue
            # at some point too. Merge rather than pick one: both halves are
            # time actually spent on the same game.
            existing = await (await db.execute(
                "SELECT total_secs, session_count, last_played FROM playtime "
                "WHERE game_key = ?", (new_key,))).fetchone()

            if existing:
                await db.execute(
                    "UPDATE playtime SET total_secs = ?, session_count = ?, "
                    "last_played = ? WHERE game_key = ?",
                    (existing["total_secs"] + row["total_secs"],
                     existing["session_count"] + row["session_count"],
                     max(filter(None, (existing["last_played"], row["last_played"])),
                         default=None),
                     new_key))
                await db.execute("DELETE FROM playtime WHERE game_key = ?",
                                 (row["game_key"],))
            else:
                await db.execute("UPDATE playtime SET game_key = ? WHERE game_key = ?",
                                 (new_key, row["game_key"]))

            # The session history moves with it, so "Recent" keeps working and
            # a future feature reading `sessions` sees one continuous history.
            await db.execute("UPDATE sessions SET game_key = ? WHERE game_key = ?",
                             (new_key, row["game_key"]))
            moved += 1
            log.info("playtime repair: %s/%r → %r (%d min, %d sessions)",
                     row["system_id"], row["game_key"], new_key,
                     row["total_secs"] // 60, row["session_count"])

        if moved:
            await db.commit()
    except Exception:
        # Never fatal: a box that boots is worth more than a tidy database, and
        # nothing here deletes data that was not merged into its replacement.
        log.exception("playtime repair: failed")
        return 0
    return moved
