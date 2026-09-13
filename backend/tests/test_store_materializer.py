"""The Store materializer; every HTTP byte comes from MockTransport."""
from __future__ import annotations

import asyncio
from pathlib import Path

import aiosqlite
import httpx

from backend import db as dbmod
from backend.services import paths
from backend.services.store import jobs
from backend.services.store.materializer import (
    HttpMaterializer, MIN_FREE_AFTER_DOWNLOAD, MaterializationError, job_dir)

REPO = Path(__file__).resolve().parents[2]


async def _database(monkeypatch) -> aiosqlite.Connection:
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    monkeypatch.setattr(dbmod, "_DB", conn)
    await dbmod.init_db()
    return conn


def test_existing_job_tables_gain_queryable_progress_columns(monkeypatch):
    async def scenario():
        conn = await aiosqlite.connect(":memory:")
        conn.row_factory = aiosqlite.Row
        await conn.execute("""
            CREATE TABLE store_jobs (
                id TEXT PRIMARY KEY, system_id TEXT NOT NULL,
                roms_dir TEXT NOT NULL DEFAULT '', title TEXT NOT NULL,
                filename TEXT NOT NULL, format TEXT NOT NULL DEFAULT '',
                size INTEGER NOT NULL DEFAULT 0, provider TEXT NOT NULL,
                source TEXT NOT NULL, state TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT '', queued_at TEXT NOT NULL,
                started_at TEXT, ended_at TEXT)
        """)
        await conn.commit()
        monkeypatch.setattr(dbmod, "_DB", conn)
        try:
            await dbmod.init_db()
            columns = {row["name"] for row in
                       await conn.execute_fetchall("PRAGMA table_info(store_jobs)")}
            assert {"downloaded_bytes", "download_total"} <= columns
        finally:
            await conn.close()
    asyncio.run(scenario())


async def _job() -> jobs.Job:
    return await jobs.enqueue(
        system_id="nes", roms_dir="emu/nes", title="Zelda",
        filename="Zelda.nes", format="nes", size=6,
        provider="fake", source="fake://zelda")


def _job_value() -> jobs.Job:
    return jobs.Job(
        id="a" * 32, system_id="nes", roms_dir="emu/nes", title="Zelda",
        filename="Zelda.nes", format="nes", size=6, provider="fake",
        source="fake://zelda", state=jobs.RUNNING, reason="",
        queued_at="2026-09-13T00:00:00+00:00", started_at="", ended_at="")


class Provider:
    name = "fake"

    async def acquire(self, job: jobs.Job) -> jobs.AcquiredTarget:
        return jobs.AcquiredTarget(
            url="https://download.invalid/Zelda.nes", filename="Zelda.nes",
            size=6, info_hash="", provider=self.name)


async def _ignore_progress(_job_id, _received, _total):
    pass


def _materializer(transport, *, free=10**12, progress=jobs._progress):
    return HttpMaterializer(progress=progress, transport=transport,
                            free_bytes=lambda _path: free)


def test_the_http_transfer_is_atomic_complete_and_reports_progress(tmp_path, monkeypatch):
    async def scenario():
        monkeypatch.setattr(paths, "GAMECORE_DATA", tmp_path)
        seen = []

        async def progress(job_id, received, total):
            seen.append((job_id, received, total))

        job = _job_value()
        target = await Provider().acquire(job)
        transport = httpx.MockTransport(lambda request: httpx.Response(
            200, content=b"abcdef", headers={"content-length": "6"}, request=request))
        await _materializer(transport, progress=progress).materialize(job, target)

        assert (job_dir(job.id) / "Zelda.nes").read_bytes() == b"abcdef"
        assert not list(tmp_path.rglob("*.part"))
        assert seen[0] == (job.id, 0, 6)
        assert seen[-1] == (job.id, 6, 6)
        assert not (tmp_path / "emu").exists()
    asyncio.run(scenario())


def test_complete_bytes_live_only_in_the_jobs_work_area_and_progress_is_queryable(
        tmp_path, monkeypatch):
    async def scenario():
        conn = await _database(monkeypatch)
        monkeypatch.setattr(paths, "GAMECORE_DATA", tmp_path)
        monkeypatch.setattr(jobs, "kick", lambda: None)
        monkeypatch.setattr(jobs, "acquisition_provider", lambda: Provider())
        transport = httpx.MockTransport(lambda request: httpx.Response(
            200, content=b"abcdef", headers={"content-length": "6"}, request=request))
        monkeypatch.setattr(jobs, "materializer", lambda: _materializer(transport))
        try:
            job = await _job()
            await asyncio.wait_for(jobs.drain(), 2)
            after = await jobs.get(job.id)
            assert after.state == jobs.FAILED
            assert after.reason == jobs.NOT_IMPORTED
            assert after.downloaded_bytes == 6
            assert after.download_total == 6
            assert (job_dir(job.id) / "Zelda.nes").read_bytes() == b"abcdef"
            assert not list(tmp_path.rglob("*.part"))
            assert not (tmp_path / "emu").exists()
        finally:
            await conn.close()
    asyncio.run(scenario())


def test_disk_space_is_checked_before_the_request_or_job_directory(tmp_path, monkeypatch):
    async def scenario():
        monkeypatch.setattr(paths, "GAMECORE_DATA", tmp_path)
        job = _job_value()
        requested = False

        def answer(request):
            nonlocal requested
            requested = True
            return httpx.Response(200, content=b"abcdef", request=request)

        target = await Provider().acquire(job)
        store = _materializer(httpx.MockTransport(answer),
                              free=target.size + MIN_FREE_AFTER_DOWNLOAD - 1)
        try:
            await store.materialize(job, target)
        except MaterializationError as error:
            assert "not enough disk space" in str(error)
        else:
            raise AssertionError("the download should have been refused")
        assert not requested
        assert not job_dir(job.id).exists()
    asyncio.run(scenario())


class SlowStream(httpx.AsyncByteStream):
    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def __aiter__(self):
        yield b"abc"
        self.started.set()
        await self.release.wait()
        yield b"def"

    async def aclose(self):
        pass


def test_cancelling_the_materializer_interrupts_stream_and_removes_partial(
        tmp_path, monkeypatch):
    async def scenario():
        monkeypatch.setattr(paths, "GAMECORE_DATA", tmp_path)
        job = _job_value()
        stream = SlowStream()
        transport = httpx.MockTransport(lambda request: httpx.Response(
            200, stream=stream, headers={"content-length": "6"}, request=request))
        transfer = asyncio.create_task(
            _materializer(transport, progress=_ignore_progress).materialize(
                job, await Provider().acquire(job)))
        await asyncio.wait_for(stream.started.wait(), 2)
        transfer.cancel()
        try:
            await transfer
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("the transfer ignored cancellation")
        assert not stream.release.is_set(), "the blocked response was allowed to finish"
        assert not job_dir(job.id).exists()
    asyncio.run(scenario())


def test_cancel_stops_the_transfer_and_removes_its_partial(tmp_path, monkeypatch):
    async def scenario():
        conn = await _database(monkeypatch)
        monkeypatch.setattr(paths, "GAMECORE_DATA", tmp_path)
        monkeypatch.setattr(jobs, "kick", lambda: None)
        monkeypatch.setattr(jobs, "acquisition_provider", lambda: Provider())
        stream = SlowStream()
        transport = httpx.MockTransport(lambda request: httpx.Response(
            200, stream=stream, headers={"content-length": "6"}, request=request))
        monkeypatch.setattr(jobs, "materializer", lambda: _materializer(transport))
        job = await _job()
        worker = asyncio.create_task(jobs.drain())
        jobs._worker = worker
        try:
            await asyncio.wait_for(stream.started.wait(), 2)
            await jobs.cancel(job.id)
            await asyncio.wait_for(worker, 2)
            assert (await jobs.get(job.id)).state == jobs.CANCELLED
            assert not job_dir(job.id).exists()
        finally:
            stream.release.set()
            await conn.close()
    asyncio.run(scenario())


def test_shutdown_stops_the_transfer_cleans_it_and_settles_the_row(tmp_path, monkeypatch):
    async def scenario():
        conn = await _database(monkeypatch)
        monkeypatch.setattr(paths, "GAMECORE_DATA", tmp_path)
        monkeypatch.setattr(jobs, "kick", lambda: None)
        monkeypatch.setattr(jobs, "acquisition_provider", lambda: Provider())
        stream = SlowStream()
        transport = httpx.MockTransport(lambda request: httpx.Response(
            200, stream=stream, headers={"content-length": "6"}, request=request))
        monkeypatch.setattr(jobs, "materializer", lambda: _materializer(transport))
        job = await _job()
        worker = asyncio.create_task(jobs.drain())
        jobs._worker = worker
        try:
            await asyncio.wait_for(stream.started.wait(), 2)
            await jobs.stop()
            after = await jobs.get(job.id)
            assert after.state == jobs.FAILED
            assert after.reason == jobs.INTERRUPTED
            assert not job_dir(job.id).exists()
        finally:
            stream.release.set()
            await conn.close()
    asyncio.run(scenario())


def test_restart_discards_an_unverifiable_partial(tmp_path, monkeypatch):
    async def scenario():
        conn = await _database(monkeypatch)
        monkeypatch.setattr(paths, "GAMECORE_DATA", tmp_path)
        monkeypatch.setattr(jobs, "kick", lambda: None)
        job = await _job()
        await conn.execute("UPDATE store_jobs SET state = ? WHERE id = ?",
                           (jobs.RUNNING, job.id))
        await conn.commit()
        owned = job_dir(job.id)
        owned.mkdir(parents=True)
        (owned / "Zelda.nes.part").write_bytes(b"abc")
        try:
            assert await jobs.resume_after_restart() == 1
            after = await jobs.get(job.id)
            assert after.state == jobs.FAILED
            assert after.reason == jobs.INTERRUPTED
            assert not owned.exists()
        finally:
            await conn.close()
    asyncio.run(scenario())


def test_an_html_error_page_never_becomes_the_completed_file(tmp_path, monkeypatch):
    async def scenario():
        monkeypatch.setattr(paths, "GAMECORE_DATA", tmp_path)
        job = _job_value()
        target = await Provider().acquire(job)
        body = b"<html"
        target = jobs.AcquiredTarget(target.url, target.filename, len(body), "", "fake")
        transport = httpx.MockTransport(lambda request: httpx.Response(
            200, content=body, headers={"content-length": str(len(body))}, request=request))
        try:
            await _materializer(transport, progress=_ignore_progress).materialize(job, target)
        except MaterializationError as error:
            assert "HTML" in str(error)
        else:
            raise AssertionError("HTML should have been refused")
        assert not job_dir(job.id).exists()
    asyncio.run(scenario())


def test_uninstall_names_only_the_store_work_root_for_cleanup():
    """Large staging files must not survive removal beside the kept library."""
    script = (REPO / "install/uninstall.sh").read_text(encoding="utf-8")
    assert 'safe_rm "$GC_DATA/store/jobs"' in script
    assert 'safe_rm "$GC_DATA/emu"' not in script
