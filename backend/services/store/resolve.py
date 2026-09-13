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

── When there is no hash, there is usually a file ─────────────────────────
Some rows publish none, and on the box this was written for that is **all** of
them. Measured against its one configured indexer::

    'mario kart' — Prowlarr returned 8 row(s)
        0/8   rows carry an info hash (0%)

`protocol=torrent`, no `infoHash`, no `magnetUrl`, and a `fileName` ending
`.torrent`. The payload is a **file**, behind Prowlarr's own credentialed proxy
link. Refusing those rows is correct and it is also the whole library, so this
module grew a second locator beside the hash rather than a second excuse.

**The rule that chooses is: a hash wins.** When a row publishes one, nothing
else is looked at and the path below is the one that was already here — tested,
cheaper, and needing no second service. The `.torrent` locator is minted only
for a row that has no hash, so a mixed set of indexers keeps every row it had.

── What a `.torrent` row carries instead, and why it is safe ──────────────
Prowlarr's `downloadUrl` is
`http://…/<indexerId>/download?apikey=<this box's key>&link=<token>&file=<name>`.
Exactly **one** parameter of it is read — `link` — and never the URL, never
`apikey`, never `file`. It rides in `source` as a `#tor:<token>` suffix, in the
same place and under the same anchor as `#btih:`.

The obvious objection is the right one to start from: *on a private tracker the
indexer's own download URL carries the owner's passkey, so storing the link
would put a credential in the database and in an API answer.* That objection is
true of the indexer's URL. It is **not** true of `link`, and the difference was
measured in Prowlarr's own binaries rather than assumed:

  · `Prowlarr.Core.dll` builds the proxy link in `ConvertToProxyLink` out of
    the fragments `"/download?apikey="`, `"&link="` and `"&file="`, and reads
    it back in `ConvertToNormalLink`;
  · both go through `IProtectionService` (`_protectionService`, `Protect`,
    `UnProtect`), and the assembly holds `Aes`, `CreateEncryptor`,
    `CreateDecryptor`, `ICryptoTransform`, `CryptoStream` and `SHA256`
    alongside `Base64UrlEncode`/`Base64UrlDecode`.

So `link` is not base64 of the indexer's URL. It is **AES ciphertext,
base64url-encoded**, keyed on `DownloadProtectionKey` — a `config.xml` element
that exists as a literal in the same assembly and is read through a getter with
no setter, i.e. generated once and persisted. A passkey inside it is unreadable
to this box, to the browser, to the database and to anyone reading either; the
only thing on earth that can open it is the owner's own Prowlarr, and reaching
that needs the API key, which never leaves the backend.

That is a claim this module **checks** rather than trusts. `torrent_token_of`
refuses any `link` that base64url-decodes to something containing `://`: a
Prowlarr that handed out plaintext links — an older build, a fork, a proxy in
front — would be handing out the passkey, and the honest answer to that is to
carry no locator at all and refuse the row by name. The private-tracker case is
therefore not a hope, it is a gate.

── And why it is durable, which is the whole question ─────────────────────
`(indexerId, guid)` failed on durability, so the replacement has to be held to
the same test. The token passes it for a reason that is structural rather than
lucky: `remoteReleases` is an `ICached<T>` — memory, cleared by a restart —
while `DownloadProtectionKey` is written to `config.xml`. A queue row and the
key that opens its token both survive the night.

Not for ever, and the failure is visible rather than silent: an owner who
reinstalls Prowlarr, or clears that element, gets a new key, and the endpoint
then answers `"Invalid Prowlarr link"` / `"Failed to normalize provided link"`
(both literals in `Prowlarr.Api.V1.dll`). `prowlarr.fetch_torrent` maps that to
a sentence telling the player to search for the game again, which is true and
is the only correct remedy.

── Why the file is fetched late rather than at search time ────────────────
The tempting alternative is to fetch every row's `.torrent` while the search is
being answered, hash it, and store only the hash — no new locator, nothing new
in the browser, nothing new in the database. It was not taken, and the reason
is in the same assembly::

    "User configurable Indexer Grab Limit of {0} in last {1} hour(s) reached."

Fetching a `.torrent` is a **grab** as far as the indexer is concerned. A search
that grabbed all 8 rows to answer a question about 8 rows would spend the
owner's hourly budget on 7 releases nobody asked for, on every search, and
would put a round trip per row in front of a player holding a gamepad. Fetching
at acquisition spends exactly one grab, for the one game that was actually
queued.

── What is still refused ──────────────────────────────────────────────────
A row with neither: a usenet release has no info hash *and* no torrent, and a
torznab indexer can answer a row with no usable `downloadUrl`. Those keep the
bare `prowlarr://<indexerId>/<guid>` and are refused here, by name, with a
sentence a player can read. That is still the honest answer rather than a
re-search — searching again for the release *title* and taking whatever comes
back is a guess about which row was meant, and a wrong guess downloads the
wrong game silently, the exact class of fault the console filter in
`prowlarr.py` was rewritten to prevent.
"""
from __future__ import annotations

import base64
import binascii
import logging
import re

from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

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

#: The longest download token this box will carry. Sized from the arithmetic
#: rather than guessed, because a cap set too low would drop legitimate rows
#: and put some indexer straight back at 0 %: the token is base64url of
#: AES-CBC, so it runs about 4/3 × (the indexer URL rounded up to 16, plus 16
#: for the IV) — roughly 300 characters for a 200-character URL and 700 for a
#: 500-character one. 1024 clears the longest URL anybody plausibly serves and
#: still keeps `source`, which is a database column and a browser string, near
#: a kilobyte rather than unbounded.
_MAX_TOKEN = 1024

#: The suffix that carries a Prowlarr download token, and the same alphabet for
#: the mint side. Anchored the way `#btih:` is, and restricted to base64url —
#: which is what `Base64UrlEncode` produces, and which contains no `#`, no `/`
#: and no `?`, so it cannot be confused with any part of the locator it is
#: appended to.
_TOR_SUFFIX = re.compile(rf"#tor:([A-Za-z0-9_-]{{8,{_MAX_TOKEN}}})$")
_TOKEN_OK = re.compile(rf"^[A-Za-z0-9_-]{{8,{_MAX_TOKEN}}}$")

#: Where `torrent_token_of` looks, and the only parameter of it that is read.
#: Named rather than inlined because "which part of `downloadUrl` may be
#: touched" is the single most important fact about this module's second half.
_LINK_PARAM = "link"


class UnresolvableSource(ValueError):
    """This source cannot be turned into anything fetchable.

    The message is shown to the player as the job's reason, so it is built
    from safe parts only: no URL, no key, no query string. It says what is
    missing and, where there is one, what the player can do instead.
    """


@dataclass(frozen=True)
class ResolvedSource:
    """What a `source` turned out to name.

    Exactly one of two fields is set, and which one decides how the job is
    acquired — see `by_hash`:

      · `info_hash`, when the indexer published one. The original path, and
        still the preferred one: it needs no second service, it is 20 bytes
        that cannot carry a credential, and it is what a debrid service
        consumes directly;
      · `torrent_token`, when it did not. Prowlarr's own protected `link`, to
        be handed back to Prowlarr — and to nobody else — for the `.torrent`
        the row actually published. The hash then comes out of that file.

    `indexer_id` and `guid` are kept because they are the audit trail — which
    of the owner's indexers offered this, and under which id. `guid` is still
    never dereferenced; `indexer_id` now is, but only as the path segment of a
    request to the owner's own Prowlarr.
    """

    #: 40 lowercase hex characters, or `""` when this row is a `.torrent` one.
    #: Normalised here so that everything downstream can compare two of them
    #: with `==`.
    info_hash: str
    indexer_id: int
    guid: str
    #: Prowlarr's protected download token, or `""` when the hash is set.
    #: **Opaque, and deliberately so**: it is AES ciphertext only the owner's
    #: own instance can open. It travels only inside the opaque `source`
    #: locator; it is never logged, exposed as a separate API field or put on
    #: a job's reason.
    torrent_token: str = ""

    @property
    def by_hash(self) -> bool:
        """Which of the two paths this row takes. One place, so that a caller
        cannot invent a third reading of the same pair of fields."""
        return bool(self.info_hash)

    @property
    def magnet(self) -> str:
        """The smallest complete request a debrid service will accept.

        Deliberately trackerless. A magnet Prowlarr answers can carry a private
        tracker's passkey in its `tr=` parameters, and that is a credential
        belonging to the owner's account — it is dropped on the way in (see
        `info_hash_of`) and never rebuilt here. The hash alone is what the
        content *is*; where to get it is the debrid service's problem and it
        has better answers than this box does.

        Only meaningful when `by_hash`. A `.torrent` row has no magnet to
        build, and building one out of an empty hash would be a request that
        fails at the far end for a reason nobody could read.
        """
        if not self.info_hash:
            raise ValueError("this source names a torrent file, not a hash")
        return f"magnet:?xt=urn:btih:{self.info_hash}"


# ── minting one, and reading it back ───────────────────────────────────────


def stamp(source: str, info_hash: str, torrent_token: str = "") -> str:
    """Put a locator on a source. The mint side of the parse below.

    Lives here rather than in `prowlarr.py` so that the two halves of the
    encoding cannot drift: a provider that wrote `#hash=` and a resolver that
    read `#btih:` would be a Store where every job fails and every test that
    checks one side passes.

    **The hash wins.** When the row published one, the token is not written
    even if the caller found one: the hash path needs no second service, is
    cheaper, and was the tested one before this argument existed. The token is
    the fallback for a row that published no hash at all, which is 100 % of
    the rows on the box this was measured on.

    Neither, or both malformed, is not an error — it is a row an indexer
    published without anything to fetch, which is normal for usenet. The source
    is returned unchanged and `resolve()` will refuse it by name later, at the
    point where there is a player to tell.
    """
    clean = _normalise(info_hash)
    if clean:
        return f"{source}#btih:{clean}"
    token = torrent_token.strip() if isinstance(torrent_token, str) else ""
    if token and _TOKEN_OK.match(token):
        return f"{source}#tor:{token}"
    return source


def resolve(source: str) -> ResolvedSource:
    """`prowlarr://<indexerId>/<guid>#btih:<hash>` → its parts.

    …or `#tor:<token>`, which is the same locator for a row that published a
    `.torrent` instead of a hash. Exactly one suffix is read, hash first, so a
    source that somehow carried both resolves the cheap way.

    Raises `UnresolvableSource` for everything else, which is three different
    situations and three different sentences:

      · a source from another provider — the demo one mints `demo://…`, and
        its rows are invented, so there is nothing behind them to fetch;
      · a source with neither suffix — the indexer published no hash *and* no
        torrent, which is what a usenet release looks like;
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
    info_hash, token = "", ""
    match = _BTIH_SUFFIX.search(body)
    if match is not None:
        info_hash = match.group(1)
    else:
        match = _TOR_SUFFIX.search(body)
        if match is not None:
            token = match.group(1)
    if match is None:
        raise UnresolvableSource(
            "the indexer listed this release without a torrent hash or a "
            "torrent file, so there is nothing this box can ask for")
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
                          guid=guid.strip(), torrent_token=token)


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


def torrent_token_of(row: object) -> str:
    """Prowlarr's protected download token for this release, or `""`.

    Only asked when `info_hash_of` has answered `""` — `stamp` prefers the hash
    and the caller does not pay for this parse otherwise. It reads **one**
    parameter of `downloadUrl`: `link`. Not the URL, which is the credentialed
    proxy link `_redact` exists for; not `apikey`, which is this box's own key;
    not `file`, which is a display name. Pulling one named parameter out is a
    different act from using the URL, and the difference is the whole reason
    this function can exist next to a `downloadUrl` that is otherwise untouched.

    Three gates, and the middle one is the point:

      · **it must be a torrent.** A usenet row's `link` fetches a `.nzb`, which
        nothing downstream can use. Refused here, where the row is, rather than
        four steps later against a file that turned out to be XML;
      · **it must be opaque.** A `link` that base64url-decodes to something
        containing `://` is a *plaintext* indexer URL — and on a private
        tracker that is the owner's passkey. Prowlarr protects it (AES, keyed
        on `DownloadProtectionKey`; see the module docstring for where that was
        measured), so a plaintext one means this is not the Prowlarr this code
        was written against, and the safe answer is to carry nothing and let
        the row be refused by name. This is the gate that makes "no credential
        in the database" a checked property rather than a belief;
      · **it must be small.** A token is a few hundred characters. `source` is
        a database column and a browser string, and there is no legitimate
        reason for a multi-kilobyte one.
    """
    if not isinstance(row, dict):
        return ""
    protocol = row.get("protocol")
    if isinstance(protocol, str) and protocol.strip().lower() not in \
            ("", "torrent"):
        return ""
    url = row.get("downloadUrl")
    if not isinstance(url, str) or not url.strip():
        return ""
    try:
        found = parse_qs(urlsplit(url).query).get(_LINK_PARAM) or []
    except ValueError:
        return ""
    token = found[0].strip() if found and isinstance(found[0], str) else ""
    if not token or not _TOKEN_OK.match(token):
        return ""
    if _looks_like_a_url(token):
        log.warning("store: an indexer row carried an unprotected download "
                    "link; it was dropped rather than stored")
        return ""
    return token


def _looks_like_a_url(token: str) -> bool:
    """Whether this token is a URL wearing base64url.

    Padding is added rather than required: `Base64UrlEncode` strips `=`, and a
    decoder that insisted on it would reject every real token. A value that
    will not decode at all is *not* a URL and is left alone — it is opaque,
    which is what was wanted.

    `://` anywhere in the plaintext, rather than a scheme at the front. That is
    deliberately over-broad and the cost is named: ciphertext is random bytes,
    so roughly one row in fifty thousand contains those three bytes by accident
    and is refused for nothing. Refusing one row by name is the cheap mistake;
    writing a passkey into `store_jobs` is the expensive one, and a gate on a
    credential should fail in the direction that is cheap to be wrong about.
    """
    try:
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
    except (binascii.Error, ValueError):
        return False
    return b"://" in raw[:2048]


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
