"""The PC library: one stub per installed Lutris game in the pack's ROM folder.

GameCore lists a system by scanning a folder and keys playtime, favourites
and covers by the file name it lists. A stub per game (`Celeste.lutris`,
holding the Lutris game id) lets all of that work unchanged, and the launcher
(`lutris_session.py`) reads the id back out of it.

Rules, each one a way to lose a player's data otherwise:

- A stub's file name is chosen once per Lutris id and kept. It is the
  playtime key: a game renamed in Lutris keeps its hours.
- A stub is deleted only when Lutris answered and the game is no longer
  installed. An unreadable or locked pga.db changes nothing.
- Only files that parse as stubs are touched; anything else in the folder is
  the owner's.

Stdlib only.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
from pathlib import Path
from typing import NamedTuple

STUB_SUFFIX = ".lutris"
STUB_KEY = "lutrisId"
DB_TIMEOUT_S = 1.0
# ext4 allows 255 bytes per name; room is left for the suffix and a " - gog".
MAX_NAME_BYTES = 180
COVER_EXTS = (".webp", ".png", ".jpg")

_INSTALLED_SQL = "SELECT id, name, slug, runner, service FROM games WHERE installed = 1"
# Games the owner hid in Lutris (the ".hidden" category) stay hidden here.
_HIDDEN_SQL = ("SELECT gc.game_id FROM games_categories gc "
               "JOIN categories c ON c.id = gc.category_id WHERE c.name = '.hidden'")
_UNSAFE_CHARS = re.compile(r'[\x00-\x1f/\\]+')
_SLUG_RE = re.compile(r"[a-z0-9][a-z0-9._-]*\Z")


class Game(NamedTuple):
    id: int
    name: str
    slug: str
    runner: str
    service: str

    def payload(self) -> dict:
        return {STUB_KEY: self.id, "name": self.name, "slug": self.slug,
                "runner": self.runner, "service": self.service}


def installed_games(db: Path) -> list[Game] | None:
    """Installed, visible games, or None when the library could not be read."""
    if not db.is_file():
        return None
    try:
        with sqlite3.connect(f"{db.as_uri()}?mode=ro", uri=True, timeout=DB_TIMEOUT_S) as con:
            rows = con.execute(_INSTALLED_SQL).fetchall()
            try:
                hidden = {r[0] for r in con.execute(_HIDDEN_SQL)}
            except sqlite3.OperationalError:
                hidden = set()          # a library from before categories existed
    except sqlite3.Error:
        return None
    games = []
    for gid, name, slug, runner, service in rows:
        if not isinstance(gid, int) or gid in hidden:
            continue
        games.append(Game(gid, str(name or slug or gid), str(slug or ""),
                          str(runner or ""), str(service or "")))
    return sorted(games, key=lambda g: g.id)


def read_stub(path: Path) -> dict | None:
    """The stub's content, or None when the file is not one of ours."""
    try:
        if path.stat().st_size > 64 * 1024:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get(STUB_KEY), int):
        return None
    return data


def game_id_of(path: Path) -> int | None:
    stub = read_stub(path)
    return stub[STUB_KEY] if stub else None


def safe_stem(name: str, fallback: str) -> str:
    """A file name stem for a title: no separator, no leading dot, bounded."""
    stem = " ".join(_UNSAFE_CHARS.sub(" ", name).split()).strip(" .")
    if not stem:
        stem = " ".join(_UNSAFE_CHARS.sub(" ", fallback).split()).strip(" .") or "Game"
    data = stem.encode("utf-8")[:MAX_NAME_BYTES]
    return data.decode("utf-8", "ignore").rstrip(" .") or "Game"


def _candidates(game: Game) -> list[str]:
    base = safe_stem(game.name, game.slug)
    extra = game.service or game.runner
    names = [base]
    if extra:
        names.append(f"{base} - {extra}")
    names.append(f"{base} - {game.id}")
    return [n + STUB_SUFFIX for n in names]


def plan(games: list[Game], stubs: dict[str, dict]) -> tuple[dict[str, Game], list[str]]:
    """({file name: game}, [stub file names to delete]). Pure."""
    installed = {g.id for g in games}
    by_id: dict[int, str] = {}
    for name, stub in sorted(stubs.items()):
        by_id.setdefault(stub[STUB_KEY], name)
    assigned = {by_id[g.id]: g for g in games if g.id in by_id}
    # Names held by an installed game, duplicates included, are never reused.
    taken = {n.lower() for n, s in stubs.items() if s[STUB_KEY] in installed}
    # A stub whose game is gone may be reused by a game of the same name: a
    # reinstall gets a new Lutris id and should keep its hours. Matched without
    # case, so a case-insensitive data disk never sees two spellings.
    free = {n.lower(): n for n, s in stubs.items() if s[STUB_KEY] not in installed}
    for game in games:
        if game.id in by_id:
            continue
        for candidate in _candidates(game):
            key = candidate.lower()
            if key in taken:
                continue
            name = free.pop(key, candidate)
            assigned[name] = game
            taken.add(key)
            break
    deletes = sorted(name for name in stubs if name not in assigned)
    return assigned, deletes


def _write_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(f".{path.name}.gamecore-tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _place_cover(game: Game, stem: str, covers_dir: Path, coverart_dir: Path) -> bool:
    """Lutris's own cover as the game's cover, unless one is already there."""
    if not _SLUG_RE.match(game.slug):
        return False
    source = coverart_dir / f"{game.slug}.jpg"
    if not source.is_file() or any((covers_dir / f"{stem}{ext}").exists() for ext in COVER_EXTS):
        return False
    covers_dir.mkdir(parents=True, exist_ok=True)
    tmp = covers_dir / f".{stem}.jpg.gamecore-tmp"
    shutil.copyfile(source, tmp)
    os.replace(tmp, covers_dir / f"{stem}.jpg")
    return True


def existing_stubs(roms_dir: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not roms_dir.is_dir():
        return out
    for path in roms_dir.iterdir():
        if path.suffix.lower() == STUB_SUFFIX and path.is_file():
            stub = read_stub(path)
            if stub is not None:
                out[path.name] = stub
    return out


def sync(roms_dir: Path, games: list[Game], covers_dir: Path | None = None,
         coverart_dir: Path | None = None) -> dict[str, list[str]]:
    """Make the stubs match `games`. Returns what was written, removed, covered."""
    stubs = existing_stubs(roms_dir)
    assigned, deletes = plan(games, stubs)
    report: dict[str, list[str]] = {"written": [], "removed": [], "covers": []}
    if assigned:
        roms_dir.mkdir(parents=True, exist_ok=True)
    for name, game in sorted(assigned.items()):
        if stubs.get(name) != game.payload():
            body = json.dumps(game.payload(), ensure_ascii=False, indent=1) + "\n"
            _write_atomic(roms_dir / name, body.encode("utf-8"))
            report["written"].append(name)
        if covers_dir is not None and coverart_dir is not None:
            stem = name[: -len(STUB_SUFFIX)]
            try:
                if _place_cover(game, stem, covers_dir, coverart_dir):
                    report["covers"].append(name)
            except OSError:
                pass                    # a missing cover is the scrapers' job
    for name in deletes:
        (roms_dir / name).unlink(missing_ok=True)
        report["removed"].append(name)
    return report
