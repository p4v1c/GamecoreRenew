"""The Store's acquisition queue — the states, the worker, and the restart.

Nothing here reaches the network and nothing here writes a game anywhere. Both
are asserted rather than assumed: there is no acquisition provider on this box
and none ships, so the honest end of every real job is a failure — and the last
test in this file stands guard over the whole data root, not just over the ROM
directory, because a queue that started writing would do it somewhere nobody
was looking.

What is pinned:

  · **the state machine is a table, and it is obeyed.** Every pair of states is
    walked; the legal moves happen and the illegal ones raise. A terminal job
    is terminal — nothing restarts a finished download by accident;
  · **cancelling is a state.** The row survives, saying it was cancelled, so a
    player can tell "I changed my mind" from "I never asked". Including the
    race: a cancel that lands while the provider is on its last line wins, and
    the worker's `done` is discarded rather than overwriting it;
  · **a reboot does not leave a ghost.** A job that was `running` when the
    process died comes back `failed`, with the interruption as its reason, and
    never `running` and never silently re-run. Queued jobs survive and are
    picked up, which is the whole reason the queue is in a database;
  · **the worker fails honestly.** With no provider it fails saying so. The
    success path is exercised by a provider this file injects — the same rule
    the Prowlarr client is tested by, where the seam is real and the thing
    behind it is not shipped.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import aiosqlite
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend import db as dbmod                                # noqa: E402
from backend.main import app                                   # noqa: E402
from backend.services import paths                             # noqa: E402
from backend.services.store import jobs                        # noqa: E402

# The same four consoles as test_store_search.py, and for the same reason: they
# are four different answers to "what does a download have to become".
INSTALLED = ["nes", "mame", "duckstation", "rpcs3"]


# ── the machinery under the tests ──────────────────────────────────────────


@pytest.fixture(autouse=True)
def _a_worker_that_does_not_outlive_its_test():
    """No task from one test may still be draining during the next.

    The worker is a module global by design — one job at a time, box-wide —
    which means it is also module state the suite has to put back. A leaked
    drain task would pick up the next test's rows in the previous test's event
    loop, and the failure would land somewhere else entirely.
    """
    yield
    jobs._worker = None
    jobs._job_task = None
    jobs._job_id = None


def _memory_db(monkeypatch):
    """A database with the real schema and no file behind it.

    `db.get_db()` hands back `_DB` whenever it still answers `SELECT 1`, so
    putting a connection there is the whole seam — the same one
    test_session_ownership.py uses. Nothing in this file may open the box's
    own `config/playtime.db`.
    """
    async def open_it():
        conn = await aiosqlite.connect(":memory:")
        conn.row_factory = aiosqlite.Row
        monkeypatch.setattr(dbmod, "_DB", conn)
        await dbmod.init_db()
        return conn
    return open_it


def _no_worker(monkeypatch):
    """Keep `enqueue` from starting the drain.

    The state-machine tests move jobs by hand and a worker racing them would
    answer a different question. The tests that want the worker call `drain()`
    themselves, which is the same coroutine `kick()` runs.
    """
    monkeypatch.setattr(jobs, "kick", lambda: None)


async def _queue(**over):
    row = dict(system_id="nes", roms_dir="emu/nes", title="Zelda",
               filename="Zelda (USA).nes", format="nes", size=512 * 1024,
               provider="demo", source="demo://nes/zelda")
    row.update(over)
    return await jobs.enqueue(**row)


class FakeAcquisition:
    """A provider that exists only inside a test.

    The success path has to be exercised somehow, and the one thing that must
    not happen is a plausible provider shipping in `backend/` to do it — a box
    would then have an acquisition provider, which is precisely the thing this
    step does not have. So it lives here, like the `httpx.MockTransport` the
    Prowlarr client is tested through.
    """

    name = "fake"

    def __init__(self, *, raises: BaseException | None = None,
                 blocks: bool = False):
        self.raises = raises
        self.blocks = blocks
        self.seen: list[jobs.Job] = []

    async def acquire(self, job: jobs.Job) -> None:
        self.seen.append(job)
        if self.raises is not None:
            raise self.raises
        # Mutable, so a test can hold one job at the provider and let the next
        # one through — which is how "cancelling one job does not stop the
        # queue" is asserted without the second job blocking for ever too.
        while self.blocks:
            await asyncio.sleep(0.01)


# ── the state machine ──────────────────────────────────────────────────────


def test_the_table_of_legal_moves_is_the_one_the_states_describe():
    """The five states and the moves between them, asserted as a shape.

    Written against the table rather than against the functions because the
    table is what the module docstring draws and what a reader will trust. A
    move added to one and not the other is exactly the drift this catches.
    """
    assert set(jobs.STATES) == {"queued", "running", "done", "failed", "cancelled"}
    assert set(jobs.LIVE) == {"queued", "running"}
    assert set(jobs.TERMINAL) == {"done", "failed", "cancelled"}
    assert set(jobs.LIVE) | set(jobs.TERMINAL) == set(jobs.STATES)

    assert jobs._LEGAL["queued"] == {"running", "cancelled"}
    assert jobs._LEGAL["running"] == {"done", "failed", "cancelled"}
    # Terminal means terminal. Not "nothing happens to be written yet" — a job
    # that finished is a record, and re-running it is a new row.
    for state in jobs.TERMINAL:
        assert jobs._LEGAL[state] == frozenset()


def test_every_illegal_move_raises_rather_than_quietly_doing_nothing(monkeypatch):
    """A no-op would hide the caller's bug; the raise is the point.

    Walked over every ordered pair so that a state added later is covered by
    this test the day it is added rather than the day it goes wrong.
    """
    async def scenario():
        conn = await _memory_db(monkeypatch)()
        _no_worker(monkeypatch)
        try:
            for frm in jobs.STATES:
                for to in jobs.STATES:
                    job = await _queue(source=f"demo://nes/{frm}-{to}")
                    await conn.execute("UPDATE store_jobs SET state = ? WHERE id = ?",
                                       (frm, job.id))
                    await conn.commit()
                    if to in jobs._LEGAL[frm]:
                        moved = await jobs._move(job.id, to, expect=frm)
                        assert moved is not None and moved.state == to
                    else:
                        with pytest.raises(jobs.IllegalTransition):
                            await jobs._move(job.id, to, expect=frm)
                        assert (await jobs.get(job.id)).state == frm
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_a_move_that_lost_the_race_changes_nothing_and_says_so(monkeypatch):
    """Compare-and-set, which is the whole of the concurrency design.

    Two things move a job — the worker and a player's cancel — and they can
    arrive in either order. The write states which state it is moving out of,
    so exactly one of them wins and the loser is told by getting `None` back
    rather than by silently overwriting the winner.
    """
    async def scenario():
        conn = await _memory_db(monkeypatch)()
        _no_worker(monkeypatch)
        try:
            job = await _queue()
            assert (await jobs._move(job.id, "cancelled", expect="queued")) is not None
            # The second caller still believes it is queued. It is not, and it
            # must not be able to say so.
            assert (await jobs._move(job.id, "running", expect="queued")) is None
            assert (await jobs.get(job.id)).state == "cancelled"
        finally:
            await conn.close()

    asyncio.run(scenario())


# ── cancelling ─────────────────────────────────────────────────────────────


def test_cancelling_a_queued_job_keeps_the_row(monkeypatch):
    """The row is the answer to "did I ask for that and change my mind?".

    A cancel that deleted it would leave a player looking at an empty list with
    no way to tell that from never having asked.
    """
    async def scenario():
        conn = await _memory_db(monkeypatch)()
        _no_worker(monkeypatch)
        try:
            job = await _queue()
            cancelled = await jobs.cancel(job.id)
            assert cancelled.state == "cancelled"
            assert cancelled.reason
            assert cancelled.ended_at

            rows = await conn.execute_fetchall("SELECT id, state FROM store_jobs")
            assert [(r["id"], r["state"]) for r in rows] == [(job.id, "cancelled")]
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_a_finished_job_cannot_be_cancelled(monkeypatch):
    """Including one that already failed. Terminal is terminal."""
    async def scenario():
        conn = await _memory_db(monkeypatch)()
        _no_worker(monkeypatch)
        try:
            for state in jobs.TERMINAL:
                job = await _queue(source=f"demo://nes/{state}")
                await conn.execute("UPDATE store_jobs SET state = ? WHERE id = ?",
                                   (state, job.id))
                await conn.commit()
                with pytest.raises(jobs.IllegalTransition):
                    await jobs.cancel(job.id)
                assert (await jobs.get(job.id)).state == state
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_cancelling_something_that_was_never_queued_is_not_a_cancellation(monkeypatch):
    async def scenario():
        conn = await _memory_db(monkeypatch)()
        _no_worker(monkeypatch)
        try:
            with pytest.raises(jobs.UnknownJob):
                await jobs.cancel("0" * 32)
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_a_cancel_that_lands_first_is_not_overwritten_by_the_finish(monkeypatch):
    """The race the worker creates, and the reason `_settle` states `expect`.

    A player cancels while the provider is on its last line. Both writes are on
    their way. Without the compare-and-set the worker's `done` would land
    second and the box would report a completed download the player had just
    stopped — and it would report it for ever, because the row persists.
    """
    async def scenario():
        conn = await _memory_db(monkeypatch)()
        _no_worker(monkeypatch)
        try:
            job = await _queue()
            running = await jobs._move(job.id, "running", expect="queued",
                                       stamp="started_at")
            assert running.state == "running"
            await jobs.cancel(job.id)
            # The worker comes back from a download that did finish.
            await jobs._settle(running, None)
            assert (await jobs.get(job.id)).state == "cancelled"
        finally:
            await conn.close()

    asyncio.run(scenario())


# ── the worker ─────────────────────────────────────────────────────────────


def test_with_no_acquisition_provider_a_job_fails_and_says_why(monkeypatch):
    """The honest end of every real job on every real box today.

    This is the behaviour the whole step is built around: there is no
    acquisition provider, so a job that reaches the worker fails with a true
    reason. A `done` here — a queue that reported success having downloaded
    nothing — would be a lie the player reads again after a reboot.
    """
    async def scenario():
        conn = await _memory_db(monkeypatch)()
        _no_worker(monkeypatch)
        try:
            # Not stubbed: this is what the shipped function answers.
            assert jobs.acquisition_provider() is None
            job = await _queue()
            await jobs.drain()
            after = await jobs.get(job.id)
            assert after.state == "failed"
            assert after.reason == jobs.NO_PROVIDER
            assert after.started_at and after.ended_at
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_the_worker_runs_the_queue_in_the_order_it_was_filled(monkeypatch):
    """Oldest first, and one at a time.

    One at a time because a box on a domestic line gains nothing from four
    concurrent downloads and loses the ability to say which one is happening.
    """
    async def scenario():
        conn = await _memory_db(monkeypatch)()
        _no_worker(monkeypatch)
        fake = FakeAcquisition()
        monkeypatch.setattr(jobs, "acquisition_provider", lambda: fake)
        try:
            first = await _queue(source="demo://nes/a", title="A")
            second = await _queue(source="demo://nes/b", title="B")
            await jobs.drain()
            assert [j.title for j in fake.seen] == ["A", "B"]
            assert (await jobs.get(first.id)).state == "done"
            assert (await jobs.get(second.id)).state == "done"
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_a_provider_that_raises_puts_its_reason_on_the_row(monkeypatch):
    """What the player is shown when something goes wrong is the provider's
    own sentence — which is why its contract says it must be safe to show."""
    async def scenario():
        conn = await _memory_db(monkeypatch)()
        _no_worker(monkeypatch)
        monkeypatch.setattr(jobs, "acquisition_provider",
                            lambda: FakeAcquisition(raises=RuntimeError("the disk is full")))
        try:
            job = await _queue()
            await jobs.drain()
            after = await jobs.get(job.id)
            assert after.state == "failed"
            assert after.reason == "the disk is full"
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_a_job_cancelled_mid_download_stops_and_stays_cancelled(monkeypatch):
    """Cancelling one job stops that job and not the queue.

    Two things are being asserted at once and they are the two halves of the
    same design: the acquisition runs as a task of its own so it can be
    interrupted alone, and the worker reads a cancelled task as the player's
    decision rather than as an error — so the row keeps saying `cancelled` and
    the next job still runs.
    """
    async def scenario():
        conn = await _memory_db(monkeypatch)()
        _no_worker(monkeypatch)
        fake = FakeAcquisition(blocks=True)
        monkeypatch.setattr(jobs, "acquisition_provider", lambda: fake)
        try:
            slow = await _queue(source="demo://nes/slow", title="Slow")
            after = await _queue(source="demo://nes/next", title="Next")

            worker = asyncio.create_task(jobs.drain())
            jobs._worker = worker
            for _ in range(200):
                await asyncio.sleep(0.01)
                if (await jobs.get(slow.id)).state == "running":
                    break
            assert (await jobs.get(slow.id)).state == "running"

            await jobs.cancel(slow.id)
            fake.blocks = False          # the next job is free to finish
            await asyncio.wait_for(worker, timeout=5)

            assert (await jobs.get(slow.id)).state == "cancelled"
            # The queue did not die with the cancelled job: the one behind it
            # ran. Cancelling the acquisition must not cancel the worker.
            assert (await jobs.get(after.id)).state == "done"
            assert [j.title for j in fake.seen] == ["Slow", "Next"]
        finally:
            await conn.close()

    asyncio.run(scenario())


# ── coming back up ─────────────────────────────────────────────────────────


def test_a_job_interrupted_by_a_restart_does_not_claim_to_be_running(monkeypatch):
    """The first of the two hard cases, and the one a screen cannot recover
    from on its own.

    A row left saying `running` describes a task that died with the process.
    Nothing will ever move it: the only thing that moves a running job is the
    worker that is no longer there. So the screen would show a download that
    nothing is downloading, for ever.

    It becomes `failed` and not `queued` on purpose. Re-queueing reads better
    and is worse — it restarts an acquisition the player did not ask to
    restart, from a position nothing recorded, and it erases the only evidence
    that the box stopped mid-download.
    """
    async def scenario():
        conn = await _memory_db(monkeypatch)()
        _no_worker(monkeypatch)
        try:
            stranded = await _queue(source="demo://nes/stranded")
            waiting = await _queue(source="demo://nes/waiting")
            finished = await _queue(source="demo://nes/finished")
            await conn.execute("UPDATE store_jobs SET state = 'running' WHERE id = ?",
                               (stranded.id,))
            await conn.execute("UPDATE store_jobs SET state = 'done' WHERE id = ?",
                               (finished.id,))
            await conn.commit()

            assert await jobs.resume_after_restart() == 1

            after = await jobs.get(stranded.id)
            assert after.state == "failed"
            assert after.reason == jobs.INTERRUPTED
            assert after.ended_at
            # A queued job is untouched — that is what makes the queue survive
            # a reboot rather than merely not lie about it.
            assert (await jobs.get(waiting.id)).state == "queued"
            assert (await jobs.get(finished.id)).state == "done"

            # Idempotent: the second start has nothing left to find.
            assert await jobs.resume_after_restart() == 0
            assert (await jobs.get(stranded.id)).reason == jobs.INTERRUPTED
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_a_queued_job_survives_the_restart_and_is_picked_up(monkeypatch):
    """The persistence, end to end, across a fresh connection.

    The row is written by one "process", read by another, and run by the worker
    that second process starts — which is the sequence the whole table exists
    for. A file-backed database rather than `:memory:`, because the thing being
    tested is that the row outlives the connection that wrote it.
    """
    async def first_boot(path):
        monkeypatch.setattr(dbmod, "PLAYTIME_DB", path)
        monkeypatch.setattr(dbmod, "_DB", None)
        _no_worker(monkeypatch)
        await dbmod.init_db()
        job = await _queue(source="demo://nes/across-a-reboot")
        conn = await dbmod.get_db()
        await conn.close()
        monkeypatch.setattr(dbmod, "_DB", None)
        return job.id

    async def second_boot(path, job_id):
        monkeypatch.setattr(dbmod, "PLAYTIME_DB", path)
        monkeypatch.setattr(dbmod, "_DB", None)
        await dbmod.init_db()
        assert (await jobs.get(job_id)).state == "queued"
        await jobs.resume_after_restart()
        assert (await jobs.get(job_id)).state == "queued"
        await jobs.drain()
        after = await jobs.get(job_id)
        conn = await dbmod.get_db()
        await conn.close()
        monkeypatch.setattr(dbmod, "_DB", None)
        return after

    def run(tmp):
        path = tmp / "playtime.db"
        job_id = asyncio.run(first_boot(path))
        return asyncio.run(second_boot(path, job_id))

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        after = run(Path(tmp))
    # It ran, and it failed for the true reason — not because it was
    # interrupted, which it was not.
    assert after.state == "failed"
    assert after.reason == jobs.NO_PROVIDER


# ── what the queue refuses ─────────────────────────────────────────────────


def test_the_same_thing_is_not_queued_twice_while_the_first_is_live(monkeypatch):
    """✕ on a television is pressed twice more often than it is pressed once.

    Two rows for one game is two downloads of it. Refused while the first is
    live; allowed again once it is not, because asking again after a failure is
    the whole way a player retries.
    """
    async def scenario():
        conn = await _memory_db(monkeypatch)()
        _no_worker(monkeypatch)
        try:
            first = await _queue()
            with pytest.raises(jobs.QueueRefused):
                await _queue()
            # Another console asking for the same release is a different job.
            await _queue(system_id="mame", roms_dir="emu/mame")

            await jobs.cancel(first.id)
            again = await _queue()
            assert again.id != first.id
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_two_presses_in_the_same_tick_make_one_row(monkeypatch):
    """✕ is a button with a repeat rate, and requests overlap.

    The dedup is a condition ON the insert rather than a check before it: read
    first and both presses see an empty queue, and the box quietly downloads
    one game twice. Run as two coroutines on one loop, which is exactly how
    two requests arrive.
    """
    async def scenario():
        conn = await _memory_db(monkeypatch)()
        _no_worker(monkeypatch)
        try:
            done = await asyncio.gather(_queue(), _queue(), _queue(),
                                        return_exceptions=True)
            made = [j for j in done if isinstance(j, jobs.Job)]
            refused = [e for e in done if isinstance(e, jobs.QueueRefused)]
            assert len(made) == 1, "the same release was queued more than once"
            assert len(refused) == 2
            assert len(await jobs.list_jobs()) == 1
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_a_held_down_button_cannot_fill_the_database(monkeypatch):
    async def scenario():
        conn = await _memory_db(monkeypatch)()
        _no_worker(monkeypatch)
        try:
            for i in range(jobs.MAX_LIVE):
                await _queue(source=f"demo://nes/{i}")
            with pytest.raises(jobs.QueueRefused):
                await _queue(source="demo://nes/one-too-many")
        finally:
            await conn.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("bad", ["../../etc/passwd", "sub/dir/game.nes",
                                 "back\\slash.nes", ".", "..", "   "])
def test_a_filename_that_is_a_path_is_never_written_down(monkeypatch, bad):
    """Refused where the row is created, not where it is used.

    Nothing in this step writes a file, so this is not stopping a traversal
    today — it is stopping one being stored today and trusted later. The
    materializer joins this name onto a directory, and a row that has been
    sitting in the database since before that code existed is exactly the input
    nobody re-checks.
    """
    async def scenario():
        conn = await _memory_db(monkeypatch)()
        _no_worker(monkeypatch)
        try:
            with pytest.raises(jobs.InvalidJob):
                await _queue(filename=bad)
            assert await jobs.list_jobs() == []
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_a_job_is_never_the_search_result_it_came_from(monkeypatch):
    """Queueing the same game twice is two rows, not one overwritten.

    A `SearchResult.id` is stable across identical searches by design, so using
    it as the key would make a retry collide with the row that recorded the
    failure — and the failure would vanish at the moment somebody wanted to
    read it.
    """
    async def scenario():
        conn = await _memory_db(monkeypatch)()
        _no_worker(monkeypatch)
        try:
            first = await _queue()
            await jobs.cancel(first.id)
            second = await _queue()
            assert first.id != second.id
            assert len(await jobs.list_jobs()) == 2
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_the_provider_locator_never_reaches_the_browser(monkeypatch):
    """`source` is the provider's, and a queue row is already queued.

    The search answer sends it because a result is ephemeral and the caller may
    want to queue it back. A job has nothing left to do with it, and it is the
    one field on the row that belongs to the indexer rather than to the player.
    """
    async def scenario():
        conn = await _memory_db(monkeypatch)()
        _no_worker(monkeypatch)
        try:
            job = await _queue(source="prowlarr://7/secret-guid")
            assert job.source == "prowlarr://7/secret-guid"
            assert "source" not in job.to_json()
            assert "secret-guid" not in json.dumps(job.to_json())
        finally:
            await conn.close()

    asyncio.run(scenario())


# ── the API ────────────────────────────────────────────────────────────────


@pytest.fixture
def box(tmp_path, monkeypatch):
    """A box with four consoles on its grid, and its own database.

    Only the DATA root moves — the catalogue is shipped code, read from where
    the loader bound it at import. `db.PLAYTIME_DB` is moved with it by hand
    because `db.py` binds it at import too, and a test that forgot would write
    into the suite's shared throwaway root.
    """
    monkeypatch.setattr(paths, "GAMECORE_DATA", tmp_path)
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "config" / "systems.json").write_text(
        json.dumps([{"id": i} for i in INSTALLED]))
    monkeypatch.setattr(dbmod, "PLAYTIME_DB", tmp_path / "config" / "playtime.db")
    monkeypatch.setattr(dbmod, "_DB", None)
    return tmp_path


@pytest.fixture
def client(box):
    with TestClient(app) as c:
        yield c


def _post(client, **over):
    body = {"systemId": "nes", "title": "Zelda", "filename": "Zelda (USA).nes",
            "source": "demo://nes/zelda", "provider": "demo", "format": "nes",
            "size": 4096}
    body.update(over)
    return client.post("/api/store/jobs", json=body)


def _settled(client, job_id, tries=200):
    """Poll until the job stops moving. Each request lets the worker run."""
    for _ in range(tries):
        rows = {j["id"]: j for j in client.get("/api/store/jobs").json()["jobs"]}
        row = rows.get(job_id)
        assert row is not None, "the job disappeared from the queue"
        if row["state"] in jobs.TERMINAL:
            return row
    raise AssertionError(f"job {job_id} never settled")


def test_queueing_answers_the_row_and_the_worker_finishes_it_honestly(client):
    """The whole round trip, as the screen makes it.

    And the end of it is a failure, on purpose: no acquisition provider exists
    on this box. `downloadReady` stays false beside it, because it is the flag
    that promises bytes in a ROM directory and nothing here delivers any.
    """
    r = _post(client)
    assert r.status_code == 201
    job = r.json()
    assert job["state"] == "queued"
    assert job["systemId"] == "nes"
    # The box's own answer for where it would land, not the client's.
    assert job["romsDir"] == "emu/nes"
    assert "source" not in job

    listed = client.get("/api/store/jobs").json()
    assert listed["downloadReady"] is False

    settled = _settled(client, job["id"])
    assert settled["state"] == "failed"
    assert settled["reason"] == jobs.NO_PROVIDER


def test_a_console_that_is_not_on_this_box_is_refused(client):
    """Same 409 and the same reason as `/search`: the job would land in a
    directory nothing scans, for a tile that is not on the grid."""
    assert _post(client, systemId="saturn").status_code == 409
    assert _post(client, systemId="NOT AN ID").status_code == 400


def test_a_row_from_a_provider_this_box_no_longer_uses_is_refused(client):
    """A tab left open across a change of provider must not queue a stale row.

    409 and not 400: the request was well formed when it was made, and the box
    changed under it. "Search again" is the actionable half.
    """
    assert _post(client, provider="prowlarr").status_code == 409


def test_the_api_refuses_a_row_it_will_not_store(client):
    assert _post(client, filename="../etc/passwd").status_code == 400
    assert _post(client, title="   ").status_code == 400
    assert _post(client, source="").status_code == 400


def test_cancelling_over_the_api_is_a_state_and_not_a_deletion(client, monkeypatch):
    """✕ on a queue row, and the row that is still there afterwards."""
    # Held at the provider so there is something to cancel — without this the
    # worker fails the job before the second request arrives.
    monkeypatch.setattr(jobs, "acquisition_provider",
                        lambda: FakeAcquisition(blocks=True))
    job = _post(client).json()

    for _ in range(200):
        rows = {j["id"]: j for j in client.get("/api/store/jobs").json()["jobs"]}
        if rows[job["id"]]["state"] == "running":
            break
    assert rows[job["id"]]["state"] == "running"

    cancelled = client.post(f"/api/store/jobs/{job['id']}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["state"] == "cancelled"

    still_there = client.get("/api/store/jobs").json()["jobs"]
    assert [j["id"] for j in still_there] == [job["id"]]
    assert still_there[0]["state"] == "cancelled"

    # And it cannot be cancelled twice.
    assert client.post(f"/api/store/jobs/{job['id']}/cancel").status_code == 409


def test_cancelling_a_job_that_does_not_exist(client):
    assert client.post("/api/store/jobs/%s/cancel" % ("a" * 32)).status_code == 404
    assert client.post("/api/store/jobs/not-an-id/cancel").status_code == 400


def test_the_queue_survives_a_restart_of_the_application(box, monkeypatch):
    """Two `TestClient`s over one data root — the reboot, as the box makes it.

    The second lifespan is where `resume_after_restart` runs, and this is the
    test that would have failed against a queue held in a module variable: the
    row is written by one application instance and read by the next.
    """
    monkeypatch.setattr(jobs, "acquisition_provider",
                        lambda: FakeAcquisition(blocks=True))
    with TestClient(app) as first:
        job = _post(first).json()
        for _ in range(200):
            rows = {j["id"]: j for j in first.get("/api/store/jobs").json()["jobs"]}
            if rows[job["id"]]["state"] == "running":
                break
        assert rows[job["id"]]["state"] == "running"

    # Second boot. Whatever the first one was in the middle of is over.
    monkeypatch.setattr(dbmod, "_DB", None)
    with TestClient(app) as second:
        rows = {j["id"]: j for j in second.get("/api/store/jobs").json()["jobs"]}
        assert rows[job["id"]]["state"] == "failed"
        assert rows[job["id"]]["reason"] == jobs.INTERRUPTED


# ── the guard ──────────────────────────────────────────────────────────────


def test_queueing_and_running_write_nothing_into_the_data_tree(box, monkeypatch):
    """The guard over the directory the ingestion steps will write into.

    The upstream half of this is `test_store_search.py`'s
    `test_searching_writes_nothing_anywhere`; this is the same assertion one
    step later, and it is deliberately wider. Searching had no reason to touch
    the disk at all, so its guard could watch everything. Queueing has exactly
    one: the row in the database this box already keeps. So the tree is
    compared path for path with the database excepted — and `emu/` is asserted
    absent by name, because that is the directory whose failure mode is a
    half-written file the library scan turns into a tile (matrix §1.1).

    A provider is injected so that the success path is walked too: "nothing was
    written" must hold for a job that *worked*, not only for one that failed
    before it started.
    """
    fake = FakeAcquisition()
    monkeypatch.setattr(jobs, "acquisition_provider", lambda: fake)

    def tree():
        return sorted(p.relative_to(box).as_posix() for p in box.rglob("*")
                      if p.name != "playtime.db")

    with TestClient(app) as client:
        before = tree()
        first = _post(client).json()
        assert _settled(client, first["id"])["state"] == "done"

        second = _post(client, source="demo://nes/other",
                       filename="Metroid (USA).nes").json()
        client.post(f"/api/store/jobs/{second['id']}/cancel")

        third = _post(client, systemId="rpcs3", source="demo://rpcs3/folder",
                      filename="BLES00000", format="folder").json()
        _settled(client, third["id"])

        assert tree() == before

    assert fake.seen, "the injected provider was never reached"
    assert not (box / "emu").exists()
    # Not even for the console the jobs named. `roms_dir` is recorded on the
    # row and read by nothing that writes.
    assert not (box / "emu" / "nes").exists()
    assert not (box / "emu" / "rpcs3").exists()
