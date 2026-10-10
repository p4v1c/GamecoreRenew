"""Standby TV clips: who gets one first, the 5 GB cap, no downloads during a
game, and the playlist the CRT standby reads. No network: gamemedia's fetch is
replaced by a function that writes a file of a chosen size."""
from __future__ import annotations

import asyncio
import json
import random
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routers import standby as standby_router
from backend.services import gamemedia, prefetch, standby_picks, standby_videos
from backend.services.gamemedia import gamemedia as gm

NOW = datetime(2026, 10, 10, 20, 0, tzinfo=timezone.utc)


def _game(sid: str, name: str) -> dict:
    return {"system_id": sid, "filename": name, "display_name": Path(name).stem,
            "system_name": sid.upper(), "target": f"/roms/{sid}/{name}"}


# ── Selection order ─────────────────────────────────────────────────────────

def test_most_played_and_recent_games_come_first_then_the_rest():
    games = [_game("nes", n) for n in ("Never.nes", "Long ago.nes", "Lots.nes", "Yesterday.nes")]
    played = {
        ("nes", "Long ago.nes"): {"total_secs": 600, "last_played": "2026-01-01T10:00:00"},
        ("nes", "Lots.nes"): {"total_secs": 40 * 3600, "last_played": "2026-09-01T10:00:00"},
        ("nes", "Yesterday.nes"): {"total_secs": 1800, "last_played": "2026-10-09T20:00:00"},
    }
    order = [g["filename"] for g in standby_picks.rank(games, played, NOW)]
    assert order == ["Yesterday.nes", "Lots.nes", "Long ago.nes", "Never.nes"]


def test_playtime_is_merged_across_profiles(tmp_path, monkeypatch):
    from backend import db as dbmod
    monkeypatch.setattr(dbmod, "PLAYTIME_DB", tmp_path / "playtime.db")
    monkeypatch.setattr(dbmod, "_DB", None)

    async def scenario():
        await dbmod.init_db()
        db = await dbmod.get_db()
        await db.execute("INSERT INTO playtime VALUES ('Zelda.nes', 'nes', 100, 1, '2026-10-01T10:00:00')")
        await db.execute("INSERT INTO profile_playtime VALUES ('p2', 'Zelda.nes', 'nes', 50, 1, "
                         "'2026-10-05T10:00:00')")
        await db.commit()
        rows = await standby_picks.played_rows()
        await db.close()
        dbmod._DB = None
        return rows

    rows = asyncio.run(scenario())
    assert rows[("nes", "Zelda.nes")] == {"total_secs": 150, "last_played": "2026-10-05T10:00:00"}


def test_weighted_shuffle_favours_valuable_games_and_favourites():
    items = [{"system_id": "nes", "filename": f"{i}.nes", "value": 0} for i in range(5)]
    items[3]["value"] = 18
    rng = random.Random(4)
    firsts = [standby_picks.weighted_shuffle(items, rng)[0]["filename"] for _ in range(400)]
    assert firsts.count("3.nes") > 200
    fav = {("nes", "1.nes")}
    firsts = [standby_picks.weighted_shuffle(items[:3], rng, fav)[0]["filename"] for _ in range(400)]
    assert firsts.count("1.nes") > firsts.count("0.nes")


# ── The cap ─────────────────────────────────────────────────────────────────

def test_cap_defaults_to_five_gigabytes_and_reads_the_environment(monkeypatch):
    monkeypatch.delenv(standby_videos.CAP_ENV, raising=False)
    assert standby_videos.cap_bytes() == 5 * 1024 ** 3
    monkeypatch.setenv(standby_videos.CAP_ENV, "1.5")
    assert standby_videos.cap_bytes() == int(1.5 * 1024 ** 3)
    monkeypatch.setenv(standby_videos.CAP_ENV, "lots")
    assert standby_videos.cap_bytes() == 5 * 1024 ** 3
    monkeypatch.setenv(standby_videos.CAP_ENV, "0")
    assert standby_videos.cap_bytes() == 0


def test_eviction_keeps_the_most_valuable_clips_and_drops_orphans_first():
    a, b, c, orphan = (Path(f"/c/nes/{n}/video.mp4") for n in ("a", "b", "c", "gone"))
    clips = {a: 40, b: 40, c: 40, orphan: 10}
    rank = {a.parent: 0, b.parent: 1, c.parent: 2}
    assert standby_videos.plan_eviction(clips, rank, 130) == []
    assert standby_videos.plan_eviction(clips, rank, 120) == [orphan]
    # Greedy by value: a small clip further down still fills a gap.
    assert standby_videos.plan_eviction(clips, rank, 90) == [c]
    assert standby_videos.plan_eviction(clips, rank, 85) == [c, orphan]


# ── The sweep, against a fake cache ─────────────────────────────────────────

@pytest.fixture
def cache(tmp_path, monkeypatch):
    """A media cache with manifests, a library, and a fake downloader."""
    before = gm.CACHE_ROOT
    gm.set_cache_root(tmp_path / "gamemedia")
    games = [_game("snes", n) for n in ("Top.sfc", "Second.sfc", "Third.sfc")]
    played = {("snes", "Top.sfc"): {"total_secs": 9000, "last_played": "2026-10-09T10:00:00"},
              ("snes", "Second.sfc"): {"total_secs": 3000, "last_played": "2026-10-01T10:00:00"}}
    for g in games:
        d = gm.entry_dir(g["system_id"], g["target"])
        d.mkdir(parents=True)
        gm.write_json(d / gm.MANIFEST, {"found": True, "media": {
            "video-normalized": {"deferred": True, "url": f"https://x/{g['filename']}.mp4"},
            "screenshot-gameplay": {"deferred": True, "url": "https://x/s.png"}}})

    calls: list[str] = []
    sizes = {"Top.sfc": 600, "Second.sfc": 500, "Third.sfc": 300}

    async def media_file(system_id, target, slug):
        name = Path(target).name
        calls.append(name)
        d = gm.entry_dir(system_id, target)
        path = d / f"{slug}.mp4"
        path.write_bytes(b"\0" * sizes[name])
        manifest = json.loads((d / gm.MANIFEST).read_text())
        manifest["media"][slug] = {"file": path.name, "bytes": sizes[name], "url": "https://x"}
        gm.write_json(d / gm.MANIFEST, manifest)
        return path

    async def played_rows():
        return played

    monkeypatch.setattr(standby_picks, "library", lambda: games)
    monkeypatch.setattr(standby_picks, "played_rows", played_rows)
    monkeypatch.setattr(gamemedia, "available", lambda: True)
    monkeypatch.setattr(gamemedia, "media_file", media_file)
    yield {"calls": calls, "games": games}
    gm.set_cache_root(before)


def _cap(monkeypatch, nbytes: int) -> None:
    monkeypatch.setenv(standby_videos.CAP_ENV, repr(nbytes / 1024 ** 3))


def test_sweep_downloads_in_value_order_and_stops_at_the_cap(cache, monkeypatch):
    _cap(monkeypatch, 1100)
    summary = asyncio.run(standby_videos.sweep())
    assert cache["calls"] == ["Top.sfc", "Second.sfc"]
    assert summary["used"] == 1100 and summary["evicted"] == 0


def test_lower_cap_evicts_the_least_valuable_and_files_it_deferred(cache, monkeypatch):
    _cap(monkeypatch, 1100)
    asyncio.run(standby_videos.sweep())
    _cap(monkeypatch, 950)
    summary = asyncio.run(standby_videos.sweep())
    assert summary["used"] == 900 and summary["evicted"] == 1
    assert cache["calls"] == ["Top.sfc", "Second.sfc", "Third.sfc"], \
        "the evicted clip is not fetched again; the smaller one after it fills the gap"
    second = cache["games"][1]
    d = gm.entry_dir(second["system_id"], second["target"])
    assert not (d / "video-normalized.mp4").exists()
    entry = json.loads((d / gm.MANIFEST).read_text())["media"]["video-normalized"]
    # Deferred with its URL: no rescrape, one download if it is wanted again.
    assert entry["deferred"] is True and entry["url"] and "file" not in entry
    assert entry["bytes"] == 500, "the size stays as a hint for the next sweep"
    asyncio.run(standby_videos.sweep())
    assert cache["calls"].count("Second.sfc") == 1, "a clip known not to fit is not refetched"


def test_a_clip_that_does_not_fit_is_dropped_and_the_sweep_stops(cache, monkeypatch):
    _cap(monkeypatch, 500)
    summary = asyncio.run(standby_videos.sweep())
    assert cache["calls"] == ["Top.sfc"], "a 600-byte clip cannot fit a 500-byte cap"
    assert summary["used"] == 0


def test_nothing_is_fetched_while_a_game_is_running(cache, monkeypatch):
    _cap(monkeypatch, 5000)
    playing = {"yes": True}

    class FakePM:
        @property
        def is_foreground(self):
            return playing["yes"]

    monkeypatch.setattr(prefetch, "process_manager", FakePM())
    monkeypatch.setattr(prefetch, "_IDLE_POLL", 0.01)

    async def scenario():
        task = asyncio.create_task(standby_videos.sweep())
        await asyncio.sleep(0.1)
        during = list(cache["calls"])
        playing["yes"] = False
        await asyncio.wait_for(task, 2)
        return during

    assert asyncio.run(scenario()) == []
    assert cache["calls"] == ["Top.sfc", "Second.sfc", "Third.sfc"]


# ── The endpoint ────────────────────────────────────────────────────────────

def test_playlist_endpoint_lists_clips_on_disk_and_stills_for_the_rest(cache, monkeypatch):
    _cap(monkeypatch, 1100)
    asyncio.run(standby_videos.sweep())
    third = cache["games"][2]
    d = gm.entry_dir(third["system_id"], third["target"])
    (d / "screenshot-gameplay.png").write_bytes(b"png")
    manifest = json.loads((d / gm.MANIFEST).read_text())
    manifest["media"]["screenshot-gameplay"] = {"file": "screenshot-gameplay.png", "url": "https://x"}
    gm.write_json(d / gm.MANIFEST, manifest)

    app = FastAPI()
    app.include_router(standby_router.router, prefix="/api")
    body = TestClient(app).get("/api/standby/videos", params={"favourite": "snes:Second.sfc"}).json()

    assert sorted(v["filename"] for v in body["videos"]) == ["Second.sfc", "Top.sfc"]
    assert [s["filename"] for s in body["stills"]] == ["Third.sfc"]
    top = next(v for v in body["videos"] if v["filename"] == "Top.sfc")
    assert set(top) == {"system_id", "filename", "display_name", "system_name",
                        "last_played", "media_type", "url"}
    assert top["url"] == "/api/media/snes/Top.sfc/media/video-normalized"
    assert top["last_played"] == "2026-10-09T10:00:00"
    assert body["stills"][0]["url"].endswith("/media/screenshot-gameplay")
