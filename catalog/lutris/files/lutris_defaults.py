"""Lutris defaults for a console: the fast paths on, written only where absent.

Keys and file shapes read from Lutris 0.5.22 and 0.5.23:

    runners/wine.yml   {"wine": {version, dxvk, vkd3d, esync, fsync, ...}}
                       (`lutris/runners/wine.py` runner options)
    system.yml         {"system": {gamemode, game_path, ...}}
                       (`lutris/sysoptions.py`)

Lutris's own defaults already turn most of these on when it detects support;
writing them makes the box's intent explicit and survives a detection that
fails inside the sandbox. A value the owner set is never changed. The one
exception is `version`: it follows the newest GE-Proton this pack installed,
but only while it still names a build this pack installed earlier.
"""
from __future__ import annotations

import os
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - the pack installs python-yaml (`packages`)
    yaml = None

WINE_DEFAULTS = {"dxvk": True, "vkd3d": True, "esync": True, "fsync": True}
SYSTEM_DEFAULTS = {"gamemode": True}


def merge_absent(doc: dict, section: str, values: dict) -> list[str]:
    """Set each key of `values` under `section` where it is absent. Pure."""
    block = doc.get(section)
    if not isinstance(block, dict):
        block = {}
        doc[section] = block
    changed = []
    for key, value in values.items():
        if key not in block:
            block[key] = value
            changed.append(key)
    return changed


def pick_version(current: object, ours: set[str], new: str) -> str | None:
    """The `version` to write, or None to leave the owner's choice alone."""
    if current is None or current == "":
        return new
    if current in ours and current != new:
        return new
    return None


def _load(path: Path) -> dict | None:
    """The YAML mapping, {} when absent, None when unreadable (never rewritten)."""
    if not path.exists():
        return {}
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError, UnicodeDecodeError):
        return None
    if doc is None:
        return {}
    return doc if isinstance(doc, dict) else None


def _save(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.gamecore-tmp")
    tmp.write_text(yaml.safe_dump(doc, default_flow_style=False), encoding="utf-8")
    os.replace(tmp, path)


def apply(config_dir: Path, *, proton: str | None, ours: set[str],
          games_dir: Path | None) -> list[str]:
    """Write the defaults. Returns one line per file changed, for the log."""
    if yaml is None:
        return ["python-yaml is missing: Lutris defaults not written"]
    out = []
    wine_yml = config_dir / "runners" / "wine.yml"
    doc = _load(wine_yml)
    if doc is None:
        out.append(f"{wine_yml} is not readable YAML: left alone")
    else:
        changed = merge_absent(doc, "wine", WINE_DEFAULTS)
        if proton and (version := pick_version(doc["wine"].get("version"), ours, proton)):
            doc["wine"]["version"] = version
            changed.append(f"version={version}")
        if changed:
            _save(wine_yml, doc)
            out.append(f"{wine_yml}: {', '.join(changed)}")

    system_yml = config_dir / "system.yml"
    doc = _load(system_yml)
    if doc is None:
        out.append(f"{system_yml} is not readable YAML: left alone")
        return out
    values = dict(SYSTEM_DEFAULTS)
    if games_dir is not None:
        values["game_path"] = str(games_dir)
    changed = merge_absent(doc, "system", values)
    if changed:
        _save(system_yml, doc)
        out.append(f"{system_yml}: {', '.join(changed)}")
    if games_dir is not None and doc["system"].get("game_path") == str(games_dir):
        games_dir.mkdir(parents=True, exist_ok=True)
    return out
