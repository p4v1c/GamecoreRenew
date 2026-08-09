"""What a pack must say about configuring ONE GAME at a time.

Sibling of `test_generator_contract.py`, and written for the same reason. That
file exists because a generator can be silently missing a function; this one
exists because a pack can be silently missing an ANSWER. The failure modes are
the same shape — nothing raises, nothing logs, a feature is simply absent for
one emulator and nobody can tell that from "this emulator cannot do it".

Three things are checked here that the schema structurally cannot:

  · `perGame.key` and `localMedia.format` are two blocks naming the same fact.
    The schema validates each on its own and has no way to notice they
    disagree. A ROM that scrapes as one game and configures as another is the
    kind of bug you find by owning the machine, not by reading the pack.

  · `why` has to be an answer. The schema can require a non-empty string; it
    cannot require that the string says something.

  · the negative branches of the schema itself. `supported: true` without a
    `path`, `supported: false` WITH one — both are conditional subschemas, and
    a conditional that never fires is a rule the catalogue does not actually
    have. This file constructs both and asserts they are refused, so the day
    the `if`/`then` support in `backend/services/catalog/schema.py` regresses,
    something goes red instead of everything staying green.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.services.catalog import load_schema, validate  # noqa: E402

CATALOG = ROOT / "catalog"
SCHEMA = load_schema(CATALOG / "_schema" / "pack.schema.json")


def _emulator_packs() -> list[tuple[str, dict]]:
    out = []
    for pack_dir in sorted(CATALOG.iterdir()):
        meta_file = pack_dir / "pack.json"
        if pack_dir.name.startswith("_") or not meta_file.is_file():
            continue
        meta = json.loads(meta_file.read_text())
        if meta.get("kind", "emulator") == "emulator":
            out.append((pack_dir.name, meta))
    return out


PACKS = _emulator_packs()
assert PACKS, "no emulator pack found — the catalogue is not where this test thinks"
IDS = [p[0] for p in PACKS]

SUPPORTING = [p for p in PACKS if p[1]["perGame"]["supported"]]
assert SUPPORTING, (
    "no pack declares perGame.supported — every test below would assert nothing, "
    "and the feature would be shipped switched off without a single red line")

UNSUPPORTED = [p for p in PACKS if not p[1]["perGame"]["supported"]]

# Selected, not skipped inside the test — the rule test_generator_contract.py
# already follows. A pack that declares only one of the two blocks has nothing
# to compare, which is a fact about the pack; reported as a `skip` it reads in
# the run summary as "this pack was not checked", and eight of those would bury
# the one line that matters the day a real disagreement appears.
BOTH_BLOCKS = [p for p in PACKS
               if (p[1].get("localMedia") or {}).get("format")
               and p[1]["perGame"].get("key")]
assert BOTH_BLOCKS, ("no pack declares both localMedia.format and perGame.key — "
                     "the agreement below is asserted about nothing")


@pytest.mark.parametrize("pack_id,meta", BOTH_BLOCKS,
                         ids=[p[0] for p in BOTH_BLOCKS])
def test_the_identity_is_spelled_the_same_in_both_blocks(pack_id, meta):
    """`localMedia.format` and `perGame.key` name the same reader.

    They are separate blocks because they answer separate questions — which
    parser reads the box art, which reader names the config file — but where a
    system has both, the answer is one string. Letting them drift would give a
    game two identities: `disc_id()` would report the serial the scraper
    matched on while the per-game file was filed under something else, and the
    setting would land on a file no emulator opens.
    """
    fmt = meta["localMedia"]["format"]
    key = meta["perGame"]["key"]
    assert fmt == key, (
        f"{pack_id}: localMedia.format is {fmt!r} but perGame.key is {key!r}. "
        f"One game, one identity — pick the reader that is actually right and "
        f"write it in both places")


@pytest.mark.parametrize("pack_id,meta", UNSUPPORTED,
                         ids=[p[0] for p in UNSUPPORTED])
def test_a_pack_that_cannot_do_it_says_something_useful(pack_id, meta):
    """"not implemented" is the one answer the reader already has.

    The `why` is read by whoever picks up this feature next, and by the player
    through the options screen. It has to name the obstacle — an identity
    nobody can read, a path nobody has verified — because the whole point of
    requiring the block was to stop "absent" and "impossible" looking alike.
    """
    why = meta["perGame"]["why"]
    assert len(why) >= 40, (
        f"{pack_id}: perGame.why is {why!r} — too short to name an obstacle")
    lowered = why.lower()
    for empty in ("not implemented", "todo", "tbd", "n/a", "not supported yet"):
        assert empty not in lowered, (
            f"{pack_id}: perGame.why says {empty!r}, which is what the reader "
            f"can already see from `supported: false`")


@pytest.mark.parametrize("pack_id,meta", SUPPORTING,
                         ids=[p[0] for p in SUPPORTING])
def test_a_supported_pack_puts_the_game_id_in_the_path(pack_id, meta):
    """One file per game, or the feature is its own bug.

    The schema pins this with a pattern; the assertion is here too because the
    schema's job is to describe the shape and this one is about the CONSEQUENCE.
    A path with no `@GAMEID@` validates as a perfectly well-formed string and
    makes every game on the system share a config — a setting placed on one
    title leaking onto all of them, which is the thing this phase set out to
    stop and would be shipped wearing its own interface.
    """
    path = meta["perGame"]["path"]
    assert "@GAMEID@" in path, (
        f"{pack_id}: perGame.path is {path!r} — no @GAMEID@, so every game on "
        f"this system would write to the same file")


@pytest.mark.parametrize("pack_id,meta", SUPPORTING,
                         ids=[p[0] for p in SUPPORTING])
def test_a_shipped_profile_names_a_game_id_and_not_a_title(pack_id, meta):
    """A profile is matched against what `key` resolves to, never against a name.

    Two dumps of one game agree on their Title ID and disagree about everything
    else — region tag, revision, the scene group in the brackets. A profile
    keyed by anything but the id would apply to one player's copy and not the
    next one's, which is indistinguishable from the profile being broken.
    """
    for profile in meta["perGame"].get("profiles", []):
        gid = profile["gameId"]
        assert gid == gid.strip() and " " not in gid, (
            f"{pack_id}: profile gameId {gid!r} looks like a title, not an id")


# ── the schema's own conditional branches ────────────────────────────────────
# Built from a real pack rather than a hand-made stub: a stub drifts from the
# schema silently, and then these tests pass because the fixture is wrong in a
# second way that cancels the first.

def _a_supporting_pack() -> dict:
    return copy.deepcopy(SUPPORTING[0][1])


def test_the_schema_refuses_supported_without_a_path():
    pack = _a_supporting_pack()
    del pack["perGame"]["path"]
    errors = validate(pack, SCHEMA, pack["id"])
    assert any("path" in e for e in errors), (
        "a pack claiming per-game support with nowhere to write it validated — "
        f"the conditional in the schema is not firing. Errors: {errors}")


def test_the_schema_refuses_a_path_with_no_game_id_in_it():
    pack = _a_supporting_pack()
    pack["perGame"]["path"] = "@FLATPAK_CONFIG@/somewhere/settings.ini"
    errors = validate(pack, SCHEMA, pack["id"])
    assert any("path" in e for e in errors), (
        f"a per-game path that names one file for every game validated: {errors}")


def test_the_schema_refuses_an_unsupported_pack_that_still_declares_a_path():
    """The contradiction has to be refused rather than resolved.

    `supported: false` with a `path` is a pack saying two things at once, and
    whichever one the reader silently believed would be wrong half the time —
    either a feature is offered that the pack disclaims, or a path is ignored
    that someone took the trouble to work out.
    """
    pack = _a_supporting_pack()
    pack["perGame"]["supported"] = False
    pack["perGame"]["why"] = "a reason long enough to be a real sentence about it"
    errors = validate(pack, SCHEMA, pack["id"])
    assert any("forbidden shape" in e for e in errors), (
        f"an unsupported pack carrying a path, a format and a key validated: {errors}")


def test_the_schema_refuses_a_profile_whose_settings_are_not_flat():
    """`additionalProperties` as a SCHEMA is the only thing checking this.

    `settings` is a map of section names nobody can enumerate — they belong to
    the emulator — so the keys cannot be listed and `additionalProperties:
    false` cannot be used. Without a subschema the block would validate as
    `type: object`, and a profile pushed down the OTA channel could nest a map
    two levels deeper than the writer understands: `pergame` would render it
    with str() and place `{'depth': 3}` in a real config file as a value.
    """
    pack = _a_supporting_pack()
    pack["perGame"]["profiles"] = [{
        "gameId": "BLES00000", "label": "Test", "why": "because",
        "emulator": ">=0.0.30",
        "settings": {"Video": {"Nested": {"depth": 3}}},
    }]
    errors = validate(pack, SCHEMA, pack["id"])
    assert errors, "a profile carrying a nested settings map validated"


def test_the_schema_refuses_a_profile_that_sets_nothing():
    """`minProperties`, and why it is worth a keyword in the validator.

    An empty `settings` is a profile that reports itself as applied on the
    options screen and changes not one byte. That is worse than no profile:
    the player reads "a known-good setting is in place", the game still does
    not start, and the one place they would look for the cause says it is fine.
    """
    pack = _a_supporting_pack()
    pack["perGame"]["profiles"] = [{
        "gameId": "BLES00000", "label": "Test", "why": "because",
        "emulator": ">=0.0.30", "settings": {},
    }]
    errors = validate(pack, SCHEMA, pack["id"])
    assert errors, "a profile with no settings at all validated"


def test_the_schema_refuses_an_unversioned_profile():
    """A profile with no emulator range is a trap with a delay on it.

    The day RPCS3 renames an option, the profile keeps writing the old key: the
    setting silently stops arriving, the options screen still says it is
    applied, and the game goes back to not starting for a reason the player
    already paid someone to solve. The range is what lets the catalogue channel
    retire a profile without a release.
    """
    pack = _a_supporting_pack()
    pack["perGame"]["profiles"] = [{
        "gameId": "BLES00000", "label": "Test", "why": "because",
        "settings": {"Video": {"Write Color Buffers": True}},
    }]
    errors = validate(pack, SCHEMA, pack["id"])
    assert any("emulator" in e for e in errors), (
        f"a profile with no emulator version range validated: {errors}")
