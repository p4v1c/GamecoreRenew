"""Per-profile saves, core half: the folders, the hook call, the launch gate.

The emulator side (melonDS's own keys) is tested in catalog/melonds/tests.
Every path is under a throwaway data root (`paths.use_roots`).
"""
from __future__ import annotations

import asyncio
import json
import time
import types
from pathlib import Path

import pytest

from backend.services import configgen, paths, profile_saves, profiles
from backend.services import launch as launch_service
from backend.services.catalog import load_catalog, load_schema, validate
from backend.services.errors import ServiceError


@pytest.fixture
def data(tmp_path):
    before = (paths.GAMECORE_ROOT, paths.GAMECORE_DATA)
    paths.use_roots(tmp_path / "code", tmp_path / "data")
    yield tmp_path / "data"
    paths.use_roots(*before)


CATALOG = Path(__file__).resolve().parents[2] / "catalog"
PRIMARY = {"id": "aaaa", "primary": True}
SAM = {"id": "b0b0", "primary": False}
ANA = {"id": "a1a1", "primary": False}


def test_the_primary_profile_keeps_the_emulator_default(data):
    assert profile_saves.player_dirs([PRIMARY], "melonds", "per-instance") == [None] * 4
    assert not paths.profile_saves_dir().exists(), "nothing created for it"


def test_another_profile_gets_its_own_folder_created_under_the_data_root(data):
    dirs = profile_saves.player_dirs([SAM], "melonDS", "per-instance")
    assert dirs[0] == data / "emu" / "profile-saves" / "b0b0" / "melonds"
    assert dirs[0].is_dir()
    assert dirs[1:] == [None, None, None], "players 2-4 stay as before"


def test_two_profiles_never_share_a_folder(data):
    (sam,) = profile_saves.player_dirs([SAM], "melonds", "p1")[:1]
    (ana,) = profile_saves.player_dirs([ANA], "melonds", "p1")[:1]
    assert sam != ana and not sam.is_relative_to(ana) and not ana.is_relative_to(sam)
    assert not sam.is_relative_to(paths.roms_root() / "melonds"), "never beside the ROMs"


def test_p1_mode_gives_players_two_to_four_nothing(data):
    dirs = profile_saves.player_dirs([SAM, ANA], "melonds", "p1")
    assert dirs[1:] == [None, None, None]
    assert profile_saves.player_dirs([SAM, ANA], "melonds", "per-instance")[1] is not None


def test_a_hand_edited_id_cannot_leave_the_root(data):
    with pytest.raises(ServiceError):
        profile_saves.player_dirs([{"id": "../../etc", "primary": False}], "melonds", "p1")


def _fake_pack(monkeypatch, hook_module, declared="per-instance", target=None):
    pack = types.SimpleNamespace(id="testpack", data={"label": "Test", "profileSaves": declared})
    monkeypatch.setattr(profile_saves, "load_catalog", lambda: {"testpack": pack})
    monkeypatch.setattr(configgen, "load_generator", lambda p: hook_module)
    monkeypatch.setattr(configgen, "generator_opts", lambda *a: {"target": target})


def test_place_hands_the_active_profile_folder_to_the_pack(data, monkeypatch):
    seen = {}
    _fake_pack(monkeypatch, types.SimpleNamespace(place_saves=lambda **kw: seen.update(kw)))
    profiles.update(profiles.active()["id"], {"name": "Max"})
    sam = profiles.create("Sam")
    profiles.set_active(sam["id"])
    dirs = profile_saves.place("testpack")
    assert seen["dirs"] == dirs and dirs[0] == paths.profile_saves_dir() / sam["id"] / "testpack"
    assert seen["root"] == paths.profile_saves_dir()


def test_a_pack_that_declares_nothing_is_never_called(data, monkeypatch):
    called = []
    _fake_pack(monkeypatch, types.SimpleNamespace(place_saves=lambda **kw: called.append(kw)),
               declared=None)
    assert profile_saves.place("testpack") is None and called == []


def test_a_declared_pack_without_the_hook_is_an_error(data, monkeypatch):
    _fake_pack(monkeypatch, types.SimpleNamespace())
    with pytest.raises(ServiceError):
        profile_saves.place("testpack")


def test_a_failed_placement_refuses_the_launch(monkeypatch):
    sent = []

    async def broadcast(event, payload):
        sent.append(event)

    def broken(_system_id):
        raise OSError("read-only")

    monkeypatch.setattr(launch_service.ws, "broadcast", broadcast)
    monkeypatch.setattr(profile_saves, "place", broken)
    with pytest.raises(launch_service.LaunchRefused):
        asyncio.run(launch_service._place_profile_saves("melonds", "game"))
    assert sent == ["game:failed"]


def test_the_schema_takes_the_implemented_modes_only():
    schema = load_schema(CATALOG / "_schema" / "pack.schema.json")
    pack = json.loads((CATALOG / "melonds" / "pack.json").read_text())
    assert validate(pack, schema) == []
    for mode in ("per-slot", "native-users", "everything"):
        assert validate({**pack, "profileSaves": mode}, schema)


def test_every_pack_that_separates_saves_can_place_them():
    declared = [p for p in load_catalog().values() if profile_saves.mode(p)]
    assert declared, "melonDS declares per-instance"
    for pack in declared:
        assert hasattr(configgen.load_generator(pack), "place_saves"), pack.id


def test_settings_learn_which_systems_separate_saves():
    assert "Nintendo DS" in profile_saves.separate_systems(load_catalog())


def test_release_hands_every_player_back_to_the_default(data, monkeypatch):
    """After the game, so the emulator started from Desktop Mode saves where it always did."""
    seen = {}
    _fake_pack(monkeypatch, types.SimpleNamespace(place_saves=lambda **kw: seen.update(kw)))
    assert profile_saves.release("testpack", started=time.time())
    assert seen["dirs"] == [None] * configgen.MAX_PLAYERS


def test_release_leaves_a_later_launch_alone(data, monkeypatch):
    """The end of game A can be seen after game B placed its saves: resetting
    them then would send B's progress to the primary profile."""
    calls = []
    _fake_pack(monkeypatch, types.SimpleNamespace(place_saves=lambda **kw: calls.append(kw["dirs"])))
    profiles.update(profiles.active()["id"], {"name": "Max"})
    profiles.set_active(profiles.create("Sam")["id"])
    game_a_started = time.time() - 60
    profile_saves.place("testpack")
    assert profile_saves.release("testpack", started=game_a_started) is False
    assert calls[-1][0] is not None, "Sam's folder stays"


def test_the_end_of_a_game_releases_its_saves(monkeypatch):
    from backend.services import process_manager as pm
    released = []
    monkeypatch.setattr(profile_saves, "release", lambda sid, started: released.append((sid, started)))
    profile_saves.release_session(pm.Session(game_key="mario.nds", system_id="melonds", start_time=12.0))
    profile_saves.release_session(pm.Session(game_key="stremio", system_id="stremio"))
    assert released == [("melonds", 12.0)], "an app keeps no profile save"
