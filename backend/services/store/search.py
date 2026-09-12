"""What a search provider is, and which one this box uses.

Three things live here and nothing else: the console a search is scoped to
(`SearchSystem`), what a search comes back with (`SearchResult`), and the
interface a provider implements (`SearchProvider`). Two implementations sit
beside this file: `demo.py`, which invents its rows and says so, and
`prowlarr.py`, which queries an indexer aggregator the box owner runs
themselves — GameCore never installs, manages or removes it.

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
that is how the demo provider offers formats this console can actually hold,
and how the Prowlarr one filters what an indexer hands it.

── What a console has to carry for an indexer to be queried ───────────────
The question step 10 had to answer: is the pack enough to build an indexer
request from? Almost. Two things are needed and only one of them was here.

  · **Names the console goes by.** Derivable, and derived in the provider
    rather than stored: `platform` and `label` between them already spell every
    console twice — `N64`/`Nintendo 64`, `PS1`/`PlayStation`, `SNES`/`Super
    Nintendo`. They are *display* strings, so they need splitting: `/` joins
    two machines on four packs (`GameCube / Wii`, `Sega Mega Drive / Genesis`)
    and parentheses hold a second name on one (`Arcade (MAME)`). That is a
    deterministic split over shipped data, so nothing new is stored for it.
  · **Which of its extensions name it and it alone** — `unique_suffixes`, the
    field added for this. NOT derivable from a single pack: `.z64` is declared
    by `gopher64` and nobody else, while `.iso` is declared by nine packs, and
    a pack cannot see the other thirty. So a release named `… .iso` is not
    evidence of a PlayStation 1 game, and a provider handed only this console
    would have had to carry a hand-written list of which extensions are
    distinctive — a per-system table, which is exactly the thing matrix §5.2
    notes this design does not need anywhere else.

Both feed one rule, which is the rule the third bullet above demands: a result
is kept only when something about it names *this* console. No evidence is a
drop, not a guess.

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
from collections import Counter
from dataclasses import dataclass, field
from typing import Protocol

from ..catalog import load_catalog
from ..paths import config_dir

log = logging.getLogger(__name__)

#: Suffixes a provider must neither offer nor recognise. One entry: `*.cmd` is
#: declared by `catalog/mame/pack.json` and explained nowhere in this
#: repository, and matrix §6.4 is explicit that until somebody knows what it is
#: "the Store should neither produce nor rewrite one". It lives here rather
#: than in one provider because both of them need it and for the same reason —
#: the demo one must not invent a `.cmd` row, and the Prowlarr one must not
#: accept a release as an arcade romset *because* it is named one.
NEVER_OFFERED = ("cmd",)


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
    #: The bare suffixes **no other pack in the catalogue declares**, so a
    #: release named with one names this console and no other.
    #:
    #: Catalogue-wide and not box-wide on purpose: `.iso` is not evidence of a
    #: PlayStation 1 game on a box where `duckstation` happens to be the only
    #: console installed. That is a property of the format, not of the grid.
    #:
    #: This is the one thing the pack cannot answer on its own and the reason
    #: this field exists — see the module note below.
    unique_suffixes: tuple[str, ...] = ()

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
    #: The bare suffix (`"zip"`, `"chd"`); `"folder"` on a `scanDirs` console
    #: where the game is a directory and has no extension at all; or **empty
    #: when the source does not say**.
    #:
    #: Empty is not a defect to be filled in with a plausible guess. An indexer
    #: lists *releases*, and a release named "Zelda - Ocarina of Time (USA)"
    #: names no format at all — the bytes decide, and the bytes have not been
    #: fetched. Guessing here would put the guess in the one field matrix §5.1
    #: keys its class predicates on, which is the design bug the matrix opens
    #: by naming. The demo provider never emits it, because it invents the file
    #: and therefore does know.
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

    # Optional. A provider that needs credentials answers False until it has
    # them, and `get_provider()` then hands back the demo one instead of a
    # provider that can only fail. It is not in the Protocol body because the
    # demo provider genuinely has nothing to be configured about, and a method
    # it would have to implement to return True is a method that exists to
    # satisfy a type checker.
    #
    #     @classmethod
    #     def configured(cls) -> bool: ...


# ── which provider this box uses ───────────────────────────────────────────
#
# Two entries, and **configuration is the switch**. With no variable set, a box
# uses the first provider that says it is ready; the demo one always is, and
# says out loud that its rows are invented. Writing
# `config/store-prowlarr.json` is therefore the whole of "turn the real Store
# on", which matters because the alternative — an environment variable — lives
# in a systemd unit the owner would have to edit and an OTA could replace.
#
# `GAMECORE_STORE_SEARCH_PROVIDER` stays, and it now overrides in both
# directions: it names a provider, and naming `demo` on a configured box is how
# the real one is turned off again without deleting the credentials.

_ENV = "GAMECORE_STORE_SEARCH_PROVIDER"
DEFAULT_PROVIDER = "demo"


def _providers() -> dict[str, type]:
    # Imported here rather than at module scope: both providers import this
    # file for their own types, and a top-level import would close the loop.
    #
    # Insertion order is the autodetect order, so it is not incidental: the
    # demo provider is last, because it is what is left when nothing else is
    # configured rather than something a box would pick over a real indexer.
    from .demo import DemoSearchProvider
    from .prowlarr import ProwlarrSearchProvider

    return {ProwlarrSearchProvider.name: ProwlarrSearchProvider,
            DemoSearchProvider.name: DemoSearchProvider}


def _ready(cls: type) -> bool:
    """Whether a provider has what it needs to answer at all.

    A provider without a `configured()` classmethod is always ready. One that
    has it and answers False is not chosen — falling back to rows that are
    honestly labelled invented beats an indexer client with no URL, which can
    only turn every search into a 502.
    """
    ready = getattr(cls, "configured", None)
    if ready is None:
        return True
    try:
        return bool(ready())
    except Exception as e:                                    # noqa: BLE001
        # Reading a credential file must never be able to take the tab down.
        log.warning("store: %s could not decide whether it is configured — %s",
                    getattr(cls, "name", cls.__name__), e)
        return False


def get_provider(name: str | None = None) -> SearchProvider:
    """The provider this box uses, falling back to the demo one.

    An unknown name is logged and ignored rather than raised, and so is a named
    provider that turns out not to be configured: the Store going quiet because
    somebody typed the variable wrong, or because a credential file was
    deleted, is worse than the Store saying on screen that these results are
    not real.
    """
    known = _providers()
    wanted = (name or os.environ.get(_ENV, "")).strip()
    if not wanted:
        # No variable: the first provider that is ready. The demo one closes
        # the list, so an unconfigured box lands on it.
        return next(c for c in known.values() if _ready(c))()
    if wanted not in known:
        log.warning("store: no search provider named %r — using %r",
                    wanted, DEFAULT_PROVIDER)
        return known[DEFAULT_PROVIDER]()
    if not _ready(known[wanted]):
        log.warning("store: %r is selected but not configured — using %r",
                    wanted, DEFAULT_PROVIDER)
        return known[DEFAULT_PROVIDER]()
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


def _suffixes_of(pack) -> set[str]:
    exts = (pack.data.get("roms") or {}).get("extensions") or []
    return {e.lstrip("*.").lower() for e in exts
            if isinstance(e, str) and e.strip("*.")}


def _unique_suffixes() -> dict[str, frozenset[str]]:
    """Per pack, the suffixes no other emulator pack declares.

    Computed over the **whole catalogue** rather than over the installed
    consoles, and over one pass rather than from a table, which is the property
    that makes it survive a new pack: `catalog/*/pack.json` is the only input,
    and a pack that starts declaring `*.iso` stops `.iso` being evidence for
    everybody in the same commit that adds it.

    Measured on the 31 emulator packs as they stand: 24 have at least one, and
    nine suffixes are shared — `zip 7z iso bin cue ccd m3u chd pbp`. The seven
    packs with none (`atomiswave` `megacd` `naomi` `naomigd` `pcsx2` `rpcs3`
    `shadps4`) declare containers only, and `mame`'s single one is `cmd`, which
    `NEVER_OFFERED` removes. Those eight are recognisable by name and by
    nothing else — see the Prowlarr provider, which is where that matters.
    """
    per = {p.id: _suffixes_of(p) for p in load_catalog().values()
           if p.kind == "emulator"}
    counts: Counter[str] = Counter()
    for suffixes in per.values():
        counts.update(suffixes)
    return {pid: frozenset(x for x in suffixes
                           if counts[x] == 1 and x not in NEVER_OFFERED)
            for pid, suffixes in per.items()}


def _from_pack(pack, unique: frozenset[str] = frozenset()) -> SearchSystem:
    roms = pack.data.get("roms") or {}
    exts = roms.get("extensions") or []
    return SearchSystem(
        id=pack.id,
        label=pack.data.get("label", pack.id),
        platform=pack.data.get("platform", ""),
        roms_dir=roms.get("dir", f"emu/{pack.id}"),
        extensions=tuple(e for e in exts if isinstance(e, str)),
        scan_dirs=bool(roms.get("scanDirs")),
        # Sorted so that two runs hand a provider the same tuple: it ends up
        # in log lines and in test fixtures, and a frozenset's order is not a
        # promise.
        unique_suffixes=tuple(sorted(unique)),
    )


def searchable_systems() -> list[SearchSystem]:
    """The installed emulators, A–Z by label.

    Ordered by label and not by id for the same reason the Consoles tab is:
    it is a list a cursor walks, and "Nintendo 64" is what the card says.
    """
    live = _installed_ids()
    unique = _unique_suffixes()
    rows = [_from_pack(p, unique.get(p.id, frozenset()))
            for p in load_catalog().values()
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
