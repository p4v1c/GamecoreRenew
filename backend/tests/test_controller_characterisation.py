"""Characterisation: what the controller pipeline writes today, locked in.

The gate before phase 4 touches `controller_profiles.py`. Fourteen scenarios
across three pad families and four slots, each producing byte-exact fixtures
committed next to the pack they belong to.

    pytest backend/tests/test_controller_characterisation.py

To regenerate after a DELIBERATE behaviour change — and only then:

    GAMECORE_UPDATE_FIXTURES=1 pytest backend/tests/test_controller_characterisation.py

A diff here is a bug in the refactor until argued otherwise against one of the
invariants in docs/architecture/08-controller-pipeline.md. That is the whole
point of the file: the logic is being MOVED, not changed.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.services import controller_profiles as cp   # noqa: E402
from backend.tests import characterisation as ch          # noqa: E402

UPDATE = os.environ.get("GAMECORE_UPDATE_FIXTURES") == "1"


@pytest.fixture
def box(request, tmp_path, monkeypatch):
    """A fresh install: every seed deployed, SDL deterministic.

    A parametrised scenario declaring `before` gets its input fixture laid over
    the seeds — the seeds describe a fresh install and must keep doing so, so a
    damaged starting state belongs to the scenario, not to the catalogue.
    """
    home = tmp_path / "home"
    home.mkdir()
    scenario = getattr(request.node, "callspec", None)
    before = getattr(scenario.params.get("scenario"), "before", None) if scenario else None
    ch.build_tree(home, before)
    ch.install_stubs(cp, home, monkeypatch)
    return home


@pytest.mark.parametrize("scenario", ch.SCENARIOS, ids=lambda s: s.name)
def test_scenario_matches_its_fixtures(box, scenario):
    ch.run_scenario(cp, scenario)
    produced = ch.snapshot(box)

    mismatches: list[str] = []
    for pack_id, files in produced.items():
        d = ch.fixture_dir(pack_id, scenario.name)
        for name, text in files.items():
            expected = d / name
            if UPDATE:
                d.mkdir(parents=True, exist_ok=True)
                expected.write_text(text, encoding="utf-8")
                continue
            if not expected.is_file():
                mismatches.append(f"{pack_id}/{name}: no fixture "
                                  f"(run with GAMECORE_UPDATE_FIXTURES=1)")
                continue
            want = expected.read_text(encoding="utf-8")
            if want != text:
                import difflib
                diff = "\n".join(list(difflib.unified_diff(
                    want.splitlines(), text.splitlines(),
                    f"fixture/{pack_id}/{name}", "produced", lineterm=""))[:30])
                mismatches.append(f"{pack_id}/{name} diverged:\n{diff}")
    if UPDATE:
        pytest.skip("fixtures regenerated")
    assert mismatches == [], "\n\n".join(mismatches)


@pytest.mark.parametrize("scenario", ch.SCENARIOS, ids=lambda s: s.name)
def test_scenario_messages_match(box, scenario):
    """The messages matter as much as the files: they are what reaches the TV
    toast and the journal, and a `Skip` that stops being reported is how a
    give-up became indistinguishable from a success."""
    messages = ch.run_scenario(cp, scenario)
    text = "\n".join(messages) + "\n"
    expected = ch.CATALOG / "_characterisation" / f"{scenario.name}.messages"
    if UPDATE:
        expected.parent.mkdir(parents=True, exist_ok=True)
        expected.write_text(text, encoding="utf-8")
        pytest.skip("fixtures regenerated")
    assert expected.is_file(), f"no message fixture for {scenario.name}"
    assert expected.read_text(encoding="utf-8") == text


# ── the invariants, asserted directly on the produced output ───────────────

def test_the_numeric_suffix_is_not_the_player_number(box):
    """Invariant 2, the one a homogeneous test cannot catch.

    RPCS3 counts devices by SHARED NAME, 1-based; Dolphin uses SDL/<k>/ with a
    per-name 0-based <k>. A lone DualShock 4 is therefore "PS4 Controller 1"
    and SDL/0/ even when it is Player 2.
    """
    ch.run_scenario(cp, next(s for s in ch.SCENARIOS if s.name == "ds4-in-slot-2"))
    snap = ch.snapshot(box)
    assert "Device: PS4 Controller 1" in snap["rpcs3"]["Default.yml"]
    assert "Device = SDL/0/PS4 Controller" in snap["dolphin"]["GCPadNew.ini"]


def test_a_mixed_roster_gives_both_pads_index_zero(box):
    """The mixed-model case. Two DS4s are 'PS4 Controller 1' and '2'; a DS4
    plus an Xbox pad are both the FIRST of their name."""
    ch.run_scenario(cp, next(s for s in ch.SCENARIOS if s.name == "two-mixed"))
    yml = ch.snapshot(box)["rpcs3"]["Default.yml"]
    assert "Device: PS4 Controller 1" in yml
    assert "Device: Xbox One Controller 1" in yml


def test_two_identical_pads_are_numbered_apart(box):
    ch.run_scenario(cp, next(s for s in ch.SCENARIOS if s.name == "two-ds4"))
    yml = ch.snapshot(box)["rpcs3"]["Default.yml"]
    assert "Device: PS4 Controller 1" in yml
    assert "Device: PS4 Controller 2" in yml


def test_slot_three_enables_the_multitap(box):
    """Invariant 7. PS1 and PS2 have two physical ports: PCSX2 refuses slot 3+
    at the SIO2 level while IsMultitapPortEnabled(port) is false, and
    DuckStation only wires Pad1/Pad2 while MultitapMode is Disabled. Writing
    [Pad3] without the tap promises a third player who can never move."""
    ch.run_scenario(cp, next(s for s in ch.SCENARIOS if s.name == "slot-3-only"))
    snap = ch.snapshot(box)
    assert "MultitapPort1 = true" in snap["pcsx2"]["PCSX2.ini"]
    assert "MultitapMode = Port1Only" in snap["duckstation"]["settings.ini"]


def test_slots_one_and_two_do_not_enable_the_multitap(box):
    """The other half: a two-player session must not gain a virtual accessory."""
    ch.run_scenario(cp, next(s for s in ch.SCENARIOS if s.name == "two-mixed"))
    snap = ch.snapshot(box)
    assert "MultitapPort1 = true" not in snap["pcsx2"]["PCSX2.ini"]
    assert "MultitapMode = Port1Only" not in snap["duckstation"]["settings.ini"]


def test_ryujinx_uses_the_guid_its_own_sdl2_reports(box):
    """Invariant 4. The GUID carries bus, version and driver signature, so it
    is read from the emulator's bundled SDL2 and converted — never derived from
    a vendor:product. Measured: the host says bus 0x05 for a Bluetooth DS4,
    Ryujinx's own SDL2 says 0x03."""
    ch.run_scenario(cp, next(s for s in ch.SCENARIOS if s.name == "one-ds4"))
    cfg = ch.snapshot(box)["ryujinx"]["Config.json"]
    assert '"0-00000003-054c-0000-cc09-000000006800"' in cfg
    assert "00000005-054c" not in cfg, "the host's bus byte must not survive"


def test_single_player_emulators_ignore_slots_above_one(box):
    """Invariant 5. azahar, mgba, Cemu and melonDS are single-player here:
    only slot 1 is ever touched, whatever player index arrives."""
    before = (box / ch.SEED_DEST["melonds"] / "melonDS.toml").read_text()
    ch.run_scenario(cp, next(s for s in ch.SCENARIOS if s.name == "slot-4-only"))
    after = (box / ch.SEED_DEST["melonds"] / "melonDS.toml").read_text()
    assert before == after


def test_running_twice_writes_nothing_the_second_time(box):
    """"Run the profiler twice and diff" — every writer must be a no-op on the
    second pass. `_ryujinx` was not, and rewrote 11 KB on every connection."""
    one = next(s for s in ch.SCENARIOS if s.name == "one-ds4")
    ch.run_scenario(cp, one)
    first = ch.snapshot(box)
    ch.run_scenario(cp, one)
    assert ch.snapshot(box) == first


def test_releasing_player_two_does_not_disturb_player_one(box):
    """release_profile resets the leaving slot and only that slot."""
    ch.run_scenario(cp, next(s for s in ch.SCENARIOS if s.name == "two-mixed"))
    p1_before = cp.section(
        (box / ch.SEED_DEST["dolphin"] / "GCPadNew.ini").read_text(), "GCPad1")
    cp.release_profile(2)
    p1_after = cp.section(
        (box / ch.SEED_DEST["dolphin"] / "GCPadNew.ini").read_text(), "GCPad1")
    assert p1_before == p1_after
