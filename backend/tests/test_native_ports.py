"""Native ports: an executable `*.sh` in any system's ROM folder is a game,
launched as is, its declared save folders following the active profile.

Every path is under a throwaway data root (`paths.use_roots`) and home.
"""
from __future__ import annotations

import asyncio
import os
import shlex
import time
from pathlib import Path

import pytest

from backend.routers.games import scan_roms
from backend.services import configgen, native_ports, paths, profile_saves, profiles
from backend.services import launch as launch_service
from backend.services.errors import ServiceError
from backend.services.rom_scanner import iter_rom_files


@pytest.fixture
def data(tmp_path, monkeypatch):
    before = (paths.GAMECORE_ROOT, paths.GAMECORE_DATA)
    paths.use_roots(tmp_path / "code", tmp_path / "data")
    monkeypatch.setattr(configgen, "HOME", tmp_path / "home")
    yield tmp_path / "data"
    paths.use_roots(*before)


def _script(folder: Path, name: str, *save_lines: str, executable: bool = True) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    header = "".join(f"# gamecore-saves: {line}\n" for line in save_lines)
    path.write_text(f"#!/bin/sh\n{header}exec true\n")
    path.chmod(0o755 if executable else 0o644)
    return path


def _second_profile() -> dict:
    profiles.update(profiles.active()["id"], {"name": "Max"})
    sam = profiles.create("Sam")
    profiles.set_active(sam["id"])
    return sam


# ── scan ─────────────────────────────────────────────────────────────────────

def test_an_executable_script_is_a_game_in_a_folder_system(tmp_path):
    roms = tmp_path / "rpcs3"
    (roms / "God of War 3").mkdir(parents=True)
    _script(roms, "Uncharted 2.sh")
    names = [f.name for f in iter_rom_files(roms, [], scan_dirs=True)]
    assert names == ["God of War 3", "Uncharted 2.sh"]


def test_a_script_is_listed_whatever_extensions_the_system_scans(tmp_path):
    roms = tmp_path / "n64"
    _script(roms, "Majora's Mask.sh")
    (roms / "mario.z64").write_bytes(b"")
    assert [f.name for f in iter_rom_files(roms, ["*.z64"])] == ["Majora's Mask.sh", "mario.z64"]


def test_a_script_without_the_executable_bit_is_not_listed(tmp_path):
    """rom-manager writes uploads 0644: a file sent over the LAN never runs."""
    roms = tmp_path / "rpcs3"
    _script(roms, "upload.sh", executable=False)
    assert list(iter_rom_files(roms, [], scan_dirs=True)) == []


def test_the_tile_shows_the_name_without_the_script_extension(tmp_path):
    roms = tmp_path / "rpcs3"
    _script(roms, "Uncharted 2.sh")
    (game,) = scan_roms(roms, [], scan_dirs=True, system_id="rpcs3")
    assert (game["display_name"], game["ext"]) == ("Uncharted 2", "")


# ── header ───────────────────────────────────────────────────────────────────

def test_the_header_declares_save_folders_with_home_and_relative_paths(tmp_path):
    home = tmp_path / "home"
    script = _script(tmp_path / "emu" / "rpcs3", "U.sh",
                     "~/.local/share/bbport/user/savedata/1/CUSA00900",
                     "@HOME@/saves", "/abs/Saves", "../ports/U/save", "/abs/Saves")
    assert native_ports.declared_saves(script, home) == [
        home / ".local/share/bbport/user/savedata/1/CUSA00900",
        home / "saves",
        Path("/abs/Saves"),
        tmp_path / "emu" / "ports" / "U" / "save",
    ]


def test_a_script_without_declarations_declares_nothing(tmp_path):
    assert native_ports.declared_saves(_script(tmp_path, "a.sh"), tmp_path) == []


def test_two_folders_with_one_name_get_two_profile_folders():
    a = native_ports.profile_folder_name(Path("/x/saves"))
    b = native_ports.profile_folder_name(Path("/y/saves"))
    assert a != b and a.startswith("saves-") and b.startswith("saves-")


# ── saves ────────────────────────────────────────────────────────────────────

def test_the_primary_profile_leaves_the_save_folder_alone(data):
    saves = configgen.HOME / "game" / "savedata"
    (saves / "slot1").mkdir(parents=True)
    script = _script(data / "emu" / "rpcs3", "U.sh", str(saves))
    assert profile_saves.place("rpcs3", str(script)) == [None] * configgen.MAX_PLAYERS
    assert saves.is_dir() and not saves.is_symlink()


def test_another_profile_gets_its_own_folder_then_the_primary_gets_its_back(data):
    saves = configgen.HOME / "game" / "savedata"
    (saves / "slot1").mkdir(parents=True)
    script = _script(data / "emu" / "rpcs3", "U.sh", str(saves))
    sam = _second_profile()
    dirs = profile_saves.place("rpcs3", str(script))
    target = (paths.profile_saves_dir() / sam["id"] / "rpcs3" / "ports"
              / native_ports.profile_folder_name(saves))
    assert dirs[0] == paths.profile_saves_dir() / sam["id"] / "rpcs3"
    assert saves.is_symlink() and Path(os.readlink(saves)) == target
    assert not (saves / "slot1").exists(), "Sam starts from an empty save"
    assert profile_saves.release("rpcs3", started=time.time(), rom_path=str(script))
    assert not saves.is_symlink() and (saves / "slot1").is_dir()


def test_a_missing_save_folder_refuses_rather_than_mixing_saves(data):
    script = _script(data / "emu" / "rpcs3", "U.sh", str(configgen.HOME / "never-run"))
    _second_profile()
    with pytest.raises(ServiceError, match="primary profile first"):
        profile_saves.place("rpcs3", str(script))


def test_a_declared_file_is_refused(data):
    save = configgen.HOME / "save.bin"
    save.parent.mkdir(parents=True)
    save.write_bytes(b"x")
    script = _script(data / "emu" / "n64", "M.sh", str(save))
    _second_profile()
    with pytest.raises(ServiceError):
        profile_saves.place("n64", str(script))
    assert not save.is_symlink()


def test_a_script_without_declarations_launches_with_shared_saves(data):
    script = _script(data / "emu" / "rpcs3", "U.sh")
    _second_profile()
    assert profile_saves.place("rpcs3", str(script))[0] is not None
    assert not (paths.profile_saves_dir() / ".primary.json").exists()


def test_a_port_never_touches_the_emulator_saves(data, monkeypatch):
    called = []
    monkeypatch.setattr(profile_saves, "_declared", lambda *a: called.append(a))
    script = _script(data / "emu" / "rpcs3", "U.sh")
    _second_profile()
    profile_saves.place("rpcs3", str(script))
    profile_saves.release("rpcs3", started=time.time(), rom_path=str(script))
    assert called == []


def test_a_late_release_does_not_undo_the_next_port_sharing_the_folder(data):
    """Uncharted 1-3: one collection, one save folder, three scripts."""
    saves = configgen.HOME / "Saves" / "CUSA02343"
    saves.mkdir(parents=True)
    u1 = _script(data / "emu" / "rpcs3", "Uncharted 1.sh", str(saves))
    u2 = _script(data / "emu" / "rpcs3", "Uncharted 2.sh", str(saves))
    _second_profile()
    u1_started = time.time() - 10
    profile_saves.place("rpcs3", str(u2))
    assert profile_saves.release("rpcs3", started=u1_started, rom_path=str(u1)) is False
    assert saves.is_symlink(), "Uncharted 2 is still on Sam's save"


# ── launch ───────────────────────────────────────────────────────────────────

def _stub_launch(monkeypatch, spawned: list):
    async def nothing(*_a, **_k):
        return None

    async def spawn(_system, _sid, rom_path, exec_path, exec_args, _key, **_k):
        spawned.append([exec_path, *shlex.split(exec_args), rom_path])
        return False

    def emulator_only(*_a, **_k):
        raise AssertionError("an emulator step ran for a native port")

    monkeypatch.setattr(launch_service.standby, "exit_standby", nothing)
    monkeypatch.setattr(launch_service, "_await_controller_profiles", nothing)
    monkeypatch.setattr(launch_service, "_spawn", spawn)
    for step in ("_gates", "_prepare", "_pack_launch_command", "_start_background_tasks"):
        monkeypatch.setattr(launch_service, step, emulator_only)


def _system(data: Path) -> dict:
    return {"id": "rpcs3", "path": "flatpak", "args": "run @APPID@",
            "romsPath": str(data / "emu" / "rpcs3")}


def test_a_port_runs_its_script_and_skips_the_emulator(data, monkeypatch):
    spawned: list = []
    _stub_launch(monkeypatch, spawned)
    script = _script(data / "emu" / "rpcs3", "Uncharted 2.sh")
    result = asyncio.run(launch_service.launch(_system(data), "rpcs3", str(script), ""))
    assert result["game_key"] == "Uncharted 2.sh"
    assert spawned == [[native_ports.ENV_BIN, str(script)]], "primary: no saves dir"


def test_another_profile_hands_the_script_its_saves_dir(data, monkeypatch):
    spawned: list = []
    _stub_launch(monkeypatch, spawned)
    script = _script(data / "emu" / "rpcs3", "Uncharted 2.sh")
    sam = _second_profile()
    asyncio.run(launch_service.launch(_system(data), "rpcs3", str(script), ""))
    saves_dir = paths.profile_saves_dir() / sam["id"] / "rpcs3" / "ports" / "Uncharted 2"
    assert spawned == [[native_ports.ENV_BIN, f"GAMECORE_SAVES_DIR={saves_dir}", str(script)]]
    assert saves_dir.is_dir()


def test_a_port_outside_the_system_folder_is_refused(data, monkeypatch):
    _stub_launch(monkeypatch, [])
    script = _script(data / "elsewhere", "evil.sh")
    with pytest.raises(launch_service.LaunchRefused) as e:
        asyncio.run(launch_service.launch(_system(data), "rpcs3", str(script), ""))
    assert e.value.status == 403


def test_a_script_inside_a_game_folder_is_not_run(data, monkeypatch):
    """The library lists top-level scripts only; a PS3 dump's own file stays
    the emulator's, so the launch takes the emulator path."""
    _stub_launch(monkeypatch, [])
    script = _script(data / "emu" / "rpcs3" / "God of War 3", "tool.sh")
    with pytest.raises(AssertionError, match="emulator step"):
        asyncio.run(launch_service.launch(_system(data), "rpcs3", str(script), ""))


def test_the_end_of_a_session_releases_by_script_only_for_a_port(monkeypatch):
    from backend.services import process_manager as pm
    released = []
    monkeypatch.setattr(profile_saves, "release",
                        lambda sid, started, rom_path="": released.append(rom_path))
    profile_saves.release_session(pm.Session(system_id="rpcs3", rom_path="/r/U.sh",
                                             exec_path=native_ports.ENV_BIN, game_key="U.sh"))
    profile_saves.release_session(pm.Session(system_id="rpcs3", rom_path="/r/G/tool.sh",
                                             exec_path="flatpak", game_key="G"))
    assert released == ["/r/U.sh", ""]
