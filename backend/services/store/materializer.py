"""Materialize one acquired target into its job-owned work directory.

The final file is ``<DATA>/store/jobs/<job-id>/<source filename>``.  It is not
the library: inspection, transformation, validation and import have not run,
and therefore nothing in this module even receives a ROM-directory path.

Interrupted transfers deliberately restart from zero.  Real-Debrid URLs are
short-lived, while a safe Range resume needs a persisted validator (ETag or
Last-Modified) and a checked 206 Content-Range.  Appending without those facts
can silently combine two different objects.  A ``.part`` is consequently
removed on every unsuccessful exit and on restart; a completed file is renamed
atomically and retained for the later ingestion stages.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import time
from pathlib import Path
from typing import Awaitable, Callable
from urllib.parse import urlsplit

import httpx

from ..paths import store_work_dir
from .jobs import AcquiredTarget, Job

Progress = Callable[[str, int, int], Awaitable[None]]
log = logging.getLogger(__name__)

# Leave enough room for SQLite, logs and the rest of the appliance to keep
# working.  The target itself is checked separately and exactly.
MIN_FREE_AFTER_DOWNLOAD = 256 * 1024 * 1024
_REPORT_EVERY_BYTES = 64 * 1024 * 1024
_REPORT_EVERY_SECONDS = 0.5
_JOB_ID = re.compile(r"^[0-9a-f]{32}$")


class MaterializationError(RuntimeError):
    """A safe, player-readable reason why no complete work file exists."""


def job_dir(job_id: str) -> Path:
    """The directory owned by one job; reject corrupted database ids."""
    if not _JOB_ID.fullmatch(job_id):
        raise MaterializationError("the job id cannot name a work directory")
    return store_work_dir() / job_id


def cleanup_job(job_id: str) -> None:
    """Remove one job's work, never a parent and never another job's bytes."""
    try:
        owned = job_dir(job_id)
    except MaterializationError:
        return
    try:
        shutil.rmtree(owned)
    except FileNotFoundError:
        pass
    except OSError as exc:
        # The id is safe to log; no target URL or filename is included.
        log.warning("store: could not clean work for job %s — %s", job_id, exc)


def _filename(raw: str) -> str:
    if not raw or raw in (".", "..") or "/" in raw or "\\" in raw or "\0" in raw:
        raise MaterializationError("the resolved filename is a path, not a name")
    return raw


def _looks_like_html(head: bytes) -> bool:
    sample = head.lstrip().lower()
    return sample.startswith((b"<!doctype html", b"<html", b"<head", b"<body"))


class HttpMaterializer:
    """Stream a direct HTTPS target atomically, observably and cancellably."""

    name = "http"

    def __init__(self, *, progress: Progress,
                 transport: httpx.AsyncBaseTransport | None = None,
                 free_bytes: Callable[[Path], int] | None = None):
        self._progress = progress
        self._transport = transport
        self._free_bytes = free_bytes or (lambda path: shutil.disk_usage(path).free)

    async def materialize(self, job: Job, target: AcquiredTarget) -> None:
        if urlsplit(target.url).scheme.lower() != "https":
            raise MaterializationError("the download target is not HTTPS")
        if target.size <= 0:
            raise MaterializationError(
                "the download size is unknown, so disk space cannot be checked safely")

        name = _filename(target.filename)
        root = store_work_dir()
        if root.is_symlink() or root.parent.is_symlink():
            raise MaterializationError(
                "the Store work area is redirected through a symbolic link")
        try:
            root.mkdir(parents=True, exist_ok=True)
            available = self._free_bytes(root)
        except OSError as exc:
            raise MaterializationError(
                "disk space for the Store work area could not be checked") from exc
        required = target.size + MIN_FREE_AFTER_DOWNLOAD
        if available < required:
            raise MaterializationError(
                f"not enough disk space ({target.size} bytes needed plus "
                f"{MIN_FREE_AFTER_DOWNLOAD} bytes kept free)")

        owned = job_dir(job.id)
        if owned.is_symlink():
            raise MaterializationError(
                "the job work area is redirected through a symbolic link")
        final = owned / name
        part = owned / f"{name}.part"
        try:
            owned.mkdir(mode=0o700, parents=False, exist_ok=True)
            owned.chmod(0o700)
            # No blind Range resume: see the module docstring.
            part.unlink(missing_ok=True)
            final.unlink(missing_ok=True)
        except OSError as exc:
            cleanup_job(job.id)
            raise MaterializationError(
                "the job work area could not be prepared") from exc

        received = 0
        first = bytearray()
        last_reported = 0
        last_report_at = time.monotonic()
        await self._progress(job.id, 0, target.size)
        try:
            timeout = httpx.Timeout(connect=15.0, read=30.0, write=30.0, pool=15.0)
            async with httpx.AsyncClient(
                    transport=self._transport, timeout=timeout,
                    follow_redirects=True,
                    headers={"Accept-Encoding": "identity"}) as client:
                async with client.stream("GET", target.url) as response:
                    if response.url.scheme.lower() != "https":
                        raise MaterializationError(
                            "the download redirected away from HTTPS")
                    if response.status_code < 200 or response.status_code >= 300:
                        raise MaterializationError(
                            f"the download service answered HTTP {response.status_code}")
                    content_type = response.headers.get("content-type", "").lower()
                    if "text/html" in content_type:
                        raise MaterializationError(
                            "the download service returned an HTML page, not the file")
                    stated = response.headers.get("content-length")
                    if stated:
                        try:
                            if int(stated) != target.size:
                                raise MaterializationError(
                                    "the download length does not match the resolved size")
                        except ValueError:
                            raise MaterializationError(
                                "the download service returned an invalid length")

                    with part.open("xb") as out:
                        async for chunk in response.aiter_bytes():
                            if not chunk:
                                continue
                            if len(first) < 512:
                                first.extend(chunk[:512 - len(first)])
                                if _looks_like_html(bytes(first)):
                                    raise MaterializationError(
                                        "the download service returned an HTML page, not the file")
                            received += len(chunk)
                            if received > target.size:
                                raise MaterializationError(
                                    "the download is larger than the resolved size")
                            out.write(chunk)
                            now = time.monotonic()
                            if (received - last_reported >= _REPORT_EVERY_BYTES
                                    or now - last_report_at >= _REPORT_EVERY_SECONDS):
                                await self._progress(job.id, received, target.size)
                                last_reported, last_report_at = received, now
                            # Cancellation is observed even by transports whose
                            # iterator can yield synchronously (notably tests).
                            await asyncio.sleep(0)
                        out.flush()
                        os.fsync(out.fileno())

            if received != target.size:
                raise MaterializationError(
                    f"the download stopped after {received} of {target.size} bytes")
            if received == 0:
                raise MaterializationError("the download was empty")
            await self._progress(job.id, received, target.size)
            part.replace(final)
        except asyncio.CancelledError:
            part.unlink(missing_ok=True)
            cleanup_job(job.id)
            raise
        except MaterializationError:
            cleanup_job(job.id)
            raise
        except (httpx.HTTPError, OSError) as exc:
            cleanup_job(job.id)
            raise MaterializationError(
                "the download could not be completed") from exc
