"""Shared ROM scanning logic — used by /api/systems/{id}/games and /api/roms/{id}."""
import fnmatch
from pathlib import Path
from typing import Iterator

from ..utils import TAG_RE


def clean_name(filename: str) -> str:
    """Strip extension and bracketed tags (e.g. '[!]', '(USA)') from a ROM name."""
    return TAG_RE.sub("", Path(filename).stem).strip()


def matches_ext(filename: str, extensions: list[str]) -> bool:
    name = filename.lower()
    return any(fnmatch.fnmatch(name, p.lower()) for p in extensions)


def iter_rom_files(roms_path: Path, extensions: list[str]) -> Iterator[Path]:
    """Yield ROM file paths in alphabetical order, applying common filters
    (no hidden files, no example files, only matching extensions)."""
    if not roms_path.exists():
        return
    for f in sorted(roms_path.iterdir(), key=lambda x: x.name.lower()):
        if not f.is_file() or f.name.startswith(".") or "example" in f.name.lower():
            continue
        if extensions and not matches_ext(f.name, extensions):
            continue
        yield f
