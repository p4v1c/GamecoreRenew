"""The Store's own services — searching for a game, and nothing else yet.

This package is the backend half of the Store's Games tab. It is deliberately
narrow: it answers *what could be downloaded for this console*, and stops
there. Acquiring the bytes, turning them into a playable game, and the six
ingestion classes that decides
([`docs/architecture/14-store-ingestion-matrix.md`](../../../docs/architecture/14-store-ingestion-matrix.md)
§5) are separate steps and no part of them is here.

**Why searching lives in the backend at all**, when the browser could talk to
an indexer itself: a search provider is configured with a URL and an API key,
and a key that reaches the browser is a key in the page source, in the devtools
network pane, and in anything the television's browser caches. The frontend
asks `/api/store/...` and never learns how the answer was obtained.
"""
from .search import (                                     # noqa: F401
    SearchProvider,
    SearchResult,
    SearchSystem,
    get_provider,
    provider_info,
    searchable_systems,
    system_for,
)
