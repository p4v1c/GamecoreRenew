#!/usr/bin/env python3
"""Ask a real Prowlarr what the Store's console filter keeps, and what it steals.

**Run by hand, never in CI.** It needs a Prowlarr instance and an API key, so
it cannot be a gate: a check that is skipped on every machine that has neither
is a check nobody reads. `backend/tests/test_store_prowlarr.py` is the gate,
and it runs offline against recorded answers. This is the manual recipe test
that produced those answers in the first place.

**It reads and writes nothing.** Not `config/store-prowlarr.json` — the URL and
key come from the environment and are never persisted, so a laptop that runs
this never ends up configured as though it were the box. No file is created
anywhere, no service is started, no production path is touched. One HTTP GET
per query, to the address you name and nowhere else.

WHAT IT MEASURES

  1. **Over-catch.** `backend/services/store/prowlarr.py` keeps a release only
     when something about it names the console, and the first version of that
     rule matched a name whole-word and stopped: "PlayStation" is a whole word
     inside "PlayStation 3", so the PlayStation 1 console kept PlayStation 3,
     PlayStation 4 and PSP releases — 7 of 7 rows on "gran turismo", 15 of 43
     on "street fighter", measured here. Every row now claimed by more than
     one console is listed, because that is what that fault looks like from
     the outside: one release, two machines, at most one of which can run it.

  2. **Under-catch on the eight name-only consoles.** 23 of the 31 consoles
     have at least one exclusive file suffix; these eight have none and depend
     entirely on their name:

         atomiswave  mame  megacd  naomi  naomigd  pcsx2  rpcs3  shadps4

     A filter can be perfect on the 23 and throw away everything on the 8, and
     a single hand-made search would not tell those two situations apart.

  3. **Which band did the work.** The "by suffix" column was 0 on all 110 rows
     of the original measurement, on every console: those indexers name a
     release `Title - Platform` and attach no file extension at all. The band
     is kept — other sources do name files — but it means the name band is
     carrying the whole filter, which is why 1. matters as much as it does.

USAGE
    export PROWLARR_URL=http://127.0.0.1:9696
    export PROWLARR_API_KEY=...            # Settings -> General -> API Key
    .venv/bin/python scripts/prowlarr-filter-check.py "mario" "gran turismo"

Run it from the repository root. Pick queries that span the library: one
cartridge-era name, one PlayStation disc name, one arcade name. The queries
sent are the words you type and nothing else — that is the provider's own
decision (adding "Nintendo 64" would lose "Super Mario 64 (USA).z64"), so the
rows do not depend on the console and one request is classified against all of
the consoles this checkout has installed.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Run from the checkout; import its code rather than reimplementing the filter,
# because a reimplementation would measure itself instead of the product.
for candidate in (Path.cwd(), *Path.cwd().parents):
    if (candidate / "backend" / "services" / "store" / "prowlarr.py").is_file():
        sys.path.insert(0, str(candidate))
        break
else:
    sys.exit("run this from inside the GameCoreRenew checkout")

from backend.services.store import prowlarr as P               # noqa: E402
from backend.services.store.search import searchable_systems    # noqa: E402

#: The consoles whose name is the only evidence they can ever have — every
#: suffix they declare is declared by another pack too. Derived, not typed:
#: `search._unique_suffixes()` is the one pass over the catalogue that knows.
NAME_ONLY = ("atomiswave", "mame", "megacd", "naomi", "naomigd",
             "pcsx2", "rpcs3", "shadps4")

BOLD, DIM, RED, GRN, YLW, RST = (
    "\033[1m", "\033[2m", "\033[31m", "\033[32m", "\033[33m", "\033[0m")


def config() -> P.ProwlarrConfig:
    url = (os.environ.get("PROWLARR_URL") or "").strip()
    key = (os.environ.get("PROWLARR_API_KEY") or "").strip()
    if not url or not key:
        sys.exit("set PROWLARR_URL and PROWLARR_API_KEY — this script reads "
                 "neither the box's config file nor anything else on disk")
    # Straight through the provider's own loader logic for the URL so a pasted
    # key in the URL is dropped here exactly as it would be on a real box.
    cleaned = P._clean_url(url)
    if not cleaned:
        sys.exit(f"{url!r} is not a usable Prowlarr address (want http://host:9696)")
    return P.ProwlarrConfig(url=cleaned, api_key=key)


async def run(cfg: P.ProwlarrConfig, queries: list[str]) -> int:
    provider = P.ProwlarrSearchProvider()
    systems = searchable_systems()
    if not systems:
        sys.exit("no installed consoles in this checkout's systems.json — "
                 "the filter has nothing to be measured against")

    print(f"{BOLD}Prowlarr{RST} {P._where(cfg)}   "
          f"{len(systems)} consoles installed in this checkout\n")

    empty: list[tuple[str, str, int]] = []
    contested = 0
    for query in queries:
        try:
            rows = await provider._get(cfg, query)
        except P.ProwlarrError as e:
            print(f"{RED}✗{RST} {query!r}: {e}")
            continue
        print(f"{BOLD}{query!r}{RST} — Prowlarr returned {len(rows)} row(s)")
        if not rows:
            print(f"  {DIM}nothing to classify; try a query your indexers "
                  f"actually have{RST}\n")
            continue

        # Every row against every console, once, so the same pass answers both
        # questions: how much each console kept, and which rows two consoles
        # both claimed.
        claims: dict[int, list[str]] = {i: [] for i in range(len(rows))}
        for system in sorted(systems, key=lambda s: s.id):
            names = P._console_names(system)
            suffixes = P._suffix_pattern(system)
            kept, rejected = [], []
            for i, row in enumerate(rows):
                out = P._result_from(row, system, names, suffixes)
                if out is None:
                    title = row.get("title") or row.get("fileName") or "?"
                    rejected.append(str(title))
                else:
                    kept.append(out)
                    claims[i].append(system.id)
            if not kept and system.id not in NAME_ONLY:
                continue                       # silence is the normal answer
            flag = " ←name-only" if system.id in NAME_ONLY else ""
            colour = GRN if kept else (RED if system.id in NAME_ONLY else YLW)
            by_suffix = sum(1 for ev, _ in kept if ev > 1)
            print(f"  {colour}{len(kept):3d}{RST}/{len(rows):<3d} "
                  f"{system.id:<13}{DIM}{by_suffix} by suffix, "
                  f"{len(kept) - by_suffix} by name{RST}{flag}")
            if system.id in NAME_ONLY and not kept and rejected:
                empty.append((query, system.id, len(rows)))
                for title in rejected[:3]:
                    print(f"      {DIM}rejected: {title[:88]}{RST}")

        # One release cannot run on two machines. Two consoles claiming it is
        # the over-catch this script was written to find, and the shape the
        # PlayStation family produced on every `gran turismo` row.
        shared = [(rows[i], ids) for i, ids in claims.items() if len(ids) > 1]
        contested += len(shared)
        if shared:
            print(f"  {YLW}{len(shared)} row(s) claimed by more than one "
                  f"console:{RST}")
            for row, ids in shared[:10]:
                title = str(row.get("title") or row.get("fileName") or "?")
                print(f"      {title[:72]:<72} {DIM}{', '.join(ids)}{RST}")
        print()

    if empty:
        print(f"{YLW}The name-only consoles kept nothing for:{RST}")
        for query, sid, total in empty:
            print(f"  {sid:<13} {query!r} ({total} rows offered)")
        print(f"\n{DIM}For these consoles the title is the only evidence there "
              f"is, so if real releases are being dropped it is the name "
              f"matching that needs widening — not the suffix rule.{RST}")
    else:
        print(f"{GRN}No name-only console was left empty by a query that had "
              f"rows.{RST}")

    if contested:
        print(f"{YLW}{contested} row(s) were claimed by two consoles or "
              f"more.{RST} {DIM}Each one is a release at most one of them can "
              f"run. Check whether the losing console's name is a part of the "
              f"winner's — that is the fault `_ConsoleNames` exists to "
              f"prevent, and a new pack can reintroduce it.{RST}")
    else:
        print(f"{GRN}No row was claimed by two consoles.{RST}")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        sys.exit('give at least one query, e.g. "mario" "gran turismo"')
    raise SystemExit(asyncio.run(run(config(), args)))
