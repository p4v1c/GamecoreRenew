"""Writing one game's settings without touching the next game's.

Everything here runs against a HOME under `tmp_path`. Not as hygiene — as the
thing being tested. `backend/tests/test_home_isolation.py` exists because a
pytest run once rewrote Player 1 of this machine's real RPCS3 config, and this
module writes to the same tree for the same reason: it is the tree emulators
read. Every call below is handed an explicit `home`, and
`test_home_isolation.py` gained a case that fails the build if any pack's
per-game path resolves outside it.

The `.bak-pergame` copies, the restore records and the "did GameCore create
this file" bit are not bookkeeping for its own sake. They are what makes
"the player can remove it" true rather than a button that lies.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.services import pergame  # noqa: E402
from backend.services.catalog import load_catalog  # noqa: E402


def _packs_that_support_it() -> list:
    """Selected from what the catalogue DECLARES, never named.

    A test that said `packs["rpcs3"]` would keep passing on the day rpcs3 lost
    its block and would say nothing about a pack that gained one.
    """
    return sorted((p for p in load_catalog().values()
                   if (p.data.get("perGame") or {}).get("supported")),
                  key=lambda p: p.id)


SUPPORTING = _packs_that_support_it()
assert SUPPORTING, "no pack declares per-game support — every test here is vacuous"

BY_FORMAT: dict[str, object] = {}
for _p in SUPPORTING:
    BY_FORMAT.setdefault(_p.data["perGame"]["format"], _p)
assert len(BY_FORMAT) >= 2, (
    "only one per-game file format is exercised — the writers are the half of "
    "this module most likely to be wrong, and one of them would be untested")


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    h.mkdir()
    return h


def _gid(pack) -> str:
    """A plausible id for this pack's key, without opening a game dump.

    The readers are `test_gameid.py`'s subject; what is under test here is what
    happens to a file once an id exists.
    """
    return {"ps3": "BLES00932", "gcwii": "GALE01", "wiiu": "0005000010143500",
            "playstation": "SLUS-20946", "filename": "somegame"}.get(
                pack.data["perGame"]["key"], "TESTID001")


# ── the promise the phase was written for ────────────────────────────────────

@pytest.mark.parametrize("pack", SUPPORTING, ids=lambda p: p.id)
def test_a_setting_on_one_game_does_not_reach_the_next(pack, home):
    """The whole point, stated as a test.

    Before this module there was one config per emulator, so ticking an option
    for the one title that needs it ticked it for every title on the system.
    Two games, one setting, and the second file must not exist at all.
    """
    one, two = _gid(pack), "OTHERGAME"
    pergame.set_settings(pack.id, one, {"Video": {"Write Color Buffers": True}})
    pergame.materialise_id(pack.id, one, home)

    first = pergame.target(pack.id, one, home)
    second = pergame.target(pack.id, two, home)
    assert first.is_file(), f"{pack.id}: nothing was written for {one}"
    assert first != second, f"{pack.id}: both games resolve to {first}"
    assert not second.is_file(), (
        f"{pack.id}: setting {one} also produced a file for {two}")


@pytest.mark.parametrize("pack", SUPPORTING, ids=lambda p: p.id)
def test_the_settings_survive_the_emulator_being_reinstalled(pack, home):
    """`flatpak uninstall --delete-data` takes `~/.var/app/<id>` with it.

    People run it when an emulator misbehaves, which is exactly when they have
    per-game settings. The record is in <DATA>; the emulator's file is derived,
    and comes back on the next launch.
    """
    gid = _gid(pack)
    pergame.set_settings(pack.id, gid, {"Video": {"Write Color Buffers": True}})
    pergame.materialise_id(pack.id, gid, home)

    import shutil
    shutil.rmtree(home / ".var", ignore_errors=True)
    assert not pergame.target(pack.id, gid, home).is_file()

    pergame.materialise_id(pack.id, gid, home)
    assert pergame.target(pack.id, gid, home).is_file(), (
        f"{pack.id}: the settings did not come back after a reinstall — the "
        f"record in <DATA> is not the source of truth it claims to be")


# ── own-keys ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("fmt,pack", sorted(BY_FORMAT.items()), ids=sorted(BY_FORMAT))
def test_everything_the_player_set_in_the_emulator_survives(fmt, pack, home):
    """The deliberate divergence from Batocera, at the per-game level.

    RPCS3 writes 288 lines into a custom config when the player saves one from
    its own window. Re-emitting that from a parsed structure would reformat
    every line and drop the order the emulator chose; overwriting it would
    throw the settings away outright. Neither is acceptable for the file the
    player is most likely to have edited by hand.
    """
    gid = _gid(pack)
    path = pergame.target(pack.id, gid, home)
    path.parent.mkdir(parents=True, exist_ok=True)
    theirs = ({"ini": "[Video]\nTheirSetting = 42\n\n[Core]\nSomethingElse = keep\n",
               "yaml": "Video:\n  Their Setting: 42\nCore:\n  Something Else: keep\n"}[fmt])
    path.write_text(theirs)

    pergame.set_settings(pack.id, gid, {"Video": {"OursNow": True}})
    pergame.materialise_id(pack.id, gid, home)

    after = path.read_text()
    assert "42" in after and "keep" in after, (
        f"{fmt}: the player's own settings were lost:\n{after}")
    assert "true" in after, f"{fmt}: our setting was not written:\n{after}"


@pytest.mark.parametrize("fmt,pack", sorted(BY_FORMAT.items()), ids=sorted(BY_FORMAT))
def test_a_boolean_is_written_the_way_the_emulator_spells_it(fmt, pack, home):
    """`str(True)` is `True`, which neither format recognises. It would land in
    a real config file as a setting that reads as present and does nothing —
    the failure mode with no symptom at all."""
    gid = _gid(pack)
    pergame.set_settings(pack.id, gid, {"Video": {"Flag": False}})
    pergame.materialise_id(pack.id, gid, home)
    text = pergame.target(pack.id, gid, home).read_text()
    assert "false" in text and "False" not in text, text


@pytest.mark.parametrize("pack", SUPPORTING, ids=lambda p: p.id)
def test_the_file_is_backed_up_before_it_is_overwritten(pack, home):
    gid = _gid(pack)
    path = pergame.target(pack.id, gid, home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[Video]\nTheirs = 1\n")

    pergame.set_settings(pack.id, gid, {"Video": {"Ours": True}})
    pergame.materialise_id(pack.id, gid, home)

    bak = path.with_name(path.name + ".bak-pergame")
    assert bak.is_file() and "Theirs = 1" in bak.read_text()


@pytest.mark.parametrize("pack", SUPPORTING, ids=lambda p: p.id)
def test_a_second_write_does_not_overwrite_the_backup(pack, home):
    """A backup taken twice is a copy of the damage, not a way back from it."""
    gid = _gid(pack)
    path = pergame.target(pack.id, gid, home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[Video]\nTheirs = original\n")

    for value in (True, False):
        pergame.set_settings(pack.id, gid, {"Video": {"Ours": value}})
        pergame.materialise_id(pack.id, gid, home)

    bak = path.with_name(path.name + ".bak-pergame")
    assert "original" in bak.read_text(), (
        "the backup was rewritten by the second pass — it now holds a file "
        "this module had already edited")


# ── removal, which is the half that is easy to get wrong ─────────────────────

@pytest.mark.parametrize("pack", SUPPORTING, ids=lambda p: p.id)
def test_removing_a_setting_takes_the_file_gamecore_created_with_it(pack, home):
    gid = _gid(pack)
    pergame.set_settings(pack.id, gid, {"Video": {"Ours": True}})
    pergame.materialise_id(pack.id, gid, home)
    assert pergame.target(pack.id, gid, home).is_file()

    pergame.release(pack.id, gid, home)
    assert not pergame.target(pack.id, gid, home).is_file()
    assert not pergame.record(pack.id, gid).get("settings")


@pytest.mark.parametrize("fmt,pack", sorted(BY_FORMAT.items()), ids=sorted(BY_FORMAT))
def test_removing_a_setting_does_not_delete_a_file_the_player_owns(fmt, pack, home):
    """Undo has to be the size of the thing it undoes.

    If the file was already there it holds settings made in the emulator's own
    window. Deleting it to retract one profile is a far larger act than the one
    the player asked for, and they would have no way of knowing it happened
    until the game next behaved differently.
    """
    gid = _gid(pack)
    path = pergame.target(pack.id, gid, home)
    path.parent.mkdir(parents=True, exist_ok=True)
    theirs = ({"ini": "[Video]\nTheirSetting = 42\n",
               "yaml": "Video:\n  Their Setting: 42\n"}[fmt])
    path.write_text(theirs)

    pergame.set_settings(pack.id, gid, {"Video": {"Ours": True}})
    pergame.materialise_id(pack.id, gid, home)
    pergame.release(pack.id, gid, home)

    assert path.is_file(), f"{fmt}: the player's own file was deleted"
    after = path.read_text()
    assert "42" in after, f"{fmt}: the player's own setting went with ours:\n{after}"
    assert "Ours" not in after, f"{fmt}: our setting outlived its removal:\n{after}"


@pytest.mark.parametrize("fmt,pack", sorted(BY_FORMAT.items()), ids=sorted(BY_FORMAT))
def test_removing_a_setting_puts_back_the_value_it_displaced(fmt, pack, home):
    """Not "delete the key" — restore it. The emulator's own default and the
    value the player deliberately chose are different things, and a removal
    that flattens both into "absent" silently discards the second."""
    gid = _gid(pack)
    path = pergame.target(pack.id, gid, home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text({"ini": "[Video]\nShared = theirs\n",
                     "yaml": "Video:\n  Shared: theirs\n"}[fmt])

    pergame.set_settings(pack.id, gid, {"Video": {"Shared": "ours"}})
    pergame.materialise_id(pack.id, gid, home)
    assert "ours" in path.read_text()

    pergame.release(pack.id, gid, home)
    assert "theirs" in path.read_text(), (
        f"{fmt}: the displaced value was not restored:\n{path.read_text()}")


@pytest.mark.parametrize("fmt,pack", sorted(BY_FORMAT.items()), ids=sorted(BY_FORMAT))
def test_writing_twice_does_not_make_our_own_value_the_thing_to_restore(fmt, pack, home):
    """The record is taken ONCE, on the first write.

    A second pass that recorded the current value would record OUR value as
    "what was there before", and the undo would then restore the thing it was
    undoing. Two launches is all it takes, so on a real box this would never
    have worked and the first pass would always have looked fine.
    """
    gid = _gid(pack)
    path = pergame.target(pack.id, gid, home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text({"ini": "[Video]\nShared = theirs\n",
                     "yaml": "Video:\n  Shared: theirs\n"}[fmt])

    for value in ("ours", "ours-again"):
        pergame.set_settings(pack.id, gid, {"Video": {"Shared": value}})
        pergame.materialise_id(pack.id, gid, home)

    pergame.release(pack.id, gid, home)
    assert "theirs" in path.read_text(), (
        f"{fmt}: restore put back {path.read_text()!r} — our own earlier value")


# ── refusing, rather than half-doing ─────────────────────────────────────────

def test_a_system_that_declares_no_support_writes_nothing_and_says_why():
    unsupported = [p for p in load_catalog().values()
                   if p.data.get("perGame") and not p.data["perGame"]["supported"]]
    assert unsupported, "no pack declares perGame unsupported — nothing to check"
    for pack in unsupported:
        assert not pergame.supported(pack.id)
        assert pergame.identify(pack.id, Path("/nonexistent/game.iso")) is None
        assert pergame.unsupported_reason(pack.id), (
            f"{pack.id} cannot do this and offers no sentence explaining it — "
            f"an empty panel and an impossible feature look identical from a sofa")


@pytest.mark.parametrize("pack", SUPPORTING, ids=lambda p: p.id)
def test_a_game_id_that_is_not_a_file_name_is_refused(pack, monkeypatch, tmp_path):
    """The id comes out of a file the player downloaded.

    Every reader constrains its output today, so this rejects nothing — which
    is why it is here. A reader added later that forgets must not be the thing
    that gets to name a path, and `../../../..` in a PARAM.SFO is a container
    holding what it was built to hold.
    """
    from backend.services import gameid
    monkeypatch.setattr(gameid, "identify", lambda _s, _r: "../../../etc/passwd")
    assert pergame.identify(pack.id, tmp_path / "game.iso") is None


@pytest.mark.parametrize("pack", SUPPORTING, ids=lambda p: p.id)
def test_an_unwritable_config_tree_costs_the_settings_and_not_the_launch(pack, home):
    """A per-game config is an improvement on a working system, never a
    precondition of it. This runs in front of a game starting."""
    gid = _gid(pack)
    path = pergame.target(pack.id, gid, home)
    # A file where the directory has to go: every mkdir and write below it
    # fails, which is the shape of a read-only or exhausted home.
    path.parent.parent.mkdir(parents=True, exist_ok=True)
    path.parent.write_text("not a directory")

    pergame.set_settings(pack.id, gid, {"Video": {"Ours": True}})
    assert pergame.materialise_id(pack.id, gid, home) is None


def test_a_record_that_cannot_be_parsed_is_a_game_with_no_settings(home):
    pack = SUPPORTING[0]
    gid = _gid(pack)
    p = pergame.record_path(pack.id, gid)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{ this is not json")
    assert pergame.record(pack.id, gid) == {}
    assert pergame.materialise_id(pack.id, gid, home) is None


def test_the_record_lands_under_the_data_root_and_not_the_installation():
    """`<DATA>` is what a backup copies and what the OTA rsync leaves alone.
    Under the code root it would be wiped by the next update."""
    from backend.services import paths
    p = pergame.record_path("rpcs3", "BLES00932")
    assert paths.pergame_dir() in p.parents
    assert paths.GAMECORE_DATA in p.parents


def test_json_records_are_written_whole_or_not_at_all(home):
    """Through a temp file in the same directory, like every other player-owned
    document on this box. A power cut mid-write must not leave a truncated JSON
    that takes the game's settings with it."""
    pack = SUPPORTING[0]
    gid = _gid(pack)
    pergame.set_settings(pack.id, gid, {"Video": {"Ours": True}})
    written = json.loads(pergame.record_path(pack.id, gid).read_text())
    assert written["settings"]["Video"]["Ours"] is True
