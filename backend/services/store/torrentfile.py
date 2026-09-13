"""Reading just enough of a `.torrent` to get its info hash — and nothing else.

**Why this file exists.** On the box this was measured on, *every* row a real
indexer answered published a `.torrent` file and no hash: 0 of 8 for `mario
kart`, one indexer, `protocol=torrent`. `resolve.py` refuses a row with no
hash, correctly and by name, so that box could queue nothing at all. The second
path — [`prowlarr.fetch_torrent`](prowlarr.py) — brings the file back; this
module is what turns it into the 20 bytes the first path was already built
around.

── What it reads, and what it refuses to read ─────────────────────────────
A `.torrent` is a bencoded dictionary. The info hash is the **SHA-1 of the
bencoded `info` value, byte for byte as it arrived** — not of a re-encoding of
a parsed structure, because bencode is only canonical if the writer made it so
and a re-encode that normalised a key order would produce a hash that is not
the release's. So the decoder below records the byte span of the `info` value
and hashes the original slice. That is the whole trick and it is the only
reason this is a parser rather than a `json.loads`.

Everything else in the file is **not read**, and that is load-bearing rather
than lazy:

  · `announce` and `announce-list` are a private tracker's passkey. They are
    the `.torrent`'s version of a magnet's `tr=` parameters, which
    `resolve.info_hash_of` already drops where it finds them, and they are
    dropped here for the same reason — nothing downstream has any use for a
    tracker, because no torrent client exists on this box to talk to one;
  · `comment`, `created by`, `publisher`, `source` and whatever else a site
    stamped on it are a stranger's strings on their way to a database row and
    a television screen.

Only `name` and `piece length` are looked at, both mandatory in BEP 3, and only
to answer *"is this actually a torrent"* — a question worth asking, because the
common failure of fetching a `.torrent` from a private tracker with a stale
cookie is an **HTML login page served with a 200**, and handing that to
Real-Debrid would fail somewhere far less explicable than here.

── Bounded on purpose ─────────────────────────────────────────────────────
Three bounds, because the input is a file a stranger's server chose to send:

  · `MAX_BYTES` — a `.torrent` is piece hashes and filenames, so a very large
    release is still a small file. 4 MiB is many times the biggest anyone has
    seen and small enough that it cannot be a memory problem;
  · `_MAX_DEPTH` — bencode nests, and `d` repeated ten thousand times is a
    stack overflow in any recursive decoder. Iterative would avoid it; a depth
    cap is smaller and says what it means;
  · integers are bounded in *length*, not value, so `i` followed by a megabyte
    of digits is refused before Python is asked to build the number.

None of it is written anywhere. The bytes arrive in memory, are hashed, and go
out of scope — which is what keeps
`test_queueing_and_running_write_nothing_into_the_data_tree` true across the
new path.
"""
from __future__ import annotations

import hashlib

#: The largest `.torrent` this box will read. See the module docstring: a
#: torrent for a 15 GB release is tens of kilobytes, so this is not a limit
#: anybody meets — it is the bound that stops an indexer answering a DVD image
#: from being a memory problem.
MAX_BYTES = 4 * 1024 * 1024

#: How deep the decoder will follow nested containers before it stops.
#: `announce-list` is a list of lists, so the real files are two or three deep.
_MAX_DEPTH = 16

#: Digits in a bencoded integer or length prefix. Twenty is more than any real
#: value needs and short enough that the conversion cannot be the slow part.
_MAX_DIGITS = 20


class NotATorrent(ValueError):
    """These bytes are not a torrent file.

    The message reaches a job's `reason` through
    `realdebrid.RealDebridError`, so it is built from safe parts only: it says
    what was wrong with the shape and never quotes the content, which — when
    this fires — is most often a login page belonging to somebody else.
    """


def info_hash_of(blob: bytes) -> str:
    """The release's info hash, as 40 lowercase hex — or `NotATorrent`.

    The answer is in the same spelling `resolve.info_hash_of` produces, so the
    two paths are indistinguishable from the moment they meet: a hash lifted
    out of a Prowlarr row and one computed here are compared with `==` and
    travel through the same `AcquiredTarget.info_hash`.
    """
    if not isinstance(blob, (bytes, bytearray)):
        raise NotATorrent("this box was handed something that is not a file")
    if not blob:
        raise NotATorrent("the indexer answered an empty file")
    if len(blob) > MAX_BYTES:
        raise NotATorrent(
            f"the indexer's torrent file is larger than this box will read "
            f"({len(blob) // 1024} KiB)")

    data = bytes(blob)
    if data[:1] != b"d":
        # The cheap check that catches the common case before any parsing: an
        # HTML login page, a JSON error, a redirect body. Named as itself.
        raise NotATorrent(
            "the indexer answered something that is not a torrent file")

    try:
        top, spans, end = _top_level(data)
    except NotATorrent:
        raise
    except (ValueError, IndexError, RecursionError):
        # Every malformed shape is one answer, because the caller's behaviour
        # is the same for all of them and a taxonomy of bencode faults is not
        # something a player can act on.
        raise NotATorrent(
            "the indexer's torrent file could not be read") from None
    if end != len(data):
        raise NotATorrent("the indexer's torrent file could not be read")

    info = top.get(b"info")
    if not isinstance(info, dict):
        raise NotATorrent(
            "the indexer's torrent file names no release (no info dictionary)")

    # Enough of a shape check to tell a torrent from a page that happened to
    # bencode-decode. `name` and `piece length` are mandatory in BEP 3 and no
    # real file omits them.
    if not isinstance(info.get(b"name"), bytes) or \
            not isinstance(info.get(b"piece length"), int):
        raise NotATorrent(
            "the indexer's torrent file is not shaped like a release")

    # The original slice, never a re-encode — see the module docstring.
    start, stop = spans[b"info"]
    return hashlib.sha1(data[start:stop]).hexdigest()


# ── the smallest bencode decoder that can answer the question ──────────────


def _top_level(data: bytes) -> tuple[dict, dict, int]:
    """The outermost dictionary, plus where each of its values sat.

    Spans are recorded **only here**. The info hash is the SHA-1 of the
    bencoded `info` value exactly as it arrived, so that one slice has to be
    remembered; nothing nested inside it does, and a decoder that carried
    offsets through every level would be a harder thing to read for no gain.
    """
    if data[:1] != b"d":
        raise ValueError("not a dictionary")
    out: dict[bytes, object] = {}
    spans: dict[bytes, tuple[int, int]] = {}
    i = 1
    while data[i:i + 1] != b"e":
        key, i = _decode(data, i, 1)
        if not isinstance(key, bytes):
            raise ValueError("non-byte key")
        start = i
        out[key], i = _decode(data, i, 1)
        spans[key] = (start, i)
    return out, spans, i + 1


def _decode(data: bytes, i: int, depth: int) -> tuple[object, int]:
    """One value at `i`, and the offset just past it."""
    if depth > _MAX_DEPTH:
        raise NotATorrent("the indexer's torrent file is nested too deeply")
    if i >= len(data):
        raise ValueError("truncated")

    kind = data[i:i + 1]
    if kind == b"i":
        end = data.index(b"e", i + 1)
        if end - i - 1 > _MAX_DIGITS:
            raise ValueError("integer too long")
        return int(data[i + 1:end]), end + 1

    if kind == b"l":
        items: list[object] = []
        i += 1
        while data[i:i + 1] != b"e":
            value, i = _decode(data, i, depth + 1)
            items.append(value)
        return items, i + 1

    if kind == b"d":
        pairs: dict[bytes, object] = {}
        i += 1
        while data[i:i + 1] != b"e":
            key, i = _decode(data, i, depth + 1)
            if not isinstance(key, bytes):
                raise ValueError("non-byte key")
            pairs[key], i = _decode(data, i, depth + 1)
        return pairs, i + 1

    if kind.isdigit():
        colon = data.index(b":", i)
        if colon - i > _MAX_DIGITS:
            raise ValueError("length prefix too long")
        length = int(data[i:colon])
        end = colon + 1 + length
        if end > len(data):
            raise ValueError("truncated string")
        return data[colon + 1:end], end

    raise ValueError(f"unexpected byte {kind!r}")
