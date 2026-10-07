"""Playtime and recents follow the profile: the primary's stay in `playtime`,
where every figure from before profiles is; another profile's are its own."""
from __future__ import annotations

import asyncio

import pytest

from backend.services import paths, playtime_rows, profiles


@pytest.fixture
def box(tmp_path, monkeypatch):
    from backend import config, db as dbmod
    before = (paths.GAMECORE_ROOT, paths.GAMECORE_DATA)
    paths.use_roots(tmp_path / "code", tmp_path / "data")
    monkeypatch.setattr(config, "PLAYTIME_DB", tmp_path / "playtime.db")
    monkeypatch.setattr(dbmod, "PLAYTIME_DB", tmp_path / "playtime.db")
    monkeypatch.setattr(dbmod, "_DB", None)
    yield dbmod
    paths.use_roots(*before)


def _played(dbmod, sessions: list[tuple[str | None, str, int]]) -> tuple[list, list, list]:
    """Play (profile id or None for the primary, game, seconds), then read each view."""
    async def main():
        await dbmod.init_db()
        db = await dbmod.get_db()
        for pid, game, secs in sessions:
            profiles.set_active(pid or profiles.list_profiles()["profiles"][0]["id"])
            await playtime_rows.record(db, game, "nes", secs, f"2026-10-0{secs % 9 + 1}")

        async def view():
            src, args = playtime_rows.source()
            return [(r["game_key"], r["total_secs"]) for r in
                    await db.execute_fetchall(f"SELECT * FROM {src} ORDER BY game_key", args)]
        first = profiles.list_profiles()["profiles"][0]["id"]
        profiles.set_active(first)
        primary = await view()
        others = []
        for p in profiles.list_profiles()["profiles"][1:]:
            profiles.set_active(p["id"])
            others.append(await view())
        legacy = [tuple(r) for r in await db.execute_fetchall("SELECT game_key, total_secs FROM playtime")]
        await db.close()
        dbmod._DB = None
        return primary, others, legacy
    return asyncio.run(main())


def test_each_profile_has_its_own_playtime_and_recents(box):
    profiles.update(profiles.active()["id"], {"name": "Max"})
    sam = profiles.create("Sam")["id"]
    primary, (sams,), legacy = _played(box, [(None, "zelda.nes", 60), (sam, "zelda.nes", 30),
                                             (sam, "metroid.nes", 20), (sam, "metroid.nes", 20)])
    assert primary == [("zelda.nes", 60)]
    assert sams == [("metroid.nes", 40), ("zelda.nes", 30)]
    assert legacy == [("zelda.nes", 60)], "the primary's table holds the primary only"


def test_a_box_without_profiles_reads_and_writes_playtime_as_before(box):
    primary, others, legacy = _played(box, [(None, "zelda.nes", 60)])
    assert primary == legacy == [("zelda.nes", 60)] and others == []
