"""The Store's own services — searching for a game, and queueing one.

This package is the backend half of the Store's Games tab: it answers *what
could be downloaded for this console*, and it writes down *that the player
asked for one*. Turning bytes into a playable game — the six ingestion classes
of
([`docs/architecture/14-store-ingestion-matrix.md`](../../../docs/architecture/14-store-ingestion-matrix.md)
§5) — is a separate step and no part of it is here.

`jobs.py` is the queue: one row per thing the player asked for, in the database
the box already has, with the five states it may be in and the worker that runs
them one at a time. **Nothing acquires anything yet** — there is no
`AcquisitionProvider` and this package ships none, so a job that reaches the
worker fails saying exactly that. A queue that reported success having
downloaded nothing would be a lie that persists across a reboot.

**Why searching lives in the backend at all**, when the browser could talk to
an indexer itself: a search provider is configured with a URL and an API key,
and a key that reaches the browser is a key in the page source, in the devtools
network pane, and in anything the television's browser caches. The frontend
asks `/api/store/...` and never learns how the answer was obtained.

Two providers live here. The demo one invents its rows and says so; the
Prowlarr one talks to an indexer aggregator **the box owner runs themselves** —
GameCore never installs, manages or removes it, and knows only a URL and an API
key, which is what keeps a .NET service and a second LAN port off the box. A
box with no `config/store-prowlarr.json` keeps the demo provider and its
banner, so nothing here has to be configured for the tab to work.
"""
from .jobs import (                                     # noqa: F401
    CANCELLED,
    DONE,
    FAILED,
    LIVE,
    NO_PROVIDER,
    QUEUED,
    RUNNING,
    STATES,
    TERMINAL,
    AcquisitionProvider,
    IllegalTransition,
    InvalidJob,
    Job,
    QueueRefused,
    UnknownJob,
)
from .prowlarr import ProwlarrSearchProvider              # noqa: F401
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
