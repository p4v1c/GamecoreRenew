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


def iter_rom_files(roms_path: Path, extensions: list[str], scan_dirs: bool = False) -> Iterator[Path]:
    """Yield ROM file/folder paths in alphabetical order, applying common filters."""
    if not roms_path.exists():
        return
    for f in sorted(roms_path.iterdir(), key=lambda x: x.name.lower()):
        if f.name.startswith(".") or "example" in f.name.lower():
            continue
        if scan_dirs:
            if f.is_dir():
                yield f
        else:
            if not f.is_file():
                continue
            if extensions and not matches_ext(f.name, extensions):
                continue
            yield f
