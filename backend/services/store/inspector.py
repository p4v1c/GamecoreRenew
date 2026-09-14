"""Inspect and classify materialized Store bytes without changing them.

The six classes and their four predicates are the contract in ingestion matrix
§5.  This module deliberately owns no system list: it reads ``roms.extensions``
and ``roms.scanDirs`` from the selected pack, plus the shape and archive member
names in the job work area.  Archive directories are listed with ``7z l``;
nothing is extracted, renamed or moved.
"""
from __future__ import annotations

import os
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from ..catalog import load_catalog
from ..rom_scanner import _DISC_DESCRIPTORS, _DISC_TRACKS, _references, matches_ext
from .materializer import job_dir

ARCHIVE_SUFFIXES = frozenset({".zip", ".7z"})

# Matrix §5.1 reserves class D to the disc images: the containers that are a
# whole disc on their own — `.chd .iso .cso .rvz .wbfs .gcm .pbp .wux .cdi` —
# plus the raw track extensions the scanner already names (`_DISC_TRACKS`
# contributes `.iso`, and a bare `.bin`/`.img` dump is a disc image on
# `duckstation` and `pcsx2`, matrix §3.3). This is a list of *formats*, never of
# systems: it is half of a pair predicate (§0), and a pack added tomorrow that
# declares `*.chd` lands in D with no edit here, which is the property §5.2
# claims for all four predicates.
DISC_IMAGE_SUFFIXES = frozenset(
    {".chd", ".cso", ".rvz", ".wbfs", ".gcm", ".pbp", ".wux", ".cdi"}) | _DISC_TRACKS

# Named, not merely reported. 7z is the only external program inspection runs,
# and when it is absent every archive class — A, B and C — fails at once; a
# message that says only "cannot be read" sends the player back to their
# download to look for a fault that is not there. `install/arch.sh` carries
# p7zip as a base package so a current box never sees this.
MISSING_7Z = ("the archive cannot be opened: this box is missing the 7z tool "
              "(the p7zip package) — a GameCore update installs it")
MAX_LISTING_ENTRIES = 10_000
MAX_LISTING_NAME_BYTES = 2 * 1024 * 1024
MAX_ARCHIVE_LISTING_BYTES = 8 * 1024 * 1024
MAX_DESCRIPTOR_BYTES = 1024 * 1024


@dataclass(frozen=True)
class Inspection:
    ingestion_class: str
    complete: bool = True
    reason: str = ""


class InspectionError(RuntimeError):
    """A bounded, player-readable reason inspection could not finish."""


def _bounded_names(lines) -> tuple[str, ...]:
    names: list[str] = []
    total = 0
    for raw in lines:
        name = raw.rstrip("\r\n")
        if not name:
            continue
        total += len(name.encode("utf-8", errors="replace"))
        if len(names) >= MAX_LISTING_ENTRIES or total > MAX_LISTING_NAME_BYTES:
            raise InspectionError("the download listing is too large to inspect safely")
        names.append(name)
    return tuple(names)


def _archive_members(archive: Path) -> tuple[str, ...]:
    """Stream an archive directory with a hard cap; never extract a member."""
    try:
        process = subprocess.Popen(
            ["7z", "l", "-slt", "-ba", "--", str(archive)],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=False)
    except FileNotFoundError as exc:
        raise InspectionError(MISSING_7Z) from exc
    except (OSError, ValueError) as exc:
        raise InspectionError("the archive directory cannot be read") from exc

    names: list[str] = []
    name_bytes = 0
    output_bytes = 0
    pending = b""
    try:
        assert process.stdout is not None
        while chunk := process.stdout.read(64 * 1024):
            output_bytes += len(chunk)
            if output_bytes > MAX_ARCHIVE_LISTING_BYTES:
                raise InspectionError("the archive listing is too large to inspect safely")
            pending += chunk
            lines = pending.split(b"\n")
            pending = lines.pop()
            for line in lines:
                if not line.startswith(b"Path = "):
                    continue
                raw_name = line[7:].rstrip(b"\r")
                name_bytes += len(raw_name)
                if (len(names) >= MAX_LISTING_ENTRIES
                        or name_bytes > MAX_LISTING_NAME_BYTES):
                    raise InspectionError(
                        "the archive listing is too large to inspect safely")
                names.append(raw_name.decode("utf-8", errors="replace"))
        status = process.wait()
    except BaseException:
        process.kill()
        process.wait()
        raise
    if status != 0:
        raise InspectionError("the archive directory cannot be read")
    return tuple(names)


def _top_level(root: Path) -> tuple[Path, ...]:
    try:
        with os.scandir(root) as entries:
            paths = _bounded_names(entry.name for entry in entries)
    except OSError as exc:
        raise InspectionError("the downloaded files cannot be listed") from exc
    return tuple(root / name for name in paths)


def declared_non_archive(name: str, extensions: tuple[str, ...]) -> bool:
    """§5.2's B-vs-C predicate: does this member carry a declared, non-archive
    extension?  Shared with `transformer.py`, which needs the same question to
    pick the members §2.4 lets it unpack — two copies of it would be the drift
    the matrix warns about."""
    suffix = PurePosixPath(name).suffix.lower()
    return suffix not in ARCHIVE_SUFFIXES and matches_ext(name, list(extensions))


def _declares_archive(extensions: tuple[str, ...]) -> bool:
    """§5.2's A-vs-B predicate, read off the pack alone: is an archive declared?"""
    return any(matches_ext(f"payload{suffix}", list(extensions))
               for suffix in ARCHIVE_SUFFIXES)


def _plain_class(entries: tuple[Path, ...], extensions: tuple[str, ...]) -> str:
    """Classify a payload that already arrived as the bare file(s) — A, B or D.

    The pair, not the system and not the format alone (§0). The format half
    decides D: a self-contained disc image is class D whichever system receives
    it, because D's validation is a disc header (§5.1) and no other class reads
    one. Everything else is a plain ROM, and there the pack half decides — §5.2:
    *"A vs B is one predicate: is the archive extension declared?"*, which is
    exactly what separates §5.1's A row (`nes` `fds` `megadrive` … , none of
    which declares `*.zip`) from its B row (`snes9x` `melonds` `mgba` `azahar`
    `gopher64` `ryujinx`, all of which do).

    Before this predicate existed every bare file answered D, so a `.sfc` and a
    `.xci` were labelled disc images and would have been validated by reading a
    disc header they do not have.
    """
    if any(entry.suffix.lower() in DISC_IMAGE_SUFFIXES for entry in entries):
        return "D"
    return "B" if _declares_archive(extensions) else "A"


def _descriptor_required_names(descriptor: Path) -> tuple[str, ...]:
    """Names a loose descriptor requires, with the shared bounded read."""
    suffix = descriptor.suffix.lower()
    if suffix == ".ccd":
        return (descriptor.with_suffix(".img").name,
                descriptor.with_suffix(".sub").name)
    if suffix == ".mds":
        return (descriptor.with_suffix(".mdf").name,)
    try:
        with descriptor.open("rb") as stream:
            raw = stream.read(MAX_DESCRIPTOR_BYTES + 1)
    except OSError as exc:
        raise InspectionError(f"the descriptor {descriptor.name} cannot be read") from exc
    if len(raw) > MAX_DESCRIPTOR_BYTES:
        raise InspectionError(
            f"the descriptor {descriptor.name} is too large to inspect safely")
    text = raw.decode("utf-8", errors="replace")
    required = tuple(Path(ref.strip()).name
                     for ref in _references(descriptor, text) if ref.strip())
    return required or ("a companion named by the descriptor",)


def _missing_descriptor_files(descriptor: Path, entries: tuple[Path, ...]) -> tuple[str, ...]:
    present = {entry.name.lower() for entry in entries}
    required = _descriptor_required_names(descriptor)
    return tuple(name for name in required if name.lower() not in present)


def _archive_member_bytes(archive: Path, member: str) -> bytes:
    """Read one descriptor from an archive, bounded like a loose descriptor."""
    try:
        if archive.suffix.lower() == ".zip":
            with zipfile.ZipFile(archive) as bundle, bundle.open(member) as stream:
                raw = stream.read(MAX_DESCRIPTOR_BYTES + 1)
        else:
            process = subprocess.Popen(
                ["7z", "x", "-so", "-spd", "--", str(archive), member],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            assert process.stdout is not None
            raw = process.stdout.read(MAX_DESCRIPTOR_BYTES + 1)
            if len(raw) > MAX_DESCRIPTOR_BYTES:
                process.kill()
            try:
                status = process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                raise
            if status and len(raw) <= MAX_DESCRIPTOR_BYTES:
                raise InspectionError(
                    f"the descriptor {PurePosixPath(member).name} cannot be read")
    except FileNotFoundError as exc:
        raise InspectionError(MISSING_7Z) from exc
    except (OSError, zipfile.BadZipFile, KeyError, subprocess.TimeoutExpired) as exc:
        raise InspectionError(
            f"the descriptor {PurePosixPath(member).name} cannot be read") from exc
    if len(raw) > MAX_DESCRIPTOR_BYTES:
        raise InspectionError(
            f"the descriptor {PurePosixPath(member).name} is too large to inspect safely")
    return raw


def _archive_set_members(archive: Path, members: tuple[str, ...],
                         extensions: tuple[str, ...]) -> tuple[tuple[str, ...],
                                                               tuple[str, ...]]:
    """Return a class-E descriptor closure and the companions it lacks.

    Member paths are compared by basename because matrix §2.4 requires a flat
    emitted set and the scanner's descriptor resolver does the same. Duplicate
    basenames remain the transformer's explicit refusal rather than silently
    selecting one.
    """
    files = tuple(name for name in members if name and not name.endswith(("/", "\\")))
    by_name: dict[str, list[str]] = {}
    for name in files:
        by_name.setdefault(PurePosixPath(name.replace("\\", "/")).name.lower(), []).append(name)
    descriptors = tuple(name for name in files
                        if PurePosixPath(name).suffix.lower() in _DISC_DESCRIPTORS
                        and matches_ext(PurePosixPath(name).name, list(extensions)))
    wanted = list(descriptors)
    missing: list[str] = []
    for stored in descriptors:
        leaf = PurePosixPath(stored.replace("\\", "/")).name
        suffix = PurePosixPath(leaf).suffix.lower()
        if suffix == ".ccd":
            required = [str(PurePosixPath(leaf).with_suffix(".img")),
                        str(PurePosixPath(leaf).with_suffix(".sub"))]
        elif suffix == ".mds":
            required = [str(PurePosixPath(leaf).with_suffix(".mdf"))]
        else:
            text = _archive_member_bytes(archive, stored).decode(
                "utf-8", errors="replace")
            required = [Path(ref.strip()).name
                        for ref in _references(Path(leaf), text) if ref.strip()]
            if not required:
                missing.append("a companion named by the descriptor")
                continue
        for required_name in required:
            matches = by_name.get(required_name.lower(), [])
            if not matches:
                missing.append(required_name)
            else:
                wanted.extend(matches)
    return tuple(dict.fromkeys(wanted)), tuple(dict.fromkeys(missing))


def inspect(job_id: str, system_id: str) -> Inspection:
    """Classify one job work area and report whether its class can be met."""
    pack = load_catalog().get(system_id)
    if pack is None or pack.data.get("kind") != "emulator":
        raise InspectionError("the downloaded job's emulator pack is unavailable")
    roms = pack.data.get("roms") or {}
    extensions = tuple(x for x in (roms.get("extensions") or [])
                       if isinstance(x, str))
    entries = _top_level(job_dir(job_id))
    if not entries:
        raise InspectionError("the download work area is empty")

    # Predicate four: folder games are the one class whose top-level object
    # must be a directory.  A loose file cannot be repaired by later stages.
    if bool(roms.get("scanDirs")):
        if any(entry.is_dir() and not entry.is_symlink() for entry in entries):
            return Inspection("F")
        arrived = ", ".join(entry.name for entry in entries[:3])
        return Inspection(
            "F", False,
            f"incomplete class F download: a complete game directory is missing; "
            f"only loose file(s) arrived ({arrived})")

    files = tuple(entry for entry in entries if entry.is_file() and not entry.is_symlink())
    if len(files) != len(entries):
        raise InspectionError("the download contains an unsupported directory or link")

    descriptors = tuple(entry for entry in files
                        if entry.suffix.lower() in _DISC_DESCRIPTORS
                        and matches_ext(entry.name, list(extensions)))
    # Predicate three: a declared descriptor is class E. What is left is a bare
    # file, and `_plain_class` splits it between D, B and A — it is not all D.
    if descriptors:
        missing: list[str] = []
        for descriptor in descriptors:
            missing.extend(_missing_descriptor_files(descriptor, files))
        if missing:
            named = ", ".join(dict.fromkeys(missing))
            return Inspection(
                "E", False,
                f"incomplete class E download: {descriptors[0].name} is missing {named}")
        return Inspection("E")

    undeclared_descriptors = tuple(entry for entry in files
                                   if entry.suffix.lower() in _DISC_DESCRIPTORS)
    if undeclared_descriptors:
        return Inspection(
            "D", False,
            f"incomplete class D download: {undeclared_descriptors[0].name} is a "
            "disc descriptor this pack does not declare")

    archives = tuple(entry for entry in files
                     if entry.suffix.lower() in ARCHIVE_SUFFIXES)
    if not archives:
        visible = tuple(entry for entry in files
                        if not extensions or matches_ext(entry.name, list(extensions)))
        if not visible:
            # Nothing here is ingestible, so the class is read off what arrived
            # rather than off what the pack can hold — the label still has to
            # name the shape the download had.
            unusable = _plain_class(files, extensions)
            return Inspection(
                unusable, False,
                f"incomplete class {unusable} download: no file has an extension "
                "declared by this pack")
        return Inspection(_plain_class(visible, extensions))
    if len(files) != 1 or len(archives) != 1:
        raise InspectionError("the download has more than one archive payload")

    archive = archives[0]
    members = _archive_members(archive)
    # Predicates one and two: whether the archive itself is declared, then
    # whether one member has a declared non-archive extension.
    archive_declared = matches_ext(archive.name, list(extensions))
    member_declared = any(declared_non_archive(name, extensions) for name in members)
    if archive_declared:
        return Inspection("B" if member_declared else "C")
    if not member_declared:
        return Inspection(
            "A", False,
            "incomplete class A download: the archive contains no member with "
            "an extension declared by this pack")
    descriptor_members = tuple(name for name in members
                               if PurePosixPath(name).suffix.lower() in _DISC_DESCRIPTORS
                               and matches_ext(PurePosixPath(name).name,
                                               list(extensions)))
    if descriptor_members:
        _wanted, missing = _archive_set_members(archive, members, extensions)
        first = PurePosixPath(descriptor_members[0]).name
        if missing:
            return Inspection(
                "E", False,
                f"incomplete class E download: {first} is missing "
                f"{', '.join(missing)}")
        return Inspection("E")
    return Inspection("A")
