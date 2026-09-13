"""Give what a job downloaded the shape its ingestion class requires.

This is the first step allowed to produce modified content, so it is the first
where a mistake costs bytes instead of a label.  The class was decided and
persisted by `inspector.py`; this module acts on that verdict and owns no
system list of its own — matrix §5.1's transform column, read off the class:

    A  unpack if archived, flat        D  unpack only if the container
    B  none                               extension is undeclared
    C  NEVER unpack                    E  keep the set together, flat
                                       F  never flatten, never unpack

A and D share one branch and one predicate — *is the archive's own extension
declared?* (§2.4) — which is why there is no table here: class A never declares
an archive, so an archive that arrived for A is always undeclared, and D's
"only if undeclared" is the same test written once.  B, C and E never unpack,
so for them the shape is the bytes as they arrived.

── The source is never touched ────────────────────────────────────────────
The final shape is produced **beside** the download, in a fresh
`<DATA>/store/jobs/<job-id>/ingest/`, and the source is not deleted here by
anyone — not on success, not on failure.  Step 17 (import) decides the tidying.

Three things make that a property rather than an intention:

  · every source path is opened `"rb"` and nothing else.  A file never opened
    for writing cannot be damaged, which is worth more than a backup — a
    backup of an 8 GB `.xci` costs 8 GB and can itself be the thing that
    fills the disk;
  · every destination is `<job>/ingest/<name>`, created with `open("xb")`.
    O_CREAT|O_EXCL means an existing path — a leftover, a symlink someone
    raced in — fails the write instead of being followed or overwritten;
  · the only removal in this module is `cleanup_shape`, which computes its
    one path from a validated job id plus the `ingest` constant and can
    therefore not name the source, a parent, or another job's bytes.

Producing beside the source doubles the footprint, which is exactly why the
free-space reserve below is checked *before* the first byte is written.

── Two questions this step had to answer ──────────────────────────────────
**A name the library scan would drop in silence.** `rom_scanner.py:127` skips
every entry whose name starts with `.` or contains `example`, unanchored, and
says nothing; matrix §5.3 rule 2 turns that into "never emit such a name".  A
game may legitimately be called that, so there were three ways out: emit it
anyway, rename it, or refuse.

  · *Emitting* is the one outcome the matrix forbids by name, and it produces
    the failure the whole matrix exists to prevent: a download that consumed
    an hour of line, reported success, and left no tile and no error.
  · *Renaming* makes the Store lie about which game this is.  The filename is
    the identity for every system whose `gameId` strategy is `filename`
    (`services/gameid.py`), so a rename moves box art, scraping and the
    player's recorded hours onto a game that does not exist — and for class C
    §5.1 requires the name *preserved*, because the emulator looks the romset
    up by it.  A silently wrong identity is worse than a refusal.
  · *Refusing* costs one clear sentence and loses nothing that was ever going
    to work.

So: **refuse, and name the file.**  `unscannable()` mirrors `:127` exactly, and
it is applied to the names that land at the top level of the ROM directory —
which is precisely what the scanner iterates.  It does not recurse, so a class
F game directory is checked by its own name and never by its contents: a PS3
dump that happens to carry a `.DS_Store` is a valid game, and rejecting it
would be inventing a rule the scanner does not have.  For a copied set the
check skips files `shadowed_by_a_descriptor` already hides, because a track is
opened by name through its `.cue` and was never going to be listed anyway.

**A malicious or malformed archive.** A member named `../../etc/truc` writes
outside the work area.  The parade here is *closed by construction*, not a
check bolted on afterwards: §2.4 requires flat extraction anyway, so a member
is only ever written to `ingest/<last component of its name>`.  A name with no
path left in it has nowhere to escape to.  Three things finish it —
separators are normalised so a Windows-written `..\\..\\x.nes` cannot smuggle
one past a POSIX basename; symlink and directory members are never written,
which closes the second half of the escape (a link whose target is outside);
and `"xb"` refuses to follow anything already sitting at the destination.

On top of that construction, a member whose stored name is absolute or carries
a `..` component is **refused outright**.  Flattening alone would already
contain it, and `sub/deep.nes` → `deep.nes` is required behaviour — but an
archive that tried to escape is worth saying out loud rather than quietly
ingesting, and the two layers mean removing either one still leaves the write
contained.  `applier._pack_file` is the same reflex one directory over.

── Bounded, cancellable, and it reports ───────────────────────────────────
A 12 GB archive does not unpack in one uninterruptible burst.  Everything here
streams in chunks inside the event loop, exactly as `materializer.py` streams a
download: progress is persisted and broadcast on its own pair of columns,
`await` between chunks makes cancellation real, and both cancellation and
failure remove the produced directory and nothing else.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import stat
import subprocess
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Awaitable, Callable

from ..catalog import load_catalog
from ..rom_scanner import matches_ext, shadowed_by_a_descriptor
from .inspector import (ARCHIVE_SUFFIXES, MAX_LISTING_ENTRIES,
                        MISSING_7Z, declared_non_archive)
from .materializer import MIN_FREE_AFTER_DOWNLOAD, job_dir

# The same reserve the download keeps, and for the same reason: it is the
# appliance's headroom — SQLite, logs, the session — not one step's.
MIN_FREE_AFTER_TRANSFORM = MIN_FREE_AFTER_DOWNLOAD

Progress = Callable[[str, int, int], Awaitable[None]]
log = logging.getLogger(__name__)

#: The one directory this step creates, inside the work area the job owns.
#: A subdirectory and not a sibling: matrix §5 keeps everything in
#: `store/jobs/<job-id>/` until import, and `test_store_jobs.py`'s write guard
#: permits exactly that prefix.
SHAPE_DIR = "ingest"

CLASSES = frozenset("ABCDEF")

_CHUNK = 1024 * 1024
_REPORT_EVERY_BYTES = 64 * 1024 * 1024
_REPORT_EVERY_SECONDS = 0.5


class TransformError(RuntimeError):
    """A bounded, player-readable reason no final shape exists."""


@dataclass(frozen=True)
class Shape:
    """What the transformation produced, for validation (16) to consume."""

    ingestion_class: str
    root: Path
    #: What lands at the top level of the ROM directory, in emitted order.
    names: tuple[str, ...] = ()
    bytes_written: int = 0


@dataclass(frozen=True)
class _Member:
    """One archive entry, as listed and never as extracted."""

    name: str
    size: int
    is_dir: bool = False
    is_link: bool = False


@dataclass(frozen=True)
class _Plan:
    """Everything decided before a single byte is produced.

    Built in full, then checked in full, then executed.  A refusal therefore
    leaves the work area exactly as inspection left it.
    """

    kind: str                                    # copy | unpack | tree
    names: tuple[str, ...]                       # what lands at the top level
    total: int                                   # bytes the shape will occupy
    sources: tuple[Path, ...] = ()               # copy: the files; unpack: the archive
    members: tuple[_Member, ...] = ()            # unpack only
    tree: tuple[tuple[Path, str, int], ...] = ()  # tree only: (source, rel, size)
    tree_dirs: tuple[str, ...] = ()              # tree only: every directory, rel


def shape_dir(job_id: str) -> Path:
    """Where this job's final shape is produced; rejects a corrupted id."""
    try:
        return job_dir(job_id) / SHAPE_DIR
    except Exception as exc:                                   # noqa: BLE001
        raise TransformError("the job id cannot name a work directory") from exc


def cleanup_shape(job_id: str) -> None:
    """Remove what this step produced — never the source, never a parent.

    The path is computed, not passed in: a validated job id joined to one
    constant cannot name the download, another job, or anything above them.
    """
    try:
        produced = shape_dir(job_id)
    except TransformError:
        return
    try:
        if produced.is_symlink():
            # Never rmtree *through* a link. This directory is created here and
            # can only be a link if something raced it, which is reason enough.
            produced.unlink()
            return
        shutil.rmtree(produced)
    except FileNotFoundError:
        pass
    except OSError as exc:
        log.warning("store: could not clean the shape for job %s — %s", job_id, exc)


def unscannable(name: str) -> str:
    """Why `rom_scanner.py:127` would drop this name, or "" if it would list it.

    A mirror of that line and deliberately not an import of it: the scanner
    applies the rule while listing, and this has to apply it while deciding
    whether a name may be written at all.  `"example"` is a substring test and
    is not anchored, which is the scanner's behaviour and therefore the rule.
    """
    if name.startswith("."):
        return "its name starts with a dot"
    if "example" in name.lower():
        return 'its name contains "example"'
    return ""


def _flat_name(raw: str) -> str:
    """The only name a member may land under: its last component, nothing else.

    Both separators are folded first.  A zip written on Windows stores
    `dir\\game.nes`, and `\\` is a legal filename character on Linux — a
    POSIX-only basename would emit a file literally called `..\\..\\etc\\x.nes`.
    """
    return PurePosixPath(raw.replace("\\", "/")).name


def _refuse_escape(raw: str) -> None:
    """Say out loud that an archive tried to leave the directory it was given.

    Containment does not depend on this — `_flat_name` already removed every
    path component — but an absolute member, or one with a `..` in it, is not
    an honest packaging choice the way `sub/game.nes` is.
    """
    folded = raw.replace("\\", "/")
    parts = PurePosixPath(folded).parts
    if folded.startswith("/") or ".." in parts:
        raise TransformError(
            f"the archive contains a member that points outside the download "
            f"({raw!r}); it was not unpacked")
    if not _flat_name(folded) or _flat_name(folded) in (".", ".."):
        raise TransformError(
            f"the archive contains a member with no usable name ({raw!r})")


# ── listing an archive, with sizes and without extracting ──────────────────


def _zip_members(archive: Path) -> tuple[_Member, ...]:
    """List a zip through the standard library: names, sizes, kinds.

    Preferred over `7z l` for zips because `ZipFile` reports the unix mode, so
    a symlink member is recognised rather than guessed, and because the entries
    come back one object each — no text to reparse.
    """
    try:
        with zipfile.ZipFile(archive) as zipped:
            infos = zipped.infolist()
            if len(infos) > MAX_LISTING_ENTRIES:
                raise TransformError(
                    "the archive holds too many members to unpack safely")
            return tuple(
                _Member(
                    name=info.filename,
                    size=int(info.file_size),
                    is_dir=info.is_dir(),
                    is_link=stat.S_ISLNK(info.external_attr >> 16),
                )
                for info in infos)
    except TransformError:
        raise
    except (OSError, zipfile.BadZipFile, ValueError) as exc:
        raise TransformError("the archive cannot be opened") from exc


def _attribute_kind(attributes: str) -> tuple[bool, bool]:
    """(is_dir, is_link) out of one `7z l -slt` Attributes line.

    Measured on 7-Zip 26.02, the field has three shapes — `D drwxrwxr-x` for a
    directory, `V 01800000 0rw-------` for a file, and ` lrwxrwxrwx` for a
    symbolic link.  The DOS flags come first when there are any, and the unix
    mode is always the last token, so the two questions are asked of the two
    ends and never of a fixed column.
    """
    tokens = attributes.split()
    if not tokens:
        return False, False
    return tokens[0] == "D", tokens[-1].startswith("l")


def _7z_members(archive: Path) -> tuple[_Member, ...]:
    """List a 7z with `7z l -slt`, parsing only Path, Size and Attributes."""
    try:
        done = subprocess.run(
            ["7z", "l", "-slt", "-ba", "--", str(archive)],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=300, check=False)
    except FileNotFoundError as exc:
        raise TransformError(MISSING_7Z) from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise TransformError("the archive directory cannot be read") from exc
    if done.returncode != 0:
        raise TransformError("the archive directory cannot be read")

    members: list[_Member] = []
    name = ""
    size = 0
    attributes = ""

    def flush() -> None:
        nonlocal name, size, attributes
        if not name:
            return
        is_dir, is_link = _attribute_kind(attributes)
        members.append(_Member(name=name, size=size,
                               is_dir=is_dir, is_link=is_link))
        name, size, attributes = "", 0, ""

    # `-slt` emits one `Key = value` block per entry, blocks separated by a
    # blank line. A `Path` also starts a new one, so a listing that ends
    # without its trailing blank line still yields its last entry.
    for raw in done.stdout.decode("utf-8", errors="replace").splitlines():
        line = raw.rstrip("\r")
        if line.startswith("Path = "):
            flush()
            name = line[7:]
        elif not name:
            continue
        elif line.startswith("Size = "):
            try:
                size = max(0, int(line[7:].strip() or 0))
            except ValueError:
                size = 0
        elif line.startswith("Attributes = "):
            attributes = line[13:]
        elif not line.strip():
            flush()
        if len(members) > MAX_LISTING_ENTRIES:
            raise TransformError(
                "the archive holds too many members to unpack safely")
    flush()
    return tuple(members)


def _members(archive: Path) -> tuple[_Member, ...]:
    if archive.suffix.lower() == ".zip":
        return _zip_members(archive)
    return _7z_members(archive)


# ── deciding what to produce ───────────────────────────────────────────────


def _tree_manifest(root: Path) -> tuple[tuple[tuple[Path, str, int], ...],
                                        tuple[str, ...]]:
    """Every file and every directory under `root`, relative to it.

    Walked once, up front, because the free-space reserve has to be checked
    before anything is created — and because a second walk could see a
    different tree.

    Directories are collected and not merely inferred from the files' parents:
    an empty one is part of the tree, and §5.1's F row says *never flatten*, so
    dropping it would be this step quietly deciding it did not matter.

    Symlinks are refused rather than skipped: copying one carries a target from
    outside the download into the library, and skipping it in silence is the
    failure mode §5.3 rule 3 describes.
    """
    manifest: list[tuple[Path, str, int]] = []
    directories: list[str] = []
    for base, dirs, files in os.walk(root, followlinks=False):
        here = Path(base)
        for name in sorted(dirs):
            if (here / name).is_symlink():
                raise TransformError(
                    f"the game directory contains a symbolic link ({name}); "
                    "it was not copied")
            directories.append((here / name).relative_to(root).as_posix())
        for name in sorted(files):
            source = here / name
            if source.is_symlink():
                raise TransformError(
                    f"the game directory contains a symbolic link ({name}); "
                    "it was not copied")
            try:
                size = source.stat().st_size
            except OSError as exc:
                raise TransformError(
                    f"a file in the game directory cannot be read ({name})") from exc
            manifest.append((source, source.relative_to(root).as_posix(), size))
        if len(manifest) + len(directories) > MAX_LISTING_ENTRIES:
            raise TransformError(
                "the game directory holds too many files to copy safely")
    return tuple(manifest), tuple(directories)


def _plan(ingestion_class: str, entries: tuple[Path, ...],
          extensions: tuple[str, ...]) -> _Plan:
    """Turn the persisted verdict into one executable plan, with no system list."""
    links = tuple(e for e in entries if e.is_symlink())
    if links:
        # Never followed and never carried: a link at the top of the work area
        # would put a target from outside the download into the shape.
        raise TransformError(
            f"the download contains a symbolic link ({links[0].name}); "
            "it was not given a shape")
    files = tuple(sorted((e for e in entries if e.is_file()),
                         key=lambda p: p.name.lower()))
    dirs = tuple(sorted((e for e in entries if e.is_dir()),
                        key=lambda p: p.name.lower()))
    if len(files) + len(dirs) != len(entries):
        raise TransformError(
            "the download contains something that is neither a file nor a "
            "directory; it was not given a shape")

    if ingestion_class == "F":
        # §5.1: never flatten, never unpack into a subdir. The tree arrives as
        # the game and leaves as the game; its interior is the emulator's
        # business and the scanner never looks inside it (§1.2).
        if not dirs:
            raise TransformError(
                "this class F download has no game directory to keep")
        # Loose files beside the game directory are *deliberately* not carried
        # into the shape: `scanDirs` is true for these packs, so the scan
        # yields directories only and a loose file is invisible to the library
        # whatever this step does with it (§1.2, §1.6). Copying it would double
        # its bytes to no effect.
        tree: list[tuple[Path, str, int]] = []
        tree_dirs: list[str] = []
        total = 0
        for top in dirs:
            files_under, dirs_under = _tree_manifest(top)
            tree_dirs.append(top.name)
            tree_dirs.extend(f"{top.name}/{rel}" for rel in dirs_under)
            for source, rel, size in files_under:
                tree.append((source, f"{top.name}/{rel}", size))
                total += size
        return _Plan(kind="tree", names=tuple(d.name for d in dirs),
                     total=total, sources=dirs, tree=tuple(tree),
                     tree_dirs=tuple(tree_dirs))

    if ingestion_class in ("A", "D"):
        archives = tuple(f for f in files
                         if f.suffix.lower() in ARCHIVE_SUFFIXES)
        # One predicate for both classes (§2.4): unpack only when the
        # container's own extension is undeclared. Class A never declares an
        # archive, so an archive that arrived for A always qualifies; D's
        # "only if undeclared" is that same test, written once.
        undeclared = tuple(a for a in archives
                           if not matches_ext(a.name, list(extensions)))
        if undeclared:
            if len(archives) > 1 or len(files) != 1:
                raise TransformError(
                    "this download has more than one payload to unpack")
            archive = undeclared[0]
            wanted: list[_Member] = []
            for member in _members(archive):
                if member.is_dir or member.is_link:
                    continue
                _refuse_escape(member.name)
                if declared_non_archive(_flat_name(member.name), extensions):
                    wanted.append(member)
            if not wanted:
                # §2.4's third row: nothing inside carries an extension this
                # pack declares, so there is nothing ingestible to produce.
                raise TransformError(
                    "the archive contains no file with an extension this "
                    "console declares, so unpacking it would produce no game")
            flat = [_flat_name(m.name) for m in wanted]
            duplicates = {n for n in flat if flat.count(n) > 1}
            if duplicates:
                # Flat is not optional (§2.4), so two members sharing a last
                # component would land on one name. Which one wins is not a
                # decision this step is allowed to take in silence.
                raise TransformError(
                    "the archive holds two files with the same name "
                    f"({sorted(duplicates)[0]}); it was not unpacked")
            return _Plan(kind="unpack", names=tuple(flat),
                         total=sum(m.size for m in wanted),
                         sources=(archive,), members=tuple(wanted))

    # B and C never unpack; A and D with a declared or absent container do not
    # either. E keeps its set together, flat. All four are the bytes as they
    # arrived, produced beside the source.
    if dirs:
        # A subdirectory on a non-`scanDirs` system produces zero games (§1.2),
        # so a copy that carried one would be a shape that cannot be listed.
        # Inspection already refuses this arrival; refused again rather than
        # dropped, because dropping it is how a game goes missing quietly.
        raise TransformError(
            f"this download holds a directory ({dirs[0].name}) on a console "
            "whose library only lists files; it was not given a shape")
    if not files:
        raise TransformError("this download has no file to give a shape to")
    return _Plan(kind="copy", names=tuple(f.name for f in files),
                 total=sum(f.stat().st_size for f in files), sources=files)


def _refuse_unscannable(plan: _Plan, extensions: tuple[str, ...]) -> None:
    """Apply matrix §5.3 rule 2 to the names that will be listed as games.

    The scanner iterates the top level of the ROM directory and does not
    recurse, so those names — and only those — are what the rule can reach.
    For a copied set the shadow map is subtracted first: a track named by a
    `.cue` is opened through the descriptor and was never going to be listed.
    An unpack cannot use the map, because the descriptor it would have to read
    does not exist until after extraction, so every emitted name is checked.
    """
    hidden: dict[str, str] = {}
    if plan.kind == "copy":
        hidden = shadowed_by_a_descriptor(list(plan.sources), list(extensions))
    for name in plan.names:
        if name.lower() in hidden:
            continue
        why = unscannable(name)
        if why:
            raise TransformError(
                f"this download cannot be added because {why}: {name!r}. "
                "The library would drop the file without a word, and renaming "
                "it would file the game under the wrong name")


# ── producing it ───────────────────────────────────────────────────────────


def _inside(produced: Path, rel: str) -> Path:
    """Join a class F relative path, refusing anything that leaves the shape.

    `rel` comes from `relative_to`, so it carries no root and no `..` and this
    can only fire if that stops being true — which is the same reflex as
    `applier._pack_file`, and the reason to keep it is that the alternative is
    trusting a walk to stay inside a directory it was given.
    """
    dest = produced / rel
    if not dest.resolve().is_relative_to(produced.resolve()):
        raise TransformError(
            f"a path in the game directory points outside it ({rel})")
    return dest


async def _pump(read: Callable[[int], bytes], dest: Path,
                on_bytes: Callable[[int], Awaitable[None]]) -> int:
    """Stream one destination into being, chunk by chunk.

    `"xb"` is the whole of the overwrite and symlink-follow protection: O_EXCL
    fails on anything already at the path instead of writing through it.
    """
    written = 0
    with dest.open("xb") as out:
        while chunk := read(_CHUNK):
            out.write(chunk)
            written += len(chunk)
            await on_bytes(len(chunk))
            # Cancellation is observed even when every read answers at once.
            await asyncio.sleep(0)
        out.flush()
        os.fsync(out.fileno())
    return written


async def _pump_7z(archive: Path, member: str, dest: Path,
                   on_bytes: Callable[[int], Awaitable[None]]) -> int:
    """Extract one 7z member **through a pipe**, so 7z writes no file itself.

    `-so` means the bytes come back on stdout and this function decides where
    they land; the tool is never given an output directory and can therefore
    not be the thing that places a file. `-spd` makes the member name literal,
    so an entry called `od[d].rom` is matched as itself and not as a pattern.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "7z", "x", "-so", "-spd", "--", str(archive), member,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    except FileNotFoundError as exc:
        raise TransformError(MISSING_7Z) from exc
    except (OSError, ValueError) as exc:
        raise TransformError("the archive cannot be unpacked") from exc

    written = 0
    try:
        assert proc.stdout is not None
        with dest.open("xb") as out:
            while chunk := await proc.stdout.read(_CHUNK):
                out.write(chunk)
                written += len(chunk)
                await on_bytes(len(chunk))
            out.flush()
            os.fsync(out.fileno())
        status = await proc.wait()
    except BaseException:
        proc.kill()
        await proc.wait()
        raise
    if status != 0:
        raise TransformError(f"the archive member {member!r} could not be unpacked")
    return written


class ShapeTransformer:
    """Produce one job's final shape beside its download, and report on it."""

    name = "shape"

    def __init__(self, *, progress: Progress,
                 free_bytes: Callable[[Path], int] | None = None):
        self._progress = progress
        self._free_bytes = free_bytes or (lambda path: shutil.disk_usage(path).free)

    async def transform(self, job, ingestion_class: str) -> Shape:
        """Decide everything, check everything, then write. In that order.

        Nothing is created until every refusal has had its chance, so a
        download this step declines leaves the work area exactly as inspection
        left it — and the source is byte-identical in every outcome, because
        the only handle ever taken on it is `"rb"`.
        """
        if ingestion_class not in CLASSES:
            raise TransformError("this download has no ingestion class to act on")

        pack = load_catalog().get(job.system_id)
        if pack is None or pack.data.get("kind") != "emulator":
            raise TransformError("the downloaded job's emulator pack is unavailable")
        roms = pack.data.get("roms") or {}
        extensions = tuple(x for x in (roms.get("extensions") or [])
                           if isinstance(x, str))

        work = job_dir(job.id)
        if work.is_symlink():
            raise TransformError(
                "the job work area is redirected through a symbolic link")
        produced = work / SHAPE_DIR
        if produced.exists() or produced.is_symlink():
            # The download itself can be called `ingest`. Refused, never
            # removed: the one path this step must not touch is the source.
            raise TransformError(
                f"the download work area already holds {SHAPE_DIR!r}, "
                "so the final shape has nowhere to go")
        try:
            entries = tuple(sorted(work.iterdir(), key=lambda p: p.name.lower()))
        except OSError as exc:
            raise TransformError("the downloaded files cannot be listed") from exc
        if not entries:
            raise TransformError("the download work area is empty")
        if len(entries) > MAX_LISTING_ENTRIES:
            raise TransformError("the download holds too many files to transform")

        try:
            plan = _plan(ingestion_class, entries, extensions)
        except OSError as exc:
            raise TransformError("the downloaded files cannot be read") from exc
        _refuse_unscannable(plan, extensions)

        # Producing beside the source doubles the footprint; the reserve is
        # checked before the first byte, never discovered halfway through.
        try:
            available = self._free_bytes(work)
        except OSError as exc:
            raise TransformError(
                "disk space for the final shape could not be checked") from exc
        required = plan.total + MIN_FREE_AFTER_TRANSFORM
        if available < required:
            raise TransformError(
                f"not enough disk space to give this download its final shape "
                f"({plan.total} bytes needed plus {MIN_FREE_AFTER_TRANSFORM} "
                "bytes kept free)")

        done = 0
        last_reported = 0
        last_report_at = time.monotonic()
        await self._progress(job.id, 0, plan.total)

        async def on_bytes(count: int) -> None:
            nonlocal done, last_reported, last_report_at
            done += count
            now = time.monotonic()
            if (done - last_reported >= _REPORT_EVERY_BYTES
                    or now - last_report_at >= _REPORT_EVERY_SECONDS):
                await self._progress(job.id, done, plan.total)
                last_reported, last_report_at = done, now

        try:
            produced.mkdir(mode=0o700, parents=False, exist_ok=False)
            written = await self._produce(plan, produced, on_bytes)
            await self._progress(job.id, done, plan.total)
        except asyncio.CancelledError:
            # Only what this step made. The download stays where it is.
            cleanup_shape(job.id)
            raise
        except TransformError:
            cleanup_shape(job.id)
            raise
        except (OSError, zipfile.BadZipFile, ValueError) as exc:
            cleanup_shape(job.id)
            raise TransformError(
                "the final shape could not be written") from exc
        except BaseException:
            # Deliberately total. A half-written shape is the one thing that
            # must not survive this step, and an exception nobody predicted —
            # a decompressor's own error type, a `KeyboardInterrupt` — would
            # otherwise leave one behind for validation to trust.
            cleanup_shape(job.id)
            raise

        return Shape(ingestion_class=ingestion_class, root=produced,
                     names=plan.names, bytes_written=written)

    async def _produce(self, plan: _Plan, produced: Path,
                       on_bytes: Callable[[int], Awaitable[None]]) -> int:
        written = 0
        if plan.kind == "copy":
            for source in plan.sources:
                # `"rb"`, and this is the only handle this module ever takes on
                # a downloaded file.
                with source.open("rb") as stream:
                    written += await _pump(stream.read, produced / source.name,
                                           on_bytes)
            return written

        if plan.kind == "tree":
            # Directories first, and all of them: an empty one is part of the
            # tree that §5.1 says never to flatten.
            for rel in plan.tree_dirs:
                _inside(produced, rel).mkdir(mode=0o700, parents=True,
                                             exist_ok=True)
            for source, rel, _size in plan.tree:
                dest = _inside(produced, rel)
                dest.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                with source.open("rb") as stream:
                    written += await _pump(stream.read, dest, on_bytes)
            return written

        archive = plan.sources[0]
        if archive.suffix.lower() == ".zip":
            with zipfile.ZipFile(archive) as zipped:
                for member in plan.members:
                    dest = produced / _flat_name(member.name)
                    with zipped.open(member.name) as stream:
                        written += await _pump(stream.read, dest, on_bytes)
            return written
        for member in plan.members:
            dest = produced / _flat_name(member.name)
            written += await _pump_7z(archive, member.name, dest, on_bytes)
        return written
