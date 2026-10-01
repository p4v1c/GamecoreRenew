"""Pictures a pack ships for themes: catalog/<id>/art/<name>.<ext>.

A theme asks for a name (`console` is the hardware photo) and falls back when
it is absent. assets/art/<id>/<name>.<ext> replaces the pack's copy and is
kept by updates. See docs/themes/README.md §7.0.

Pictures are merged name by name across the catalogue's tiers (shipped, OTA,
config/catalog.d) rather than read from the pack that won: an OTA correction
or a local pack.json replaces the pack's data, not its photo. Read straight
from the folders, never through `load_catalog()`, so a grid request or a photo
costs a few stat calls instead of a catalogue reload.
"""
from __future__ import annotations

import re
from pathlib import Path

from .paths import art_dir, catalog_dir, config_dir

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


def _tiers() -> list[Path]:
    """Where a pack's own art/ may sit, lowest priority first (as load_catalog)."""
    from .catalog.ota import state_dir     # the catalog package imports this module
    return [catalog_dir(), state_dir(), config_dir() / "catalog.d"]


def art_for(pack_id: str) -> dict[str, Path]:
    """The pack's pictures, tier over tier, with the operator's replacements on top."""
    pid = pack_id.lower()
    if not NAME.match(pid):
        return {}
    merged: dict[str, Path] = {}
    for root in _tiers():
        merged.update(pictures_in(root / pid / "art"))
    merged.update(pictures_in(art_dir() / pid))
    return merged


def _urls(system_id: str, pictures: dict[str, Path]) -> dict[str, str]:
    # The mtime in the query makes a replaced picture a new URL, not a stale hit.
    return {name: f"/api/systems/{system_id}/art/{name}?v={int(p.stat().st_mtime)}"
            for name, p in sorted(pictures.items())}


def with_art(items: list[dict]) -> list[dict]:
    """Grid rows plus `art`: {name: url}, the pictures a theme may choose from."""
    return [{**item, "art": _urls(item["id"], art_for(item["id"]))} for item in items]


def picture(system_id: str, name: str) -> Path | None:
    """One picture by name, looked up rather than joined: both come from a URL."""
    return art_for(system_id).get(name.lower())
