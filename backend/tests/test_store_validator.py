"""Store validation on tiny, synthetic, offline fixtures.

Every fixture here is built in a temporary directory and is a few bytes long —
one of them claims to be 8 GB and costs nothing, because it is a hole.  The one
real download this project has (an 8 GB Switch `.xci` in a sandbox on the
development box) is referenced by nothing: it is versioned nowhere, it took an
hour to fetch, and a suite that depends on it is a suite that cannot be run
twice.  What it *taught* is recorded in `validator._XCI` and nowhere else.

Three properties are asserted over and over rather than once, because they are
the three this step can break in a way nothing downstream would notice:

  · **it changes nothing.** The source and the produced shape are both
    fingerprinted before and after, in success and in refusal alike;
  · **it reads little.** A file that says it is 8 GB is judged by a few hundred
    bytes, counted;
  · **it can refuse.** Every class has a case it turns down, because a check
    that cannot fail is worse than no check at all.
"""
from __future__ import annotations

import hashlib
import io
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pytest

from backend.services import paths
from backend.services.store import validator
from backend.services.store.transformer import SHAPE_DIR, Shape
from backend.services.store.validator import (REFUSED, UNVERIFIED, VERIFIED,
                                              ValidationError, validate)

JOB_ID = "d" * 32

# Enough of each header to satisfy the signature, and nothing more: these are
# fixtures, not dumps. Their provenance is `validator._SIGNATURES`, where every
# entry carries the source it came from.
INES = b"NES\x1a" + b"\x01\x01" + b"\x00" * 10
CHD = b"MComprHD" + b"\x00" * 56
NDS = b"\x00" * 0xC0 + bytes.fromhex("24ffae51699aa221") + b"\x00" * 64
SFC = b"\x00" * 512 + b"raw snes dump with no header anywhere"


def param_sfo(title: str = "Uncharted 2") -> bytes:
    """A one-entry PARAM.SFO, built to the layout `identity.read_sfo` parses.

    Synthesised rather than copied from a dump: the reader is what is under
    test here, and a real SFO would carry a title somebody owns.
    """
    keys = b"TITLE\x00"
    data = title.encode() + b"\x00"
    key_table = 20 + 16
    return (b"\x00PSF"
            + (1 << 8).to_bytes(4, "little")
            + key_table.to_bytes(4, "little")
            + (key_table + len(keys)).to_bytes(4, "little")
            + (1).to_bytes(4, "little")
            + (0).to_bytes(2, "little") + (0x0204).to_bytes(2, "little")
            + len(data).to_bytes(4, "little") + len(data).to_bytes(4, "little")
            + (0).to_bytes(4, "little")
            + keys + data)


@dataclass(frozen=True)
class _Job:
    id: str = JOB_ID
    system_id: str = "nes"


@pytest.fixture
def work(tmp_path, monkeypatch) -> Path:
    """A job work area with its produced shape directory, and nothing in it."""
    monkeypatch.setattr(paths, "GAMECORE_DATA", tmp_path)
    root = tmp_path / "store" / "jobs" / JOB_ID
    (root / SHAPE_DIR).mkdir(parents=True)
    return root


def shape_of(work: Path, ingestion_class: str) -> Shape:
    produced = work / SHAPE_DIR
    return Shape(ingestion_class=ingestion_class, root=produced,
                 names=tuple(sorted(p.name for p in produced.iterdir())))


def fingerprint(root: Path) -> dict[str, str]:
    """Every path under `root` — source *and* shape — hashed.

    Wider than `test_store_transformer.py`'s, which excludes the shape because
    the shape is its output. Here the shape is an input: validation reads it
    and must leave it exactly as the transformation wrote it.
    """
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        out[rel] = "dir/" if path.is_dir() else hashlib.sha256(
            path.read_bytes()).hexdigest()
    return out


# ── one validation per class, and one refusal per class ────────────────────


def _accepted(work: Path, ingestion_class: str) -> None:
    """A shape of that class that a box should let through."""
    shape = work / SHAPE_DIR
    if ingestion_class == "A":
        (shape / "Zelda.nes").write_bytes(INES)
    elif ingestion_class == "B":
        (shape / "Mario.nds").write_bytes(NDS)
    elif ingestion_class == "C":
        for root in (work, shape):
            with zipfile.ZipFile(root / "sf2.zip", "w") as zipped:
                zipped.writestr("sf2_01.rom", b"chip")
    elif ingestion_class == "D":
        (shape / "Ridge Racer.chd").write_bytes(CHD)
    elif ingestion_class == "E":
        (shape / "Ridge Racer.cue").write_text('FILE "Ridge Racer.bin" BINARY\n')
        (shape / "Ridge Racer.bin").write_bytes(b"track" * 16)
    else:
        game = shape / "BLES01234" / "PS3_GAME"
        game.mkdir(parents=True)
        (game / "PARAM.SFO").write_bytes(param_sfo())


def _refused(work: Path, ingestion_class: str) -> str:
    """A shape of that class a box must turn down, and what it is called."""
    shape = work / SHAPE_DIR
    if ingestion_class == "A":
        # Unpacked, and what came out is not a ROM: the library would list
        # nothing and the tile would never appear.
        (shape / "readme.txt").write_bytes(b"just the packaging")
        return "no file the library would list"
    if ingestion_class == "B":
        # A `.nds` without the Nintendo logo the DS firmware checks.
        (shape / "Mario.nds").write_bytes(b"not a cartridge" * 64)
        return "is not a Nintendo DS cartridge"
    if ingestion_class == "C":
        # The archive copied through as a truncated file: it no longer opens,
        # and a romset that does not open is a game MAME cannot read.
        for root in (work, shape):
            (root / "sf2.zip").write_bytes(b"PK\x03\x04truncated here")
        return "cannot be opened"
    if ingestion_class == "D":
        (shape / "Ridge Racer.chd").write_bytes(b"not a CHD at all" * 4)
        return "is not a MAME CHD image"
    if ingestion_class == "E":
        # The descriptor arrived; the track it names did not.
        (shape / "Ridge Racer.cue").write_text('FILE "Ridge Racer.bin" BINARY\n')
        return "which the shape does not hold"
    game = shape / "BLES01234"
    game.mkdir()
    (game / "EBOOT.BIN").write_bytes(b"no identity file beside me")
    return "carries no readable identity file"


CLASSES = [
    ("A", "nes"),
    ("B", "melonds"),
    ("C", "mame"),
    ("D", "duckstation"),
    ("E", "duckstation"),
    ("F", "rpcs3"),
]


@pytest.mark.parametrize("ingestion_class,system", CLASSES)
def test_one_validation_per_class_accepts_what_the_matrix_describes(
        work, ingestion_class, system):
    """§5.1's validate column, one shape per class, checked rather than trusted."""
    _accepted(work, ingestion_class)
    before = fingerprint(work)

    checked = validate(shape_of(work, ingestion_class), system)

    assert checked.ok, checked.reason
    assert checked.verdict == VERIFIED, checked
    assert checked.proven, "a passing class must say what it proved"
    # The whole point of a step that only reads, asserted for every class.
    assert fingerprint(work) == before


@pytest.mark.parametrize("ingestion_class,system", CLASSES)
def test_one_refusal_per_class_and_the_bytes_survive_it(
        work, ingestion_class, system):
    """Every class turns something down, and a refusal costs nothing.

    Both halves matter. A validation that cannot refuse is worse than no
    validation, because it looks like a filter — and a validation that repairs
    or removes what it refused would destroy the download the player waited an
    hour for, when the fix may be one missing track away.
    """
    expected = _refused(work, ingestion_class)
    before = fingerprint(work)

    checked = validate(shape_of(work, ingestion_class), system)

    assert not checked.ok, checked
    assert checked.verdict == REFUSED
    assert expected in checked.reason, checked.reason
    assert fingerprint(work) == before


# ── what a signature is worth ──────────────────────────────────────────────


def test_a_format_with_no_signature_is_unverified_and_never_refused(work):
    """§5.1 records that the SNES has no usable proof. So this says so.

    A `.sfc` is a raw memory dump: there is no field at a fixed offset that any
    reader checks, so inventing one would refuse good dumps and prove nothing
    about the rest. The honest answer is a verdict the row carries, not a pass
    dressed up as a check.
    """
    (work / SHAPE_DIR / "Mario.sfc").write_bytes(SFC)

    checked = validate(shape_of(work, "B"), "snes9x")

    assert checked.ok
    assert checked.verdict == UNVERIFIED
    assert checked.proven == ()
    assert checked.unproven == ("Mario.sfc",)


def test_an_empty_file_is_refused_whatever_its_extension(work):
    """The floor, and the reason no class ends in a check that cannot fail.

    A `.sfc` carries no signature, so nothing above could refuse one — but an
    empty file is not a game in any format. The acquisition size is `0`
    whenever the service does not say (`jobs.AcquiredTarget`), so nothing
    before this point compared a length either.
    """
    (work / SHAPE_DIR / "Mario.sfc").write_bytes(b"")

    checked = validate(shape_of(work, "B"), "snes9x")

    assert not checked.ok
    assert checked.verdict == REFUSED
    assert "has no content" in checked.reason


def test_every_signature_carries_the_source_it_came_from():
    """A box may refuse a download on four bytes only if it can say why.

    Not decoration: the `source` field is what a reviewer checks a signature
    against, and an entry added without one is an entry nobody can audit. The
    strengths are asserted too — a `proof` refuses, so the set that may refuse
    is pinned here rather than left to whoever edits the table next.
    """
    for suffix, signature in validator._SIGNATURES.items():
        assert signature.source.strip(), f"{suffix} has no cited source"
        assert signature.probes, f"{suffix} has no probe"
        assert signature.what.strip(), f"{suffix} does not name its format"

    hints = {s for s, sig in validator._SIGNATURES.items() if not sig.proof}
    # The extensions that name more than one format, or where this project has
    # material evidence of a variant without the field.
    assert hints == {".iso", ".cdi", ".gen", ".32x", ".xci", ".wad", ".mds",
                     ".ccd"}, hints


def test_a_hint_that_misses_is_unverified_where_a_proof_that_misses_refuses(work):
    """The two strengths, on the same shape, one line apart.

    `.chd` is a proof — MAME's own tag, which every CHD carries — so a file
    without it is refused. `.iso` is a hint, because the set of disc families
    that legitimately use that extension is open: a Wii U `WUD` is none of the
    ones this box knows and is still a disc. So a miss there is reported, not
    refused.
    """
    (work / SHAPE_DIR / "Game.iso").write_bytes(b"\x00" * 0x9000)

    checked = validate(shape_of(work, "D"), "pcsx2")

    assert checked.ok, checked.reason
    assert checked.verdict == UNVERIFIED
    assert checked.unproven == ("Game.iso",)

    (work / SHAPE_DIR / "Game.iso").unlink()
    (work / SHAPE_DIR / "Game.chd").write_bytes(b"\x00" * 0x9000)

    refused = validate(shape_of(work, "D"), "pcsx2")

    assert not refused.ok
    assert "is not a MAME CHD image" in refused.reason


def test_an_iso_shorter_than_its_own_first_header_is_refused(work):
    """A hint still has a floor: 32 KiB of nothing is not a disc image.

    The one refusal `.iso` can make, and it is a real one — a truncated
    download whose resolved size was `0` reaches this step looking complete.
    """
    (work / SHAPE_DIR / "Game.iso").write_bytes(b"x" * 4096)

    checked = validate(shape_of(work, "D"), "pcsx2")

    assert not checked.ok
    assert "too short to be a disc image" in checked.reason


def test_a_signature_reads_a_few_hundred_bytes_of_an_eight_gigabyte_file(work):
    """Decision 2, measured: an 8 GB file is judged by its head, not its bulk.

    The file is a hole — `truncate` then one write — so this costs no disk and
    no time, which is exactly the point being made about the real thing: a
    checksum of 8 GB would take minutes to produce an answer nothing can
    compare against, since `AcquiredTarget.info_hash` hashes torrent metadata
    and not this file's content.
    """
    huge = work / SHAPE_DIR / "Game.chd"
    with huge.open("wb") as stream:
        stream.truncate(8 << 30)
        stream.write(CHD)
    assert huge.stat().st_size == 8 << 30

    read = _counted_read(huge, lambda: validate(shape_of(work, "D"), "duckstation"))

    assert read < 4096, f"validation read {read} bytes of an 8 GB file"


def _counted_read(target: Path, run):
    """Run `run()`, counting the bytes actually read from `target`."""
    counted = {"bytes": 0}
    real_open = Path.open

    def open_and_count(self, *args, **kwargs):
        stream = real_open(self, *args, **kwargs)
        if self != target:
            return stream
        inner_read = stream.read

        def read(size=-1):
            data = inner_read(size)
            counted["bytes"] += len(data)
            return data

        stream.read = read                                 # type: ignore[method-assign]
        return stream

    Path.open = open_and_count                             # type: ignore[method-assign]
    try:
        run()
    finally:
        Path.open = real_open                              # type: ignore[method-assign]
    return counted["bytes"]


def test_a_cdi_is_judged_by_its_last_eight_bytes(work):
    """The one format whose version word sits at the end, and it is read there.

    Proof that "read a header" is not a synonym for "read offset zero": a seek
    to the end costs the same as a seek to the start, and a `.cdi` judged by
    its first bytes could only ever answer "unverified".
    """
    disc = work / SHAPE_DIR / "Shenmue.cdi"
    with disc.open("wb") as stream:
        stream.truncate(1 << 20)
        stream.seek(-8, io.SEEK_END)
        stream.write(b"\x05\x00\x00\x80" + b"\x00\x00\x00\x00")

    checked = validate(shape_of(work, "D"), "dreamcast")

    assert checked.ok
    assert checked.verdict == VERIFIED
    assert any("DiscJuggler" in line for line in checked.proven)


# ── the classes that are not about one file ────────────────────────────────


def test_class_c_refuses_an_archive_that_was_renamed_on_the_way_through(work):
    """§5.1's C row asks for the name *preserved*, so a rename is a refusal.

    MAME looks a romset up by its filename, so `sf2.zip` arriving and leaving
    as `Street Fighter II.zip` is not a cosmetic difference — it is a game the
    emulator will not find. The source sitting beside the shape is what makes
    the comparison possible at all.
    """
    with zipfile.ZipFile(work / "sf2.zip", "w") as zipped:
        zipped.writestr("sf2_01.rom", b"chip")
    with zipfile.ZipFile(work / SHAPE_DIR / "Street Fighter II.zip", "w") as zipped:
        zipped.writestr("sf2_01.rom", b"chip")
    before = fingerprint(work)

    checked = validate(shape_of(work, "C"), "mame")

    assert not checked.ok
    assert "renamed on the way through" in checked.reason
    assert fingerprint(work) == before


def test_class_c_opens_a_7z_without_extracting_a_single_member(work):
    """The other archive format, and the listing is a directory read.

    `7z l` is the same bounded listing inspection uses — no member is
    extracted, so the cost of opening a 4 GB romset is its table of contents.
    """
    staging = work.parent / "staging"
    staging.mkdir()
    (staging / "sf2_01.rom").write_bytes(b"chip")
    subprocess.run(["7z", "a", "-bd", "-y", str(work / "sf2.7z"),
                    str(staging / "sf2_01.rom")],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    (staging / "sf2_01.rom").unlink()
    staging.rmdir()
    (work / SHAPE_DIR / "sf2.7z").write_bytes((work / "sf2.7z").read_bytes())
    before = fingerprint(work)

    checked = validate(shape_of(work, "C"), "mame")

    assert checked.ok, checked.reason
    assert any("opens and holds 1 file(s)" in line for line in checked.proven)
    assert fingerprint(work) == before
    assert sorted(p.name for p in (work / SHAPE_DIR).iterdir()) == ["sf2.7z"]


def test_class_e_asks_the_completeness_question_of_the_shape_not_the_download(work):
    """The arithmetic is inspection's; what is new is *where* it is asked.

    A download can be complete and its shape short of a track — that is a
    transformation fault, and it is invisible to a check that only ever looked
    at the download. So the descriptor and its companions are counted again, on
    the files import would actually carry.
    """
    # The download is complete…
    (work / "Ridge Racer.cue").write_text(
        'FILE "Ridge Racer (Track 1).bin" BINARY\n'
        'FILE "Ridge Racer (Track 2).bin" BINARY\n')
    (work / "Ridge Racer (Track 1).bin").write_bytes(b"one" * 32)
    (work / "Ridge Racer (Track 2).bin").write_bytes(b"two" * 32)
    # …and the shape is one track short of it.
    shape = work / SHAPE_DIR
    (shape / "Ridge Racer.cue").write_text(
        'FILE "Ridge Racer (Track 1).bin" BINARY\n'
        'FILE "Ridge Racer (Track 2).bin" BINARY\n')
    (shape / "Ridge Racer (Track 1).bin").write_bytes(b"one" * 32)

    checked = validate(shape_of(work, "E"), "duckstation")

    assert not checked.ok
    assert "Ridge Racer (Track 2).bin" in checked.reason


def test_class_e_refuses_a_named_track_that_is_present_and_empty(work):
    """Present is not the same as playable, and the floor reaches the tracks.

    `_missing_descriptor_files` answers a question about names; a zero-byte
    track passes it and stops the game at the first read.
    """
    shape = work / SHAPE_DIR
    (shape / "Ridge Racer.cue").write_text('FILE "Ridge Racer.bin" BINARY\n')
    (shape / "Ridge Racer.bin").write_bytes(b"")

    checked = validate(shape_of(work, "E"), "duckstation")

    assert not checked.ok
    assert "Ridge Racer.bin has no content" in checked.reason


def test_class_f_reads_the_identity_file_the_scraper_already_reads(work):
    """§5.1's F row, through `identity.read_sfo` and not a second reader.

    A tree this accepted but the scraper could not read would be an import that
    produces a tile with no name — so the check *is* the scraper's parse, and
    the title it recovers is what the verdict reports.
    """
    game = work / SHAPE_DIR / "BLES01234" / "PS3_GAME"
    game.mkdir(parents=True)
    (game / "PARAM.SFO").write_bytes(param_sfo("Uncharted 2"))

    checked = validate(shape_of(work, "F"), "rpcs3")

    assert checked.ok
    assert "Uncharted 2" in checked.proven[0]


def test_class_f_refuses_an_identity_file_that_is_there_and_unreadable(work):
    """Presence is not the check; the parse is.

    A zero-byte `PARAM.SFO` exists, and a check written as "is the file there"
    would pass it. `read_sfo` compares the `\\x00PSF` magic first, so this is
    refused for the same reason a truncated one would be.
    """
    game = work / SHAPE_DIR / "BLES01234" / "PS3_GAME"
    game.mkdir(parents=True)
    (game / "PARAM.SFO").write_bytes(b"")

    checked = validate(shape_of(work, "F"), "rpcs3")

    assert not checked.ok
    assert "carries no readable identity file" in checked.reason


def test_a_track_hidden_by_its_descriptor_is_not_judged_as_a_game(work):
    """The scan's own shadow map decides what is a library entry.

    A `.bin` opened through its `.cue` is never listed, so asking whether it
    carries a recognisable header would refuse a set that works — and `.bin` is
    raw track data, which has no header by definition.
    """
    shape = work / SHAPE_DIR
    (shape / "Ridge Racer.cue").write_text('FILE "Ridge Racer.bin" BINARY\n')
    (shape / "Ridge Racer.bin").write_bytes(b"track" * 16)

    checked = validate(shape_of(work, "E"), "duckstation")

    assert checked.ok, checked.reason
    assert "Ridge Racer.bin" not in checked.unproven


# ── the BIOS, named and never blocking ─────────────────────────────────────


def test_a_missing_required_bios_is_reported_and_the_validation_still_passes(work):
    """§5.3 rule 4, both halves in one test.

    `saturn` declares `saturn_bios.bin` as `required: true`, the suite's HOME is
    a throwaway tree, so it is absent — the state of a box that has never had
    one. The import must still be correct and the tile must still appear: the
    box refuses the *launch* and names the file (`bios.py:222-250`), which the
    player can fix by copying one in. A Store that refused instead would leave
    them with nothing to fix.
    """
    (work / SHAPE_DIR / "Panzer Dragoon.chd").write_bytes(CHD)

    checked = validate(shape_of(work, "D"), "saturn")

    assert checked.ok, checked.reason
    assert checked.verdict == VERIFIED
    assert checked.bios_warning
    assert "saturn_bios.bin" in checked.bios_warning
    assert "not a reason to refuse" in checked.bios_warning


def test_a_console_with_no_required_bios_says_nothing_about_one(work):
    """The warning is a fact, not a ritual: `nes` needs no BIOS and gets none."""
    (work / SHAPE_DIR / "Zelda.nes").write_bytes(INES)

    checked = validate(shape_of(work, "A"), "nes")

    assert checked.ok
    assert checked.bios_warning == ""


def test_the_bios_check_never_costs_an_import_when_it_cannot_run(work, monkeypatch):
    """A check that cannot run must not be the thing that refuses a download.

    The same rule `bios.missing_required` states about itself, asserted one
    layer up: this one is not even allowed to fail the validation it decorates.
    """
    def explode(*_a, **_kw):
        raise RuntimeError("the catalogue is on fire")

    monkeypatch.setattr(validator, "missing_required", explode)
    (work / SHAPE_DIR / "Panzer Dragoon.chd").write_bytes(CHD)

    checked = validate(shape_of(work, "D"), "saturn")

    assert checked.ok
    assert checked.bios_warning == ""


# ── what validation refuses to guess ───────────────────────────────────────


def test_a_shape_that_is_not_there_is_an_error_and_not_a_refusal(work):
    """"This box could not check" and "this download is bad" are different.

    The same split `inspector.InspectionError` makes: a player who reads the
    second goes back to the download, and one who reads the first has a box to
    repair. An empty shape is the transformation's fault, never the file's.
    """
    with pytest.raises(ValidationError):
        validate(Shape(ingestion_class="A", root=work / "nowhere"), "nes")

    with pytest.raises(ValidationError):
        validate(shape_of(work, "A"), "nes")


def test_a_class_outside_the_six_is_refused_rather_than_guessed(work):
    """A verdict is persisted; a corrupted one must not be acted on."""
    (work / SHAPE_DIR / "Zelda.nes").write_bytes(INES)
    with pytest.raises(ValidationError):
        validate(shape_of(work, "Z"), "nes")


def test_a_pack_that_is_not_an_emulator_is_refused(work):
    """`steam`, `stremio` and the rest hold no ROMs and validate nothing."""
    (work / SHAPE_DIR / "Zelda.nes").write_bytes(INES)
    with pytest.raises(ValidationError):
        validate(shape_of(work, "A"), "steam")


def test_validation_writes_nowhere_in_the_whole_data_root(work, tmp_path):
    """The narrow version of `test_store_jobs.py`'s guard, one step later.

    That one watches a queue run; this one watches the step that is allowed to
    read everything and write nothing, so a `mkdir` added here fails next to
    the code that added it.
    """
    _accepted(work, "A")
    before = {p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*")}

    validate(shape_of(work, "A"), "nes")
    with pytest.raises(ValidationError):
        validate(shape_of(work, "Z"), "nes")

    assert {p.relative_to(tmp_path).as_posix()
            for p in tmp_path.rglob("*")} == before
    assert not (tmp_path / "emu").exists()
