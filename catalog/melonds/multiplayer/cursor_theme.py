"""The player arrows wear the box's own cursor theme (Xcursor files, stdlib).

Theme and size come from XCURSOR_THEME / XCURSOR_SIZE, else from KDE's
~/.config/kcminputrc ([Mouse] cursorTheme, cursorSize), else the "default"
theme. A theme missing the arrow is followed through its Inherits= line.
None when nothing is found: the arrows fall back to a drawn one.
"""
from __future__ import annotations

import configparser
import os
import struct
from dataclasses import dataclass
from pathlib import Path

ARROW_NAMES = ("left_ptr", "default", "arrow")
_IMAGE_CHUNK = 0xFFFD0002
_DEFAULT_SIZE = 24


@dataclass
class CursorImage:
    width: int
    height: int
    hot_x: int
    hot_y: int
    argb: bytes          # width * height little-endian ARGB words, premultiplied


def _search_dirs(home: Path) -> list[Path]:
    return [home / ".local/share/icons", home / ".icons", Path("/usr/share/icons")]


def active_theme(home: Path, env: dict[str, str]) -> tuple[str, int]:
    """(theme name, nominal size) the session's own pointer uses."""
    name, size = env.get("XCURSOR_THEME", ""), env.get("XCURSOR_SIZE", "")
    if not name:
        kde = configparser.ConfigParser(interpolation=None, strict=False)
        try:
            kde.read(home / ".config/kcminputrc")
            name = kde.get("Mouse", "cursorTheme", fallback="")
            size = size or kde.get("Mouse", "cursorSize", fallback="")
        except configparser.Error:
            pass
    try:
        nominal = int(size)
    except ValueError:
        nominal = _DEFAULT_SIZE
    return name or "default", nominal


def _inherits(theme_dir: Path) -> list[str]:
    ini = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        ini.read(theme_dir / "index.theme")
        return [t.strip() for t in ini.get("Icon Theme", "Inherits", fallback="").split(",") if t.strip()]
    except configparser.Error:
        return []


def find_arrow_file(theme: str, home: Path, seen: set[str] | None = None) -> Path | None:
    seen = seen if seen is not None else set()
    if theme in seen:
        return None
    seen.add(theme)
    parents: list[str] = []
    for base in _search_dirs(home):
        theme_dir = base / theme
        for name in ARROW_NAMES:
            candidate = theme_dir / "cursors" / name
            if candidate.is_file():
                return candidate
        if theme_dir.is_dir():
            parents += _inherits(theme_dir)
    for parent in parents:
        found = find_arrow_file(parent, home, seen)
        if found:
            return found
    return None


def read_xcursor(data: bytes, nominal: int) -> CursorImage | None:
    """The first image of the size closest to `nominal`, or None."""
    if data[:4] != b"Xcur" or len(data) < 16:
        return None
    _magic, _header, _version, count = struct.unpack_from("<4sIII", data, 0)
    best = None
    for i in range(count):
        kind, subtype, position = struct.unpack_from("<III", data, 16 + i * 12)
        if kind == _IMAGE_CHUNK and (best is None or abs(subtype - nominal) < abs(best[0] - nominal)):
            best = (subtype, position)
    if best is None:
        return None
    _size, _kind, _sub, _ver, width, height, hot_x, hot_y, _delay = struct.unpack_from(
        "<9I", data, best[1])
    start = best[1] + 36
    argb = data[start:start + width * height * 4]
    if len(argb) != width * height * 4:
        return None
    return CursorImage(width, height, hot_x, hot_y, argb)


def load_arrow(home: Path | None = None, env: dict[str, str] | None = None) -> CursorImage | None:
    home = home or Path.home()
    theme, nominal = active_theme(home, dict(os.environ) if env is None else env)
    path = find_arrow_file(theme, home)
    if path is None:
        return None
    try:
        return read_xcursor(path.read_bytes(), nominal)
    except (OSError, struct.error):
        return None
