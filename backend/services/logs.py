"""The logs directory: one folder per section, readable without journalctl.

    <DATA>/logs/backend/backend.log      what the backend logs (journal level)
    <DATA>/logs/launch/<system>/*.log    each launch's own output, newest kept

Every file is capped, and every directory is created on the write that needs
it, so a purge (`purge()`) never needs a restart. Nothing here names an
emulator: the launch section is whatever `process_manager` starts.
"""
from __future__ import annotations

import contextlib
import logging
import re
import shutil
import subprocess
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .paths import logs_dir

SECTION_MAX_BYTES = 2 * 1024 * 1024
SECTION_BACKUPS = 2
LAUNCHES_KEPT = 10
# A launch log is not capped while the game runs (the emulator writes to it
# directly); older ones are cut to their tail on the next launch.
LAUNCH_MAX_BYTES = 4 * 1024 * 1024
FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")

log = logging.getLogger(__name__)


class SectionFile(RotatingFileHandler):
    """A capped log file that recreates its directory, e.g. after a purge."""

    def __init__(self, path: Path):
        super().__init__(path, maxBytes=SECTION_MAX_BYTES,
                         backupCount=SECTION_BACKUPS, delay=True, encoding="utf-8")
        self.setFormatter(logging.Formatter(FORMAT))

    def _open(self):
        Path(self.baseFilename).parent.mkdir(parents=True, exist_ok=True)
        return super()._open()


def install() -> None:
    """Copy the backend's log records into `backend/backend.log`. Idempotent."""
    root = logging.getLogger()
    if not any(isinstance(h, SectionFile) for h in root.handlers):
        root.addHandler(SectionFile(logs_dir() / "backend" / "backend.log"))


def _safe(name: str) -> str:
    return _UNSAFE.sub("_", Path(name).name).strip("._")[:80] or "unknown"


def _tidy_launches(folder: Path) -> None:
    """Keep the newest LAUNCHES_KEPT logs, each cut to its last LAUNCH_MAX_BYTES."""
    logs = sorted(folder.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in logs[LAUNCHES_KEPT - 1:]:
        old.unlink(missing_ok=True)
    for kept in logs[:LAUNCHES_KEPT - 1]:
        if kept.stat().st_size > LAUNCH_MAX_BYTES:
            with kept.open("rb") as f:
                f.seek(-LAUNCH_MAX_BYTES, 2)
                tail = f.read()
            kept.write_bytes(b"[older output cut]\n" + tail)


@contextlib.contextmanager
def launch_output(system_id: str, game: str, cmd: list[str]):
    """The file a launch writes its stdout and stderr to; DEVNULL if it cannot
    be opened. Never fatal: a log must not cost the player the game."""
    try:
        folder = logs_dir() / "launch" / _safe(system_id or "unknown")
        folder.mkdir(parents=True, exist_ok=True)
        _tidy_launches(folder)
        path = folder / f"{time.strftime('%Y%m%d-%H%M%S')}-{_safe(game)}.log"
        out = path.open("ab")
        out.write(f"$ {' '.join(cmd)}\n".encode())
        out.flush()
    except OSError:
        log.warning("logs: no launch log for %s", system_id, exc_info=True)
        yield subprocess.DEVNULL
        return
    with out:
        yield out


def _files() -> list[Path]:
    root = logs_dir()
    return [p for p in root.rglob("*") if p.is_file()] if root.is_dir() else []


def usage() -> dict:
    """How much the logs directory holds."""
    files = _files()
    return {"files": len(files), "bytes": sum(p.stat().st_size for p in files)}


def purge() -> dict:
    """Delete every log. Returns what was freed, as `usage()` measured it."""
    freed = usage()
    for h in logging.getLogger().handlers:
        if isinstance(h, SectionFile):
            h.close()           # reopened (and its directory recreated) on the next record
    root = logs_dir()
    if root.is_dir():
        for child in root.iterdir():
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
    log.info("logs: purged %d files, %d bytes", freed["files"], freed["bytes"])
    return freed
