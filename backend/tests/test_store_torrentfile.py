"""Reading a `.torrent`, and every way this box refuses to.

Offline by construction: `torrentfile.py` makes no request at all and touches
no disk. Every fixture here is bencoded in this file by `_be` below, so the
suite runs on a box with the cable out and there is no sample file anywhere in
the tree for a future change to start depending on.

**No real tracker and no real passkey appears.** Announce URLs point at
`.invalid`, which RFC 2606 reserves, and the "passkey" is an obvious pattern.
They are here precisely to be asserted *absent* from everything that comes out.

What is pinned, in the order it matters:

  · **the hash is the hash** — SHA-1 of the `info` value byte for byte as it
    arrived, so a file whose keys are not in canonical order still hashes to
    what the swarm calls it;
  · **nothing but the hash comes out** — a private tracker's passkey lives in
    `announce` and `announce-list`, and this module is the `.torrent`'s version
    of dropping a magnet's `tr=` parameters;
  · **a login page is not a release** — the common failure of fetching a
    `.torrent` with a stale cookie is HTML served with a 200, and it is named
    as itself here rather than four steps later;
  · **a stranger's file is bounded** — size, nesting depth and digit count.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.services.store import torrentfile                       # noqa: E402
from backend.services.store.torrentfile import (                     # noqa: E402
    MAX_BYTES, NotATorrent, info_hash_of)

#: An obvious pattern, and the thing every assertion below looks for the
#: absence of. A private tracker puts one of these in the announce URL of every
#: `.torrent` it serves, per account.
PASSKEY = "b7f3e1c95a2d4806b7f3e1c95a2d4806"
ANNOUNCE = f"https://private.invalid/announce/{PASSKEY}"


def _be(value) -> bytes:
    """Bencode, for building fixtures only.

    Deliberately *not* imported from the product: `torrentfile.py` has no
    encoder and must not grow one, and a test that shared an implementation
    with the thing it tests measures itself.
    """
    if isinstance(value, int):
        return b"i%de" % value
    if isinstance(value, bytes):
        return b"%d:%s" % (len(value), value)
    if isinstance(value, list):
        return b"l" + b"".join(_be(v) for v in value) + b"e"
    if isinstance(value, dict):
        return b"d" + b"".join(_be(k) + _be(v)
                               for k, v in value.items()) + b"e"
    raise TypeError(value)


def _keys(over: dict) -> dict:
    """`piece_length=…` → `b"piece length"`. Keyword arguments cannot be bytes
    and cannot contain a space, and the fixtures read better with them."""
    return {k.encode().replace(b"_", b" "): v for k, v in over.items()}


def _info(**over) -> dict:
    info = {b"name": b"Zelda.z64", b"piece length": 16384,
            b"length": 32 * 1024 * 1024, b"pieces": b"\x01" * 20}
    info.update(_keys(over))
    return info


def _torrent(info=None, **over) -> bytes:
    body = {b"announce": ANNOUNCE.encode(),
            b"announce-list": [[ANNOUNCE.encode()]],
            b"comment": b"uploaded by somebody",
            b"created by": b"a site this box has no relationship with",
            b"info": _info() if info is None else info}
    body.update(_keys(over))
    return _be(body)


# ── the hash is the hash ───────────────────────────────────────────────────

def test_the_hash_is_the_sha1_of_the_info_value_as_it_arrived():
    """What the swarm calls this release, and what Real-Debrid will be asked
    for. 40 lowercase hex, the same spelling `resolve.info_hash_of` answers, so
    the two paths are indistinguishable from here on."""
    info = _info()
    got = info_hash_of(_torrent(info))
    assert got == hashlib.sha1(_be(info)).hexdigest()
    assert len(got) == 40 and got == got.lower()


def test_a_file_whose_keys_are_not_sorted_still_hashes_correctly():
    """The reason this is a parser and not a decode-then-re-encode.

    Bencode is only canonical if the writer made it so. Re-encoding a parsed
    structure would normalise the key order and produce a hash that is not the
    release's — the torrent would be added to Real-Debrid and never match
    anything.
    """
    odd = {b"pieces": b"\x02" * 20, b"piece length": 16384,
           b"name": b"Rel.iso", b"length": 10}
    blob = _torrent(odd)
    assert info_hash_of(blob) == hashlib.sha1(_be(odd)).hexdigest()
    # …and the naive answer really would have differed, or this proves nothing.
    canonical = dict(sorted(odd.items()))
    assert _be(canonical) != _be(odd)


def test_a_multi_file_release_is_read_the_same_way():
    """A folder of ROMs plus a NFO is one torrent with one info hash. Which of
    its files is the game is `realdebrid._choose_file`'s question, not this
    module's."""
    info = {b"name": b"Zelda Collection", b"piece length": 262144,
            b"pieces": b"\x03" * 40,
            b"files": [{b"length": 100, b"path": [b"a", b"one.z64"]},
                       {b"length": 20, b"path": [b"readme.txt"]}]}
    assert info_hash_of(_torrent(info)) == hashlib.sha1(_be(info)).hexdigest()


def test_bytes_and_bytearray_are_both_files():
    blob = _torrent()
    assert info_hash_of(bytearray(blob)) == info_hash_of(blob)


# ── the passkey, which is the whole reason the trackers are not read ───────

def test_the_announce_urls_are_never_read_and_never_come_back_out():
    """The `.torrent`'s version of dropping a magnet's `tr=` parameters.

    `announce` and `announce-list` carry the owner's passkey on a private
    tracker. Nothing downstream has any use for a tracker — this box has no
    torrent client to talk to one — so they are dropped where they are found.
    """
    blob = _torrent()
    # The fixture really does contain it, or the assertion below is vacuous.
    assert PASSKEY.encode() in blob
    got = info_hash_of(blob)
    assert PASSKEY not in got
    assert "private.invalid" not in got


def test_two_accounts_downloading_the_same_release_get_the_same_hash():
    """The strongest form of the same statement.

    Same release, two different passkeys in the announce URL — which is exactly
    what two members of one private tracker are handed. The info hash is
    identical, because the passkey is not in the `info` dictionary and is not
    read. A hash that differed per account would have been a credential.
    """
    info = _info()
    mine = _torrent(info, announce=b"https://private.invalid/announce/AAAA1111")
    theirs = _torrent(info, announce=b"https://private.invalid/announce/BBBB2222")
    assert mine != theirs
    assert info_hash_of(mine) == info_hash_of(theirs)


def test_a_comment_a_site_stamped_on_it_is_not_read_either():
    """A stranger's string on its way to a database row and a television."""
    blob = _torrent(comment=b"<script>alert(1)</script> visit private.invalid")
    assert info_hash_of(blob) == hashlib.sha1(_be(_info())).hexdigest()


# ── a login page is not a release ──────────────────────────────────────────

def test_a_login_page_served_with_a_200_is_named_as_itself():
    """The common failure of fetching a `.torrent` from a private tracker with
    a stale cookie, and the reason the bytes are checked before the account is
    touched. Handing this to Real-Debrid would fail somewhere far less
    explicable."""
    page = b"<!DOCTYPE html>\n<title>Log in</title><form action=/login>"
    with pytest.raises(NotATorrent) as e:
        info_hash_of(page)
    assert "not a torrent file" in str(e.value)


def test_the_page_itself_is_never_quoted_in_the_message():
    """The message becomes a job's `reason`, which a player reads on a
    television. When this fires the content is most often somebody else's
    session page, so none of it is repeated."""
    page = b"<html>session=SECRETCOOKIE7788 welcome back, owner</html>"
    with pytest.raises(NotATorrent) as e:
        info_hash_of(page)
    assert "SECRETCOOKIE7788" not in str(e.value)
    assert "welcome back" not in str(e.value)


@pytest.mark.parametrize("blob,expected", [
    (b"", "an empty file"),
    (b"{\"error\": \"not found\"}", "not a torrent file"),
    (_be({b"announce": b"x"}), "no info dictionary"),
    (_be({b"info": b"not a dictionary"}), "no info dictionary"),
    (_be({b"info": {b"piece length": 1}}), "not shaped like a release"),
    (_be({b"info": {b"name": b"x"}}), "not shaped like a release"),
    (_be({b"info": {b"name": 7, b"piece length": 1}}),
     "not shaped like a release"),
    (b"d4:infod" + b"1:xd" * 30 + b"e" * 30 + b"ee", "nested too deeply"),
    (b"di" + b"9" * 40 + b"ee", "could not be read"),
    (b"d4:name99999:short", "could not be read"),
])
def test_every_shape_that_is_not_a_release_says_which_way(blob, expected):
    """Each of these ends on a job row, so "it did not work" is not an
    acceptable answer for any of them."""
    with pytest.raises(NotATorrent) as e:
        info_hash_of(blob)
    assert expected in str(e.value)


def test_trailing_bytes_after_the_dictionary_are_refused():
    """A torrent is one bencoded dictionary and nothing else. Anything appended
    means this is not the file it claims to be, and hashing the part that
    parsed would be trusting half of a stranger's answer."""
    with pytest.raises(NotATorrent):
        info_hash_of(_torrent() + b"appended")


def test_a_truncated_file_is_refused_rather_than_half_read():
    with pytest.raises(NotATorrent):
        info_hash_of(_torrent()[:-6])


# ── bounded, because the input is a stranger's file ────────────────────────

def test_a_file_larger_than_the_cap_is_refused_before_it_is_parsed():
    """A `.torrent` is piece hashes and filenames, so a 15 GB release is still
    tens of kilobytes. The cap is not a limit anybody meets — it is what stops
    an indexer answering a DVD image from being a memory problem."""
    with pytest.raises(NotATorrent) as e:
        info_hash_of(b"d" + b"\x00" * MAX_BYTES)
    assert "larger than this box will read" in str(e.value)


def test_a_file_exactly_at_the_cap_is_still_read():
    """The bound is `>`, not `>=` — an off-by-one here would refuse a legal
    file for no reason."""
    info = _info()
    pad = MAX_BYTES
    while True:
        padded = _be({b"pad": b"\x00" * pad, b"info": info})
        if len(padded) <= MAX_BYTES:
            break
        pad -= len(padded) - MAX_BYTES
    assert len(padded) == MAX_BYTES
    assert info_hash_of(padded) == hashlib.sha1(_be(info)).hexdigest()


@pytest.mark.parametrize("blob", [None, "a string", 42, ["list"]])
def test_something_that_is_not_bytes_is_not_a_file(blob):
    with pytest.raises(NotATorrent):
        info_hash_of(blob)


def test_nothing_is_written_anywhere(tmp_path, monkeypatch):
    """The bytes live in memory and go out of scope.

    Pinned here as well as in `test_store_jobs.py` because this is the module
    that *could* have been written as "save it and shell out to a tool", and
    the whole ingestion design depends on it not being.
    """
    monkeypatch.chdir(tmp_path)
    before = set(tmp_path.rglob("*"))
    info_hash_of(_torrent())
    with pytest.raises(NotATorrent):
        info_hash_of(b"<html>")
    assert set(tmp_path.rglob("*")) == before


def test_the_module_opens_nothing(monkeypatch):
    """Stated as a property rather than as an absence of files: `open` raises
    if anything in this path reaches for it."""
    def refuse(*a, **k):
        raise AssertionError("torrentfile opened something")
    monkeypatch.setattr(torrentfile, "__builtins__", dict(
        __builtins__ if isinstance(__builtins__, dict)
        else __builtins__.__dict__, open=refuse), raising=False)
    assert len(info_hash_of(_torrent())) == 40
