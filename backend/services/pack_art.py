"""Pictures a pack ships for themes: catalog/<id>/art/<name>.<ext>.

A theme asks for a name (`console` is the hardware photo) and falls back when
it is absent. assets/art/<id>/<name>.<ext> replaces the pack's copy and is
kept by updates. See docs/themes/README.md §7.0.
"""
from __future__ import annotations

import re
from pathlib import Path

from .paths import art_dir

SUFFIXES = (".webp", ".png", ".jpg", ".jpeg", ".svg")
# Names travel in URLs and become keys a theme reads: keep them plain.
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


def _shipped() -> dict[str, dict[str, Path]]:
    """Every pack's own pictures. A broken catalogue means none, never an error."""
    try:
        from .catalog import load_catalog
        return {pid: pack.art for pid, pack in load_catalog().items()}
    except Exception:
        return {}


def _urls(system_id: str, pictures: dict[str, Path]) -> dict[str, str]:
    # The mtime in the query makes a replaced picture a new URL, not a stale hit.
    return {name: f"/api/systems/{system_id}/art/{name}?v={int(p.stat().st_mtime)}"
            for name, p in sorted(pictures.items())}


def with_art(items: list[dict]) -> list[dict]:
    """Grid rows plus `art`: {name: url}, the pictures a theme may choose from."""
    shipped = _shipped()
    return [{**item, "art": _urls(item["id"], art_for(item["id"], shipped.get(item["id"])))}
            for item in items]


def picture(system_id: str, name: str) -> Path | None:
    """One picture by name, looked up rather than joined: both come from a URL."""
    return art_for(system_id, _shipped().get(system_id)).get(name.lower())
