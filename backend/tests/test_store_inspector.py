"""Store inspection/classification on tiny, synthetic, offline fixtures."""
from __future__ import annotations

import hashlib
import subprocess
import zipfile
from pathlib import Path

import pytest

from backend.services import paths
from backend.services.store import inspector


JOB_ID = "b" * 32


@pytest.fixture
def work(tmp_path, monkeypatch) -> Path:
    monkeypatch.setattr(paths, "GAMECORE_DATA", tmp_path)
    root = tmp_path / "store" / "jobs" / JOB_ID
    root.mkdir(parents=True)
    return root


def archive(root: Path, name: str, members: dict[str, bytes]) -> Path:
    target = root / name
    with zipfile.ZipFile(target, "w") as zipped:
        for member, content in members.items():
            zipped.writestr(member, content)
    return target


def classify(system: str):
    return inspector.inspect(JOB_ID, system)


def test_class_a_is_an_undeclared_archive_with_a_declared_member(work):
    archive(work, "Zelda.zip", {"Zelda.nes": b"NES\x1a"})
    assert classify("nes") == inspector.Inspection("A")


def test_class_b_is_a_declared_archive_with_a_declared_plain_member(work):
    archive(work, "Mario.zip", {"Mario.sfc": b"tiny"})
    assert classify("snes9x") == inspector.Inspection("B")


def test_class_c_archive_is_never_extracted_or_changed(work):
    romset = archive(work, "sf2.zip", {"sf2_01.rom": b"chip"})
    before = hashlib.sha256(romset.read_bytes()).digest()

    assert classify("mame") == inspector.Inspection("C")

    # Extraction would add sf2_01.rom (or a directory) and this goes red. The
    # byte check also pins matrix §5's byte-identical final shape.
    assert [path.name for path in work.iterdir()] == ["sf2.zip"]
    assert hashlib.sha256(romset.read_bytes()).digest() == before


def test_a_7z_archive_is_listed_without_extraction(work, tmp_path):
    source = tmp_path / "chip.rom"
    source.write_bytes(b"chip")
    romset = work / "set.7z"
    subprocess.run(
        ["7z", "a", "-bd", "-y", str(romset), str(source)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    assert classify("mame") == inspector.Inspection("C")
    assert [path.name for path in work.iterdir()] == ["set.7z"]


def test_class_d_is_a_self_contained_file(work):
    (work / "Ridge Racer.chd").write_bytes(b"MComprHD")
    assert classify("duckstation") == inspector.Inspection("D")


def test_class_e_is_a_declared_descriptor_with_every_named_track(work):
    (work / "Ridge Racer.cue").write_text('FILE "Ridge Racer.bin" BINARY\n')
    (work / "Ridge Racer.bin").write_bytes(b"track")
    assert classify("duckstation") == inspector.Inspection("E")


def test_class_f_is_a_top_level_game_directory(work):
    game = work / "BLES01234"
    game.mkdir()
    (game / "PS3_GAME").mkdir()
    assert classify("rpcs3") == inspector.Inspection("F")


def test_an_incomplete_class_e_names_the_missing_track(work):
    (work / "Ridge Racer.cue").write_text('FILE "Ridge Racer.bin" BINARY\n')
    verdict = classify("duckstation")
    assert verdict.ingestion_class == "E"
    assert verdict.complete is False
    assert "Ridge Racer.bin" in verdict.reason
    assert "incomplete class E" in verdict.reason


def test_a_loose_file_cannot_satisfy_class_f(work):
    (work / "PS3 release.pkg").write_bytes(b"not a game tree")
    verdict = classify("rpcs3")
    assert verdict.ingestion_class == "F"
    assert verdict.complete is False
    assert "complete game directory is missing" in verdict.reason


def test_archive_listing_work_is_bounded(work, monkeypatch):
    monkeypatch.setattr(inspector, "MAX_LISTING_ENTRIES", 1)
    archive(work, "many.zip", {"one.nes": b"1", "two.nes": b"2"})
    with pytest.raises(inspector.InspectionError, match="too large"):
        classify("nes")


# ── One case per class, checked against matrix §5.1 ──────────────────────────
#
# The seven rows below are the table read literally: the (system, format) pair
# on the left, the class §5.1 puts it in on the right. Two of them were wrong
# before `_plain_class` existed — `snes9x`/`Mario.sfc` and `ryujinx`/`Game.xci`
# both answered "D", because every bare file did. Remove `_plain_class` and
# this test goes red on exactly those two.
#
# It is a table of *expectations*, not a table the code reads: nothing here is
# imported by `inspector`, which still derives all four predicates from the pack
# (§5.2).
TABLE = [
    ("nes",         "Mario.zip",    "A"),
    ("snes9x",      "Mario.sfc",    "B"),
    ("mame",        "sf2.zip",      "C"),
    ("duckstation", "game.chd",     "D"),
    ("duckstation", "game.cue",     "E"),
    ("ryujinx",     "Game.xci",     "B"),
    ("rpcs3",       "BLES00000",    "F"),
]


@pytest.mark.parametrize("system,arrival,expected", TABLE)
def test_one_case_per_class_matches_the_matrix_table(work, system, arrival, expected):
    if arrival.endswith(".zip"):
        member = "Mario.nes" if system == "nes" else "sf2_01.rom"
        archive(work, arrival, {member: b"payload"})
    elif arrival.endswith(".cue"):
        (work / arrival).write_text('FILE "game.bin" BINARY\n')
        (work / "game.bin").write_bytes(b"track")
    elif "." in arrival:
        (work / arrival).write_bytes(b"payload")
    else:
        (work / arrival / "PS3_GAME").mkdir(parents=True)

    verdict = classify(system)
    assert verdict == inspector.Inspection(expected), (
        f"{system} + {arrival} is class {expected} in matrix §5.1, "
        f"got {verdict.ingestion_class}")


def test_a_plain_rom_is_not_labelled_a_disc_image(work):
    """§5.1's B row, which is the whole point: `.sfc` has no disc header.

    Class D validates by reading a disc header (§5.1). A `.sfc` classified D is
    a row that passes inspection today and fails validation at step 16, with a
    class already persisted in `store_jobs.ingestion_class`.
    """
    (work / "Chrono Trigger.sfc").write_bytes(b"tiny")
    assert classify("snes9x").ingestion_class == "B"
    assert inspector.DISC_IMAGE_SUFFIXES.isdisjoint({".sfc", ".xci", ".nds", ".nes"})


def test_a_bare_file_on_a_pack_that_declares_no_archive_is_class_a(work):
    """The other half of §5.2's A-vs-B predicate, on the same bare-file path.

    `nes` declares no `*.zip` (§3.2), so §5.1 puts it in row A for *any* arriving
    format — not only for an archive. It answered D before `_plain_class`.
    """
    (work / "Zelda.nes").write_bytes(b"NES\x1a")
    assert classify("nes").ingestion_class == "A"


def test_a_bare_disc_image_stays_class_d_whatever_the_pack_declares(work):
    """D is the format half of the pair: `dolphin` declares `*.zip`, `xenia` does not."""
    (work / "Melee.rvz").write_bytes(b"disc")
    assert classify("dolphin").ingestion_class == "D"


def test_a_missing_7z_names_the_tool_instead_of_blaming_the_download(work,
                                                                     monkeypatch,
                                                                     tmp_path):
    """Defect 3: with 7z off PATH the failure was "the archive directory cannot
    be read", which points a player at bytes that are fine."""
    empty = tmp_path / "empty-path"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    archive(work, "Mario.zip", {"Mario.sfc": b"tiny"})

    with pytest.raises(inspector.InspectionError) as raised:
        classify("snes9x")
    assert "7z" in str(raised.value)
    assert "p7zip" in str(raised.value)
