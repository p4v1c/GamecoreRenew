"""Per-profile saves, core half: the folders, the hook call, the launch gate.

The emulator side (melonDS's own keys) is tested in catalog/melonds/tests.
Every path is under a throwaway data root (`paths.use_roots`).
"""
from __future__ import annotations

import asyncio
import json
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
