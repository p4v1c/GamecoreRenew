"""A pad nobody can name must not get a config written from a guess.

`resolve_name()` is a fallback chain, and only its first rung ever said
anything when it failed — and only if it RAISED. The common failure is not an
exception, it is an absence: libSDL3 answers perfectly well and simply does not
know this pad, which is the case the comment on SDL3_FALLBACK_NAMES describes
itself ("the pad went back to sleep between the evdev scan and this call").
No exception, a valid dict without the entry, and the chain walked quietly down
to the raw kernel name.

That name is then written. Measured through the real generators against the
real seeds, before this was fixed:

    rpcs3/Default.yml     Device: Generic USB Gamepad 1
    dolphin/GCPadNew.ini  Device = SDL/0/Generic USB Gamepad

Neither string is anything those emulators enumerate, so the pad is dead in
game — and the only trace is "SDL: Adding empty device" in the EMULATOR's log,
which nobody reads from a sofa. **The defect is not the wrong name, it is the
silence.**

Two things follow, and both are tested here: the guess is not written, and the
give-up is said out loud — in our journal, and at the API where the owner is
holding the pad and asking.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.services import controller_profiles as cp             # noqa: E402
from backend.services.configgen import controllers as cc           # noqa: E402
from backend.tests import characterisation as ch                   # noqa: E402

PAD = ch.UNKNOWN

# conftest.py points GAMECORE_ROOT at a throwaway directory, so the vendored
# gamecontrollerdb.txt is NOT there under test and db_name_for() answers None
# for everything. Every assertion about the community DB would then hold
# vacuously — including the guard rail that says the unknown pad is unknown.
# This repo has already shipped one test that passed by exercising nothing for
# exactly this reason, so the real file is pointed at explicitly.
REAL_DB = ROOT / "backend" / "data" / "gamecontrollerdb.txt"


@pytest.fixture(autouse=True)
def community_db(monkeypatch):
    assert REAL_DB.is_file(), f"the vendored SDL DB moved: {REAL_DB}"
    monkeypatch.setattr(cc, "DB_FILE", REAL_DB)
    cc._logged_resolution.clear()


@pytest.fixture
def a_pad_the_db_knows_and_sdl3_does_not():
    """A real vendor:product that gamecontrollerdb.txt names and
    SDL3_FALLBACK_NAMES does not — the case where the old chain produced an
    SDL2-era name and wrote it into an SDL3 config."""
    found = next(((v, p) for v, p in (("0f0d", "00ee"), ("2f24", "0091"))
                  if cc.db_name_for(v, p)
                  and (v, p) not in cc.SDL3_FALLBACK_NAMES), None)
    assert found, "no pad is in the community DB and outside the table"
    return found


@pytest.fixture
def box(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    ch.build_tree(home)
    ch.install_stubs(cp, home, monkeypatch)
    cc._logged_resolution.clear()
    return home


# ── the premise ──────────────────────────────────────────────────────────────

def test_the_unknown_pad_is_really_unknown():
    """Guard rail. If this vendor:product ever entered either table, every test
    below would pass by resolving successfully and prove nothing at all."""
    assert (PAD.vendor, PAD.product) not in cc.SDL3_FALLBACK_NAMES
    assert cc.db_name_for(PAD.vendor, PAD.product) is None
    assert not PAD.sdl3_name, "the harness pad must be one libSDL3 does not know"


def test_a_known_pad_still_resolves_and_is_trusted(box):
    """The other guard rail: the chain must still WORK. A change that made
    every pad unknown would satisfy "no guess is written" perfectly."""
    resolved = cp.resolve_name(ch.DS4.vendor, ch.DS4.product, ch.DS4.evdev_name)
    assert resolved == ch.DS4.sdl3_name
    assert resolved.source in cp.SDL3_TRUSTED


# ── the finding ──────────────────────────────────────────────────────────────

def test_falling_through_the_chain_is_said_out_loud(box, caplog):
    """The constat. SDL3 did not raise — it answered without this pad."""
    with caplog.at_level(logging.DEBUG, logger=cc.log.name):
        resolved = cp.resolve_name(PAD.vendor, PAD.product, PAD.evdev_name)

    assert resolved.source == "unknown"
    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warnings, (
        "resolve_name() reached its last rung and wrote nothing to the "
        "journal. Only the SDL3 exception was ever reported; the absence, "
        "which is the common case, was not.")
    said = warnings[0].getMessage()
    assert PAD.vendor in said and PAD.product in said, said


def test_the_guess_never_reaches_a_config(box):
    """The cost, measured where it was paid — on the real seed tree.

    Every file the pipeline touches, not just the two that name a device: a
    guessed name must not turn up anywhere.
    """
    cp.apply_profile(1, PAD.vendor, PAD.product, PAD.evdev_name, 0)

    for pack_id, rels in ch.WATCHED.items():
        for rel in rels:
            p = box / rel
            if p.is_file():
                assert PAD.evdev_name not in p.read_text(), (
                    f"{pack_id}/{Path(rel).name} was written with the kernel's "
                    f"name {PAD.evdev_name!r}. RPCS3 and Dolphin match this "
                    f"string against their own SDL3 enumeration, so what it "
                    f"produces is a dead pad and a config that looks right.")


def test_the_give_up_is_reported_not_swallowed(box):
    """A give-up that reaches nobody is the same silence one layer up.

    `Skip` is what separates "nothing to do" from "I refused" — a distinction
    this pipeline lost once already, and RPCS3's players 2-4 sat dead for a
    week because of it.
    """
    result = cp.apply_profile(1, PAD.vendor, PAD.product, PAD.evdev_name, 0)

    assert result.skipped, "the pass reported no give-up at all"
    assert not result.complete, "an incomplete pass must not look complete"
    named = " ".join(result.skipped)
    assert f"{PAD.vendor}:{PAD.product}" in named, named


def test_the_give_up_is_also_reported_in_words_a_player_knows(box):
    """The same give-ups, named as systems rather than as diagnostics.

    `skipped` is for the journal: "ryujinx: SDL2 would not report a GUID for
    1d79:0f0f" tells an owner reading logs exactly what happened, and tells a
    player on a sofa nothing. The arrival toast needs "Nintendo Switch", and
    it must come from the pack rather than from splitting the prefix off a
    Skip string — a pack id is not a system name.
    """
    result = cp.apply_profile(1, PAD.vendor, PAD.product, PAD.evdev_name, 0)

    assert len(result.skipped_labels) == len(result.skipped), (
        "every give-up needs a name the player can read")
    from backend.services import configgen
    labels = {p.data.get("label")
              for p in configgen.profilable_packs(configgen.load_catalog())}
    assert set(result.skipped_labels) <= labels, (
        f"{result.skipped_labels} is not a set of catalogue labels — this is "
        "what pack ids leaking into the toast looks like")


def test_the_emulators_that_do_not_match_by_name_still_work(box):
    """The refusal must be narrow. PCSX2 and DuckStation bind by SDL role with
    no device identity at all, so a name nobody knows changes nothing for
    them — refusing there would break a pad that works."""
    result = cp.apply_profile(1, PAD.vendor, PAD.product, PAD.evdev_name, 0)

    assert list(result), (
        f"nothing at all was configured for an unknown pad: {result.skipped}. "
        f"The emulators that never name a device must be unaffected.")


def test_the_warning_is_not_repeated_on_every_lookup(box, caplog):
    """`Pad.name` is a property, so one pass resolves the same pad about ten
    times and the monitor retries an incomplete pass five more. Fifty copies of
    one warning is how the line that names the cause gets buried."""
    with caplog.at_level(logging.WARNING, logger=cc.log.name):
        for _ in range(5):
            cp.apply_profile(1, PAD.vendor, PAD.product, PAD.evdev_name, 0)

    # Scoped to the resolution logger on purpose. apply_profile emits its own
    # one-line summary per pass, which is right and is not what this measures.
    warnings = [r for r in caplog.records
                if r.name == cc.log.name and r.levelno >= logging.WARNING]
    assert len(warnings) == 1, f"logged {len(warnings)}x"


# ── the community DB is out of the SDL3 chain, not deleted ───────────────────

def test_the_community_db_no_longer_names_an_sdl3_device(
        box, a_pad_the_db_knows_and_sdl3_does_not):
    """It is an SDL2-era name and wrong for SDL3 on real pads — "PS5
    Controller" against "DualSense Wireless Controller". A pad the DB knows and
    SDL3 does not must still come back `unknown`, or the guess is simply
    reached by a different road."""
    known_to_db = a_pad_the_db_knows_and_sdl3_does_not
    resolved = cp.resolve_name(*known_to_db, "some kernel name")
    assert resolved.source == "unknown", (
        f"{known_to_db} resolved from the community DB as {resolved!r} — that "
        f"name is what RPCS3 logs as 'SDL: Adding empty device'")


def test_the_community_db_still_names_a_pad_for_a_human(
        box, a_pad_the_db_knows_and_sdl3_does_not):
    """"Restrict it, do not delete it." A label on screen only has to be
    recognisable, and "Horipad Mini 4" tells the owner which pad is in their
    hands where the kernel string does not."""
    known_to_db = a_pad_the_db_knows_and_sdl3_does_not
    label = cp.display_name(*known_to_db, "generic evdev string")
    assert label == cc.db_name_for(*known_to_db), (
        f"the human-facing name fell back to the kernel string ({label!r}) — "
        f"db_name_for was removed rather than restricted")


# ── it reaches the router ────────────────────────────────────────────────────

def test_the_router_says_the_pad_is_unidentified(box, monkeypatch):
    """Where the owner is standing when they need to know.

    "Scan mapping" is the one gesture whose whole point is "tell me what you
    know about the pad in my hands". A pad we cannot name gets no RPCS3 and no
    Dolphin config, and until now the only sign of that was a line in the
    emulator's own log.
    """
    from fastapi.testclient import TestClient

    from backend import main
    monkeypatch.setattr(cp, "detect_pads",
                        lambda *_a, **_k: [(PAD.vendor, PAD.product, PAD.evdev_name)])
    monkeypatch.setattr("backend.services.configgen.detect_pads",
                        lambda *_a, **_k: [(PAD.vendor, PAD.product, PAD.evdev_name)])

    with TestClient(main.app) as client:
        body = client.post("/api/controllers/scan-mapping").json()

    assert body["ok"] is True, (
        f"an unnameable pad is not a failed scan — the GUID-bound emulators "
        f"are fine: {json.dumps(body)}")
    assert body["identified"] is False, json.dumps(body)
    assert PAD.vendor in body["detail"], body["detail"]


def test_the_router_says_nothing_special_about_a_known_pad(box, monkeypatch):
    """The flag must mean something. If it were always false it would be noise
    the first person to see it would learn to ignore."""
    from fastapi.testclient import TestClient

    from backend import main
    pads = [(ch.DS4.vendor, ch.DS4.product, ch.DS4.evdev_name)]
    monkeypatch.setattr(cp, "detect_pads", lambda *_a, **_k: pads)
    monkeypatch.setattr("backend.services.configgen.detect_pads",
                        lambda *_a, **_k: pads)

    with TestClient(main.app) as client:
        body = client.post("/api/controllers/scan-mapping").json()

    assert body["identified"] is True, json.dumps(body)
    assert "detail" not in body
    assert body["controller"] == ch.DS4.sdl3_name
