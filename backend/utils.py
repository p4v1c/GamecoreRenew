"""Shared utilities used across multiple backend modules."""
import re
from pathlib import Path

from .config import resolve_path

TAG_RE = re.compile(r"[\(\[].*?[\)\]]")


def rom_in_root(system: dict, filename: str) -> Path | None:
    """The ROM `filename` names inside its system's ROMs directory, or None.

    `filename` arrives from a `{filename:path}` route parameter, and the :path
    converter happily accepts slashes and '..' — so it has to be confined
    before anything opens it, the same way launch_game confines rom_path
    (routers/games.py). docs/architecture/09-gotchas.md states the invariant.

    It lives here because three call sites need it — covers, metadata and
    media — and the third one is what turned two near-identical copies into a
    rule that has to be remembered rather than imported.
    """
    roms_root = resolve_path(system.get("romsPath", ""))
    if not roms_root:
        return None
    try:
        candidate = (roms_root / filename).resolve()
        candidate.relative_to(roms_root.resolve())
    except (ValueError, OSError):
        return None
    return candidate if candidate.exists() else None


def fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024  # type: ignore[assignment]
    return f"{n:.1f} TB"
