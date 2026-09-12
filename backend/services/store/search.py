"""What a search provider is, and which one this box uses.

Three things live here and nothing else: the console a search is scoped to
(`SearchSystem`), what a search comes back with (`SearchResult`), and the
interface a provider implements (`SearchProvider`). The only implementation
shipped today is the demo one beside this file.

── Why a search is scoped to one console ──────────────────────────────────
A player picks a system first and searches inside it. That is not a UI
preference, it is what makes the rest of the Store possible:

  · the target directory is `<DATA>/emu/<roms.dir>/`, which is a property of
    the system and of nothing else (matrix §1.3);
  · the ingestion class is a property of the **pair** (system, incoming
    format) — the same `.zip` is the ROM on `mame` and packaging on `snes9x`
    (matrix §0, §2), so a result with no system attached cannot be classified
    at all;
  · no indexer sorts its results by console reliably. Asking one for "mario"
    across everything and then guessing which machine each hit is for is a
    guess this repository would have to be right about every time.

So `SearchSystem` is an argument to `search()` rather than something a result
carries back, and a provider is handed the pack's own declared extensions:
that is how the demo provider below offers formats this console can actually
hold, and how a real one will filter what an indexer hands it.

── Why only installed consoles are searchable ─────────────────────────────
`searchable_systems()` joins the catalogue against `config/systems.json`.
Offering a Saturn game on a box with no Saturn produces a download that lands
in a directory nothing scans, for a tile that is not on the grid. The frontend
applies the same rule from the list it already has; this is the half that
cannot be skipped by calling the endpoint directly.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Protocol

from ..catalog import load_catalog
from ..paths import config_dir

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SearchSystem:
    """One console, as a provider is allowed to see it.

    Everything here comes from the pack. A provider gets no HTTP client, no
    settings object and no way back into the box — it is handed a console and
    a query and it answers rows.
    """

    id: str
    label: str
    platform: str
    #: `emu/<dir>`, relative to `<DATA>` — matrix §1.3. Where a download for
    #: this console would have to land, and the reason the system is chosen
    #: before anything is searched for.
    roms_dir: str
    #: The pack's own `roms.extensions`, glob-style (`*.nes`). Empty for the
    #: two `scanDirs` packs, which declare none — matrix §1.5.
    extensions: tuple[str, ...] = ()
    #: `roms.scanDirs` — the game is a directory, not a file (matrix §5.1 F).
    scan_dirs: bool = False

    @property
    def suffixes(self) -> tuple[str, ...]:
        """`roms.extensions` as bare suffixes: `("nes", "unf", "unif")`."""
        return tuple(e.lstrip("*.").lower() for e in self.extensions if e.strip("*."))


@dataclass(frozen=True)
class SearchResult:
    """One thing that could be downloaded for one console.

    The fields are what the ingestion steps will need to decide anything, and
    they are here now so that a provider written later does not have to invent
    them — see matrix §5.1, whose four class predicates read exactly two
    things: the pack, and the shape of what arrives.

      · `filename` carries the incoming **format**, which is half of the pair
        the class is keyed on. It is also what class C has to preserve byte
        for byte ("the archive, name preserved"), so it is recorded as the
        source names it and never normalised here.
      · `size` is what the player is about to spend, and what a box with a
        full disk has to be able to refuse before it starts.
      · `source` is how to find this again. Nothing dereferences it today.

    What is deliberately **not** here is the archive's member list, which is
    the other half of §2.4's decision: it is not knowable from a search
    result, only from the bytes. Guessing it here would be the design bug the
    matrix opens by naming.
    """

    #: Stable across identical searches — see the demo provider for how.
    id: str
    title: str
    #: The name the download would arrive under, extension included.
    filename: str
    #: The bare suffix (`"zip"`, `"chd"`), or `"folder"` on a `scanDirs`
    #: console where the game is a directory and has no extension at all.
    format: str
    #: Bytes. `0` when the source does not say — not a small download.
    size: int
    system_id: str
    provider: str
    #: The provider's own locator. Opaque to everything outside the provider
    #: that produced it, and never a URL the frontend is expected to follow.
    source: str
    region: str = ""
    languages: tuple[str, ...] = field(default_factory=tuple)

    def to_json(self) -> dict:
        """camelCase, like every other row this frontend reads."""
        return {
            "id": self.id,
            "title": self.title,
            "filename": self.filename,
            "format": self.format,
            "size": self.size,
            "systemId": self.system_id,
            "provider": self.provider,
            "source": self.source,
            "region": self.region,
            "languages": list(self.languages),
        }


class SearchProvider(Protocol):
    """Where results come from.

    One method. A provider does not download, does not write, does not decide
    what a result becomes — those are later steps with their own seams, and a
    provider that reached into them would be the place a second copy of the
    ingestion rules grew.

    `search` is `async` because the one that matters will be I/O: the demo
    implementation answers instantly and still declares it, so the router and
    its tests are written against the shape the real one will have rather than
    against the one that is convenient today.
    """

    #: Short id, matched against `GAMECORE_STORE_SEARCH_PROVIDER`.
    name: str
    #: What to call it on screen.
    label: str
    #: False when the rows are not real sources. The Games tab says so, out
    #: loud — a store that invented plausible rows and looked identical to one
    #: with a real indexer behind it would be the dishonest empty state this
    #: tab replaced.
    live: bool

    async def search(self, system: SearchSystem, query: str,
                     limit: int = 40) -> list[SearchResult]:
        ...


# ── which provider this box uses ───────────────────────────────────────────
#
# One entry today, and the environment variable is what a later step adds a
# second to. There is no secret store here and no settings row: a provider
# that needs a URL and a key is step 10's problem, and building the store for
# it now would be an abstraction with nothing behind it.

_ENV = "GAMECORE_STORE_SEARCH_PROVIDER"
DEFAULT_PROVIDER = "demo"


def _providers() -> dict[str, type]:
    # Imported here rather than at module scope: the demo provider imports
    # this file for its own types, and a top-level import would close the loop.
    from .demo import DemoSearchProvider

    return {DemoSearchProvider.name: DemoSearchProvider}


def get_provider(name: str | None = None) -> SearchProvider:
    """The configured provider, falling back to the demo one by name.

    An unknown name is logged and ignored rather than raised: the Store going
    quiet because somebody typed the variable wrong is worse than the Store
    saying, on screen, that these results are not real.
    """
    wanted = (name or os.environ.get(_ENV, "") or DEFAULT_PROVIDER).strip()
    known = _providers()
    if wanted not in known:
        if wanted != DEFAULT_PROVIDER:
            log.warning("store: no search provider named %r — using %r",
                        wanted, DEFAULT_PROVIDER)
        wanted = DEFAULT_PROVIDER
    return known[wanted]()


def provider_info() -> dict:
    """What the Games tab says about where its rows came from."""
    p = get_provider()
    return {
        "name": p.name,
        "label": p.label,
        "live": p.live,
        "systemFirst": True,
    }


# ── the consoles a search may be scoped to ─────────────────────────────────


def _installed_ids() -> set[str]:
    """Every emulator whose tile is on the grid.

    `config/systems.json` is written by `gamecore-emu` when a pack is
    installed, and it is the same file the Consoles tab's `installed` flag is
    derived from.

    Not `routers.catalog._live_ids`, which answers a different question — it
    merges `apps.json` too, because it reports on both kinds of pack. A
    service importing a router would also be backwards. The read is six lines
    and several modules here already do their own; what must not be duplicated
    is a *decision*, and this is a file.
    """
    try:
        rows = json.loads((config_dir() / "systems.json").read_text())
    except (OSError, ValueError) as e:
        # A box whose systems.json cannot be read has bigger problems than the
        # Store, and "nothing is searchable" is the honest answer here rather
        # than a 500 on a screen the player opened to browse.
        log.warning("store: config/systems.json unreadable — %s", e)
        return set()
    if not isinstance(rows, list):
        return set()
    return {r["id"] for r in rows if isinstance(r, dict) and "id" in r}


def _from_pack(pack) -> SearchSystem:
    roms = pack.data.get("roms") or {}
    exts = roms.get("extensions") or []
    return SearchSystem(
        id=pack.id,
        label=pack.data.get("label", pack.id),
        platform=pack.data.get("platform", ""),
        roms_dir=roms.get("dir", f"emu/{pack.id}"),
        extensions=tuple(e for e in exts if isinstance(e, str)),
        scan_dirs=bool(roms.get("scanDirs")),
    )


def searchable_systems() -> list[SearchSystem]:
    """The installed emulators, A–Z by label.

    Ordered by label and not by id for the same reason the Consoles tab is:
    it is a list a cursor walks, and "Nintendo 64" is what the card says.
    """
    live = _installed_ids()
    rows = [_from_pack(p) for p in load_catalog().values()
            if p.kind == "emulator" and p.id in live]
    return sorted(rows, key=lambda s: s.label.lower())


def system_for(system_id: str) -> SearchSystem | None:
    """One searchable console by id, or `None` when it is not one.

    `None` covers three different things on purpose — no such pack, a pack
    that is not an emulator, and an emulator that is not installed — because
    the caller's answer is the same for all three and telling them apart from
    an unauthenticated request only says what this box has on it.
    """
    return next((s for s in searchable_systems() if s.id == system_id), None)
