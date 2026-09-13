"""What a job's `source` turns back into, and what it refuses to.

The whole file is offline by construction: `resolve.py` makes no request at
all. That is the point of it — the measurement recorded in its docstring is
that `(indexerId, guid)` is **not** re-resolvable against Prowlarr, so the
answer had to be something the row already carries rather than a second round
trip.

No real credential and no real host appears here. Hashes are obvious patterns,
guids point at `tracker.invalid`, and nothing in this file could reach a
stranger if the parse were replaced by an HTTP call tomorrow.
"""
from __future__ import annotations

import base64
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.services.store import resolve                          # noqa: E402
from backend.services.store.resolve import (                        # noqa: E402
    UnresolvableSource, info_hash_of, stamp)

HASH = "a1" * 20
GUID = "https://tracker.invalid/details/1"


# ── what the pair could and could not do ───────────────────────────────────

def test_the_indexer_and_guid_alone_are_refused_by_name():
    """The finding this whole module exists to record.

    `prowlarr://<indexerId>/<guid>` was chosen to be re-resolvable against
    Prowlarr and it is not: measured against `Prowlarr.Api.V1.dll` 2.5.2.5491,
    the only endpoint that takes the pair is the grab, which reads a cache that
    expires — *"Couldn't find requested release in cache, cache timeout
    probably expired"* — and then hands the release to a download client. So a
    source with no hash on it is refused here, in the one place that can say
    why, rather than failing later against a service that did nothing wrong.
    """
    with pytest.raises(UnresolvableSource) as e:
        resolve.resolve(f"prowlarr://3/{GUID}")
    assert "without a torrent hash" in str(e.value)


def test_a_hash_makes_the_same_row_resolvable_for_ever():
    """20 bytes saying what the content *is*: no key, no session, no expiry.

    This is the property `(indexerId, guid)` turned out not to have, and the
    reason the extra field is a hash rather than a URL — a queue row outlives a
    reboot by design, and a cache entry does not.
    """
    found = resolve.resolve(stamp(f"prowlarr://3/{GUID}", HASH))
    assert found.info_hash == HASH
    assert found.indexer_id == 3
    assert found.guid == GUID
    assert found.magnet == f"magnet:?xt=urn:btih:{HASH}"


def test_the_magnet_carries_no_trackers_and_therefore_no_passkey():
    """A private tracker's magnet carries the owner's passkey in `tr=`.

    Only the hash survives, so `source` — which travels to the browser — cannot
    carry a credential even when the indexer's own answer did.
    """
    magnet = resolve.resolve(stamp(f"prowlarr://3/{GUID}", HASH)).magnet
    assert "tr=" not in magnet and "passkey" not in magnet
    assert magnet == f"magnet:?xt=urn:btih:{HASH}"


# ── the encoding, and the guid it has to survive ───────────────────────────

def test_a_guid_that_is_itself_a_url_is_kept_whole():
    """Guids are very often URLs, so the split is on the FIRST slash only."""
    guid = "https://tracker.invalid/a/b/c?x=1"
    found = resolve.resolve(stamp(f"prowlarr://11/{guid}", HASH))
    assert found.guid == guid and found.indexer_id == 11


def test_a_guid_containing_a_hash_sign_is_not_mistaken_for_the_suffix():
    """The parse is anchored to the end and to exactly 40 hex characters.

    That anchor is the whole of its safety: a guid is whatever the indexer
    chose to put there, and `#` is a character.
    """
    guid = "https://tracker.invalid/d#btih:not-a-hash"
    found = resolve.resolve(stamp(f"prowlarr://3/{guid}", HASH))
    assert found.guid == guid
    assert found.info_hash == HASH


def test_stamping_a_row_that_has_no_hash_changes_nothing():
    """Not an error — it is a row the indexer published without one, which is
    normal. The refusal happens later, where there is a player to tell."""
    bare = f"prowlarr://3/{GUID}"
    assert stamp(bare, "") == bare
    assert stamp(bare, "not a hash") == bare


@pytest.mark.parametrize("source,expected", [
    ("demo://nes/whatever", "examples, not real games"),
    ("prowlarr://notanumber/guid#btih:" + HASH, "not one this box wrote"),
    (f"prowlarr://3/#btih:{HASH}", "names no release"),
    ("", "can no longer resolve"),
    ("something else entirely", "can no longer resolve"),
])
def test_every_unusable_source_says_which_way_it_was_unusable(source, expected):
    """Four different situations, four different sentences.

    Each ends up on a job row a player reads, so "it did not work" is not an
    acceptable answer for any of them.
    """
    with pytest.raises(UnresolvableSource) as e:
        resolve.resolve(source)
    assert expected in str(e.value)


# ── lifting a hash out of an indexer's answer ──────────────────────────────

def test_the_info_hash_field_is_read_first():
    assert info_hash_of({"infoHash": HASH.upper()}) == HASH


def test_a_magnet_gives_up_its_hash_and_nothing_else():
    """`magnetUrl` is read for the `xt=` value only. Everything else in it —
    the tracker list above all — is dropped where it is found."""
    magnet = (f"magnet:?xt=urn:btih:{HASH}&dn=Zelda"
              "&tr=http://tracker.invalid/announce/SECRETPASSKEY")
    assert info_hash_of({"magnetUrl": magnet}) == HASH


def test_a_base32_hash_is_the_same_twenty_bytes():
    """Plenty of magnets spell it that way, and refusing them would drop rows
    for a difference of encoding."""
    b32 = base64.b32encode(bytes.fromhex(HASH)).decode()
    assert len(b32) == 32
    assert info_hash_of({"infoHash": b32}) == HASH


def test_the_download_url_is_never_read():
    """It is the credentialed proxy link — `…/download?apikey=<this box's
    key>&link=…` — and it holds no hash anyway."""
    row = {"downloadUrl": f"http://prowlarr.invalid/3/download?apikey=SECRET"
                          f"&link=x&file=y&infohash={HASH}"}
    assert info_hash_of(row) == ""


@pytest.mark.parametrize("row", [
    {}, {"infoHash": ""}, {"infoHash": "zz" * 20}, {"infoHash": 12345},
    {"magnetUrl": "magnet:?dn=no-hash-here"}, {"infoHash": "a1b2"}, "not a row",
])
def test_a_row_with_no_usable_hash_answers_empty(row):
    """`""` and not a guess. A usenet release genuinely has none, and inventing
    one would make a job fail somewhere far less explicable."""
    assert info_hash_of(row) == ""
