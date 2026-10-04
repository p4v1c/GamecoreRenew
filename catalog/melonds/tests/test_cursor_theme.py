"""The player arrows wear the box's cursor theme: which theme, which file,
which image size, and the fallback when there is none."""
from __future__ import annotations

import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "multiplayer"))

import cursor_theme  # noqa: E402


def _xcursor(*images: tuple[int, int, int, int]) -> bytes:
    """An Xcursor file holding (nominal, width, hot_x, hot_y) square images."""
    toc, chunks, pos = [], b"", 16 + 12 * len(images)
    for nominal, w, hx, hy in images:
        chunk = struct.pack("<9I", 36, 0xFFFD0002, nominal, 1, w, w, hx, hy, 0)
        chunk += bytes([0x10, 0x20, 0x30, 0xFF]) * (w * w)
        toc.append(struct.pack("<III", 0xFFFD0002, nominal, pos))
        chunks += chunk
        pos += len(chunk)
    return struct.pack("<4sIII", b"Xcur", 16, 0x10000, len(images)) + b"".join(toc) + chunks


def _theme(home: Path, name: str, inherits: str = "", arrow: bytes | None = None) -> None:
    d = home / ".local/share/icons" / name
    (d / "cursors").mkdir(parents=True)
    (d / "index.theme").write_text(f"[Icon Theme]\nName={name}\nInherits={inherits}\n")
    if arrow is not None:
        (d / "cursors/left_ptr").write_bytes(arrow)


def test_the_kde_theme_and_size_are_used(tmp_path):
    (tmp_path / ".config").mkdir()
    (tmp_path / ".config/kcminputrc").write_text("[Mouse]\ncursorTheme=DS-Lite\ncursorSize=32\n")
    _theme(tmp_path, "DS-Lite", arrow=_xcursor((24, 24, 0, 23), (32, 32, 0, 31), (48, 48, 0, 47)))
    img = cursor_theme.load_arrow(tmp_path, env={})
    assert (img.width, img.hot_x, img.hot_y) == (32, 0, 31)
    assert len(img.argb) == 32 * 32 * 4


def test_xcursor_env_wins_over_kde(tmp_path):
    (tmp_path / ".config").mkdir()
    (tmp_path / ".config/kcminputrc").write_text("[Mouse]\ncursorTheme=Other\n")
    assert cursor_theme.active_theme(tmp_path, {"XCURSOR_THEME": "Mine", "XCURSOR_SIZE": "48"}) == ("Mine", 48)


def test_a_theme_without_the_arrow_inherits_it(tmp_path):
    _theme(tmp_path, "Child", inherits="Parent")
    _theme(tmp_path, "Parent", arrow=_xcursor((24, 24, 4, 4)))
    assert cursor_theme.find_arrow_file("Child", tmp_path).parent.parent.name == "Parent"


def test_no_theme_means_the_drawn_arrow(tmp_path):
    assert cursor_theme.load_arrow(tmp_path, env={"XCURSOR_THEME": "missing"}) is None


def test_a_broken_file_is_ignored():
    assert cursor_theme.read_xcursor(b"not a cursor", 32) is None
