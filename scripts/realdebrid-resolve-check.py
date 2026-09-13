#!/usr/bin/env python3
"""Resolve one real source end to end, and print every step of it.

**Run by hand, never in CI.** It needs a real Prowlarr, a real Real-Debrid
account and the API credentials of both, so it cannot be a gate: a check that
is skipped on every machine that has neither is a check nobody reads.
`backend/tests/test_store_realdebrid.py` and
`backend/tests/test_store_resolve.py` are the gates, and they run offline
against recorded answers. This is the manual recipe that says whether those
recorded answers still describe the world.

**It reads and writes nothing.** Not `config/store-prowlarr.json`, not
`config/store-realdebrid.json` — every credential comes from the environment
and none is persisted, so a laptop that runs this never ends up configured as
though it were the box. No file is created anywhere, no service is started, no
production path is touched.

**It downloads nothing.** Acquiring resolves: the last thing it prints is that
a direct URL exists and how big Real-Debrid says it is. It never fetches it.
It also never *deletes* anything from the account — a torrent this leaves
caching is work the account has already begun, and throwing that away would
make the next attempt slower rather than faster.

WHAT IT MEASURES

  1. **That `(indexerId, guid)` really is not enough.** It is not, and the
     evidence is static: `Prowlarr.Api.V1.dll` 2.5.2.5491 holds
     `SearchController.GrabRelease`, a `_remoteReleaseCache` over a cache named
     `remoteReleases`, and the literal *"Couldn't find requested release in
     cache, cache timeout probably expired."* — so the pair is a key into an
     expiring cache, and a successful grab hands the release to a **download
     client**, which this box does not have. `backend/services/store/resolve.py`
     records the whole finding. What this script measures is the consequence:
     how many of your indexers' rows actually publish the info hash that
     replaced the pair, because a row without one cannot be queued.

  2. **That a hash your indexers publish is one Real-Debrid accepts.** These
     are two different services with no relationship, and "the row had a hash"
     does not mean "the content can be fetched". Cached, still fetching, dead
     and refused are four different outcomes and each prints as itself.

  3. **That nothing leaks on the way.** Every line printed is passed through
     the same redaction the product uses, and the direct URL is never printed
     at all — it is minted against your account and anyone holding it spends
     your bandwidth.

USAGE
    export PROWLARR_URL=http://127.0.0.1:9696
    export PROWLARR_API_KEY=...            # Settings -> General -> API Key
    export REALDEBRID_API_KEY=...          # My Account -> API token
    .venv/bin/python scripts/realdebrid-resolve-check.py "mario kart"

Run it from the repository root. Give it a **query**, and it resolves the first
row that carries a hash; or give it a `prowlarr://<indexerId>/<guid>#btih:<hash>`
source straight out of a job row or a `/api/store/search` answer, and it
resolves exactly that one.

Without `REALDEBRID_API_KEY` it still runs and stops after the Prowlarr half,
which is the useful half of 1. above and needs no paid account.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Run from the checkout; import its code rather than reimplementing any of it,
# because a reimplementation would measure itself instead of the product.
for candidate in (Path.cwd(), *Path.cwd().parents):
    if (candidate / "backend" / "services" / "store" / "resolve.py").is_file():
        sys.path.insert(0, str(candidate))
        break
else:
    sys.exit("run this from inside the GameCoreRenew checkout")

from backend.services.store import jobs, resolve                    # noqa: E402
from backend.services.store import prowlarr as P                    # noqa: E402
from backend.services.store import realdebrid as RD                 # noqa: E402

BOLD, DIM, RED, GRN, YLW, RST = (
    "\033[1m", "\033[2m", "\033[31m", "\033[32m", "\033[33m", "\033[0m")


def prowlarr_config() -> P.ProwlarrConfig:
    url = (os.environ.get("PROWLARR_URL") or "").strip()
    key = (os.environ.get("PROWLARR_API_KEY") or "").strip()
    if not url or not key:
        sys.exit("set PROWLARR_URL and PROWLARR_API_KEY — this script reads "
                 "neither the box's config files nor anything else on disk")
    cleaned = P._clean_url(url)
    if not cleaned:
        sys.exit(f"{url!r} is not a usable Prowlarr address "
                 f"(want http://host:9696)")
    return P.ProwlarrConfig(url=cleaned, api_key=key)


def realdebrid_config() -> RD.RealDebridConfig | None:
    """`None` when no token is set, which is a supported way to run this."""
    key = (os.environ.get("REALDEBRID_API_KEY") or "").strip()
    if not key:
        return None
    return RD.RealDebridConfig(api_key=key, wait=float(
        os.environ.get("REALDEBRID_WAIT") or RD.DEFAULT_WAIT))


async def sources_for(cfg: P.ProwlarrConfig, query: str) -> list[tuple[str, str]]:
    """`(title, source)` for every row Prowlarr answers — hashes and all.

    Straight through the provider's own `_get`, so what is counted is what the
    product would see, including the redaction. The console filter is
    deliberately *not* applied: this script is about resolution, and a row's
    console has nothing to do with whether it can be fetched.
    """
    rows = await P.ProwlarrSearchProvider()._get(cfg, query)
    print(f"{BOLD}{query!r}{RST} — Prowlarr returned {len(rows)} row(s)\n")
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or row.get("fileName") or "?")
        guid = row.get("guid")
        guid = guid if isinstance(guid, str) and guid.strip() else title
        indexer = row.get("indexerId")
        indexer = indexer if isinstance(indexer, int) else 0
        source = P._redact(resolve.stamp(
            f"prowlarr://{indexer}/{guid.strip()}", resolve.info_hash_of(row)))
        out.append((P._redact(title), source))
    return out


def report_hashes(rows: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Finding 1: how many of these rows can be queued at all."""
    usable, bare = [], []
    for title, source in rows:
        (usable if "#btih:" in source else bare).append((title, source))
    total = len(rows) or 1
    colour = GRN if len(usable) else RED
    print(f"  {colour}{len(usable):3d}{RST}/{len(rows):<3d} rows carry an info "
          f"hash {DIM}({100 * len(usable) // total}%){RST}")
    for title, _ in bare[:5]:
        print(f"      {RED}no hash{RST} {DIM}{title[:72]}{RST}")
    if bare:
        print(f"  {DIM}A row with no hash cannot be resolved: (indexerId, guid)"
              f" is a key into a Prowlarr cache that expires, not a locator."
              f" Those rows queue and then fail saying so.{RST}")
    print()
    return usable


async def resolve_one(cfg: RD.RealDebridConfig, title: str,
                      source: str) -> int:
    """Finding 2 and 3: one source, all the way to a direct URL."""
    print(f"{BOLD}resolving{RST} {title[:72]}")
    print(f"  {DIM}source   {source}{RST}")
    try:
        found = resolve.resolve(source)
    except resolve.UnresolvableSource as e:
        print(f"  {RED}✗ {e}{RST}\n")
        return 1
    print(f"  {DIM}indexer  {found.indexer_id}{RST}")
    print(f"  {DIM}magnet   {found.magnet}{RST}   "
          f"{DIM}(hash only — no trackers, so no passkey){RST}")

    # The job the box would have written down. Built here rather than read from
    # a database: this script touches no database, and `acquire` needs only the
    # source and the filename.
    job = jobs.Job(
        id="0" * 32, system_id="?", roms_dir="", title=title,
        filename=title, format="", size=0, provider="prowlarr",
        source=source, state="running", reason="", queued_at="",
        started_at="", ended_at="")

    try:
        target = await _acquire_with(cfg, job)
    except (RD.RealDebridError, resolve.UnresolvableSource) as e:
        # Exactly the sentence a player would have read on the job row.
        print(f"  {RED}✗ Real-Debrid: {e}{RST}\n")
        return 1

    # `redacted()` and never the URL: it is minted against your account.
    print(f"  {GRN}✓ resolved{RST} {target.redacted()}")
    print(f"  {DIM}a direct https URL exists and was NOT fetched — "
          f"downloading is the materializer's, and this box has none{RST}\n")
    return 0


async def _acquire_with(cfg: RD.RealDebridConfig, job: jobs.Job):
    """`RealDebridAcquisition.acquire`, against a config from the environment.

    The provider reads `config/store-realdebrid.json` itself, and this script
    must not create one — so `load_config` is answered from the environment for
    the duration of the call and put back afterwards. Nothing on disk is read
    or written either way.
    """
    original = RD.load_config
    RD.load_config = lambda: cfg                   # type: ignore[assignment]
    try:
        return await RD.RealDebridAcquisition().acquire(job)
    finally:
        RD.load_config = original                  # type: ignore[assignment]


async def run(query: str) -> int:
    rd = realdebrid_config()
    if rd is None:
        print(f"{YLW}REALDEBRID_API_KEY is not set{RST} {DIM}— the Prowlarr "
              f"half runs and nothing is resolved. That half is the one that "
              f"needs no paid account.{RST}\n")

    if query.startswith(f"{resolve.SCHEME}://"):
        rows = [(query, query)]
        print(f"{BOLD}one source given{RST}, taken as it is\n")
    else:
        cfg = prowlarr_config()
        print(f"{BOLD}Prowlarr{RST} {P._where(cfg)}\n")
        try:
            rows = await sources_for(cfg, query)
        except P.ProwlarrError as e:
            print(f"{RED}✗{RST} {query!r}: {e}")
            return 1
        rows = report_hashes(rows)
        if not rows:
            print(f"{RED}No row carried an info hash, so there is nothing to "
                  f"resolve.{RST} {DIM}Try a query your indexers actually have, "
                  f"or an indexer that publishes torrents.{RST}")
            return 1

    if rd is None:
        return 0
    print(f"{BOLD}Real-Debrid{RST} {RD._where(rd)}   "
          f"{DIM}waiting up to {rd.wait:g}s for content{RST}\n")
    return await resolve_one(rd, *rows[0])


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) != 1:
        sys.exit('give one query, e.g. "mario kart" — or one '
                 'prowlarr://<indexerId>/<guid>#btih:<hash> source')
    raise SystemExit(asyncio.run(run(args[0])))
