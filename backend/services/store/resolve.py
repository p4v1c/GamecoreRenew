"""Turning a job's opaque `source` back into something that can be fetched.

`SearchResult.source` is minted by the search provider and is opaque to
everything else: `prowlarr://<indexerId>/<guid>`. It deliberately carries no
URL. Prowlarr's own `downloadUrl` is shaped
`http://…/<indexerId>/download?apikey=<this box's key>&link=…&file=…`, and
`source` travels to the browser — so a locator that was a URL would be the
box's Prowlarr key in the page source of a television nobody logs out of.

That left one thing unverified, and this is the step where it had to be
settled: **is the pair `(indexerId, guid)` enough to find the release again?**

── It is not, and the evidence is in Prowlarr's own binary ────────────────
Measured against `Prowlarr.Api.V1.dll` from Prowlarr **2.5.2.5491** — the
build the box owner actually runs — rather than against a wiki page.

Prowlarr has exactly one endpoint that takes that pair: `POST /api/v1/search`,
the *grab*. The assembly holds `Prowlarr.Api.V1.Search.SearchController`, its
`GrabRelease` method, a `GetCacheKey` helper, a field `_remoteReleaseCache` of
type `ICached<T>`, a cache named `remoteReleases`, and these two literals::

    "Couldn't find requested release in cache, cache timeout probably expired."
    "Couldn't find requested release in cache, try searching again"

So the pair is not a locator at all. It is a **key into an in-memory cache
that expires**, and Prowlarr's own remedy for a miss is *search again*. A queue
row outlives a reboot by design — that is the whole reason `jobs.py` is a table
and not a variable — and a cache entry does not outlive a restart of Prowlarr,
never mind a night with the television off.

Even on a hit, a grab is not a link. The same assembly holds::

    "Failed to send grabbed release to download client"

A successful grab hands the release to a **download client**: a torrent daemon,
on some machine, with a port. That is precisely what this design exists to
avoid, so the one endpoint that accepts `(indexerId, guid)` is unusable twice
over.

The other candidate is the proxy that `downloadUrl` points at.
`Prowlarr.Core.dll` builds it in `ConvertToProxyLink`, out of the fragments
`"/download?apikey="`, `"&link="` and `"&file="`. It is keyed on **`link`** —
the indexer's own URL for the release — and a `guid` is not a `link`. It also
carries the key in the query string, which is the leak `prowlarr._redact`
exists to stop.

── What `SearchResult` has to carry, then ─────────────────────────────────
One more thing, and it must not be a credentialed URL — that constraint is why
the field was written the way it was, and it does not move.

**The BitTorrent info hash.** Prowlarr answers it as `infoHash` on a release,
and it is in the `magnetUrl` when it answers one of those instead. It is the
right answer on every count that matters here:

  · it carries **no credential** — 20 bytes identifying content, not a URL, not
    a session, not a passkey. A magnet's *tracker* parameters can carry a
    private tracker's passkey; the hash cannot, and only the hash is kept;
  · it never **expires**. It is what the bytes hash to, so it is as durable as
    the queue row it sits on, which is the property `(indexerId, guid)` turned
    out not to have;
  · it is exactly what a debrid service consumes. `magnet:?xt=urn:btih:<hash>`
    is a complete request, so resolution needs no second Prowlarr round trip,
    no remembered query, and no guess about which release a re-search meant.

It is carried **inside `source`**, as a `#btih:<40 hex>` suffix, rather than as
a new field. `source` is already documented as opaque to everything outside the
provider that minted it, so a suffix is what that field is for; and this way the
whole path from `/search` through the browser, `POST /jobs`, the `store_jobs`
row and the worker carries it with no schema change, no new column, and no new
thing for `QueueRequest` to be trusted about. The parse is anchored to the end
of the string and to 40 hex characters, so a `guid` that itself contains a `#`
cannot be mistaken for one.

── When there is no hash ──────────────────────────────────────────────────
Some rows have none: usenet releases have no info hash at all, and a torznab
indexer that publishes neither `infoHash` nor `magnetUrl` leaves nothing to
lift. Those rows keep the bare `prowlarr://<indexerId>/<guid>` and this module
refuses them, by name, with a sentence a player can read. That is the honest
answer rather than a re-search: searching again for the release *title* and
taking whatever comes back is a guess about which row was meant, and a wrong
guess downloads the wrong game silently — the exact class of fault the console
filter in `prowlarr.py` was rewritten to prevent.
"""
from __future__ import annotations

import base64
import binascii
import logging
import re

from dataclasses import dataclass

log = logging.getLogger(__name__)

#: The scheme `prowlarr.py` mints and this module reads. One constant, because
#: a second spelling of it is a source that resolves on one side and not the
#: other.
SCHEME = "prowlarr"

#: The suffix that carries the info hash. Anchored to the end and to exactly
#: 40 lowercase hex characters — see the module docstring for why the anchor
#: is the whole of the parse's safety.
_BTIH_SUFFIX = re.compile(r"#btih:([0-9a-f]{40})$")

#: `xt=urn:btih:…` inside a magnet URI, in either of the two spellings the
#: BitTorrent conventions allow: 40 hex, or 32 characters of base32.
_MAGNET_BTIH = re.compile(r"(?i)xt=urn:btih:([0-9a-fA-F]{40}|[a-zA-Z2-7]{32})")


class UnresolvableSource(ValueError):
    """This source cannot be turned into anything fetchable.

    The message is shown to the player as the job's reason, so it is built
    from safe parts only: no URL, no key, no query string. It says what is
    missing and, where there is one, what the player can do instead.
    """


@dataclass(frozen=True)
class ResolvedSource:
    """What a `source` turned out to name.

    `info_hash` is the load-bearing field and the only one an acquisition
    provider needs. `indexer_id` and `guid` are kept because they are the
    audit trail — which of the owner's indexers offered this, and under which
    id — and because a log line that can name them is worth more than one that
    cannot. Neither is dereferenced.
    """

    #: 40 lowercase hex characters. Normalised here so that everything
    #: downstream can compare two of them with `==`.
    info_hash: str
    indexer_id: int
    guid: str

    @property
    def magnet(self) -> str:
        """The smallest complete request a debrid service will accept.

        Deliberately trackerless. A magnet Prowlarr answers can carry a private
        tracker's passkey in its `tr=` parameters, and that is a credential
        belonging to the owner's account — it is dropped on the way in (see
        `info_hash_of`) and never rebuilt here. The hash alone is what the
        content *is*; where to get it is the debrid service's problem and it
        has better answers than this box does.
        """
        return f"magnet:?xt=urn:btih:{self.info_hash}"


# ── minting one, and reading it back ───────────────────────────────────────


def stamp(source: str, info_hash: str) -> str:
    """Put the hash on a source. The mint side of the parse below.

    Lives here rather than in `prowlarr.py` so that the two halves of the
    encoding cannot drift: a provider that wrote `#hash=` and a resolver that
    read `#btih:` would be a Store where every job fails and every test that
    checks one side passes.

    An empty or malformed hash is not an error — it is a row the indexer
    published without one, which is normal. The source is returned unchanged
    and `resolve()` will refuse it by name later, at the point where there is
    a player to tell.
    """
    clean = _normalise(info_hash)
    return f"{source}#btih:{clean}" if clean else source


def resolve(source: str) -> ResolvedSource:
    """`prowlarr://<indexerId>/<guid>#btih:<hash>` → its parts.

    Raises `UnresolvableSource` for everything else, which is three different
    situations and three different sentences:

      · a source from another provider — the demo one mints `demo://…`, and
        its rows are invented, so there is nothing behind them to fetch;
      · a source with no hash on it — the indexer published none;
      · a source that is not the shape this module mints at all.
    """
    raw = (source or "").strip()
    prefix = f"{SCHEME}://"
    if not raw.startswith(prefix):
        scheme = raw.split("://", 1)[0] if "://" in raw else ""
        if scheme == "demo":
            # The demo provider's rows are invented and say so on screen. A
            # job made from one is a player trying to download a made-up game.
            raise UnresolvableSource(
                "these results are examples, not real games — this box has no "
                "search provider configured")
        raise UnresolvableSource(
            "this result was found by a provider this box can no longer resolve")

    body = raw[len(prefix):]
    match = _BTIH_SUFFIX.search(body)
    if match is None:
        raise UnresolvableSource(
            "the indexer listed this release without a torrent hash, so there "
            "is nothing this box can ask for")
    info_hash = match.group(1)
    body = body[:match.start()]

    # Split on the FIRST slash only: a guid is very often a URL and carries
    # slashes of its own, so `rsplit` or a `split()` without a bound would cut
    # it in the middle.
    indexer_part, _, guid = body.partition("/")
    try:
        indexer_id = int(indexer_part)
    except ValueError:
        raise UnresolvableSource(
            "this result's locator is not one this box wrote") from None
    if not guid.strip():
        raise UnresolvableSource(
            "this result's locator names no release") from None

    return ResolvedSource(info_hash=info_hash, indexer_id=indexer_id,
                          guid=guid.strip())


# ── lifting one out of an indexer's answer ─────────────────────────────────


def info_hash_of(row: object) -> str:
    """The info hash a Prowlarr release names, or `""`.

    Two places to look, in order of how much else comes with them:

      · `infoHash`, which is the hash and nothing else;
      · `magnetUrl`, from which **only** the `xt=urn:btih:` value is taken.
        Everything else in a magnet is dropped on purpose — the `tr=` tracker
        list on a private tracker's magnet carries the owner's passkey, and
        `source` travels to the browser.

    `downloadUrl` is never read. It is the credentialed proxy link, it is what
    `prowlarr._redact` exists for, and it holds no hash anyway.
    """
    if not isinstance(row, dict):
        return ""
    direct = row.get("infoHash") or row.get("infohash")
    if isinstance(direct, str):
        clean = _normalise(direct)
        if clean:
            return clean
    magnet = row.get("magnetUrl")
    if isinstance(magnet, str):
        found = _MAGNET_BTIH.search(magnet)
        if found:
            return _normalise(found.group(1))
    return ""


def _normalise(value: object) -> str:
    """40 lowercase hex, from either spelling — or `""` for anything else.

    Base32 is accepted because that is how a good many magnets spell the same
    20 bytes, and refusing it would drop rows for a difference of encoding.
    Anything that is neither is not a hash, and the honest answer to "is this a
    hash" is no rather than a value that will fail later somewhere less
    explicable.
    """
    text = value.strip() if isinstance(value, str) else ""
    if len(text) == 40 and all(c in "0123456789abcdefABCDEF" for c in text):
        return text.lower()
    if len(text) == 32:
        try:
            return base64.b32decode(text.upper()).hex()
        except (binascii.Error, ValueError):
            return ""
    return ""
