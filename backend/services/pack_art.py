"""Pictures a pack ships for themes: catalog/<id>/art/<name>.<ext>.

A theme used to carry its own photo of every console, keyed by pack id in its
JavaScript. Two themes meant two copies, a new pack meant editing every theme,
and changing a photo meant editing code. The picture belongs to the pack; the
theme only says which name it wants (`console`, …) and falls back when a pack
has none.

The operator can replace one without touching the release: a file at
assets/art/<id>/<name>.<ext> wins over the pack's, the way assets/logos/ wins
over a pack logo, and survives updates for the same reason.
"""
from __future__ import annotations

import re
from pathlib import Path

from .paths import art_dir

SUFFIXES = (".webp", ".png", ".jpg", ".jpeg", ".svg")
# Names travel in URLs and become dict keys a theme reads: keep them plain.
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")


def pictures_in(folder: Path) -> dict[str, Path]:
    """{name: file} for every picture directly in `folder`; first suffix wins."""
    found: dict[str, Path] = {}
    if not folder.is_dir():
        return found
    for suffix in SUFFIXES:
        for f in sorted(folder.glob(f"*{suffix}")):
            name = f.stem.lower()
            if f.is_file() and NAME.match(name) and name not in found:
                found[name] = f
    return found


def art_for(pack_id: str, pack_art: dict[str, Path] | None = None) -> dict[str, Path]:
    """The pack's pictures with the operator's replacements on top."""
    if not NAME.match(pack_id.lower()):
        return {}
    merged = dict(pack_art or {})
    merged.update(pictures_in(art_dir() / pack_id.lower()))
    return merged


def art_urls(system_id: str, pictures: dict[str, Path]) -> dict[str, str]:
    """What a theme reads off a system: name → URL. The file's mtime rides in
    the query so a replaced picture is fetched again rather than revalidated
    against a stale cache entry."""
    return {name: f"/api/systems/{system_id}/art/{name}?v={int(p.stat().st_mtime)}"
            for name, p in sorted(pictures.items())}
