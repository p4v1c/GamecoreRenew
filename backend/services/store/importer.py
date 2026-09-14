"""Publish a validated Store shape in the live ROM library.

This is the only Store stage allowed to write below ``<DATA>/emu``.  Its
destination is the ``roms_dir`` persisted from the pack when the job was
queued, checked again against that same pack before anything is moved.

Every object first crosses from ``store/jobs`` to a hidden name in the target
directory with :func:`os.rename`.  That is the same-filesystem, atomic move
the data layout promises. Linux ``renameat2(RENAME_NOREPLACE)`` then publishes
both files and class-F directories without replacing an existing name. If
the first rename reports ``EXDEV`` we fail closed: copying would make a
partially-written file visible to the library scan.

On success the whole job work directory is removed: the library now owns the
validated shape, while retaining the downloaded source would needlessly keep
a second multi-gigabyte copy.  On refusal only ``ingest/`` is removed and the
original download stays, so a collision can be resolved without downloading
again and a failed import does not keep both copies.
"""
from __future__ import annotations

import ctypes
import errno
import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from ..catalog import load_catalog
from ..paths import roms_root
from .materializer import cleanup_job
from .transformer import Shape, cleanup_shape, shape_dir

log = logging.getLogger(__name__)

_AT_FDCWD = -100
_RENAME_NOREPLACE = 1


class ImportError(RuntimeError):
    """A player-readable reason a validated shape was not published."""


@dataclass(frozen=True)
class Imported:
    names: tuple[str, ...]
    warning: str = ""


def _pack_roms_dir(system_id: str) -> str:
    pack = load_catalog().get(system_id)
    if pack is None or pack.kind != "emulator":
        raise ImportError(f"{system_id!r} is not an emulator pack")
    roms = pack.data.get("roms") or {}
    return str(roms.get("dir", f"emu/{pack.id}")).rstrip("/")


def _destination(job) -> Path:
    """Resolve only the pack-derived, persisted ``emu/<dir>`` field."""
    raw = str(job.roms_dir).rstrip("/")
    expected = _pack_roms_dir(job.system_id)
    if raw != expected:
        raise ImportError(
            f"the job's ROM directory {raw!r} is not the directory declared "
            f"by the {job.system_id!r} pack ({expected!r})")
    parts = PurePosixPath(raw).parts
    if len(parts) != 2 or parts[0] != "emu" or parts[1] in ("", ".", ".."):
        raise ImportError("the pack's ROM directory is not one emu/<system> directory")
    root = roms_root()
    destination = root / parts[1]
    # A pack directory redirected by a symlink is no longer the directory the
    # job names, and may no longer share the work area's filesystem.
    if root.is_symlink() or (destination.exists()
                             and destination.resolve().parent != root.resolve()):
        raise ImportError("the pack's ROM directory is redirected outside emu/")
    return destination


def _rename_noreplace(source: Path, destination: Path) -> None:
    """Atomically publish an entry without POSIX rename's replacement."""
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise ImportError(
            "this system cannot atomically publish a game without "
            "risking an overwrite")
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p,
                          ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    result = renameat2(_AT_FDCWD, os.fsencode(source),
                       _AT_FDCWD, os.fsencode(destination),
                       _RENAME_NOREPLACE)
    if result:
        code = ctypes.get_errno()
        if code in (errno.EEXIST, errno.ENOTEMPTY):
            raise FileExistsError(code, os.strerror(code), destination)
        raise OSError(code, os.strerror(code), destination)


def _publish(source: Path, hidden: Path, destination: Path) -> None:
    """Move one complete object into the filesystem, then reveal it once."""
    try:
        os.rename(source, hidden)
    except OSError as exc:
        if exc.errno == errno.EXDEV:
            raise ImportError(
                "the Store work area and ROM library are on different "
                "filesystems; import was refused rather than copied non-atomically") from exc
        raise

    try:
        _rename_noreplace(hidden, destination)
    except FileExistsError as exc:
        raise ImportError(
            f"the library already contains {destination.name!r}; it was not overwritten") from exc


def _remove_published(path: Path) -> None:
    """Rollback only an entry this invocation proved it created."""
    try:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
    except FileNotFoundError:
        pass


def _import_shape(job, shape: Shape) -> Imported:
    """Implementation; the public wrapper owns refusal cleanup."""
    if shape.ingestion_class not in set("ABCDEF"):
        raise ImportError("the shape has no ingestion class A through F")
    root = shape.root
    expected_shape = shape_dir(job.id)
    if root.is_symlink() or root.resolve() != expected_shape.resolve():
        raise ImportError("the validated shape is not this job's ingest directory")
    try:
        entries = tuple(sorted(root.iterdir(), key=lambda p: p.name.lower()))
    except OSError as exc:
        raise ImportError("the validated shape cannot be listed for import") from exc
    if not entries:
        raise ImportError("the validated shape is empty")
    if shape.ingestion_class == "F":
        if any(not entry.is_dir() or entry.is_symlink() for entry in entries):
            raise ImportError("class F must import top-level game directories")
    elif any(not entry.is_file() or entry.is_symlink() for entry in entries):
        raise ImportError(f"class {shape.ingestion_class} must import flat files")

    destination_root = _destination(job)
    destination_root.mkdir(parents=True, exist_ok=True)
    finals = tuple(destination_root / entry.name for entry in entries)
    for final in finals:
        if os.path.lexists(final):
            cleanup_shape(job.id)
            raise ImportError(
                f"the library already contains {final.name!r}; it was not overwritten")

    published: list[Path] = []
    hidden: list[tuple[Path, Path]] = []
    try:
        for index, (entry, final) in enumerate(zip(entries, finals)):
            temporary = destination_root / f".gamecore-import-{job.id}-{index}"
            if os.path.lexists(temporary):
                raise ImportError("a previous hidden import entry still exists")
            hidden.append((temporary, entry))
            _publish(entry, temporary, final)
            published.append(final)
    except Exception as exc:
        for final in reversed(published):
            _remove_published(final)
        for temporary, original in reversed(hidden):
            if os.path.lexists(temporary) and not os.path.lexists(original):
                try:
                    os.rename(temporary, original)
                except OSError:
                    log.exception("store: could not restore refused import %s", job.id)
        cleanup_shape(job.id)
        if isinstance(exc, ImportError):
            raise
        raise ImportError(f"the validated shape could not be imported: {exc}") from exc

    warning = ""
    if any(path.suffix.lower() == ".nsp" for path in finals):
        warning = ("Imported with caution: an .nsp can be a base game, an update, "
                   "or DLC, and this box cannot distinguish them from the file.")
    cleanup_job(job.id)
    return Imported(tuple(path.name for path in finals), warning)


def import_shape(job, shape: Shape) -> Imported:
    """Publish classes A-E flat and class F as one top-level directory.

    Every refusal keeps the original download but drops the produced duplicate.
    """
    try:
        return _import_shape(job, shape)
    except Exception:
        cleanup_shape(job.id)
        raise
