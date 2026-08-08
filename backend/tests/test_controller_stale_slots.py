"""Slots that name a controller nobody is holding.

The pipeline wrote on connect and never un-wrote. Measured on the reference
box with ONE DualShock 4 plugged in:

    RPCS3    Player 2 = "Xbox One Controller 1"
             Player 3 = "Xbox One Wireless Controller 2"
             Player 4 = "Xbox One Wireless Controller 3"
    Ryujinx  Player3 = index 2, Player4 = index 3 — indexes with no device
    Dolphin  GCPad4  = SDL/3/PS4 Controller

Two distinct holes produced that, and they need two distinct tests:

  · `release()` existed on ONE generator out of ten. The others were assumed to
    "just go input-less when a pad leaves", which is false — they keep NAMING
    an absent device, and a PS3 game at four then sees four players, two of
    them dead.
  · `_reconcile()` only ever released a slot whose departure it WITNESSED. At
    backend start `was` is empty, so a pad unplugged while the box was off
    produces no departure event at all and its slot is never freed. That is the
    hole a reboot goes through, and it is the one the box was actually in.

No test names a pack. Which emulators must stop naming a device is derived from
`controllers.strategy` in pack.json: the three device-bound strategies below
write a device identity, `sdl-index-clone` binds by SDL index and carries none.
A pack added tomorrow is covered the day it declares its strategy.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.services import controller_profiles as cp        # noqa: E402
from backend.services import controller_registry as reg       # noqa: E402
from backend.services import gamepad_monitor as gm            # noqa: E402
from backend.tests import characterisation as ch              # noqa: E402

# Strategies whose generator writes a DEVICE IDENTITY into the config — a name,
# a GUID, an SDL qualifier. Those are the ones a departure invalidates, and the
# only ones a stale slot can name a ghost through. Read off pack.json, so the
# set follows the catalogue rather than a list kept in a test.
DEVICE_BOUND = {"rewrite-player-block", "rewrite-device-line", "guid-rebind"}


def _packs_by_strategy(wanted: set[str]) -> list[tuple[str, dict]]:
    out = []
    for pack_dir in sorted((ROOT / "catalog").iterdir()):
        meta = pack_dir / "pack.json"
        if pack_dir.name.startswith("_") or not meta.is_file():
            continue
        ctl = (json.loads(meta.read_text()).get("controllers") or {})
        if ctl.get("strategy") in wanted and pack_dir.name in ch.WATCHED:
            out.append((pack_dir.name, ctl))
    return out


DEVICE_BOUND_PACKS = _packs_by_strategy(DEVICE_BOUND)
assert DEVICE_BOUND_PACKS, ("no pack declares a device-bound strategy — the "
                            "catalogue moved, and this file tests nothing")


@pytest.fixture
def box(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    ch.build_tree(home)
    ch.install_stubs(cp, home, monkeypatch)
    return home


def _named_device_counts(home: Path, name: str) -> dict[str, int]:
    """{watched file → how many times the pad's name appears in it}.

    One connected pad may legitimately be named once per file. Anything above
    that is a slot describing a controller that is not there.
    """
    counts: dict[str, int] = {}
    for pack_id, _ctl in DEVICE_BOUND_PACKS:
        for rel in ch.WATCHED[pack_id]:
            p = home / rel
            if p.is_file():
                counts[f"{pack_id}/{Path(rel).name}"] = p.read_text().count(name)
    return counts


# ── the departure the monitor DOES see ───────────────────────────────────────

def test_three_pads_leaving_stop_being_named(box):
    """Four DualShock 4s, then three unplug. Only player 1 may still be named.

    `release()` lived on dolphin alone, so RPCS3 kept "PS4 Controller 2/3/4" in
    players 2-4 and Ryujinx kept three Player entries pointing at indexes that
    no longer resolve. In a PS3 game at four that is four players, two of whom
    cannot move.
    """
    ch.run_scenario(cp, next(s for s in ch.SCENARIOS
                             if s.name == "four-then-one-ds4"))

    counts = _named_device_counts(box, ch.DS4.sdl3_name)
    assert counts, "no device-bound config was produced — the tree is wrong"
    ghosts = {f: n for f, n in counts.items() if n > 1}
    assert not ghosts, (
        f"one pad is connected, but {ch.DS4.sdl3_name!r} is still named more "
        f"than once in {ghosts}. Those are the ghost slots: an emulator asked "
        f"for four players will present pads that left.")


def test_the_multitap_goes_back_off_when_the_players_leave(box):
    """The write with no inverse — and the reason a slot index is not enough.

    `tier0.apply()` turns the pack's multitap key on as soon as a player at or
    above `fromPlayer` arrives, which is required: PCSX2 refuses slot 3 at the
    SIO2 level without it. Nothing ever turned it back off, so every solo
    session after a session at four ran with a virtual accessory on port 1.

    A release that receives only a slot number CANNOT decide this: whether the
    tap is still needed is a property of the whole roster.
    """
    tapped = [(pid, ctl["multitap"]) for pid, ctl in
              _packs_by_strategy({"sdl-index-clone"}) if ctl.get("multitap")]
    assert tapped, "no pack declares a multitap — nothing to assert"

    ch.run_scenario(cp, next(s for s in ch.SCENARIOS
                             if s.name == "four-then-one-ds4"))

    for pack_id, tap in tapped:
        text = (box / ch.WATCHED[pack_id][0]).read_text()
        assert f"{tap['key']} = {tap['value']}" not in text, (
            f"{pack_id}: every player above {tap['fromPlayer']} has left and "
            f"[{tap['section']}] {tap['key']} is still {tap['value']!r}")


# ── the departure the monitor NEVER sees: a reboot ───────────────────────────

class _FakeWS:
    async def broadcast(self, *_a, **_k):
        pass


def _node(path: str, mac: str, pad: ch.Pad):
    return {path: (pad.evdev_name, mac, True, pad.vendor, pad.product, 0x05)}


@pytest.fixture
def registry():
    reg._slots.clear(); reg._labels.clear()
    try:
        yield reg
    finally:
        reg._slots.clear(); reg._labels.clear()


def test_a_backend_restart_with_one_pad_frees_the_other_slots(box, registry,
                                                              monkeypatch):
    """The hole a reboot goes through, and the one the box was sitting in.

    Someone plays at four, powers the box off, unplugs three pads, powers it
    back on. `_reconcile` starts with an empty `was`, so it sees three
    ARRIVALS-that-never-happened rather than three departures: no departure
    event is ever raised and slots 2-4 keep naming pads that are in a drawer.

    Nothing is stubbed below the monitor — the real generators write into the
    real seed tree — because the defect is precisely that the monitor never
    asks them to undo anything.
    """
    monkeypatch.setattr(gm, "_game_running", lambda: False)

    # The session before the reboot: four identical pads, slots 1-4 written.
    for slot in range(1, 5):
        cp.apply_profile(slot, ch.DS4.vendor, ch.DS4.product,
                         ch.DS4.evdev_name, slot - 1)
    before = _named_device_counts(box, ch.DS4.sdl3_name)
    assert any(n >= 4 for n in before.values()), (
        f"the four-player state was not built, so nothing is being cleaned "
        f"up: {before}")

    # Reboot: fresh monitor state, one pad left in the box.
    registry._slots.clear(); registry._labels.clear()
    live = gm.pads_by_key(_node("/dev/input/event20", "84:30:95:07:c8:1c", ch.DS4))
    asyncio.run(gm._reconcile({}, live, {}, True, _FakeWS()))

    after = _named_device_counts(box, ch.DS4.sdl3_name)
    ghosts = {f: n for f, n in after.items() if n > 1}
    assert not ghosts, (
        f"after a restart with a single pad, {ch.DS4.sdl3_name!r} is still "
        f"named more than once in {ghosts}. No departure event was raised, so "
        f"nothing released those slots — that is the reboot hole, and it is "
        f"why the reference box showed four RPCS3 players with one pad.")


def test_a_restart_leaves_the_connected_pad_alone(box, registry, monkeypatch):
    """The other half: the sweep must not free the slot that IS occupied.

    Releasing every slot and re-profiling would also pass the test above while
    being useless — and would rewrite a config the box had right.
    """
    monkeypatch.setattr(gm, "_game_running", lambda: False)
    for slot in range(1, 5):
        cp.apply_profile(slot, ch.DS4.vendor, ch.DS4.product,
                         ch.DS4.evdev_name, slot - 1)

    registry._slots.clear(); registry._labels.clear()
    live = gm.pads_by_key(_node("/dev/input/event20", "84:30:95:07:c8:1c", ch.DS4))
    asyncio.run(gm._reconcile({}, live, {}, True, _FakeWS()))

    counts = _named_device_counts(box, ch.DS4.sdl3_name)
    silent = [f for f, n in counts.items() if n == 0]
    assert not silent, (
        f"player 1 is connected and {silent} name no device at all — the "
        f"sweep freed the occupied slot too, so the pad drives nothing")


# ── the repair that no scenario ever exercised (F-010) ───────────────────────

def test_a_slot_left_unbound_is_rebuilt_from_a_healthy_one(tmp_path, monkeypatch):
    """RPCS3 leaves a slot whose Device matched nothing at `Handler: "Null"`
    with every binding blanked — so the one case that needed repairing was the
    one case the old code returned early on. Players 2-4 sat like that for a
    week on the reference box.

    Every characterisation scenario started from the seed, which ships four
    healthy players, so the damaged state was never built and the repair was
    never run. Replacing `_is_bound()` with `return True`, which disables the
    repair outright, left the whole suite green.
    """
    home = tmp_path / "home"
    home.mkdir()
    scenario = next(s for s in ch.SCENARIOS if s.name == "rpcs3-player-2-null")
    ch.build_tree(home, scenario.before)
    ch.install_stubs(cp, home, monkeypatch)

    messages = ch.run_scenario(cp, scenario)
    text = "\n".join(messages)
    # Qualified with the emulator, and that is not pedantry: `"rebuilt" in
    # text` passed even with the repair disabled, because Dolphin reports
    # "GCPad2 rebuilt from GCPad1" in the same pass. The bare substring made
    # this test vacant — it was green on the very defect it is here to catch,
    # which is the failure mode F-010 is about in the first place.
    assert "rpcs3: Player 2 rebuilt" in text, (
        f"Player 2 was Handler: \"Null\" with empty bindings and RPCS3's slot "
        f"was not rebuilt — the pass reported: {text!r}. A retarget leaves the "
        f"slot dead: the Device line is right and there is nothing behind it.")


def test_the_rebuilt_slot_actually_carries_bindings(tmp_path, monkeypatch):
    """The message is not the point — the bindings are.

    A test asserting only on the word "rebuilt" would stay green if the clone
    copied nothing. This reads the file: the repaired slot must come back with
    the SDL handler and real face buttons, not an empty shell with a correct
    name on it.
    """
    home = tmp_path / "home"
    home.mkdir()
    scenario = next(s for s in ch.SCENARIOS if s.name == "rpcs3-player-2-null")
    ch.build_tree(home, scenario.before)
    ch.install_stubs(cp, home, monkeypatch)
    yml = home / ch.WATCHED["rpcs3"][0]

    sick = yml.read_text()
    assert 'Handler: "Null"' in sick and "Cross: \"\"" in sick, (
        "the input fixture no longer carries the damaged state it exists for")

    ch.run_scenario(cp, scenario)
    block = _rpcs3_block(yml.read_text(), 2)
    assert "Handler: SDL" in block, "Player 2 came back still on the Null handler"
    assert "Cross: South" in block, (
        "Player 2 was renamed but its bindings are still blank — the pad has a "
        "correct device line and no buttons behind it")
    assert f"Device: {ch.DS4.sdl3_name} 1" in block


def _rpcs3_block(text: str, i: int) -> str:
    """The `Player <i> Input:` block. Spelled out here rather than imported
    from the generator: a test that reuses the parser it is checking cannot
    catch the parser being wrong."""
    lines = text.splitlines(keepends=True)
    start = next(n for n, l in enumerate(lines) if l.startswith(f"Player {i} Input:"))
    end = next((n for n in range(start + 1, len(lines))
                if lines[n].startswith("Player ")), len(lines))
    return "".join(lines[start:end])
