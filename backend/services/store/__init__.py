"""The Store's own services — searching for a game, and queueing one.

This package is the backend half of the Store's Games tab: it answers *what
could be downloaded for this console*, and it writes down *that the player
asked for one*. Turning bytes into a playable game — the six ingestion classes
of
([`docs/architecture/14-store-ingestion-matrix.md`](../../../docs/architecture/14-store-ingestion-matrix.md)
§5) — is a separate step and no part of it is here.

`jobs.py` is the queue: one row per thing the player asked for, in the database
the box already has, with the five states it may be in and the worker that runs
them one at a time. Running one is **resolve, then store**, and only the first
half exists: `realdebrid.py` turns a job's source into a direct URL, and
`jobs.materializer()` — which would fetch it — answers `None` on every box.
So a job still fails, now for one of two true reasons: nothing configured, or
resolved and nowhere to put it. A queue that reported success having downloaded
nothing would be a lie that persists across a reboot.

**Nothing here downloads anything**, and that is what the split is for. An
acquisition provider answers an `AcquiredTarget` — a URL and what it takes to
check the bytes — and moves none of them; matrix §5 is the step that does.

**Why searching lives in the backend at all**, when the browser could talk to
an indexer itself: a search provider is configured with a URL and an API key,
and a key that reaches the browser is a key in the page source, in the devtools
network pane, and in anything the television's browser caches. The frontend
asks `/api/store/...` and never learns how the answer was obtained.

Two search providers live here. The demo one invents its rows and says so; the
Prowlarr one talks to an indexer aggregator **the box owner runs themselves** —
GameCore never installs, manages or removes it, and knows only a URL and an API
key, which is what keeps a .NET service and a second LAN port off the box. A
box with no `config/store-prowlarr.json` keeps the demo provider and its
banner, so nothing here has to be configured for the tab to work.

**Real-Debrid is external in exactly the same way**, and is here for exactly
that reason: it turns a magnet into a plain HTTPS URL, so this box needs no
torrent client — no daemon, no listening port, nothing for the uninstaller to
take away. The owner has their own account and GameCore knows one token, in
`config/store-realdebrid.json`. No file, no acquisition provider.
"""
from .jobs import (                                     # noqa: F401
    CANCELLED,
    DONE,
    FAILED,
    LIVE,
    NO_MATERIALIZER,
    NO_PROVIDER,
    QUEUED,
    RUNNING,
    STATES,
    TERMINAL,
    AcquiredTarget,
    AcquisitionProvider,
    IllegalTransition,
    InvalidJob,
    Job,
    Materializer,
    QueueRefused,
    UnknownJob,
)
from .prowlarr import ProwlarrSearchProvider              # noqa: F401
from .realdebrid import RealDebridAcquisition             # noqa: F401
from .resolve import ResolvedSource, UnresolvableSource   # noqa: F401
from .search import (                                     # noqa: F401
    NEVER_OFFERED,
    SearchProvider,
    SearchResult,
    SearchSystem,
    get_provider,
    provider_info,
    searchable_systems,
    system_for,
)
