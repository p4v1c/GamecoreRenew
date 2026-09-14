"""The one Store stage permitted to publish into a synthetic ROM library."""
from __future__ import annotations

import errno
import os
from dataclasses import dataclass
from pathlib import Path

import pytest

from backend.routers import games
from backend.services import paths
from backend.services.store import importer
from backend.services.store.importer import ImportError, import_shape
from backend.services.store.transformer import SHAPE_DIR, Shape

JOB_ID = "e" * 32


@dataclass(frozen=True)
class Job:
    id: str = JOB_ID
    system_id: str = "nes"
    roms_dir: str = "emu/nes"


@pytest.fixture
def work(tmp_path, monkeypatch) -> Path:
    monkeypatch.setattr(paths, "GAMECORE_DATA", tmp_path)
    root = tmp_path / "store" / "jobs" / JOB_ID
    (root / SHAPE_DIR).mkdir(parents=True)
    return root


def shape(work: Path, cls: str) -> Shape:
    root = work / SHAPE_DIR
    return Shape(cls, root, tuple(p.name for p in root.iterdir()))


@pytest.mark.parametrize("cls", list("ABCDE"))
def test_classes_a_to_e_land_flat_and_the_work_copy_is_removed(work, cls):
    produced = work / SHAPE_DIR / "Game.nes"
    produced.write_bytes(b"NES\x1a complete")
    (work / "download.zip").write_bytes(b"source kept only until success")

    result = import_shape(Job(), shape(work, cls))

    assert result.names == ("Game.nes",)
    assert (work.parents[2] / "emu" / "nes" / "Game.nes").read_bytes() == \
        b"NES\x1a complete"
    assert not work.exists(), "success must not retain a second large copy"
    assert not (work.parents[2] / "emu" / "nes" / "ingest").exists()


def test_class_f_keeps_one_top_level_game_directory(work):
    game = work / SHAPE_DIR / "BLES01234" / "PS3_GAME"
    game.mkdir(parents=True)
    (game / "PARAM.SFO").write_bytes(b"\x00PSF identity")

    result = import_shape(
        Job(system_id="rpcs3", roms_dir="emu/rpcs3"), shape(work, "F"))

    destination = work.parents[2] / "emu" / "rpcs3" / "BLES01234"
    assert result.names == ("BLES01234",)
    assert (destination / "PS3_GAME" / "PARAM.SFO").read_bytes() == b"\x00PSF identity"
    assert not (destination / "BLES01234").exists(), "class F is not nested twice"


def test_a_collision_names_the_existing_file_and_changes_no_byte(work):
    produced = work / SHAPE_DIR / "Mario Kart 8 Deluxe.nes"
    produced.write_bytes(b"new")
    source = work / "download.nes"
    source.write_bytes(b"original download")
    existing = work.parents[2] / "emu" / "nes" / produced.name
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"known working game")

    with pytest.raises(ImportError, match="Mario Kart 8 Deluxe.nes"):
        import_shape(Job(), shape(work, "A"))

    assert existing.read_bytes() == b"known working game"
    assert source.read_bytes() == b"original download"
    assert not (work / SHAPE_DIR).exists(), "a refused import keeps one copy, not two"


def test_a_collision_racing_the_final_rename_still_cannot_be_overwritten(
        work, monkeypatch):
    (work / SHAPE_DIR / "Zelda.nes").write_bytes(b"new game")
    source = work / "download.nes"
    source.write_bytes(b"original download")
    real_publish = importer._rename_noreplace

    def race(_hidden, destination):
        Path(destination).write_bytes(b"game copied there at the last instant")
        return real_publish(_hidden, destination)

    monkeypatch.setattr(importer, "_rename_noreplace", race)
    with pytest.raises(ImportError, match="Zelda.nes"):
        import_shape(Job(), shape(work, "A"))

    existing = work.parents[2] / "emu" / "nes" / "Zelda.nes"
    assert existing.read_bytes() == b"game copied there at the last instant"
    assert source.read_bytes() == b"original download"


def test_publication_never_exposes_a_partially_written_final_name(
        work, monkeypatch):
    payload = b"NES\x1a" + b"x" * 4096
    (work / SHAPE_DIR / "Zelda.nes").write_bytes(payload)
    real_rename = os.rename
    real_publish = importer._rename_noreplace
    observations: list[str] = []

    def watched_rename(source, destination):
        destination = Path(destination)
        if "emu" in destination.parts:
            assert destination.name.startswith(".gamecore-import-")
            assert not (destination.parent / "Zelda.nes").exists()
            observations.append("hidden-complete")
        return real_rename(source, destination)

    def watched_publish(source, destination):
        assert Path(source).read_bytes() == payload
        assert not os.path.lexists(destination)
        observations.append("publish-complete")
        return real_publish(source, destination)

    monkeypatch.setattr(importer.os, "rename", watched_rename)
    monkeypatch.setattr(importer, "_rename_noreplace", watched_publish)
    import_shape(Job(), shape(work, "A"))

    assert observations == ["hidden-complete", "publish-complete"]


def test_cross_filesystem_import_is_refused_instead_of_copied(work, monkeypatch):
    (work / SHAPE_DIR / "Zelda.nes").write_bytes(b"NES\x1a complete")
    source = work / "Zelda.nes"
    source.write_bytes(b"original download")

    def across_filesystems(_source, _destination):
        raise OSError(errno.EXDEV, "cross-device link")

    monkeypatch.setattr(importer.os, "rename", across_filesystems)
    with pytest.raises(ImportError, match="different filesystems"):
        import_shape(Job(), shape(work, "A"))

    assert not (work.parents[2] / "emu" / "nes" / "Zelda.nes").exists()
    assert source.read_bytes() == b"original download"
    assert not (work / SHAPE_DIR).exists()


def test_the_importer_refuses_a_directory_other_than_the_system_packs(work):
    (work / SHAPE_DIR / "Zelda.nes").write_bytes(b"NES\x1a complete")

    with pytest.raises(ImportError, match="not the directory declared"):
        import_shape(Job(roms_dir="emu/rpcs3"), shape(work, "A"))

    assert not (work.parents[2] / "emu").exists()


def test_an_nsp_is_imported_with_an_explicit_ambiguity_warning(work):
    package = work / SHAPE_DIR / "FIFA 22 [0100216014472000][v0][US].nsp"
    package.write_bytes(b"PFS0 base game")

    result = import_shape(
        Job(system_id="ryujinx", roms_dir="emu/ryujinx"), shape(work, "B"))

    assert result.warning
    assert "base game, an update, or DLC" in result.warning
    assert (work.parents[2] / "emu" / "ryujinx" / package.name).exists()


def test_import_then_listing_needs_no_refresh_endpoint(work, monkeypatch):
    (work / SHAPE_DIR / "Zelda (USA).nes").write_bytes(b"NES\x1a complete")
    import_shape(Job(), shape(work, "A"))
    monkeypatch.setattr(games, "list_all", lambda: [{
        "id": "nes", "kind": "emulator", "romsPath": "emu/nes/",
        "extensions": ["*.nes"], "scanDirs": False,
    }])
    monkeypatch.setattr(games.prefetch, "note_scan", lambda *_args: None)

    listed = games.list_games("nes")

    assert [row["filename"] for row in listed] == ["Zelda (USA).nes"]
