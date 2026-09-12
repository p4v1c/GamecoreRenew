"""The Store's Games tab — searching, and only searching.

Two endpoints: which provider is answering, and what it answers for one
console. Nothing here downloads, writes a byte, or remembers a request. That
is not an oversight to be filled in later by accident — acquisition, the job
that survives a reboot, and the six ingestion classes a download has to become
(`docs/architecture/14-store-ingestion-matrix.md` §5) are separate steps with
their own seams, and half of one of them built here would have to be undone.

**Why the search lives behind this router at all.** A provider is configured
with an indexer's URL and its API key. A key that reaches the browser is a key
in the page source and in the devtools network pane of a television nobody
logs out of. So the frontend asks `/api/store/...`, and the credential — when
there ever is one — stays on this side.

Shaped after `routers/catalog.py` in what matters: the system id is validated
against what the catalogue declares rather than trusted, because this endpoint
is reachable from the LAN interface behind forward_auth. Unlike that router it
starts nothing and holds no lock — a search is a question, not an action, so
there is no busy state to report and no `catalog:done` to wait for.
"""
from __future__ import annotations

import logging
import re

from fastapi import APIRouter, HTTPException, Query

from ..services.store import get_provider, provider_info, searchable_systems, system_for

router = APIRouter(prefix="/store", tags=["store"])
log = logging.getLogger(__name__)

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
#: Long enough for any real title, short enough that a hostile query cannot
#: become a giant request to somebody else's indexer once one is wired up.
_MAX_QUERY = 120
#: How many rows one search may answer with. A television grid pages at eight;
#: five pages of results is already more than a player will walk through.
_MAX_RESULTS = 40


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
