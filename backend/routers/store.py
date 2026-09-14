"""The Store's Games tab — searching, and the queue of what was asked for.

Two halves, and the line between them is the point. The search routes ask a
question: they start nothing, hold no lock, and remember nothing. The job
routes write down a request that outlives the screen it was made on — one row
per game the player asked for, in the database this box already has.

The worker owns the whole ingestion chain. Every stage through validation is
confined to `<DATA>/store/jobs/<id>/`; import alone publishes below the one
pack-derived `emu/<dir>/`, and only then may the row say `done`.

**Why the search lives behind this router at all.** A provider is configured
with an indexer's URL and its API key. A key that reaches the browser is a key
in the page source and in the devtools network pane of a television nobody
logs out of. So the frontend asks `/api/store/...`, and the credential — when
there ever is one — stays on this side.

Shaped after `routers/catalog.py` in what matters: the system id is validated
against what the catalogue declares rather than trusted, because this endpoint
is reachable from the LAN interface behind forward_auth; and the queue runs one
job at a time behind a task handle rather than a lock, for the reason stated
over `_current` there. It differs in one way that matters — `catalog.py` holds
its state in a module variable that dies with the process, and this one cannot:
a download is minutes long and a box gets turned off.
"""
from __future__ import annotations

import logging
import re

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..services.store import (get_provider, jobs, provider_info,
                              searchable_systems, system_for)

router = APIRouter(prefix="/store", tags=["store"])
log = logging.getLogger(__name__)

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
#: Long enough for any real title, short enough that a hostile query cannot
#: become a giant request to somebody else's indexer once one is wired up.
_MAX_QUERY = 120
#: How many rows one search may answer with. A television grid pages at eight;
#: five pages of results is already more than a player will walk through.
_MAX_RESULTS = 40
#: A job id as `jobs.enqueue` mints them — `uuid4().hex`. Checked before the
#: id reaches a query for the same reason the system id is: this route is
#: reachable from the LAN, and an id shape is the cheapest thing to be sure of.
_JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")


@router.get("/provider")
def describe_provider():
    """Which provider answers, and whether its rows are real.

    `live` is the field that matters and it is sent rather than inferred: the
    demo provider invents plausible rows, and a tab that could not tell them
    from an indexer's would be inviting a player to press ✕ on a game that
    does not exist.
    """
    return provider_info()


@router.get("/systems")
def list_searchable_systems():
    """The consoles a search may be scoped to — the installed ones.

    The Games tab does not read this: it already holds the catalogue for its
    Consoles tab and filters it there, and a second reader of the same fact is
    how two screens come to disagree about it. It is here because the rule has
    to hold for a caller that is not that screen, and because "which of these
    can I search" is otherwise only answerable by trying each one.
    """
    return [
        {
            "id": s.id,
            "label": s.label,
            "platform": s.platform,
            "romsDir": s.roms_dir,
            "extensions": list(s.extensions),
            "scanDirs": s.scan_dirs,
        }
        for s in searchable_systems()
    ]


@router.get("/search")
async def search_games(
    system: str = Query(..., description="the console to search inside"),
    q: str = Query(..., description="what the player typed"),
):
    """What could be downloaded for one console.

    **System first, always.** There is no search across the catalogue and
    there will not be one: the ingestion class of a download is a property of
    the pair (system, incoming format) — the same `.zip` is the ROM on `mame`
    and packaging on `snes9x` (matrix §0, §2) — and the target directory is a
    property of the system (§1.3). A result with no console attached could be
    neither placed nor classified, and no indexer sorts its own results by
    console reliably enough to attach one afterwards.

    A console that is not installed is refused rather than searched. The
    download would land in a directory nothing scans, for a tile that is not
    on the grid.
    """
    if not _ID_RE.fullmatch(system):
        raise HTTPException(400, "invalid system id")
    query = q.strip()
    if not query:
        raise HTTPException(400, "nothing to search for")
    if len(query) > _MAX_QUERY:
        raise HTTPException(400, f"the query is longer than {_MAX_QUERY} characters")

    target = system_for(system)
    if target is None:
        # 409 and not 404: the pack may very well exist. What is missing is
        # the console on this box, and "install it first" is the actionable
        # half of that — see `system_for` for why the three causes are not
        # told apart in the answer.
        raise HTTPException(409, f"{system!r} is not an installed console on this box")

    provider = get_provider()
    try:
        rows = await provider.search(target, query, limit=_MAX_RESULTS)
    except Exception as e:
        # A provider that throws is a provider that is down, misconfigured, or
        # answering something unexpected. 502, with the reason logged and not
        # returned: it may carry a URL or a key.
        log.warning("store: search provider %r failed — %s", provider.name, e)
        raise HTTPException(502, "the search provider did not answer")

    return {
        "system": target.id,
        "label": target.label,
        # Where a download for this console would have to land — matrix §1.3,
        # and the concrete reason the system is chosen before anything is
        # searched for. Relative to <DATA>, like `romsPath` in systems.json.
        "romsDir": target.roms_dir,
        "provider": provider.name,
        "live": provider.live,
        "query": query,
        "results": [r.to_json() for r in rows[:_MAX_RESULTS]],
    }


# ── the queue ──────────────────────────────────────────────────────────────
#
# Three routes, and deliberately three: put one in, read them back, take one
# out. No route restarts a job, no route deletes a row, and there is no
# "clear finished" — a job is a record of something the player asked for, and
# the first two of those would each be a second way to change a state that
# `services/store/jobs.py` already owns exactly one way of changing.
#
# Unlike the search routes above, these ACT. They are still cheap — the work
# happens on a worker task and every one of them answers immediately — but
# they write to the database the box keeps its play history in, so the
# validation below is the same shape as `catalog.py`'s: the system id is
# checked against what the catalogue declares rather than trusted, because this
# endpoint is reachable from the LAN interface behind forward_auth.


class QueueRequest(BaseModel):
    """One search result, handed back to be queued.

    The client sends the row it is looking at rather than an id the backend
    could look up again, because there is nothing to look it up in: a search is
    a question asked of somebody else's indexer and nothing here remembers the
    answer. So the fields arrive from the browser and are treated as such —
    `jobs.enqueue` refuses what it will not store, and the two facts the box
    can answer for itself are not taken from here at all:

      · **where it would land** comes from the pack (`system_for().roms_dir`),
        not from the request. It is the one field that decides a directory, and
        a client that could name it would be a client that could name any
        directory;
      · **which provider found it** is checked against the one answering now,
        so a tab left open across a change of provider cannot queue a row from
        the old one.

    A Pydantic body is also what keeps this route off the list in `main.py`'s
    cross-origin guard: a form-driven cross-origin POST cannot send JSON, and
    FastAPI answers 422 to anything else.
    """

    systemId: str
    title: str
    filename: str
    #: The provider's own opaque locator, as it was handed out by `/search`.
    source: str
    provider: str
    format: str = ""
    size: int = 0


@router.get("/jobs")
async def list_jobs():
    """The queue, newest first — every state, not just the live ones.

    Finished jobs stay in the list because the screen has nowhere else to say
    what happened: a download that failed at three in the morning is only ever
    read about afterwards, and a queue that emptied itself on completion would
    be a queue that never explains anything.
    """
    return {
        "jobs": [j.to_json() for j in await jobs.list_jobs()],
        # True means a successful row owns a live library entry, not merely
        # staged bytes. The importer is now the last worker seam.
        "downloadReady": True,
        # Kept separate: a box may know how to import while lacking a configured
        # acquisition/materialization path for a particular request.
        "materializerReady": jobs.materializer() is not None,
    }


@router.post("/jobs", status_code=201)
async def queue_job(body: QueueRequest):
    """Ask the box to bring one result in.

    Answers as soon as the row is written. The work happens on a worker task
    and is reported by state on `GET /jobs` and on the `store:jobs` socket
    event — a request that waited for the download would be a request that
    holds a connection open for minutes and tells a player nothing while it
    does.

    A configured box downloads into `<DATA>/store/jobs/<job-id>/`, validates
    the produced shape, then imports it atomically into the pack's ROM folder.
    """
    if not _ID_RE.fullmatch(body.systemId):
        raise HTTPException(400, "invalid system id")
    target = system_for(body.systemId)
    if target is None:
        # Same 409 and the same reason as `/search`: the pack may well exist,
        # what is missing is the console on this box. A job for a console that
        # is not installed would land in a directory nothing scans.
        raise HTTPException(409,
                            f"{body.systemId!r} is not an installed console on this box")

    answering = get_provider().name
    if body.provider.strip() != answering:
        # Not a 400: the request was well formed when it was made. The box
        # changed under it, and "search again" is the actionable half.
        raise HTTPException(409, "that result came from a provider this box is "
                                 "no longer using — search again")

    try:
        job = await jobs.enqueue(
            system_id=target.id,
            # The box's own answer, never the client's — see QueueRequest.
            roms_dir=target.roms_dir,
            title=body.title, filename=body.filename, format=body.format,
            size=body.size, provider=answering, source=body.source)
    except jobs.InvalidJob as e:
        raise HTTPException(400, str(e))
    except jobs.QueueRefused as e:
        raise HTTPException(409, str(e))
    return job.to_json()


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    """Stop a job, whether it has started or not.

    Cancelling is a **state**, not a deletion, so this is a POST onto the job
    and not a DELETE of it: the row stays, saying it was cancelled, which is
    the only way a player can tell "I changed my mind" from "I never asked".
    """
    if not _JOB_ID_RE.fullmatch(job_id):
        raise HTTPException(400, "invalid job id")
    try:
        return (await jobs.cancel(job_id)).to_json()
    except jobs.UnknownJob:
        raise HTTPException(404, "no such job")
    except jobs.IllegalTransition as e:
        raise HTTPException(409, str(e))
