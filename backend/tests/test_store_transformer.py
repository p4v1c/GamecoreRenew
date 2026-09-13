"""Store transformation on tiny, synthetic, offline fixtures.

Every fixture here is built in a temporary directory and is a few bytes long.
The one real download this project has — an 8 GB Switch `.xci` in a sandbox on
the development box — is deliberately not referenced: it took an hour to fetch,
it is versioned nowhere, and a test suite that depends on it is a test suite
that cannot be run twice.

Two properties are asserted over and over rather than once, because they are
the two this step can break in a way nothing downstream would notice:

  · **the source is byte-identical afterwards**, in every class and in every
    outcome, success or failure;
  · **nothing is written outside the job's own work area**, including when the
    archive is built specifically to try.
"""
from __future__ import annotations

import asyncio
import hashlib
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pytest

from backend.services import paths
from backend.services.store import transformer
from backend.services.store.transformer import ShapeTransformer, TransformError

JOB_ID = "c" * 32


@dataclass(frozen=True)
class _Job:
    """What the transformer actually reads off a job: an id and a console."""

    id: str = JOB_ID
    system_id: str = "nes"


@pytest.fixture
def work(tmp_path, monkeypatch) -> Path:
    monkeypatch.setattr(paths, "GAMECORE_DATA", tmp_path)
    root = tmp_path / "store" / "jobs" / JOB_ID
    root.mkdir(parents=True)
    return root


class Recorder:
    """The queue's progress sink, without the queue."""

    def __init__(self):
        self.seen: list[tuple[str, int, int]] = []

    async def __call__(self, job_id: str, done: int, total: int) -> None:
        self.seen.append((job_id, done, total))


def shaper(*, progress=None, free: int | None = None) -> ShapeTransformer:
    return ShapeTransformer(progress=progress or Recorder(),
                            free_bytes=lambda _path: (1 << 40) if free is None else free)


def transform(system: str, ingestion_class: str, **kw):
    """Run one transformation the way the worker runs it."""
    return asyncio.run(
        shaper(**kw).transform(_Job(system_id=system), ingestion_class))


def archive(root: Path, name: str, members: dict[str, bytes],
            *, compression: int = zipfile.ZIP_DEFLATED) -> Path:
    target = root / name
    with zipfile.ZipFile(target, "w", compression) as zipped:
        for member, content in members.items():
            zipped.writestr(member, content)
    return target


def fingerprint(root: Path) -> dict[str, str]:
    """Every path under `root` except the produced shape, hashed.

    The shape is excluded because it is the output; everything else is the
    source, and the source is what must come out the far end unchanged.
    """
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if rel == transformer.SHAPE_DIR or rel.startswith(f"{transformer.SHAPE_DIR}/"):
            continue
        out[rel] = "dir/" if path.is_dir() else hashlib.sha256(
            path.read_bytes()).hexdigest()
    return out


def emitted(work: Path) -> list[str]:
    shape = work / transformer.SHAPE_DIR
    return sorted(path.name for path in shape.iterdir()) if shape.is_dir() else []


# ── one transformation per class ───────────────────────────────────────────
#
# A table of *expectations*, like `test_store_inspector.py`'s: nothing here is
# imported by `transformer`, which reads the persisted class and the pack.

CASES = [
    # class, system, how it arrived, what the shape holds afterwards
    ("A", "nes", "archive", ["Zelda.nes"]),
    ("A", "nes", "bare", ["Zelda.nes"]),
    ("B", "snes9x", "archive", ["Mario.zip"]),
    ("C", "mame", "archive", ["sf2.zip"]),
    ("D", "duckstation", "bare", ["Ridge Racer.chd"]),
    ("E", "duckstation", "set", ["Ridge Racer.bin", "Ridge Racer.cue"]),
    ("F", "rpcs3", "tree", ["BLES01234"]),
]


def _arrive(work: Path, system: str, how: str) -> None:
    if how == "archive":
        if system == "nes":
            archive(work, "Zelda.zip", {"Zelda.nes": b"NES\x1a payload"})
        elif system == "snes9x":
            archive(work, "Mario.zip", {"Mario.sfc": b"sfc payload"})
        else:
            archive(work, "sf2.zip", {"sf2_01.rom": b"chip"})
    elif how == "bare":
        if system == "nes":
            (work / "Zelda.nes").write_bytes(b"NES\x1a payload")
        else:
            (work / "Ridge Racer.chd").write_bytes(b"MComprHD" + b"disc" * 8)
    elif how == "set":
        (work / "Ridge Racer.cue").write_text('FILE "Ridge Racer.bin" BINARY\n')
        (work / "Ridge Racer.bin").write_bytes(b"track" * 16)
    else:
        game = work / "BLES01234" / "PS3_GAME"
        game.mkdir(parents=True)
        (game / "PARAM.SFO").write_bytes(b"\x00PSF" + b"sfo" * 8)
        (game / "ICON0.PNG").write_bytes(b"\x89PNG")


@pytest.mark.parametrize("ingestion_class,system,how,expected", CASES)
def test_one_transformation_per_class_matches_the_matrix_table(
        work, ingestion_class, system, how, expected):
    """§5.1's transform column, one case per class, checked against the shape.

    The interesting rows are the ones that must *not* act: `B` keeps a `.zip`
    a core reads directly (§2.2) and `C` keeps the archive that **is** the
    romset (§2.1) — unpacking either is the failure the matrix was written to
    stop, and it would show up here as an extra name.
    """
    _arrive(work, system, how)
    before = fingerprint(work)

    shape = transform(system, ingestion_class)

    assert emitted(work) == expected, (
        f"class {ingestion_class} on {system} arriving as {how} must produce "
        f"{expected} (matrix §5.1)")
    assert sorted(shape.names) == expected
    assert shape.ingestion_class == ingestion_class
    # The whole point of producing beside the source, asserted for every class.
    assert fingerprint(work) == before


def test_the_shape_is_produced_beside_the_source_inside_the_job_work_area(work):
    """Decision 1: nothing leaves `store/jobs/<job-id>/`.

    The queue-wide version of this is `test_store_jobs.py`'s
    `test_queueing_and_running_write_only_into_job_work_areas_never_emu`, which
    watches the entire data root. This is the same statement about one
    transformation, so a change here fails next to the code that caused it.
    """
    _arrive(work, "nes", "archive")
    data_root = work.parents[2]
    before = {p.relative_to(data_root).as_posix() for p in data_root.rglob("*")}

    shape = transform("nes", "A")

    assert shape.root == work / transformer.SHAPE_DIR
    assert shape.root.resolve().is_relative_to(work.resolve())
    new = {p.relative_to(data_root).as_posix()
           for p in data_root.rglob("*")} - before
    prefix = shape.root.relative_to(data_root).as_posix()
    assert new and all(p == prefix or p.startswith(f"{prefix}/") for p in new), new
    assert not (data_root / "emu").exists()


def test_class_c_is_byte_identical_and_keeps_its_name(work):
    """§5.1's C row, measured rather than described.

    Decompressing a romset does not degrade it, it deletes it: §2.1 records
    `{sf2/, sf2_01.rom} -> []`, because the scan is flat and `scanDirs` is
    false for the four arcade packs. So this asserts three things — the name
    survived, the bytes survived, and `sf2_01.rom` is nowhere in the shape.
    """
    romset = archive(work, "sf2.zip", {"sf2_01.rom": b"chip", "sf2_02.rom": b"more"})
    digest = hashlib.sha256(romset.read_bytes()).hexdigest()

    shape = transform("mame", "C")

    produced = shape.root / "sf2.zip"
    assert emitted(work) == ["sf2.zip"]
    assert hashlib.sha256(produced.read_bytes()).hexdigest() == digest
    assert not list(shape.root.glob("*.rom"))
    assert not (shape.root / "sf2").exists()
    # …and the source romset is still exactly the one that was downloaded.
    assert hashlib.sha256(romset.read_bytes()).hexdigest() == digest


def test_a_7z_archive_unpacks_through_a_pipe(work):
    """The other archive format, which takes the subprocess path.

    `7z x -so` streams the member to stdout, so 7z is never given an output
    directory and cannot be the thing that places a file — the destination is
    computed here. `-spd` keeps a name like `od[d].nes` literal instead of
    letting 7z read it as a pattern.
    """
    source = work.parent / "staging"
    source.mkdir()
    (source / "Zelda.nes").write_bytes(b"NES\x1a from 7z")
    (source / "od[d].nes").write_bytes(b"bracketed")
    (source / "notes.txt").write_bytes(b"packaging noise")
    subprocess.run(["7z", "a", "-bd", "-y", str(work / "set.7z"),
                    *(str(p) for p in sorted(source.iterdir()))],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for leftover in source.iterdir():
        leftover.unlink()
    source.rmdir()
    before = fingerprint(work)

    shape = transform("nes", "A")

    # Only the declared members, and `notes.txt` is not one of them (§2.4).
    assert emitted(work) == ["Zelda.nes", "od[d].nes"]
    assert (shape.root / "od[d].nes").read_bytes() == b"bracketed"
    assert (shape.root / "Zelda.nes").read_bytes() == b"NES\x1a from 7z"
    assert fingerprint(work) == before


def test_unpacking_is_flat_and_keeps_only_declared_members(work):
    """§2.4: flat always, and only what carries an extension the pack declares.

    A subdirectory on a non-`scanDirs` system produces zero games (§1.2), so
    `sub/Mario.nes` has to land beside its siblings and not under a `sub/`.
    """
    archive(work, "Pack.zip", {
        "sub/Mario.nes": b"mario",
        "readme.txt": b"not a rom",
        "inner.zip": b"PK not recursed into",
    })

    shape = transform("nes", "A")

    assert emitted(work) == ["Mario.nes"]
    assert not (shape.root / "sub").exists()
    assert (shape.root / "Mario.nes").read_bytes() == b"mario"


def test_class_f_keeps_the_tree_and_never_flattens_it(work):
    """§5.1's F row: a top-level directory, with its interior intact."""
    _arrive(work, "rpcs3", "tree")

    shape = transform("rpcs3", "F")

    assert emitted(work) == ["BLES01234"]
    assert (shape.root / "BLES01234").is_dir()
    assert (shape.root / "BLES01234" / "PS3_GAME" / "PARAM.SFO").read_bytes() \
        == b"\x00PSF" + b"sfo" * 8
    # Flattened, this would be `PARAM.SFO` at the top and no game at all.
    assert not (shape.root / "PARAM.SFO").exists()


def test_an_empty_directory_inside_a_class_f_game_is_kept(work):
    """"Never flatten" includes the parts of the tree that hold no bytes.

    A directory is only inferable from a file's parents when it has one, so an
    empty one has to be collected deliberately — otherwise this step quietly
    decides it did not matter, and the emulator that wanted it finds it gone.
    """
    game = work / "BLES01234"
    (game / "PS3_GAME" / "USRDIR").mkdir(parents=True)
    (game / "PS3_GAME" / "PARAM.SFO").write_bytes(b"\x00PSF")
    (game / "PS3_GAME" / "TROPDIR").mkdir()        # empty, and part of the game

    shape = transform("rpcs3", "F")

    assert (shape.root / "BLES01234" / "PS3_GAME" / "TROPDIR").is_dir()
    assert (shape.root / "BLES01234" / "PS3_GAME" / "USRDIR").is_dir()


# ── the escape ─────────────────────────────────────────────────────────────


def test_a_member_that_points_outside_the_work_area_is_refused(work, tmp_path):
    """The naive implementation escapes. This one cannot, and says so.

    Two layers, and the test exercises both. Containment is *by construction*:
    §2.4 requires flat extraction, so a member is only ever written to
    `ingest/<last component>`, and a name with no path left in it has nowhere
    to go. On top of that, an absolute or `..`-carrying member is refused
    outright, because unlike `sub/game.nes` it cannot be an honest packaging
    choice.

    The proof that this is not a theoretical risk is performed, not asserted:
    the same member name is joined the obvious way into a throwaway directory
    and the bytes land outside it.
    """
    # Two levels, and the naive destination below is nested deeper than that,
    # so the escape this test *performs* lands inside the test's own temporary
    # tree. An escape that reached past `tmp_path` would be this test writing
    # onto the machine to prove that writing onto the machine is possible.
    escaping = "../../escaped.nes"
    archive(work, "Evil.zip", {escaping: b"ESCAPED"})
    before = fingerprint(work)
    root_before = {p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*")}

    with pytest.raises(TransformError) as refused:
        transform("nes", "A")

    assert "outside the download" in str(refused.value)
    # Refused before anything was created: no shape, and the source untouched.
    assert not (work / transformer.SHAPE_DIR).exists()
    assert fingerprint(work) == before
    assert {p.relative_to(tmp_path).as_posix()
            for p in tmp_path.rglob("*")} == root_before

    # The naive version, run for real, escapes the directory it was given.
    naive_dest = tmp_path / "naive" / "deep" / "deeper"
    naive_dest.mkdir(parents=True)
    with zipfile.ZipFile(work / "Evil.zip") as zipped:
        landed = naive_dest / escaping          # the obvious join, and the bug
        landed.parent.mkdir(parents=True, exist_ok=True)
        landed.write_bytes(zipped.read(escaping))

    assert not landed.resolve().is_relative_to(naive_dest.resolve()), (
        "the escape fixture no longer escapes, so this test proves nothing")
    assert landed.resolve().read_bytes() == b"ESCAPED"
    assert landed.resolve() == tmp_path / "naive" / "escaped.nes"
    # …contained in the test's own temporary tree, which is the only reason
    # this half of the test is allowed to exist.
    assert landed.resolve().is_relative_to(tmp_path.resolve())


@pytest.mark.parametrize("raw", [
    "../../etc/truc.nes",
    "/etc/truc.nes",
    "..\\..\\etc\\truc.nes",       # a zip written on Windows
    "sub/../../truc.nes",
])
def test_every_shape_of_escaping_name_is_refused(raw):
    with pytest.raises(TransformError):
        transformer._refuse_escape(raw)


@pytest.mark.parametrize("raw,flat", [
    ("sub/game.nes", "game.nes"),
    ("deep/deeper/game.nes", "game.nes"),
    ("dir\\game.nes", "game.nes"),    # `\` is a legal filename byte on Linux
    ("game.nes", "game.nes"),
])
def test_a_member_is_flattened_to_its_last_component(raw, flat):
    """Why containment does not depend on the refusal above.

    Flattening is required behaviour (§2.4), not a security measure bolted on —
    which is what makes it a good one: every member goes through it, so the
    write is contained even for a name nobody thought to refuse.
    """
    assert transformer._flat_name(raw) == flat


def test_a_symbolic_link_member_is_never_written(work):
    """The other half of the escape: a link whose target is outside.

    Writing `link.nes -> ../../../etc/passwd` puts nothing outside the work
    area by itself, and then validation reads a host file through it.
    """
    target = work / "Evil.zip"
    with zipfile.ZipFile(target, "w") as zipped:
        info = zipfile.ZipInfo("link.nes")
        info.external_attr = 0xA1FF << 16          # S_IFLNK | 0777
        zipped.writestr(info, b"../../../../etc/passwd")
        zipped.writestr("Real.nes", b"a real rom")

    shape = transform("nes", "A")

    assert emitted(work) == ["Real.nes"]
    assert not (shape.root / "link.nes").exists(follow_symlinks=False)


def test_a_symbolic_link_inside_a_class_f_tree_is_refused(work):
    """F copies a whole directory, so the link check has to be there too."""
    game = work / "BLES01234"
    game.mkdir()
    (game / "PARAM.SFO").write_bytes(b"\x00PSF")
    (game / "escape").symlink_to("/etc/passwd")

    with pytest.raises(TransformError) as refused:
        transform("rpcs3", "F")

    assert "symbolic link" in str(refused.value)
    assert not (work / transformer.SHAPE_DIR).exists()


def test_two_members_sharing_a_last_component_are_refused(work):
    """Flat is not optional, so a collision is a decision — and not this step's."""
    archive(work, "Pack.zip", {"a/Mario.nes": b"one", "b/Mario.nes": b"two"})

    with pytest.raises(TransformError) as refused:
        transform("nes", "A")

    assert "same name" in str(refused.value)
    assert not (work / transformer.SHAPE_DIR).exists()


# ── the name the library scan would drop ───────────────────────────────────


@pytest.mark.parametrize("name,why", [
    (".hidden.nes", "starts with a dot"),
    ("Example Game.nes", 'contains "example"'),
    ("counterexample.nes", 'contains "example"'),   # unanchored, like `:127`
])
def test_a_name_the_scan_would_drop_refuses_the_transformation(work, name, why):
    """Question (a), decided: refuse and name the file.

    `rom_scanner.py:127` drops these without a word. Emitting one is the
    outcome §5.3 rule 2 forbids and produces a download that reported success
    and left no tile; renaming one files the game under a name that is not its
    identity (`gameid.py`'s `filename` strategy), which moves box art and the
    player's hours onto a game that does not exist. Refusing costs one
    sentence, and the sentence has to name the file.
    """
    (work / name).write_bytes(b"NES\x1a payload")
    before = fingerprint(work)

    with pytest.raises(TransformError) as refused:
        transform("nes", "A")

    assert why in str(refused.value)
    assert name in str(refused.value)
    assert not (work / transformer.SHAPE_DIR).exists()
    assert fingerprint(work) == before


def test_the_rule_reaches_a_name_that_only_appears_after_unpacking(work):
    """The archive is fine; the member inside it is not."""
    archive(work, "Zelda.zip", {"example.nes": b"NES\x1a"})

    with pytest.raises(TransformError) as refused:
        transform("nes", "A")

    assert "example.nes" in str(refused.value)


def test_the_rule_is_the_scanners_rule_and_not_a_second_copy_of_it(work):
    """`unscannable` must answer exactly what `:127` skips.

    Written as a comparison rather than as a list of cases so that the day the
    scanner's filter changes, this goes red instead of drifting quietly.
    """
    from backend.services.rom_scanner import iter_rom_files

    roms = work.parent / "roms"
    roms.mkdir()
    candidates = ["Zelda.nes", ".hidden.nes", "Example Game.nes",
                  "counterexample.nes", "normal (USA).nes"]
    for name in candidates:
        (roms / name).write_bytes(b"NES\x1a")

    listed = {path.name for path in iter_rom_files(roms, ["*.nes"])}
    assert {name for name in candidates if not transformer.unscannable(name)} == listed


def test_a_class_f_directory_is_judged_by_its_own_name_only(work):
    """The scan does not recurse (§1.2), so the rule cannot reach the interior.

    A PS3 dump made on a Mac carries a `.DS_Store`, and a hidden file inside a
    folder game is invisible to a scan that only ever lists the top level.
    Refusing the game for it would be inventing a rule the scanner has not got.
    """
    game = work / "BLES01234"
    (game / "PS3_GAME").mkdir(parents=True)
    (game / ".DS_Store").write_bytes(b"mac noise")
    (game / "PS3_GAME" / "example.txt").write_bytes(b"not scanned")
    (game / "PS3_GAME" / "PARAM.SFO").write_bytes(b"\x00PSF")

    shape = transform("rpcs3", "F")

    assert emitted(work) == ["BLES01234"]
    assert (shape.root / "BLES01234" / ".DS_Store").exists()


def test_a_track_the_descriptor_hides_is_not_judged_by_the_rule(work):
    """A companion is opened through its `.cue`, so it was never going to be listed.

    `shadowed_by_a_descriptor` is the existing answer to "which of these names
    does the library actually present as a game", and reusing it keeps this
    from becoming a second, drifting notion of a companion file.
    """
    (work / "Ridge Racer.cue").write_text('FILE ".example track.bin" BINARY\n')
    (work / ".example track.bin").write_bytes(b"track")

    shape = transform("duckstation", "E")

    assert emitted(work) == [".example track.bin", "Ridge Racer.cue"]
    assert (shape.root / ".example track.bin").read_bytes() == b"track"


# ── space, progress, cancellation, failure ─────────────────────────────────


def test_disk_space_is_checked_before_the_first_byte(work):
    """Decision 4: producing beside the source doubles the footprint.

    An appliance that fills its disk from the Store loses more than the
    download, which is why the reserve is the same one the download keeps.
    """
    (work / "Zelda.nes").write_bytes(b"NES\x1a" * 64)
    before = fingerprint(work)

    with pytest.raises(TransformError) as refused:
        transform("nes", "A", free=1024)

    assert "not enough disk space" in str(refused.value)
    assert str(transformer.MIN_FREE_AFTER_TRANSFORM) in str(refused.value)
    assert not (work / transformer.SHAPE_DIR).exists()
    assert fingerprint(work) == before


def test_the_reserve_is_the_appliances_and_not_one_steps(work):
    """Just enough for the shape is not enough: the box keeps its headroom."""
    payload = b"NES\x1a" * 64
    (work / "Zelda.nes").write_bytes(payload)

    with pytest.raises(TransformError):
        transform("nes", "A", free=len(payload) + 1)

    shape = transform("nes", "A",
                      free=len(payload) + transformer.MIN_FREE_AFTER_TRANSFORM)
    assert emitted(work) == ["Zelda.nes"]
    assert shape.bytes_written == len(payload)


def test_progress_is_reported_against_the_total_the_plan_computed(work):
    """It reports, and it reports the size of the shape rather than of the source."""
    payload = b"NES\x1a" * 32
    archive(work, "Zelda.zip", {"Zelda.nes": payload})
    recorder = Recorder()

    shape = transform("nes", "A", progress=recorder)

    assert recorder.seen, "the transformation reported no progress at all"
    # The total is the shape's size, not the archive's: what is being produced
    # is what the bar is measuring.
    assert recorder.seen[0] == (JOB_ID, 0, len(payload))
    assert recorder.seen[-1] == (JOB_ID, len(payload), len(payload))
    assert shape.bytes_written == len(payload)
    assert (work / "Zelda.zip").stat().st_size != len(payload)
    assert all(job_id == JOB_ID for job_id, _done, _total in recorder.seen)


def test_a_failure_halfway_leaves_no_shape_and_an_intact_source(work):
    """Item 7's hardest half: the source survives a transformation that dies.

    The second member's CRC is corrupted, so the first file is written and the
    read of the second raises — a real download that arrived damaged, not an
    injected exception. What must be true afterwards is that the half-made
    shape is gone (validation would otherwise trust it) and that the archive
    is byte-for-byte the one that was downloaded.
    """
    target = archive(work, "Pack.zip",
                     {"aaa.nes": b"FIRSTPAYLOAD", "bbb.nes": b"SECONDPAYLOAD"},
                     compression=zipfile.ZIP_STORED)
    raw = bytearray(target.read_bytes())
    raw[raw.find(b"SECONDPAYLOAD")] = ord("X")
    target.write_bytes(bytes(raw))
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    before = fingerprint(work)

    with pytest.raises(TransformError):
        transform("nes", "A")

    assert not (work / transformer.SHAPE_DIR).exists(), (
        "a half-written shape survived, and validation would read it as finished")
    assert hashlib.sha256(target.read_bytes()).hexdigest() == digest
    assert fingerprint(work) == before


@pytest.mark.parametrize("ingestion_class,system,how", [
    (ingestion_class, system, how) for ingestion_class, system, how, _ in CASES])
def test_the_source_survives_a_failure_in_every_class(
        work, monkeypatch, ingestion_class, system, how):
    """Item 7, across the table: whatever fails, the download is untouched.

    The cause is injected here rather than crafted per class, because the
    property under test is the unwind and not the cause — the crafted version
    of it is the corrupted archive above.

    The injection lets the first destination land *and then* fails, so every
    class — including the single-file ones — unwinds with a real, partly
    written shape on disk rather than with nothing to clean up.
    """
    _arrive(work, system, how)
    before = fingerprint(work)
    real_pump = transformer._pump
    produced: list[Path] = []

    async def failing_pump(read, dest, on_bytes):
        await real_pump(read, dest, on_bytes)
        produced.append(dest)
        raise OSError("no space left on device")

    monkeypatch.setattr(transformer, "_pump", failing_pump)

    with pytest.raises(TransformError):
        transform(system, ingestion_class, free=1 << 40)

    assert produced, "the injected failure never fired"
    assert not (work / transformer.SHAPE_DIR).exists()
    assert not produced[0].exists()
    assert fingerprint(work) == before


def test_a_cancelled_transformation_removes_what_it_made_and_nothing_else(work):
    """Decision 5: cancellation is effective, and it cleans up its own bytes only.

    A 12 GB archive must not be an uninterruptible burst, so production streams
    inside the event loop with an `await` between chunks — the same shape as
    `materializer.py`. Here the transformation is parked with one file already
    produced, then cancelled.
    """
    _arrive(work, "duckstation", "set")
    before = fingerprint(work)
    real_pump = transformer._pump

    async def scenario():
        first_written = asyncio.Event()

        async def parking_pump(read, dest, on_bytes):
            written = await real_pump(read, dest, on_bytes)
            first_written.set()
            await asyncio.sleep(3600)       # held, with the shape half-made
            return written

        transformer._pump = parking_pump
        try:
            task = asyncio.create_task(
                shaper().transform(_Job(system_id="duckstation"), "E"))
            await asyncio.wait_for(first_written.wait(), timeout=5)
            shape = work / transformer.SHAPE_DIR
            assert shape.is_dir() and list(shape.iterdir()), (
                "nothing was produced yet, so this cancels the wrong moment")
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            transformer._pump = real_pump

    asyncio.run(scenario())

    assert not (work / transformer.SHAPE_DIR).exists()
    assert fingerprint(work) == before


# ── refusals that are not about bytes ──────────────────────────────────────


def test_a_download_named_like_the_shape_directory_is_refused_never_removed(work):
    """The one collision that could have cost the source.

    A download may legitimately be called `ingest`. Creating the shape
    directory over it would mean deleting the file this step exists to
    preserve, so the collision is refused instead.
    """
    source = work / transformer.SHAPE_DIR
    source.write_bytes(b"NES\x1a a download that is called ingest")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()

    with pytest.raises(TransformError) as refused:
        transform("nes", "A")

    assert transformer.SHAPE_DIR in str(refused.value)
    assert source.is_file()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == digest


def test_an_archive_with_nothing_the_console_declares_is_refused(work):
    """§2.4's third row: unpacking would produce no game, so it does not run."""
    archive(work, "Zelda.zip", {"readme.txt": b"no rom in here"})

    with pytest.raises(TransformError) as refused:
        transform("nes", "A")

    assert "no file with an extension this console declares" in str(refused.value)
    assert not (work / transformer.SHAPE_DIR).exists()


def test_a_class_that_was_never_persisted_is_refused(work):
    """The verdict is the input. A blank one is a bug upstream, not a default."""
    (work / "Zelda.nes").write_bytes(b"NES\x1a")

    for bad in ("", "G", "a", "AB"):
        with pytest.raises(TransformError) as refused:
            transform("nes", bad)
        assert "no ingestion class" in str(refused.value)
    assert not (work / transformer.SHAPE_DIR).exists()


def test_an_empty_work_area_is_refused_rather_than_producing_an_empty_shape(work):
    with pytest.raises(TransformError):
        transform("nes", "A")
    assert not (work / transformer.SHAPE_DIR).exists()


def test_cleanup_removes_the_shape_and_can_name_nothing_else(work):
    """The only removal in the module, and what stops it reaching the source."""
    (work / "Zelda.nes").write_bytes(b"NES\x1a")
    shape = transform("nes", "A")
    assert shape.root.is_dir()

    transformer.cleanup_shape(JOB_ID)

    assert not shape.root.exists()
    assert (work / "Zelda.nes").exists(), "cleanup reached the download"
    assert work.is_dir()
    # A corrupted id names nothing at all rather than a relative path.
    transformer.cleanup_shape("../../etc")
    assert work.is_dir() and (work / "Zelda.nes").exists()
    # Idempotent: the queue may clean a job that already failed before this step.
    transformer.cleanup_shape(JOB_ID)


def test_a_stray_directory_on_a_file_console_is_refused_not_dropped(work):
    """A subdirectory on a non-`scanDirs` system produces zero games (§1.2).

    Inspection refuses this arrival already. It is refused here too rather
    than filtered out, because a shape quietly missing part of what arrived is
    how a game goes missing with nobody told.
    """
    (work / "Zelda.nes").write_bytes(b"NES\x1a")
    (work / "extras").mkdir()

    with pytest.raises(TransformError) as refused:
        transform("nes", "A")

    assert "only lists files" in str(refused.value)
    assert not (work / transformer.SHAPE_DIR).exists()


def test_a_symbolic_link_at_the_top_of_the_work_area_is_refused(work):
    """The link is never followed and never carried into the shape."""
    (work / "Zelda.nes").write_bytes(b"NES\x1a")
    (work / "elsewhere.nes").symlink_to("/etc/passwd")

    with pytest.raises(TransformError) as refused:
        transform("nes", "A")

    assert "symbolic link" in str(refused.value)
    assert not (work / transformer.SHAPE_DIR).exists()


def test_a_missing_7z_names_the_tool_instead_of_blaming_the_download(work, monkeypatch):
    """Same reflex as inspection's: name the missing package, not the file.

    Without 7z every `.7z` in classes A and D stops here, and a message saying
    only "cannot be unpacked" sends the player back to their download to look
    for a fault that is not in it.
    """
    (work / "set.7z").write_bytes(b"7z\xbc\xaf\x27\x1c not really")

    def no_7z(*_args, **_kw):
        raise FileNotFoundError("7z")

    monkeypatch.setattr(transformer.subprocess, "run", no_7z)

    with pytest.raises(TransformError) as refused:
        transform("nes", "A")

    assert "p7zip" in str(refused.value)
    assert not (work / transformer.SHAPE_DIR).exists()


def test_an_unforeseen_exception_still_leaves_no_half_written_shape(work, monkeypatch):
    """The cleanup is total on purpose.

    A decompressor's own error type, or a `KeyboardInterrupt` from the
    console session, must not be the one path that leaves a partial shape for
    validation to read as finished.
    """
    _arrive(work, "duckstation", "set")
    before = fingerprint(work)
    real_pump = transformer._pump

    async def surprising_pump(read, dest, on_bytes):
        await real_pump(read, dest, on_bytes)
        raise KeyboardInterrupt("the box was interrupted mid-unpack")

    monkeypatch.setattr(transformer, "_pump", surprising_pump)

    with pytest.raises(KeyboardInterrupt):
        transform("duckstation", "E")

    assert not (work / transformer.SHAPE_DIR).exists()
    assert fingerprint(work) == before
