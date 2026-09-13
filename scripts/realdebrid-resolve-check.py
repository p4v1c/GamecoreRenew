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

  1. **How many of your rows can be acquired at all, and by which path.**
     `(indexerId, guid)` is not a locator: `Prowlarr.Api.V1.dll` 2.5.2.5491
     holds `SearchController.GrabRelease`, a `_remoteReleaseCache` over a cache
     named `remoteReleases`, and the literal *"Couldn't find requested release
     in cache, cache timeout probably expired."* — a key into an expiring
     cache, whose successful grab hands the release to a **download client**
     this box does not have. So a row has to carry something durable of its
     own, and there are two:

       · **by hash** — `infoHash`, or the `xt=urn:btih:` of a `magnetUrl`;
       · **by .torrent** — Prowlarr's protected `link` token, for a row that
         published a file instead. It is AES ciphertext (`ConvertToProxyLink`
         → `IProtectionService`; `Aes`, `CreateEncryptor`, `Base64UrlEncode`
         in `Prowlarr.Core.dll`), so it carries no passkey even when the
         indexer's own URL would have.

     Every row prints as `hash`, `torrent` or `none`, with the rate for each.
     That is the number this whole step exists to move: on the box it was
     written for it was **0/8 by hash (0 %)** for `mario kart`, one indexer,
     every row a `.torrent`.

  2. **That what your indexers publish is what Real-Debrid accepts.** These
     are two different services with no relationship, and "the row had a
     locator" does not mean "the content can be fetched". Cached, still
     fetching, dead and refused are four different outcomes and each prints as
     itself. A `.torrent` row exercises the whole second path: fetched from
     Prowlarr with the key in a header, hashed here, and `PUT` to
     `/torrents/addTorrent` as a raw body.

  3. **That nothing leaks on the way.** Every line printed is passed through
     the same redaction the product uses; the direct URL is never printed at
     all — it is minted against your account and anyone holding it spends your
     bandwidth — and neither is the download token, which is a bearer reference
     to a file that may carry your tracker passkey.

USAGE
    export PROWLARR_URL=http://127.0.0.1:9696
    export PROWLARR_API_KEY=...            # Settings -> General -> API Key
    export REALDEBRID_API_KEY=...          # My Account -> API token
    .venv/bin/python scripts/realdebrid-resolve-check.py "mario kart"

Run it from the repository root. Give it a **query**, and it resolves the first
row that carries a locator of either kind; or give it a
`prowlarr://<indexerId>/<guid>#btih:<hash>` or `…#tor:<token>` source straight
out of a job row or a `/api/store/search` answer, and it resolves exactly that
one.

`PROWLARR_URL` and `PROWLARR_API_KEY` are needed for the `.torrent` path even
when a source is given on the command line: that path fetches the file from
your Prowlarr, which is where the credential for your indexer lives.

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
    """`(title, source)` for every row Prowlarr answers — every kind of row.

    Straight through the provider's own `_get` and its own `stamp`, so what is
    counted is what the product would see, including the redaction and
    including the rule that a hash wins over a `.torrent` token. The console
    filter is deliberately *not* applied: this script is about resolution, and
    a row's console has nothing to do with whether it can be fetched.
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
            f"prowlarr://{indexer}/{guid.strip()}",
            resolve.info_hash_of(row), resolve.torrent_token_of(row)))
        out.append((P._redact(title), source))
    return out


#: How a row is counted, and how the count reads. `none` is the only one that
#: cannot be queued — and the whole point of the second path is that it used to
#: be the only kind this box's indexer ever produced.
_PATHS = (
    ("hash", "#btih:", GRN, "by hash        "),
    ("torrent", "#tor:", GRN, "by .torrent    "),
    ("none", "", RED, "not at all     "),
)


def path_of(source: str) -> str:
    """`hash`, `torrent` or `none` — read off the source, not guessed.

    Read from the same string the queue row would hold, so this measures the
    product rather than a parallel opinion about it.
    """
    for name, marker, _, _phrase in _PATHS:
        if marker and marker in source:
            return name
    return "none"


def report_paths(rows: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Finding 1: how many of these rows can be acquired, and by which path.

    Prints a line per path with its rate, then names the rows that have none.
    The rate is what to re-measure after a change: it was 0 % by hash and 0 %
    overall on the box this was written for, and every one of those rows was a
    `.torrent`.
    """
    by_path = {name: [] for name, _, _, _ in _PATHS}
    for title, source in rows:
        by_path[path_of(source)].append((title, source))

    total = len(rows) or 1
    for name, _, colour, phrase in _PATHS:
        found = by_path[name]
        shade = colour if found else DIM
        print(f"  {shade}{len(found):3d}{RST}/{len(rows):<3d} rows resolve "
              f"{shade}{phrase}{RST}{DIM}({100 * len(found) // total}%){RST}")

    bare = by_path["none"]
    for title, _ in bare[:5]:
        print(f"      {RED}neither{RST} {DIM}{title[:72]}{RST}")
    if bare:
        print(f"  {DIM}A row with neither cannot be resolved: (indexerId, guid)"
              f" is a key into a Prowlarr cache that expires, not a locator,"
              f" and there is no file to fetch either. Usenet rows look like"
              f" this. They queue and then fail saying so.{RST}")

    usable = by_path["hash"] + by_path["torrent"]
    if by_path["torrent"]:
        print(f"  {DIM}A `.torrent` row is resolved by fetching the file from"
              f" your Prowlarr with the key in a header, hashing it here, and"
              f" PUTting it to /torrents/addTorrent. Its locator is"
              f" Prowlarr's own protected token, which carries no"
              f" passkey.{RST}")
    print()
    return usable


async def resolve_one(cfg: RD.RealDebridConfig, title: str,
                      source: str, prowlarr: P.ProwlarrConfig | None = None) -> int:
    """Finding 2 and 3: one source, all the way to a direct URL."""
    print(f"{BOLD}resolving{RST} {title[:72]}")
    print(f"  {DIM}source   {source}{RST}")
    try:
        found = resolve.resolve(source)
    except resolve.UnresolvableSource as e:
        print(f"  {RED}✗ {e}{RST}\n")
        return 1
    print(f"  {DIM}indexer  {found.indexer_id}{RST}")
    if found.by_hash:
        print(f"  {DIM}path     hash → POST /torrents/addMagnet{RST}")
        print(f"  {DIM}magnet   {found.magnet}{RST}   "
              f"{DIM}(hash only — no trackers, so no passkey){RST}")
    else:
        # The token itself is never printed: it is a bearer reference to a file
        # that may carry your tracker passkey, and this output gets pasted into
        # issues.
        print(f"  {DIM}path     .torrent → GET Prowlarr "
              f"/api/v1/indexer/{found.indexer_id}/download "
              f"→ PUT /torrents/addTorrent{RST}")
        print(f"  {DIM}token    <{len(found.torrent_token)} characters, not "
              f"printed>{RST}")

    # The job the box would have written down. Built here rather than read from
    # a database: this script touches no database, and `acquire` needs only the
    # source and the filename.
    job = jobs.Job(
        id="0" * 32, system_id="?", roms_dir="", title=title,
        filename=title, format="", size=0, provider="prowlarr",
        source=source, state="running", reason="", queued_at="",
        started_at="", ended_at="")

    try:
        target = await _acquire_with(cfg, job, prowlarr)
    except (RD.RealDebridError, P.ProwlarrError,
            resolve.UnresolvableSource) as e:
        # Exactly the sentence a player would have read on the job row.
        print(f"  {RED}✗ Real-Debrid: {e}{RST}\n")
        return 1

    # `redacted()` and never the URL: it is minted against your account.
    print(f"  {GRN}✓ resolved{RST} {target.redacted()}")
    print(f"  {DIM}a direct https URL exists and was NOT fetched — "
          f"downloading is the materializer's, and this box has none{RST}\n")
    return 0


async def _acquire_with(cfg: RD.RealDebridConfig, job: jobs.Job,
                        prowlarr: P.ProwlarrConfig | None = None):
    """`RealDebridAcquisition.acquire`, against configs from the environment.

    The provider reads `config/store-realdebrid.json` itself, and the
    `.torrent` path reads `config/store-prowlarr.json` — and this script must
    not create either. So both `load_config`s are answered from the environment
    for the duration of the call and put back afterwards. Nothing on disk is
    read or written either way.
    """
    original_rd, original_p = RD.load_config, P.load_config
    RD.load_config = lambda: cfg                   # type: ignore[assignment]
    if prowlarr is not None:
        P.load_config = lambda: prowlarr           # type: ignore[assignment]
    try:
        return await RD.RealDebridAcquisition().acquire(job)
    finally:
        RD.load_config = original_rd               # type: ignore[assignment]
        P.load_config = original_p                 # type: ignore[assignment]


async def run(query: str) -> int:
    rd = realdebrid_config()
    if rd is None:
        print(f"{YLW}REALDEBRID_API_KEY is not set{RST} {DIM}— the Prowlarr "
              f"half runs and nothing is resolved. That half is the one that "
              f"needs no paid account.{RST}\n")

    if query.startswith(f"{resolve.SCHEME}://"):
        rows = [(query, query)]
        print(f"{BOLD}one source given{RST}, taken as it is "
              f"{DIM}({path_of(query)}){RST}\n")
        # Needed only when that source is a `.torrent` one: the file is fetched
        # from Prowlarr, which is where the indexer credential lives. A
        # `#btih:` source still needs nothing but a Real-Debrid token, which is
        # how this script has always been runnable with one credential.
        cfg = prowlarr_config() if path_of(query) == "torrent" else None
    else:
        cfg = prowlarr_config()
        print(f"{BOLD}Prowlarr{RST} {P._where(cfg)}\n")
        try:
            rows = await sources_for(cfg, query)
        except P.ProwlarrError as e:
            print(f"{RED}✗{RST} {query!r}: {e}")
            return 1
        rows = report_paths(rows)
        if not rows:
            print(f"{RED}No row carried a hash or a torrent file, so there is "
                  f"nothing to resolve.{RST} {DIM}Try a query your indexers "
                  f"actually have, or an indexer that publishes torrents "
                  f"rather than usenet.{RST}")
            return 1

    if rd is None:
        return 0
    print(f"{BOLD}Real-Debrid{RST} {RD._where(rd)}   "
          f"{DIM}waiting up to {rd.wait:g}s for content{RST}\n")
    return await resolve_one(rd, *rows[0], prowlarr=cfg)


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) != 1:
        sys.exit('give one query, e.g. "mario kart" — or one '
                 'prowlarr://<indexerId>/<guid>#btih:<hash> or …#tor:<token> '
                 'source')
    raise SystemExit(asyncio.run(run(args[0])))
