"""The Store's own services — searching for a game, and queueing one.

This package is the backend half of the Store's Games tab: it answers *what
could be downloaded for this console*, and it writes down *that the player
asked for one*. Turning bytes into a playable game — the six ingestion classes
of
([`docs/architecture/14-store-ingestion-matrix.md`](../../../docs/architecture/14-store-ingestion-matrix.md)
§5) — is a separate step and no part of it is here.

`jobs.py` is the persistent queue. Running one resolves through Real-Debrid,
then `materializer.py` streams the bytes into the job-owned work area under
`<DATA>/store/jobs/`. `inspector.py` classifies that unchanged staging shape,
and `transformer.py` gives it the shape its class requires — beside the
download, in `store/jobs/<job-id>/ingest/`, with the download itself never
opened for writing and never removed. `validator.py` then judges that shape
against its class and persists a verdict, reading a few bytes of each produced
file and writing nowhere at all. `importer.py` then publishes only an accepted
shape, and only inside the pack-derived ROM directory. That is the one point
allowed to write below `emu/` and the one point after which the row may say
`done`.

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
from .validator import (                                  # noqa: F401
    REFUSED,
    UNVERIFIED,
    VERIFIED,
    Validation,
    ValidationError,
)
