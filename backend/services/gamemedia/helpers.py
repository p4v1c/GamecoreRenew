"""What is a game, what is junk, and where its entry goes.

Split out of gamemedia.py, which had grown to 1 605 lines. Four functions with
no opinion about scraping at all: they decide whether a filename is a game,
what to key it by, which directory its cache entry lives in, and how a manifest
is written.

`entry_dir` is the one to read twice. It CONFINES the result under the cache
root: the system id and the filename both come from a URL on an endpoint the
LAN can reach, and a path built by joining them is a path an attacker chooses.

Imported by gamemedia.py, which re-exports every public name below — no caller
outside this package changes an import.
"""
from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from pathlib import Path

# `paths` is imported as a MODULE on purpose: CACHE_ROOT moves at runtime (see
# paths.set_cache_root), and a from-import would freeze whatever it pointed at
# when this file was first imported.
try:
    from . import paths
except ImportError:                                    # plain-script CLI
    import paths

log = logging.getLogger(__name__)

# ── Helpers ─────────────────────────────────────────────────────────────────

# What sits in a ROM directory without being a game.
_JUNK_NAMES = {".gitkeep", ".gitignore", "desktop.ini", "thumbs.db", ".ds_store",
               "readme", "readme.txt", "covers", "media", "metadata", "manuals"}
_JUNK_EXTS = {"txt", "nfo", "dat", "xml", "json", "md", "log", "sav", "srm",
              "state", "png", "jpg", "jpeg", "cfg", "ini", "db", "bak", "part"}


def looks_like_game(filename: str) -> str:
    """"" when the entry could be a game, otherwise the reason for refusing.

    A ROM directory also holds .gitkeep files, covers/, notes. Without this
    filter the service scraped them: ".gitkeep" matched "The Keep" on LaunchBox
    and "Samurai Deeper Kyo" on ScreenScraper. A wrong result in the cache does
    more harm than no result at all.
    """
    name = Path(filename).name
    if not name or name.startswith("."):
        return "hidden file"
    if name.lower() in _JUNK_NAMES:
        return "service file"
    ext = Path(name).suffix.lower().lstrip(".")
    if ext in _JUNK_EXTS:
        return f"unplayable extension (.{ext})"
    # A one or two character title cannot be searched for seriously.
    if len(re.sub(r"[^A-Za-z0-9]", "", Path(name).stem)) < 3:
        return "name too short"
    return ""


def game_key(filename: str) -> str:
    """Stable, safe cache key from a ROM name.

    No accents, no exotic separator, never empty, never a path: this value
    becomes a directory name, and `filename` comes from a URL parameter.
    """
    stem = Path(filename).name
    for _ in range(2):                                  # "game.nds.zip" → "game"
        stem = Path(stem).stem
    flat = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode()
    flat = re.sub(r"[^A-Za-z0-9]+", "-", flat).strip("-").lower()
    return flat[:120] or "unnamed"


def entry_dir(system: str, filename: str) -> Path:
    """Cache directory, confined under the cache root.

    The confinement is explicit because `system` and `filename` come from the
    HTTP request: a `..` in either must not be able to write elsewhere. Same rule
    as everywhere else — resolve, then verify.
    """
    sysid = re.sub(r"[^A-Za-z0-9_-]+", "", system).lower() or "unknown"
    d = (paths.CACHE_ROOT / sysid / game_key(filename)).resolve()
    root = paths.CACHE_ROOT.resolve()
    if not (d == root or root in d.parents):
        raise ValueError("cache path outside the root")
    return d


def write_json(path: Path, payload: dict) -> None:
    """tmp + os.replace: an interruption must not leave an unreadable manifest,
    or the game would be rescraped on every call for no visible reason."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    os.replace(tmp, path)
