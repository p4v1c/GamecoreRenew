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


# ── the second locator: a row that publishes a file, not a hash ────────────

#: A token shaped like what `Base64UrlEncode(AES(...))` produces: base64url,
#: opaque, and — the point — not a URL when you decode it.
TOKEN = "Q2lwaGVydGV4dC1ub3QtYS1VUkwtMTIzNDU2Nzg5"
#: The measured shape of a real row on the box this was written for: a
#: `.torrent` filename, no `infoHash`, no `magnetUrl`, and the payload behind
#: Prowlarr's own credentialed proxy link.
BOX_KEY = "0123456789abcdef0123456789abcdef"


def _torrent_row(**over) -> dict:
    row = {
        "protocol": "torrent",
        "fileName": "Mario Kart 8 Deluxe - Nintendo Switch.torrent",
        "guid": "https://indexer.invalid/download/gAAAAAB0000",
        "indexerId": 1,
        "downloadUrl": f"http://prowlarr.invalid/1/download?apikey={BOX_KEY}"
                       f"&link={TOKEN}&file=Mario+Kart",
    }
    row.update(over)
    return row


def test_the_measured_row_carried_no_hash_at_all():
    """0 of 8 rows for `mario kart`, on the one indexer that box has.

    This is the number the second path exists for. A row shaped like this one
    resolved to nothing before, which is why `resolve()` was refusing the whole
    library rather than an edge case.
    """
    assert info_hash_of(_torrent_row()) == ""


def test_a_torrent_row_becomes_resolvable_through_its_token():
    """The same row, now with somewhere to go.

    `by_hash` is `False`, which is what sends `realdebrid.acquire` down the
    `PUT /torrents/addTorrent` branch instead of `addMagnet`.
    """
    row = _torrent_row()
    source = stamp(f"prowlarr://1/{row['guid']}", info_hash_of(row),
                   resolve.torrent_token_of(row))
    found = resolve.resolve(source)
    assert found.by_hash is False
    assert found.torrent_token == TOKEN
    assert found.info_hash == ""
    assert found.indexer_id == 1 and found.guid == row["guid"]


def test_a_hash_still_wins_when_the_row_publishes_both():
    """The rule that chooses, pinned.

    The hash path needs no second service and was the tested one first, so a
    row carrying both resolves the cheap way and the token is not even written.
    """
    row = _torrent_row(infoHash=HASH)
    source = stamp(f"prowlarr://1/{GUID}", info_hash_of(row),
                   resolve.torrent_token_of(row))
    assert "#tor:" not in source
    found = resolve.resolve(source)
    assert found.by_hash is True and found.info_hash == HASH
    assert found.torrent_token == ""


def test_only_the_link_parameter_of_the_download_url_is_ever_read():
    """Not the URL, not `apikey`, not `file`.

    `downloadUrl` carries this box's own Prowlarr key. Reading one named
    parameter out of it is a different act from using it, and this is the test
    that keeps the difference real: the key appears in no part of what is kept.
    """
    token = resolve.torrent_token_of(_torrent_row())
    assert token == TOKEN
    assert BOX_KEY not in token
    source = stamp(f"prowlarr://1/{GUID}", "", token)
    assert BOX_KEY not in source
    assert "apikey" not in source and "download?" not in source


# ── the private tracker, which is the case that decides the design ─────────

#: A passkey in a **path segment** — the shape `prowlarr._redact` cannot catch,
#: because it is not a query parameter. This is the leak the gate below exists
#: to stop.
PASSKEY = "b7f3e1c95a2d4806b7f3e1c95a2d4806"
PRIVATE_URL = f"https://private.invalid/download/{PASSKEY}/4711"


def test_a_prowlarr_that_hands_out_a_plaintext_link_is_refused_outright():
    """The private-tracker gate, and the reason the token can be stored at all.

    Prowlarr protects `link`: `Prowlarr.Core.dll` builds it in
    `ConvertToProxyLink` through `IProtectionService`, and the same assembly
    holds `Aes`, `CreateEncryptor`, `CryptoStream` and `Base64UrlEncode`. So a
    real token is ciphertext and a passkey inside it is unreadable to this box,
    to the browser and to the database.

    That is checked rather than trusted. A `link` that decodes to a URL means
    this is **not** that Prowlarr — an older build, a fork, something in front
    — and on a private tracker that URL is the owner's passkey. The answer is
    to carry no locator at all, so the row is refused by name later instead of
    putting a credential in `store_jobs`.
    """
    plain = base64.urlsafe_b64encode(PRIVATE_URL.encode()).decode().rstrip("=")
    row = _torrent_row(downloadUrl=f"http://prowlarr.invalid/1/download"
                                   f"?apikey={BOX_KEY}&link={plain}&file=x")
    assert resolve.torrent_token_of(row) == ""

    source = stamp(f"prowlarr://1/{row['guid']}", info_hash_of(row),
                   resolve.torrent_token_of(row))
    assert PASSKEY not in source
    assert plain not in source
    assert "#tor:" not in source
    with pytest.raises(UnresolvableSource) as e:
        resolve.resolve(source)
    assert "without a torrent hash" in str(e.value)


def test_an_opaque_token_does_not_decode_to_anything_that_reveals_a_tracker():
    """The other half of the same property, stated positively.

    What *is* carried decodes to no URL — that is exactly the condition the
    gate tests — so nothing in `source` names a tracker, a host or a passkey.
    """
    token = resolve.torrent_token_of(_torrent_row())
    raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
    assert b"://" not in raw
    assert PASSKEY.encode() not in raw


@pytest.mark.parametrize("row,why", [
    (_torrent_row(protocol="usenet"), "a .nzb is not a torrent"),
    (_torrent_row(downloadUrl=""), "no download url at all"),
    (_torrent_row(downloadUrl="http://prowlarr.invalid/1/download?apikey=k"),
     "no link parameter"),
    (_torrent_row(downloadUrl="http://prowlarr.invalid/1/download?link="),
     "an empty link"),
    (_torrent_row(downloadUrl="http://prowlarr.invalid/1/d?link=short"),
     "too short to be a token"),
    (_torrent_row(downloadUrl=f"http://prowlarr.invalid/1/d?link={'A' * 1100}"),
     "too long for a database column and a browser string"),
    (_torrent_row(downloadUrl="http://prowlarr.invalid/1/d?link=has spaces!!"),
     "not the base64url alphabet"),
    ("not a row", "not a row"),
])
def test_a_row_with_no_usable_token_answers_empty(row, why):
    """`""` and not a guess, exactly as `info_hash_of` answers.

    Each of these ends with the row refused by name at the job, which is the
    honest answer — a locator invented here would fail somewhere far less
    explicable."""
    assert resolve.torrent_token_of(row) == "", why


def test_a_token_from_a_long_indexer_url_is_still_accepted():
    """The cap is sized from the arithmetic, not guessed.

    The token is base64url of AES-CBC, so it runs about 4/3 × the indexer URL:
    roughly 700 characters for a 500-character one, which long Cardigann links
    genuinely reach. A cap set at a round number below that would drop every
    row from such an indexer and put it straight back at 0 %.
    """
    long_token = "A" * 700
    row = _torrent_row(
        downloadUrl=f"http://prowlarr.invalid/1/d?apikey={BOX_KEY}"
                    f"&link={long_token}")
    assert resolve.torrent_token_of(row) == long_token
    found = resolve.resolve(stamp(f"prowlarr://1/{GUID}", "", long_token))
    assert found.torrent_token == long_token


def test_stamping_a_row_with_neither_changes_nothing():
    bare = f"prowlarr://3/{GUID}"
    assert stamp(bare, "", "") == bare
    assert stamp(bare, "", "not a token!") == bare


def test_a_guid_containing_the_token_marker_is_not_mistaken_for_the_suffix():
    """Same anchor, same safety as `#btih:` — a guid is whatever the indexer
    chose to put there, and `#` is a character."""
    guid = "https://indexer.invalid/d#tor:NOT_THE_REAL_ONE_1234567"
    found = resolve.resolve(stamp(f"prowlarr://3/{guid}", "", TOKEN))
    assert found.guid == guid
    assert found.torrent_token == TOKEN


def test_a_torrent_source_has_no_magnet_to_offer():
    """`magnet` is only meaningful for the hash path.

    Building `magnet:?xt=urn:btih:` out of an empty hash would be a request
    that fails at Real-Debrid for a reason nobody could read.
    """
    found = resolve.resolve(stamp(f"prowlarr://1/{GUID}", "", TOKEN))
    with pytest.raises(ValueError):
        found.magnet
