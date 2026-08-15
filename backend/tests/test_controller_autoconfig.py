"""The autoconfig switch: what it persists, and what it refuses to lose.

The characterisation suite covers what the pipeline WRITES with the switch in
each position (`autoconfig-off`, `autoconfig-off-dolphin-only`,
`autoconfig-turned-off-after`). This file covers the switch itself — the state
file, the composition rule, and the two things a settings screen has to be able
to say out loud.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.services import controller_autoconfig as ac   # noqa: E402
from backend.services import paths                         # noqa: E402


@pytest.fixture
def state(tmp_path, monkeypatch):
    """The switch, pointed at a throwaway file.

    Through `state_file()` rather than a module constant, which is the reason
    that function exists: a path resolved at import cannot be moved by a test,
    and `test_playtime_repair` spent a while asserting on a repair that had
    quietly stopped finding anything for exactly that reason.
    """
    f = tmp_path / "controller-autoconfig.json"
    monkeypatch.setattr(ac, "state_file", lambda: f)
    return f


# ── the default, and the failure direction ──────────────────────────────────

def test_a_box_that_was_never_asked_is_on(state):
    """No file at all — a fresh install, or a config directory that was lost."""
    assert not state.exists()
    assert ac.enabled() is True
    assert ac.enabled_for("dolphin") is True


def test_a_half_written_file_reads_as_on(state):
    """The power-cut case the tmp+replace write exists to prevent, met from the
    reading side anyway — because the file can also be lost, truncated by a full
    disk, or edited by hand into something that will not parse.

    Failing to ON is the whole rule: a setting whose loss leaves every pad
    unconfigured turns a corrupt 200-byte file into a box where plugging a
    controller in does nothing, with no error and nothing to search for.
    """
    state.write_text('{"enabled": fal')
    assert ac.enabled() is True
    assert ac.enabled_for("rpcs3") is True


def test_a_json_file_that_is_not_an_object_reads_as_on(state):
    state.write_text('["enabled"]')
    assert ac.enabled() is True


def test_a_packs_key_of_the_wrong_shape_does_not_take_the_switch_down(state):
    """Only `packs` is malformed; the global answer beside it is still good and
    must survive. Discarding the whole file over one bad key would turn a typo
    into a silent re-enable of something the owner turned off."""
    state.write_text(json.dumps({"enabled": False, "packs": "dolphin"}))
    assert ac.enabled() is False
    assert ac.enabled_for("dolphin") is False


# ── persistence ─────────────────────────────────────────────────────────────

def test_the_switch_survives_a_restart(state):
    """A restart is a fresh read of the file and nothing else — there is no
    cache to invalidate, which is the point of resolving it per call."""
    ac.set_enabled(False)
    assert json.loads(state.read_text())["enabled"] is False
    assert ac.enabled() is False
    ac.set_enabled(True)
    assert ac.enabled() is True


def test_the_write_is_atomic(state, monkeypatch):
    """tmp + os.replace, not write_text.

    Asserted on the mechanism rather than on the outcome, because the outcome
    of the wrong one is identical every time the power stays on. `write_text`
    truncates and THEN writes; the window between is where themes.json was lost.
    """
    seen = []
    real = ac.os.replace
    monkeypatch.setattr(ac.os, "replace", lambda a, b: (seen.append((a, b)), real(a, b))[1])
    ac.set_enabled(False)
    assert len(seen) == 1
    tmp, dest = seen[0]
    assert str(tmp).endswith(".tmp") and dest == state
    assert not Path(tmp).exists()          # replaced, not left behind


def test_it_lives_under_the_data_root(monkeypatch, tmp_path):
    """A choice the owner made is data, so an OTA into the installation must not
    be able to erase it and a backup of the data root must already carry it."""
    monkeypatch.setattr(paths, "GAMECORE_DATA", tmp_path / "data")
    monkeypatch.setattr(paths, "GAMECORE_ROOT", tmp_path / "code")
    assert (tmp_path / "data") in ac.state_file().parents
    assert (tmp_path / "code") not in ac.state_file().parents


# ── composition: the global switch wins ─────────────────────────────────────

def test_an_exception_carves_one_emulator_out_and_leaves_the_rest(state):
    ac.set_pack("dolphin", False)
    assert ac.enabled_for("dolphin") is False
    assert ac.enabled_for("rpcs3") is True
    assert ac.enabled() is True


def test_the_global_switch_beats_a_pack_that_says_it_is_on(state):
    """The composition rule, stated once here so the UI can restate it.

    Anything else would need a settings screen to explain that a row reading
    "on" means off — and this feature's whole failure mode is a setting nobody
    can read.
    """
    state.write_text(json.dumps({"enabled": False, "packs": {"dolphin": True}}))
    assert ac.enabled_for("dolphin") is False


def test_clearing_an_exception_removes_the_record_rather_than_storing_true(state):
    """"Follows the global switch" stays the ABSENCE of an entry.

    Storing `true` would mean two ways to spell the default, and two spellings
    of a default are two things that can disagree later.
    """
    ac.set_pack("dolphin", False)
    ac.set_pack("dolphin", True)
    assert json.loads(state.read_text())["packs"] == {}


def test_turning_the_global_switch_off_and_on_does_not_resurrect_an_exception(state):
    """The exception was never deleted and was never in force while the global
    switch was off, so it is still there afterwards — which is what somebody who
    set it would expect, and the opposite of what silently dropping it would do."""
    ac.set_pack("dolphin", False)
    ac.set_enabled(False)
    ac.set_enabled(True)
    assert ac.enabled_for("dolphin") is False
    assert ac.enabled_for("rpcs3") is True


# ── the HTTP surface the settings screen talks to ───────────────────────────

@pytest.fixture
def client(state, monkeypatch):
    """A client whose gamepad monitor cannot see the developer's own pad.

    `TestClient` runs the app lifespan, which starts `gamepad_monitor.run()`,
    which scans the REAL /dev/input every three seconds. That matters more than
    it looks here, because `_applied` is module-global and outlives the test: a
    pad found once, profiled into the fake home and left with retries to spare,
    keeps `pending` true for the rest of the session — so the monitor reconciles
    on every pass of every later test, and `test_launch_reconcile`'s counters
    pick up release calls nobody in that test made. Measured: two of its tests
    went red on this machine and only with a controller connected.

    An empty device list gives every box the same run, and the two globals are
    put back afterwards so nothing leaks either way.
    """
    from backend.main import app
    from backend.services import gamepad_monitor as gm

    monkeypatch.setattr(gm, "_find_gamepad_devices", dict)
    applied, dirty = dict(gm._applied), gm._dirty
    try:
        yield TestClient(app)
    finally:
        gm._applied.clear()
        gm._applied.update(applied)
        gm._dirty = dirty


def test_the_screen_is_told_what_is_effectively_off(client, state):
    """`effective` is not `enabled`, and the difference is what stops the screen
    showing rows that read "on" for emulators that are not running."""
    client.post("/api/controllers/autoconfig", json={"enabled": False})
    body = client.get("/api/controllers/autoconfig").json()
    assert body["enabled"] is False
    assert body["packs"], "no emulator profiles pads — the catalogue is wrong"
    assert all(p["effective"] is False for p in body["packs"])
    # Their own rows are untouched: nobody asked for an exception.
    assert all(p["enabled"] is True for p in body["packs"])


def test_an_unknown_emulator_is_refused_before_anything_is_written(client, state):
    got = client.post("/api/controllers/autoconfig",
                      json={"enabled": False, "pack": "nintendo64dd"}).json()
    assert got["ok"] is False
    assert not state.exists(), "a rejected request must not persist anything"


def test_turning_it_back_on_asks_the_monitor_to_start_again(client, state, monkeypatch):
    """"Resume immediately" is the monitor's next pass, at most 3 s away — not
    the next time somebody unplugs a pad. `_reconcile` is the only thing that
    knows the roster, the dup indexes and the slot compaction, so the switch
    asks it to run rather than recomputing them itself."""
    from backend.services import gamepad_monitor

    calls = []
    monkeypatch.setattr(gamepad_monitor, "request_reprofile", lambda: calls.append(1))
    client.post("/api/controllers/autoconfig", json={"enabled": False})
    assert calls == [], "turning it OFF must not re-profile — it cleans up"
    got = client.post("/api/controllers/autoconfig", json={"enabled": True}).json()
    assert calls == [1]
    assert got["reprofiling"] is True


def test_a_reprofile_request_survives_a_pass_where_the_roster_also_changed(
        monkeypatch):
    """The short-circuit bug, asserted directly.

    `was != live or pending or _take_dirty()` reads fine and is wrong: `or`
    stops at the first true operand, so a request arriving on a pass that was
    going to reconcile anyway is never consumed and re-profiles every three
    seconds for the life of the process.
    """
    from backend.services import gamepad_monitor as gm

    applied, dirty = dict(gm._applied), gm._dirty
    try:
        gm.request_reprofile()
        assert gm._take_dirty() is True
        assert gm._take_dirty() is False, "consumed exactly once"
    finally:
        # Both globals restored: `request_reprofile` empties `_applied` on
        # purpose, and a live monitor in a later test would read that as "these
        # pads were never profiled" and profile them again mid-assertion.
        gm._applied.clear()
        gm._applied.update(applied)
        gm._dirty = dirty
