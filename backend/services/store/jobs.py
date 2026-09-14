"""The acquisition queue — one job, its states, and the worker that runs them.

A player who asks for a game is making a request that outlives the screen they
made it on: the box may be busy, the download is minutes long, and the
television gets turned off. So "asked for" is a **row**, not a variable, and
this module is the whole of what that row means — the shape of it, the states
it may move between, who may move it, what happens to one the box was killed in
the middle of, and the worker that picks the next one up.

Everything about a job is here and nothing about a job is anywhere else. That
is not tidiness: at step 7 the same sequence existed in three copies on the
front end and they had already drifted on three points, one of them a
destructive removal that asked once in one copy and twice in the other. The
router below this file maps HTTP onto these functions and decides nothing; the
screen draws what `GET /store/jobs` answers and decides nothing.

── The five states, and why cancelling is one of them ─────────────────────
::

    queued ──► running ──► done
      │           ├──────► failed
      │           └──────► cancelled
      └──────────────────► cancelled

`cancelled` is a state and not a `DELETE`. A queue whose cancel removed the row
would be a queue that cannot tell "I never asked for that" from "I asked and
changed my mind", and a player looking at an empty list has no way to know
which happened. It is also the only spelling that survives the race the worker
creates: `cancel()` writes the durable state *before* it interrupts the task,
and `_settle()` writes the finish only `expect=RUNNING` — so a cancel that
arrives one tick before the download completes wins, and the completion is
discarded rather than overwriting the player's decision.

The three terminal states are terminal. Nothing moves out of `done`, `failed`
or `cancelled`, and asking for it raises rather than quietly doing nothing:
a caller that thinks it can restart a finished job is a caller with a bug, and
a no-op would hide it. Queueing the same thing again is a new row.

── Where a job is written down ────────────────────────────────────────────
`<DATA>/config/playtime.db`, in `store_jobs` — the database this box already
has, created by `db.py:init_db()` with the same `CREATE TABLE IF NOT EXISTS`
motif as `playtime` and `sessions`. See that module's docstring for why one
database and not two, and for what living under `config/` means the day
somebody uninstalls GameCore.

── The complete ingestion chain ──────────────────────────────────────────
Running a job is **resolve, then store**, and they are deliberately not one
thing:

  · `acquisition_provider()` turns the job's opaque `source` into an
    `AcquiredTarget` — a direct URL, and what it takes to check the bytes are
    the right ones. It moves nothing. `realdebrid.py` is one, and it answers
    `None` on a box with no `config/store-realdebrid.json`, which is every box
    until its owner puts one there;
  · `materializer()` fetches that target into the job-owned work area under
    `<DATA>/store/jobs/`. It never receives `roms_dir`, because inspection,
    transformation, validation and import are later steps;
  · `inspect_download()` classifies what arrived as one of matrix §5's six
    ingestion classes and persists the verdict on the row, changing nothing on
    disk;
  · `transformer()` gives the classified bytes the shape their class
    requires, beside the download in `store/jobs/<job-id>/ingest/`. It is the
    first step that produces modified content, and it still writes nowhere
    near a ROM directory;
  · `validate_shape()` judges that produced shape against its class — a
    signature, an archive directory, a descriptor's companions, an identity
    file — and persists a verdict. It changes nothing, on either the source or
    the shape;
  · `import_shape()` publishes that accepted shape in the pack's ROM directory
    without replacing an existing name, then removes staging.

Only that last seam can make the row `done`. `NO_PROVIDER` and
`NO_MATERIALIZER` remain distinct diagnostics for the earlier missing seams,
and every later refusal says what actually stopped it.

── What every stage except import must never do ───────────────────────────
Write into `<DATA>/emu/<system>/`. The importer is the single exception and
may write only below the one pack directory persisted as `roms_dir`.
`backend/tests/test_store_jobs.py` keeps both halves of that guard.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

import aiosqlite

from ... import ws
from ...db import get_db

log = logging.getLogger(__name__)

# ── the states ─────────────────────────────────────────────────────────────

QUEUED = "queued"
RUNNING = "running"
DONE = "done"
FAILED = "failed"
CANCELLED = "cancelled"

#: Every state, in the order a job walks them. Exported because the front end
#: and the tests both need the vocabulary and neither may spell its own.
STATES: tuple[str, ...] = (QUEUED, RUNNING, DONE, FAILED, CANCELLED)

#: A job that has not finished. The two that a cancel may act on, the two that
#: count against the queue depth, and the two a restart has to have an answer
#: for.
LIVE: tuple[str, ...] = (QUEUED, RUNNING)

#: A job nothing will move again.
TERMINAL: tuple[str, ...] = (DONE, FAILED, CANCELLED)

#: Which moves are legal, spelled out rather than implied by the code that
#: makes them. A table is checkable — `test_store_jobs.py` walks every pair —
#: where "whatever the four call sites happen to do" is not.
_LEGAL: dict[str, frozenset[str]] = {
    QUEUED:    frozenset({RUNNING, CANCELLED}),
    RUNNING:   frozenset({DONE, FAILED, CANCELLED}),
    DONE:      frozenset(),
    FAILED:    frozenset(),
    CANCELLED: frozenset(),
}

#: Why a job that reached the worker failed, while no acquisition provider
#: exists. One string, in one place, because it is the sentence the player
#: reads and the string the tests assert on.
NO_PROVIDER = "no acquisition provider is configured on this box"

#: Why a job whose source resolved *perfectly* still failed. Acquisition
#: answers with a target; fetching it is the materializer's (matrix §5), and
#: this box has none. Two reasons and not one, because "nothing is configured"
#: and "it resolved and this box cannot store it" are different facts about a
#: different half of the pipeline, and a player who reads the second has a
#: working Real-Debrid and nothing to fix.
NO_MATERIALIZER = "this box can find this download but cannot store it yet"

#: Why a job that was `running` when the process died is `failed` afterwards.
INTERRUPTED = "the box stopped while this job was running"

#: How many unfinished jobs one box may hold. A gamepad is an input device
#: with a repeat rate: ✕ held down on a results row is a hundred rows in the
#: database and a hundred failures on screen. Refused with a reason rather
#: than silently dropped.
MAX_LIVE = 20

#: How many rows one listing answers with. The queue screen pages at seven.
MAX_LISTED = 100

# Field caps. Everything on a job row comes from a provider's answer, which
# came from somebody else's indexer, and it lands in a database that persists.
# None of these is a security boundary on its own — they are what stops one
# hostile row being unbounded.
_MAX_TEXT = 400
_MAX_SOURCE = 2000


class IllegalTransition(ValueError):
    """A move the state machine does not allow — including out of a terminal
    state. Raised rather than ignored: a caller that believed it could restart
    a finished job has a bug, and a silent no-op hides it."""


class UnknownJob(LookupError):
    """No row with that id. Distinct from a job that cannot move."""


class InvalidJob(ValueError):
    """The thing being queued is not something this box will write down.

    About the *row*, where `QueueRefused` is about the queue. The router maps
    this to a 400 and that one to a 409, which is the difference between "fix
    what you sent" and "the box is not taking this right now".
    """


class QueueRefused(ValueError):
    """A well-formed job the queue will not take: already in it, or full."""


@dataclass(frozen=True)
class Job:
    """One thing the player asked the box to bring in.

    The fields are a `SearchResult` plus what a queue needs on top of it: which
    state it is in, why it left the one before, and when. Frozen, because a job
    is only ever changed by writing the database and reading it back — an
    object that could be mutated in place would be a second copy of the state,
    and the one on disk is the one that survives the reboot.
    """

    id: str
    system_id: str
    #: `emu/<dir>` relative to `<DATA>` — where this would land, as the box
    #: told the player when they queued it. **Recorded, never written to by
    #: anything in this module.** See the module docstring.
    roms_dir: str
    title: str
    filename: str
    format: str
    size: int
    provider: str
    #: The search provider's own opaque, redacted locator
    #: (`prowlarr://<indexerId>/<guid>`). Kept because it is the only thing
    #: that can find this again, and never sent to the browser — see
    #: `to_json`.
    source: str
    state: str
    #: Why it is in that state, when the state has a reason: `NO_PROVIDER`,
    #: `INTERRUPTED`, whatever a provider raised. Empty otherwise.
    reason: str
    queued_at: str
    started_at: str
    ended_at: str
    downloaded_bytes: int = 0
    download_total: int = 0
    #: Matrix §5 ingestion verdict. Empty until downloaded bytes are inspected.
    ingestion_class: str = ""
    #: Transformation progress, on its own pair rather than sharing the
    #: download's: the two phases move different bytes for different reasons.
    transformed_bytes: int = 0
    transform_total: int = 0
    #: `verified`, `unverified` or `refused` — `validator.py`'s verdict on the
    #: produced shape. Empty until validation runs.
    validation: str = ""
    #: The launch blocker this console will hit for want of a BIOS file
    #: (§5.3 rule 4). Recorded because it is true and useful; read by nothing
    #: that decides whether the download may proceed.
    bios_warning: str = ""

    @property
    def live(self) -> bool:
        return self.state in LIVE

    def to_json(self) -> dict:
        """camelCase, like every other row this front end reads.

        `source` is deliberately absent. The screen has no use for it — it
        draws a title, a state and a reason — and it is the one field on the
        row that belongs to the provider rather than to the player. The search
        answer sends it because a result is ephemeral and the caller may want
        to queue it back; a queue row is already queued.
        """
        return {
            "id": self.id,
            "systemId": self.system_id,
            "romsDir": self.roms_dir,
            "title": self.title,
            "filename": self.filename,
            "format": self.format,
            "size": self.size,
            "provider": self.provider,
            "state": self.state,
            "reason": self.reason,
            "queuedAt": self.queued_at,
            "startedAt": self.started_at,
            "endedAt": self.ended_at,
            "downloadedBytes": self.downloaded_bytes,
            "downloadTotal": self.download_total,
            "ingestionClass": self.ingestion_class,
            "transformedBytes": self.transformed_bytes,
            "transformTotal": self.transform_total,
            "validation": self.validation,
            "biosWarning": self.bios_warning,
        }


@dataclass(frozen=True)
class AcquiredTarget:
    """What acquiring a job produces: one thing that can be fetched.

    **Acquisition resolves; it does not download.** The previous shape of this
    contract said "bring this job's bytes in" and returned nothing, and that
    was one step doing two jobs. Turning an indexer's opaque locator into a URL
    is a conversation with somebody else's service that can fail in its own
    ways — a key refused, a link nothing supports, a wait that ran out — and
    moving bytes onto a disk is a different activity with different failures:
    no space, a name that will not sit in a directory, an archive that is not
    what it claimed. Fused, every one of those is "the download failed" and the
    player is told nothing useful. Split, each says what actually happened.

    So a provider answers with this, and the **materializer** — matrix §5, the
    step after this one — is what fetches it and puts it somewhere. That is
    also what keeps this step honest about writing nothing: a resolver has
    nowhere to put bytes even by accident.

    The fields are what fetching and *checking* one needs, and no more:

      · `url` is a direct HTTPS URL, already unrestricted, ready for a plain
        `GET`. It is **not** shown to the player and not sent to the browser —
        it is credentialed by construction (it is minted against the box
        owner's debrid account) and it is short-lived;
      · `size` is the completeness check the materializer can apply. The
        `info_hash` identifies the torrent for acquisition, but is not a file
        checksum (it hashes torrent metadata and piece hashes), so content
        validation cannot compare the downloaded file to it. `0` and `""` are
        honest answers where the service does not say, not defaults to trust;
      · `filename` is what the source calls it. The materializer decides what
        it lands as — matrix §1.3 — and does not take a name from here
        unchecked.
    """

    url: str
    filename: str
    #: Bytes, as the acquisition service reports them. `0` when it does not
    #: say — never a guess, and never the size the indexer claimed.
    size: int
    #: 40 lowercase hex, when the target came from a torrent. `""` otherwise.
    info_hash: str
    #: Which provider minted it, for the log line and for a materializer that
    #: one day has to treat two of them differently.
    provider: str

    def redacted(self) -> str:
        """The target, for a log line — never the URL.

        Every acquisition URL is a credential: it is issued against the owner's
        account and anyone holding it can spend their bandwidth. It goes in no
        journal, no exception and no job reason, so this is the only spelling
        of an `AcquiredTarget` that is safe to print.
        """
        return (f"{self.provider}:{self.filename} "
                f"({self.size} bytes, {self.info_hash or 'no hash'})")


class AcquisitionProvider(Protocol):
    """How a job's source becomes something fetchable.

    `acquisition_provider()` answers `None` on a box that has not configured
    one, which is every box by default, and that is what makes an unconfigured
    queue fail honestly rather than succeed by pretending.

    One method, and it stays thin — but it no longer returns `None`. The
    previous version of this docstring said the next step would define what
    acquisition does with what it fetches; that step is this one, and the
    answer is that it does not fetch. See `AcquiredTarget`.
    """

    #: Short id, for the log line and the job's `reason` when it raises.
    name: str

    async def acquire(self, job: Job) -> AcquiredTarget:
        """Resolve this job's source into a fetchable target, or raise.

        Returning an `AcquiredTarget` is success and moves nothing. Raising is
        failure and the exception's text becomes the job's `reason`, so it must
        be safe to show a player — a provider's own message can carry a URL and
        a URL can carry a key. Being cancelled is neither:
        `asyncio.CancelledError` must propagate, and the worker treats it as
        the player's cancel rather than an error.
        """
        ...


class Materializer(Protocol):
    """What writes a resolved target into its job-owned work area.

    Named now for the same reason `AcquisitionProvider` was named before there
    was one: so the worker has a shape to be written against and one place to
    ask. The shipped implementation stops in a private work directory; it does
    not inspect, transform, validate or import the result.

    After this returns, inspection classifies the staging bytes. They are still
    not a playable game; `NO_MATERIALIZER` remains the diagnosis when this seam
    is explicitly disabled.
    """

    name: str

    async def materialize(self, job: Job, target: AcquiredTarget) -> None:
        """Fetch the target into the job-owned work area."""
        ...


def acquisition_provider() -> AcquisitionProvider | None:
    """The provider this box acquires with, or `None`.

    `None` on a box with no `config/store-realdebrid.json`, which is the
    normal state and not an error: the file is the switch, exactly as
    `config/store-prowlarr.json` is the switch for searching. Imported inside
    the function rather than at module scope so that `jobs.py` keeps having no
    opinion about which provider exists — and so a test that injects one
    replaces this whole function without loading a client it will not use.
    """
    from .realdebrid import RealDebridAcquisition

    if not RealDebridAcquisition.configured():
        return None
    return RealDebridAcquisition()


def materializer() -> Materializer | None:
    """The HTTP materializer, injected here with the queue's progress sink."""
    from .materializer import HttpMaterializer
    return HttpMaterializer(progress=_progress)


def inspect_download(job: Job):
    """Inspect materialized bytes; one seam keeps worker tests filesystem-free."""
    from .inspector import inspect
    return inspect(job.id, job.system_id)


def validate_shape(job: Job, shape):
    """Judge the produced shape; one seam keeps worker tests filesystem-free.

    The same shape as `inspect_download` and for the same reason: validation
    needs no account, no service and no progress sink — only a few bytes of a
    file that is already on the disk — so there is nothing to inject and
    nothing that can be unconfigured. A function, so a test can replace it.
    """
    from .validator import validate
    return validate(shape, job.system_id)


def transformer():
    """The shape producer, injected with the queue's own progress sink.

    A function and not a constant for the same reason `materializer()` is one:
    it is the seam a test replaces. Unlike that one it never answers `None` —
    transforming needs no account, no token and no service, only the bytes
    already on the disk, so there is no box on which it is *not* configured.
    """
    from .transformer import ShapeTransformer
    return ShapeTransformer(progress=_transform_progress)


def import_shape(job: Job, shape):
    """Publish a validated shape; a seam for filesystem-free worker tests."""
    from .importer import import_shape as publish
    return publish(job, shape)


# ── reading and writing a row ──────────────────────────────────────────────


def _now() -> str:
    """UTC, ISO-8601, seconds. Same shape as `playtime.last_played`."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


_COLUMNS = ("id, system_id, roms_dir, title, filename, format, size, provider, "
            "source, state, reason, queued_at, started_at, ended_at, "
            "downloaded_bytes, download_total, ingestion_class, "
            "transformed_bytes, transform_total, validation, bios_warning")


def _row(r: aiosqlite.Row) -> Job:
    return Job(
        id=r["id"], system_id=r["system_id"], roms_dir=r["roms_dir"],
        title=r["title"], filename=r["filename"], format=r["format"],
        size=int(r["size"] or 0), provider=r["provider"], source=r["source"],
        state=r["state"], reason=r["reason"] or "",
        queued_at=r["queued_at"], started_at=r["started_at"] or "",
        ended_at=r["ended_at"] or "",
        downloaded_bytes=int(r["downloaded_bytes"] or 0),
        download_total=int(r["download_total"] or 0),
        ingestion_class=r["ingestion_class"] or "",
        transformed_bytes=int(r["transformed_bytes"] or 0),
        transform_total=int(r["transform_total"] or 0),
        validation=r["validation"] or "",
        bios_warning=r["bios_warning"] or "",
    )


async def get(job_id: str) -> Job | None:
    db = await get_db()
    cur = await db.execute(f"SELECT {_COLUMNS} FROM store_jobs WHERE id = ?",
                           (job_id,))
    row = await cur.fetchone()
    await cur.close()
    return _row(row) if row else None


async def list_jobs(limit: int = MAX_LISTED) -> list[Job]:
    """Every job, newest first.

    Newest first because the queue is read from the top on a television and
    what just happened is what the player is looking for. The live ones are
    not floated above the finished ones: a list that reorders itself as a job
    finishes moves the row out from under a cursor that was pointing at it.
    """
    db = await get_db()
    cur = await db.execute(
        f"SELECT {_COLUMNS} FROM store_jobs ORDER BY queued_at DESC, rowid DESC"
        " LIMIT ?", (max(1, min(int(limit), MAX_LISTED)),))
    rows = await cur.fetchall()
    await cur.close()
    return [_row(r) for r in rows]


async def live_jobs() -> list[Job]:
    """The unfinished ones, oldest first — the order the worker drains them."""
    db = await get_db()
    cur = await db.execute(
        f"SELECT {_COLUMNS} FROM store_jobs WHERE state IN (?, ?)"
        " ORDER BY queued_at, rowid", LIVE)
    rows = await cur.fetchall()
    await cur.close()
    return [_row(r) for r in rows]


async def _move(job_id: str, to_state: str, *, expect: str,
                reason: str = "", stamp: str = "") -> Job | None:
    """Move one job, but only if it is still where the caller last saw it.

    Compare-and-set, and that is the whole of the concurrency design. Two
    things move a job — the worker and a player's cancel — and they can arrive
    in either order for the same row. Rather than a lock (which would have to
    be held across a download) the write states which state it is moving *out*
    of, so exactly one of the two wins and the loser is told it lost by getting
    `None` back.

    `stamp` names the timestamp column this move fills in, if any.
    """
    if to_state not in _LEGAL.get(expect, frozenset()):
        raise IllegalTransition(f"{expect} → {to_state} is not a move a job makes")

    sets = ["state = ?", "reason = ?"]
    args: list[object] = [to_state, reason]
    if stamp:
        sets.append(f"{stamp} = ?")
        args.append(_now())
    args += [job_id, expect]

    db = await get_db()
    cur = await db.execute(
        f"UPDATE store_jobs SET {', '.join(sets)} WHERE id = ? AND state = ?",
        tuple(args))
    moved = cur.rowcount
    await cur.close()
    await db.commit()
    if not moved:
        return None
    job = await get(job_id)
    if job is not None:
        await _announce(job)
    return job


async def _announce(job: Job) -> None:
    """Tell whatever is on screen that this row changed.

    The payload is the whole row rather than a bare id: a client that only
    wants to know *what just happened* — a notification, a sound — must not
    have to diff two lists to find out. The Store's own queue re-reads anyway,
    because one list with one source of truth beats a list assembled from
    events that can be missed.

    Never allowed to take a transition down with it. The database is the
    record; a socket is how the screen hears about it sooner.
    """
    try:
        await ws.broadcast("store:jobs", {"job": job.to_json()})
    except Exception:                                          # noqa: BLE001
        log.exception("store: could not announce job %s", job.id)


async def _progress(job_id: str, received: int, total: int) -> None:
    """Persist and announce progress while, and only while, the job is live.

    The database is the queryable truth; the socket only makes the screen hear
    sooner. A late chunk after cancellation cannot rewrite the terminal row.
    """
    db = await get_db()
    cur = await db.execute(
        "UPDATE store_jobs SET downloaded_bytes = ?, download_total = ?"
        " WHERE id = ? AND state = ?",
        (max(0, int(received)), max(0, int(total)), job_id, RUNNING))
    changed = cur.rowcount
    await cur.close()
    await db.commit()
    if changed:
        job = await get(job_id)
        if job is not None:
            await _announce(job)


async def _transform_progress(job_id: str, done: int, total: int) -> None:
    """Persist and announce transformation progress, live jobs only.

    Deliberately not `_progress`: an 8 GB archive being unpacked is not the
    download happening again, and a screen that reuses one bar for both cannot
    say which phase it is showing. Same guard as `_progress` — a late chunk
    after cancellation cannot rewrite a terminal row.
    """
    db = await get_db()
    cur = await db.execute(
        "UPDATE store_jobs SET transformed_bytes = ?, transform_total = ?"
        " WHERE id = ? AND state = ?",
        (max(0, int(done)), max(0, int(total)), job_id, RUNNING))
    changed = cur.rowcount
    await cur.close()
    await db.commit()
    if changed:
        job = await get(job_id)
        if job is not None:
            await _announce(job)


async def _record_inspection(job_id: str, ingestion_class: str) -> None:
    """Persist the classifier's verdict while, and only while, the job runs."""
    if ingestion_class not in {"A", "B", "C", "D", "E", "F"}:
        raise ValueError("an ingestion class must be A through F")
    db = await get_db()
    cur = await db.execute(
        "UPDATE store_jobs SET ingestion_class = ? WHERE id = ? AND state = ?",
        (ingestion_class, job_id, RUNNING))
    changed = cur.rowcount
    await cur.close()
    await db.commit()
    if changed:
        persisted = await get(job_id)
        if persisted is not None:
            await _announce(persisted)


async def _record_validation(job_id: str, verdict: str,
                             bios_warning: str) -> None:
    """Persist the verdict — including a refusal — while the job still runs.

    Written *before* the job is failed, so a download refused by validation
    leaves a row that says which of the two happened: the shape was checked and
    found wrong (`refused`), or it was checked, found right, and stopped at the
    missing import (`verified` / `unverified`). A row that carried only the
    sentence would lose that the moment step 17 rewrites it.
    """
    from .validator import REFUSED, UNVERIFIED, VERIFIED
    if verdict not in {VERIFIED, UNVERIFIED, REFUSED}:
        raise ValueError("a validation verdict must be verified, unverified "
                         "or refused")
    db = await get_db()
    cur = await db.execute(
        "UPDATE store_jobs SET validation = ?, bios_warning = ?"
        " WHERE id = ? AND state = ?",
        (verdict, bios_warning[:_MAX_TEXT], job_id, RUNNING))
    changed = cur.rowcount
    await cur.close()
    await db.commit()
    if changed:
        persisted = await get(job_id)
        if persisted is not None:
            await _announce(persisted)


# ── queueing ───────────────────────────────────────────────────────────────


def _text(value: object, field: str, *, cap: int = _MAX_TEXT,
          required: bool = True) -> str:
    raw = "" if value is None else str(value)
    out = raw.strip()
    if required and not out:
        raise InvalidJob(f"{field} is required")
    if len(out) > cap:
        raise InvalidJob(f"{field} is longer than {cap} characters")
    return out


def _clean_filename(value: object) -> str:
    """The name the download would arrive under, checked before it is stored.

    Nothing in this step writes a file, so this is not stopping a traversal
    today. It is stopping one being *written down* today and trusted later: the
    materializer joins this name onto a directory (matrix §1.3), and a row that
    has been sitting in the database since before that code existed is exactly
    the input nobody re-checks. A separator, a `.` or a `..` is refused here,
    where the row is created and where the refusal can still be shown to the
    player as "that result is not something this box will queue".

    Deliberately NOT normalised. Matrix §5.1 class C has to keep the archive's
    name byte for byte, so the choice is to accept it as it came or to refuse
    it — never to quietly rewrite it into something the source never named.
    """
    name = _text(value, "filename")
    if "/" in name or "\\" in name or "\0" in name:
        raise InvalidJob("the filename is a path, not a name")
    if name in (".", ".."):
        raise InvalidJob("the filename is a directory, not a name")
    return name


async def enqueue(*, system_id: str, roms_dir: str, title: str, filename: str,
                  format: str, size: object, provider: str, source: str) -> Job:
    """Write down that the player asked for this. Starts the worker.

    Refuses three things, each for a reason the caller can show:

      · a row it will not store — see `_clean_filename`;
      · the **same source, queued twice** while the first is still live. ✕ on a
        television is pressed twice more often than it is pressed once, and two
        rows for one game is two downloads of it;
      · a queue already `MAX_LIVE` deep.

    The worker is kicked here rather than by the router, so that every path
    that creates a job — including one written later — starts it.
    """
    system_id = _text(system_id, "systemId", cap=64)
    title = _text(title, "title")
    filename = _clean_filename(filename)
    provider = _text(provider, "provider", cap=64)
    source = _text(source, "source", cap=_MAX_SOURCE)
    roms_dir = _text(roms_dir, "romsDir", required=False)
    fmt = _text(format, "format", cap=32, required=False)
    try:
        # `0` is what a provider answers when the source does not say, and a
        # negative one is a source saying something impossible. Neither is a
        # reason to refuse the download; both are a reason not to store it.
        n = max(0, int(size))
    except (TypeError, ValueError):
        n = 0

    job = Job(
        # Fresh per job, and not the search result's id: that one is stable
        # across identical searches by design, so queueing the same game after
        # a failure would collide with the row that recorded the failure.
        id=uuid.uuid4().hex,
        system_id=system_id, roms_dir=roms_dir, title=title, filename=filename,
        format=fmt, size=n, provider=provider, source=source,
        state=QUEUED, reason="", queued_at=_now(), started_at="", ended_at="",
    )

    # Both refusals are conditions ON the insert rather than checks before it,
    # and that is not caution for its own sake: ✕ is a gamepad button with a
    # repeat rate, two presses arrive before the first request has answered,
    # and a `SELECT` followed by an `INSERT` has an await between them. Read
    # first and both presses see an empty queue; written this way the second
    # statement matches nothing and one row exists. One statement, so there is
    # no window — and no module-level lock, which would bind itself to the
    # first event loop that took it and raise in the second.
    db = await get_db()
    cur = await db.execute(
        "INSERT INTO store_jobs (id, system_id, roms_dir, title, filename,"
        " format, size, provider, source, state, reason, queued_at)"
        " SELECT ?,?,?,?,?,?,?,?,?,?,?,?"
        "  WHERE NOT EXISTS (SELECT 1 FROM store_jobs"
        "                     WHERE system_id = ? AND source = ?"
        "                       AND state IN (?, ?))"
        "    AND (SELECT COUNT(*) FROM store_jobs WHERE state IN (?, ?)) < ?",
        (job.id, job.system_id, job.roms_dir, job.title, job.filename,
         job.format, job.size, job.provider, job.source, job.state, job.reason,
         job.queued_at,
         job.system_id, job.source, *LIVE,
         *LIVE, MAX_LIVE))
    written = cur.rowcount
    await cur.close()
    await db.commit()

    if not written:
        # Which of the two it was. Read afterwards rather than before, so the
        # sentence describes the queue as it actually is — and the refusal is
        # the accurate one even when the answer changed under the request.
        live = await live_jobs()
        if any(j.system_id == system_id and j.source == source for j in live):
            raise QueueRefused("that is already in the queue")
        raise QueueRefused(
            f"the queue is full — {MAX_LIVE} jobs are already waiting or running")

    await _announce(job)
    kick()
    return job


async def cancel(job_id: str) -> Job:
    """Stop a job, whether it has started or not.

    One call for both, because the player pressing ✕ on a row does not know or
    care which it is — and because the row can move between the read and the
    write. The durable state is written **first** and the running task is
    interrupted afterwards: a process that dies in between leaves a row that
    correctly says `cancelled`, where the other order would leave one that says
    `running` for a task that no longer exists.
    """
    job = await get(job_id)
    if job is None:
        raise UnknownJob(job_id)
    if job.state in TERMINAL:
        raise IllegalTransition(f"that job is already {job.state}")

    moved = await _move(job_id, CANCELLED, expect=job.state,
                        reason="cancelled from the Store", stamp="ended_at")
    if moved is None:
        # It moved under us — the worker started it, or finished it. Re-read
        # and answer with the truth rather than with what was asked for.
        again = await get(job_id)
        if again is None:
            raise UnknownJob(job_id)
        if again.state in TERMINAL:
            raise IllegalTransition(f"that job is already {again.state}")
        moved = await _move(job_id, CANCELLED, expect=again.state,
                            reason="cancelled from the Store", stamp="ended_at")
        if moved is None:
            raise IllegalTransition("that job finished before it could be cancelled")

    await _interrupt(job_id)
    # Also covers the last-byte race: materialization may have atomically
    # renamed just before cancellation won the row transition.
    from .materializer import cleanup_job
    cleanup_job(job_id)
    return moved


async def _interrupt(job_id: str) -> None:
    """Stop the acquisition in flight, if it is this one.

    A no-op for a job that had not started: there is nothing to interrupt and
    the row is already `cancelled`.
    """
    if _job_id == job_id and _job_task is not None and not _job_task.done():
        _job_task.cancel()
        await asyncio.gather(_job_task, return_exceptions=True)


# ── the worker ─────────────────────────────────────────────────────────────
#
# One job at a time, box-wide, on the shape `routers/catalog.py` uses for
# `gamecore-emu`: the task handle is the check, not a lock. Two requests
# arriving in the same loop tick both see a lock unlocked — the task has not
# started yet — and the second silently queues behind the first instead of
# being recognised as "already running". Checking and assigning `_worker` is
# atomic because there is no `await` between them.
#
# One and not several because a box on a domestic line gains nothing from four
# concurrent downloads and loses the ability to say which one is happening.

_worker: asyncio.Task | None = None
_job_task: asyncio.Task | None = None
_job_id: str | None = None


def kick() -> None:
    """Make sure a worker is draining the queue. Idempotent and cheap."""
    global _worker
    if _worker is not None and not _worker.done():
        return
    _worker = asyncio.create_task(drain())
    _worker.add_done_callback(
        lambda t: t.cancelled() or (t.exception() and
                                    log.warning("store: the acquisition worker "
                                                "stopped: %s", t.exception())))


async def drain() -> None:
    """Run queued jobs until there are none left, then stop.

    Stopping rather than idling is what makes the worker cheap to start: there
    is no loop ticking on a box whose Store has never been opened, and `kick()`
    is a no-op whenever one is already running. This is the same coroutine the
    task runs, exported so a test can await the whole drain without racing it.
    """
    global _job_task, _job_id
    while True:
        job = await _claim_next()
        if job is None:
            return
        task = asyncio.create_task(_acquire(job))
        _job_task, _job_id = task, job.id
        try:
            # `wait`, not `await task`. Awaiting the task directly makes the
            # job's cancellation indistinguishable from the worker's own —
            # both surface as a CancelledError raised here — and the worker
            # would exit on a single cancelled job. `wait` hands the task back
            # instead, and only raises when it is *this* coroutine being
            # cancelled, which is the shutdown case and should stop the loop.
            await asyncio.wait({task})
        finally:
            # Only if it is still ours: `stop()` clears these on the way out,
            # and this must not put back what it cleared.
            if _job_task is task:
                _job_task, _job_id = None, None

        if task.cancelled():
            # A cancel asked for it, and `cancel()` has already written the
            # row. Nothing to settle.
            continue
        error = task.exception()
        result = "" if error is not None else task.result()
        await _settle(job, error, success_reason=result)


async def _claim_next() -> Job | None:
    """Take the oldest queued job, or answer `None`.

    The claim is the `queued → running` move itself, compare-and-set, so a job
    cancelled between the read and the write is not started: the update matches
    no row and the loop asks for the next one.
    """
    while True:
        db = await get_db()
        cur = await db.execute(
            f"SELECT {_COLUMNS} FROM store_jobs WHERE state = ?"
            " ORDER BY queued_at, rowid LIMIT 1", (QUEUED,))
        row = await cur.fetchone()
        await cur.close()
        if row is None:
            return None
        claimed = await _move(row["id"], RUNNING, expect=QUEUED,
                              stamp="started_at")
        if claimed is not None:
            return claimed


async def _acquire(job: Job) -> str:
    """Resolve, materialize, classify, shape, check and import one job.

    The six seams are named here rather than fused — see `AcquiredTarget` and
    matrix §5. Only the final one receives ``roms_dir`` and can write in the
    live library.

    Separate from `drain` so that it is a task of its own and therefore
    cancellable on its own: cancelling the worker would stop the queue, and
    cancelling one job must not.
    """
    provider = acquisition_provider()
    if provider is None:
        raise RuntimeError(NO_PROVIDER)
    target = await provider.acquire(job)

    # `redacted()` and never the target itself: an acquisition URL is minted
    # against the owner's account and spends their bandwidth, so it belongs in
    # no journal.
    log.info("store: job %s resolved to %s", job.id, target.redacted())

    store = materializer()
    if store is None:
        raise RuntimeError(NO_MATERIALIZER)
    await store.materialize(job, target)

    # Inspection reads only the job-owned work area and the selected pack. Its
    # verdict is durable so transform/validate/import consume it later instead
    # of independently rediscovering a class that could drift between stages.
    # Archive directories can contain thousands of names. Keep their bounded,
    # read-only walk off the event loop so cancellation and the rest of the
    # backend remain responsive while it runs.
    verdict = await asyncio.to_thread(inspect_download, job)
    await _record_inspection(job.id, verdict.ingestion_class)
    if not verdict.complete:
        raise RuntimeError(verdict.reason)

    # Transformation reads the persisted verdict and produces the class's final
    # shape *beside* the download, under `store/jobs/<job-id>/ingest/`. It is
    # the first step that writes content rather than a label, and it is still
    # nowhere near `emu/<system>/`: placing bytes where the library scan finds
    # them is import's (17). The source is never opened for writing and never
    # removed here — on success or failure — so a job that fails at this step
    # leaves its download byte-identical for the next one to use.
    shape = await transformer().transform(job, verdict.ingestion_class)
    log.info("store: job %s shaped as class %s into %s (%d bytes)",
             job.id, shape.ingestion_class, shape.root.name, shape.bytes_written)

    # Validation reads the produced shape and the pack, and writes nothing: not
    # the source, not the shape. Off the event loop for the same reason
    # inspection is — it opens every produced file and may list an archive
    # through `7z l` — and its verdict is persisted whichever way it goes, so a
    # refused download leaves a row that says the check ran and what it found.
    checked = await asyncio.to_thread(validate_shape, job, shape)
    await _record_validation(job.id, checked.verdict, checked.bios_warning)
    if checked.proven:
        log.info("store: job %s verified — %s", job.id, _few(checked.proven, "; "))
    if checked.unproven:
        # Not a warning. A `.sfc` carries no field anybody checks, and saying
        # so at INFO is the honest record; at WARNING it would read as a fault
        # of the download.
        log.info("store: job %s holds file(s) no signature can prove: %s",
                 job.id, _few(checked.unproven))
    if checked.bios_warning:
        # §5.3 rule 4: said out loud, and read by nothing below.
        log.warning("store: job %s — %s", job.id, checked.bios_warning)
    if not checked.ok:
        raise RuntimeError(checked.reason)

    # This is the only call in the chain allowed to receive the destination.
    # Its warning is a successful row's reason: `.nsp` ambiguity must be
    # visible without pretending the package can be classified.
    imported = await asyncio.to_thread(import_shape, job, shape)
    log.info("store: job %s imported %s", job.id, _few(imported.names))
    return " ".join(part for part in
                    (imported.warning, checked.bios_warning) if part)


def _few(items: tuple[str, ...], join: str = ", ", limit: int = 5) -> str:
    """The first few of a list, for a log line that must not be a shape dump.

    A shape may legitimately hold hundreds of files, and a journal entry that
    reproduces all of them is one nobody reads twice.
    """
    shown = join.join(items[:limit])
    return shown if len(items) <= limit else f"{shown} (+{len(items) - limit} more)"


async def _settle(job: Job, error: BaseException | None,
                  success_reason: str = "") -> None:
    """Write what became of a job that ran to its end.

    `expect=RUNNING` is the half that makes a cancel safe. A player who
    cancelled while the provider was on its last line has already moved the row
    to `cancelled`; this update then matches nothing and the finish is
    discarded, rather than overwriting the player's decision with a `done` they
    did not ask for.
    """
    if error is None:
        await _move(job.id, DONE, expect=RUNNING,
                    reason=success_reason[:_MAX_TEXT], stamp="ended_at")
        return
    # str(), not repr(), and whatever the provider chose to say. A provider's
    # own message is the only description of the failure there is; the contract
    # on `AcquisitionProvider.acquire` is that it is built from safe parts.
    # Truncated rather than refused: this runs inside the worker, and a reason
    # too long to store is not a reason to lose the fact that the job failed.
    reason = (str(error).strip() or error.__class__.__name__)[:_MAX_TEXT]
    log.warning("store: job %s (%s) failed — %s", job.id, job.filename, reason)
    await _move(job.id, FAILED, expect=RUNNING, reason=reason, stamp="ended_at")


# ── coming back up ─────────────────────────────────────────────────────────


async def resume_after_restart() -> int:
    """What becomes of a job the box was killed in the middle of.

    Called once, from the lifespan, before anything can read the queue. A row
    left saying `running` describes a task that died with the process, and the
    one thing it must not do is come back up still claiming to run: the screen
    would show a download that nothing is downloading, and it would show it for
    ever, because the only thing that ever moves a `running` row is the worker
    that is no longer there.

    **It becomes `failed`, with `INTERRUPTED` as the reason — not `queued`.**
    Re-queueing would read better and be worse: it restarts an acquisition the
    player did not ask to restart, from a position nothing recorded, and it
    erases the only evidence that the box stopped mid-download. A row that says
    what happened, and a player who can ask again, is the honest pair. Queued
    jobs are left alone and picked up normally — that is what makes the queue
    survive a reboot at all.

    Idempotent: after the first pass there is no `running` row to find.
    """
    db = await get_db()
    cur = await db.execute("SELECT id FROM store_jobs WHERE state = ?", (RUNNING,))
    stranded_ids = [row["id"] for row in await cur.fetchall()]
    await cur.close()
    # Restart-from-zero policy: a stale part has no persisted HTTP validator.
    from .materializer import cleanup_job
    for job_id in stranded_ids:
        cleanup_job(job_id)
    cur = await db.execute(
        "UPDATE store_jobs SET state = ?, reason = ?, ended_at = ?"
        " WHERE state = ?", (FAILED, INTERRUPTED, _now(), RUNNING))
    stranded = cur.rowcount
    await cur.close()
    await db.commit()
    if stranded:
        log.warning("store: %d job%s were running when the box stopped — "
                    "marked failed", stranded, "" if stranded == 1 else "s")
    return stranded


async def stop() -> None:
    """Put the worker down on the way out.

    A graceful stop has time to tell the truth immediately: cancel the transfer,
    remove its owned work directory, then mark the row interrupted. A crash is
    repaired by `resume_after_restart()` with the same state and cleanup.
    """
    global _worker, _job_task, _job_id
    active_id = _job_id
    for task in (_job_task, _worker):
        if task is not None and not task.done():
            task.cancel()
    pending = [t for t in (_job_task, _worker) if t is not None]
    _worker = _job_task = None
    _job_id = None
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    if active_id is not None:
        from .materializer import cleanup_job
        cleanup_job(active_id)
        await _move(active_id, FAILED, expect=RUNNING, reason=INTERRUPTED,
                    stamp="ended_at")


async def wait_idle() -> None:
    """Wait for the worker to run the queue dry. Nothing if none is running."""
    task = _worker
    if task is not None and not task.done():
        await asyncio.gather(task, return_exceptions=True)
