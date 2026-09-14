"""The acquisition-to-library compositions which component tests cannot prove."""
from __future__ import annotations

import asyncio
import struct
import zipfile
from pathlib import Path

import httpx

from backend.services import paths
from backend.services.rom_scanner import iter_rom_files
from backend.services.store import jobs
from backend.services.store.importer import import_shape
from backend.services.store.inspector import inspect
from backend.services.store.jobs import AcquiredFile, AcquiredTarget
from backend.services.store.materializer import HttpMaterializer
from backend.services.store.transformer import ShapeTransformer
from backend.services.store.validator import validate


def _sfo(title: str, title_id: str) -> bytes:
    fields = {"TITLE": title, "TITLE_ID": title_id}
    keys = b"".join(key.encode() + b"\0" for key in fields)
    values = b""
    entries = b""
    for offset, value in zip((0, len("TITLE") + 1), fields.values()):
        encoded = value.encode() + b"\0"
        entries += struct.pack("<HHIII", offset, 0x0204, len(encoded),
                               len(encoded), len(values))
        values += encoded
    key_table = 20 + len(entries)
    data_table = key_table + len(keys)
    return (struct.pack("<4sIIII", b"\x00PSF", 0x0101, key_table,
                        data_table, len(fields)) + entries + keys + values)


class _Provider:
    name = "fixture"

    def __init__(self, target: AcquiredTarget):
        self.target = target

    async def acquire(self, _job):
        return self.target


async def _run(monkeypatch, tmp_path: Path, *, system: str, roms_dir: str,
               filename: str, payloads: dict[str, bytes], import_it: bool = True):
    monkeypatch.setattr(paths, "GAMECORE_DATA", tmp_path)
    members = tuple(AcquiredFile(
        url=f"https://download.invalid/{index}", path=name, size=len(body))
        for index, (name, body) in enumerate(payloads.items()))
    target = AcquiredTarget(files=members, info_hash="a1" * 20,
                            provider="fixture")
    bodies = {f"/{index}": body
              for index, body in enumerate(payloads.values())}
    transport = httpx.MockTransport(lambda request: httpx.Response(
        200, content=bodies[request.url.path],
        headers={"content-length": str(len(bodies[request.url.path]))},
        request=request))
    job = jobs.Job(
        id="d" * 32, system_id=system, roms_dir=roms_dir, title="Fixture",
        filename=filename, format=Path(filename).suffix.lstrip("."), size=1,
        provider="fixture", source="fixture://release", state=jobs.RUNNING,
        reason="", queued_at="2026-09-14T00:00:00+00:00",
        started_at="2026-09-14T00:00:01+00:00", ended_at="")
    acquired = await _Provider(target).acquire(job)
    materializer = HttpMaterializer(
        progress=lambda *_args: asyncio.sleep(0), transport=transport,
        free_bytes=lambda _path: 10**12)
    await materializer.materialize(job, acquired)
    verdict = inspect(job.id, job.system_id)
    if not verdict.complete:
        return job, verdict, None, None
    shape = await ShapeTransformer(
        progress=lambda *_args: asyncio.sleep(0),
        free_bytes=lambda _path: 10**12).transform(
            job, verdict.ingestion_class)
    checked = validate(shape, job.system_id)
    if not checked.ok:
        return job, verdict, shape, checked
    if import_it:
        import_shape(job, shape)
    return job, verdict, shape, checked


def test_class_e_arrives_as_a_whole_set_and_is_visible(monkeypatch, tmp_path):
    _job, verdict, _shape, _checked = asyncio.run(_run(
        monkeypatch, tmp_path, system="dreamcast", roms_dir="emu/dreamcast",
        filename="Game.cue",
        payloads={"Game.cue": b'FILE "Game.bin" BINARY\n',
                  "Game.bin": b"track", "readme.txt": b"notes"}))

    assert verdict.ingestion_class == "E"
    library = tmp_path / "emu/dreamcast"
    assert [path.name for path in iter_rom_files(
        library, ["*.cdi", "*.chd", "*.gdi", "*.cue", "*.m3u"])] == ["Game.cue"]
    assert (library / "Game.bin").read_bytes() == b"track"
    assert not (library / "readme.txt").exists()


def test_class_f_arrives_with_its_tree_and_is_visible(monkeypatch, tmp_path):
    _job, verdict, _shape, _checked = asyncio.run(_run(
        monkeypatch, tmp_path, system="rpcs3", roms_dir="emu/rpcs3",
        filename="Demon Souls",
        payloads={
            "BLES00932/PS3_GAME/PARAM.SFO": _sfo("Demon's Souls", "BLES00932"),
            "BLES00932/PS3_GAME/USRDIR/EBOOT.BIN": b"elf",
        }))

    assert verdict.ingestion_class == "F"
    library = tmp_path / "emu/rpcs3"
    assert [path.name for path in iter_rom_files(library, [], scan_dirs=True)] == [
        "BLES00932"]
    assert (library / "BLES00932/PS3_GAME/USRDIR/EBOOT.BIN").read_bytes() == b"elf"


def test_incomplete_class_f_names_the_missing_identity(monkeypatch, tmp_path):
    _job, verdict, shape, checked = asyncio.run(_run(
        monkeypatch, tmp_path, system="rpcs3", roms_dir="emu/rpcs3",
        filename="Broken Game",
        payloads={"BLES00000/PS3_GAME/USRDIR/EBOOT.BIN": b"elf"},
        import_it=False))

    assert verdict.ingestion_class == "F"
    assert shape is not None and checked is not None
    assert checked.ok is False
    assert "PS3_GAME/PARAM.SFO" in checked.reason
    assert "sce_sys/param.sfo" in checked.reason
    assert not (tmp_path / "emu/rpcs3").exists()


def _dreamcast_zip(path: Path, *, with_track: bool) -> bytes:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Game.cue", 'FILE "Game.bin" BINARY\n')
        if with_track:
            archive.writestr("Game.bin", b"track")
    return path.read_bytes()


def test_dreamcast_archive_is_class_e_and_keeps_its_track(monkeypatch, tmp_path):
    blob = _dreamcast_zip(tmp_path / "complete.zip", with_track=True)
    job, verdict, shape, _checked = asyncio.run(_run(
        monkeypatch, tmp_path, system="dreamcast", roms_dir="emu/dreamcast",
        filename="Game.zip", payloads={"Game.zip": blob}, import_it=False))

    assert verdict.ingestion_class == "E"
    source = tmp_path / "store/jobs" / ("d" * 32) / "Game.zip"
    assert source.read_bytes() == blob
    assert shape is not None
    assert {path.name for path in shape.root.iterdir()} == {"Game.cue", "Game.bin"}
    import_shape(job, shape)
    assert (tmp_path / "emu/dreamcast/Game.cue").is_file()
    assert (tmp_path / "emu/dreamcast/Game.bin").read_bytes() == b"track"


def test_incomplete_dreamcast_archive_names_the_missing_track(monkeypatch,
                                                              tmp_path):
    blob = _dreamcast_zip(tmp_path / "incomplete.zip", with_track=False)
    _job, verdict, shape, _checked = asyncio.run(_run(
        monkeypatch, tmp_path, system="dreamcast", roms_dir="emu/dreamcast",
        filename="Game.zip", payloads={"Game.zip": blob}, import_it=False))

    assert verdict.complete is False
    assert verdict.ingestion_class == "E"
    assert "Game.bin" in verdict.reason
    assert shape is None
    assert (tmp_path / "store/jobs" / ("d" * 32) / "Game.zip").read_bytes() == blob
    assert not (tmp_path / "emu/dreamcast").exists()
