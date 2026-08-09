"""Playtime must survive a change in what the library lists.

`game_key` is the filename the library showed. Hiding a `.bin` behind its
`.cue` therefore orphans every hour recorded against that `.bin`: the row stays
in the database, nothing points at it, and a game played for hours reports as
never played. Measured on the reference box before this existed — one row,
15 minutes, 21 sessions.
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

_root = os.environ.get("GAMECORE_TEST_ROOT")
if _root is None:
    _root = str(Path(tempfile.mkdtemp(prefix="gamecore-test-")) / "fake_root")
    os.environ["GAMECORE_TEST_ROOT"] = _root
    os.environ["GAMECORE_PATH"] = _root
ROOT = Path(_root)


def _library(tmp_path: Path) -> Path:
    """A GAMECORE_ROOT with one PS1 dump and a systems.json pointing at it."""
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    roms = tmp_path / "emu" / "duckstation"
    roms.mkdir(parents=True, exist_ok=True)
    # The real shape: the .cue names a .bin that was renamed away.
    (roms / "Dragon Ball Z .cue").write_text('FILE "Dragon Ball Z (Europe).bin" BINARY\n')
    (roms / "Dragon Ball Z .bin").write_bytes(b"x")
    (tmp_path / "config" / "systems.json").write_text(json.dumps([{
        "id": "duckstation", "name": "PS1", "romsPath": "emu/duckstation/",
        "extensions": ["*.bin", "*.cue"], "path": "/bin/true",
    }]))
    (tmp_path / "config" / "apps.json").write_text("[]")
    return tmp_path


def _run(tmp_path: Path, seed: list[tuple], passes: int = 1) -> tuple[list, list[int]]:
    """Seed playtime rows, run the repair `passes` times, return the final rows.

    Everything happens inside a single `asyncio.run`: an aiosqlite connection
    belongs to the loop that opened it, and the module keeps a global one.
    """
    from backend import config, db as dbmod
    from backend.routers import systems as systems_router
    from backend.services import paths, playtime_repair

    # config caches its paths at import; point them at this library.
    # `paths.use_roots` first: `romsPath` is relative and resolves against the
    # DATA root, so without it the repair would scan the suite's throwaway root
    # instead of this library — and report nothing to repair, in green.
    paths.use_roots(tmp_path)
    config.GAMECORE_ROOT = tmp_path
    config.SYSTEMS_FILE = tmp_path / "config" / "systems.json"
    config.APPS_FILE = tmp_path / "config" / "apps.json"
    config.PLAYTIME_DB = tmp_path / "config" / "playtime.db"
    systems_router.SYSTEMS_FILE = config.SYSTEMS_FILE
    systems_router.APPS_FILE = config.APPS_FILE
    systems_router._file_cache.clear()
    dbmod.PLAYTIME_DB = config.PLAYTIME_DB
    dbmod._DB = None

    async def main():
        await dbmod.init_db()
        d = await dbmod.get_db()
        for key, sid, secs, count, last in seed:
            await d.execute(
                "INSERT INTO playtime (game_key, system_id, total_secs, session_count, last_played)"
                " VALUES (?,?,?,?,?)", (key, sid, secs, count, last))
            await d.execute(
                "INSERT INTO sessions (game_key, system_id, started_at) VALUES (?,?,?)",
                (key, sid, last))
        await d.commit()

        moved = [await playtime_repair.rekey_shadowed_entries() for _ in range(passes)]

        rows = [tuple(r) for r in await (await d.execute(
            "SELECT game_key, system_id, total_secs, session_count, last_played"
            " FROM playtime ORDER BY game_key")).fetchall()]
        sessions = [tuple(r) for r in await (await d.execute(
            "SELECT game_key FROM sessions")).fetchall()]
        await d.close()
        dbmod._DB = None
        return rows, sessions, moved

    rows, sessions, moved = asyncio.run(main())
    return (rows, sessions), moved


def test_playtime_follows_the_file_that_replaced_it(tmp_path):
    (rows, sessions), moved = _run(_library(tmp_path), [
        ("Dragon Ball Z .bin", "duckstation", 909, 21, "2026-07-20T21:07:29+00:00"),
    ])
    assert moved == [1]
    assert rows == [("Dragon Ball Z .cue", "duckstation", 909, 21,
                     "2026-07-20T21:07:29+00:00")], rows
    # The history moves too, so "Recent" keeps working.
    assert sessions == [("Dragon Ball Z .cue",)]


def test_the_repair_is_idempotent(tmp_path):
    """It runs on every start. The second pass must find nothing to do."""
    (rows, _), moved = _run(_library(tmp_path), [
        ("Dragon Ball Z .bin", "duckstation", 909, 21, "2026-07-20T21:07:29+00:00"),
    ], passes=3)
    assert moved == [1, 0, 0]
    assert len(rows) == 1 and rows[0][2] == 909


def test_both_halves_are_merged_not_dropped(tmp_path):
    """The player may have launched the .cue too — both are time on one game."""
    (rows, _), moved = _run(_library(tmp_path), [
        ("Dragon Ball Z .bin", "duckstation", 909, 21, "2026-07-20T21:07:29+00:00"),
        ("Dragon Ball Z .cue", "duckstation", 600, 4, "2026-01-01T00:00:00+00:00"),
    ])
    assert moved == [1]
    assert len(rows) == 1, rows
    key, _sid, secs, count, last = rows[0]
    assert key == "Dragon Ball Z .cue"
    assert secs == 1509 and count == 25          # nothing is lost
    assert last == "2026-07-20T21:07:29+00:00"   # the later of the two


def test_a_library_with_nothing_to_repair_is_left_alone(tmp_path):
    root = _library(tmp_path)
    (rows, _), moved = _run(root, [
        ("Some Other Game.iso", "duckstation", 120, 2, "2026-05-05T00:00:00+00:00"),
    ])
    assert moved == [0]
    assert rows == [("Some Other Game.iso", "duckstation", 120, 2,
                     "2026-05-05T00:00:00+00:00")]


def _old_catalogue_library(tmp_path: Path) -> Path:
    """A box whose systems.json predates `*.cue` — config/ is OTA-excluded."""
    root = _library(tmp_path)
    (root / "config" / "systems.json").write_text(json.dumps([{
        "id": "duckstation", "name": "PS1", "romsPath": "emu/duckstation/",
        "extensions": ["*.bin", "*.iso", "*.img", "*.zip"],   # no *.cue
        "path": "/bin/true",
    }]))
    return root


def test_playtime_comes_back_when_the_descriptor_is_not_listed(tmp_path):
    """The state a bad release left this box in.

    A version that hid the .bin behind a .cue the catalogue does not scan moved
    the playtime onto that .cue. Once the .bin is listed again, the hours have
    to come back to it — otherwise the fix leaves the data exactly as
    unreachable as the bug did.
    """
    (rows, sessions), moved = _run(_old_catalogue_library(tmp_path), [
        ("Dragon Ball Z .cue", "duckstation", 909, 21, "2026-07-20T21:07:29+00:00"),
    ])
    assert moved == [1]
    assert rows == [("Dragon Ball Z .bin", "duckstation", 909, 21,
                     "2026-07-20T21:07:29+00:00")], rows
    assert sessions == [("Dragon Ball Z .bin",)]


def test_the_direction_follows_the_catalogue_not_the_extension(tmp_path):
    """Same two files, opposite catalogues, opposite moves."""
    (rows_new, _), _ = _run(_library(tmp_path / "new"), [
        ("Dragon Ball Z .bin", "duckstation", 60, 1, "2026-01-01T00:00:00+00:00"),
    ])
    (rows_old, _), _ = _run(_old_catalogue_library(tmp_path / "old"), [
        ("Dragon Ball Z .bin", "duckstation", 60, 1, "2026-01-01T00:00:00+00:00"),
    ])
    assert rows_new[0][0] == "Dragon Ball Z .cue"   # catalogue scans *.cue
    assert rows_old[0][0] == "Dragon Ball Z .bin"   # catalogue does not


def test_a_group_nobody_lists_is_left_alone(tmp_path):
    """No visible representative → no move. Moving it would hide it further."""
    root = _library(tmp_path)
    (root / "config" / "systems.json").write_text(json.dumps([{
        "id": "duckstation", "name": "PS1", "romsPath": "emu/duckstation/",
        "extensions": ["*.chd"],                      # neither .bin nor .cue
        "path": "/bin/true",
    }]))
    (rows, _), moved = _run(root, [
        ("Dragon Ball Z .cue", "duckstation", 909, 21, "2026-07-20T21:07:29+00:00"),
    ])
    assert moved == [0]
    assert rows[0][0] == "Dragon Ball Z .cue"
