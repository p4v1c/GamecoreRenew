"""What every part of gamescrape needs and none of them owns.

Split out of gamescrape.py so the four modules around it can be imported in any
order: constants, the one output helper, and the slug rule. Nothing here knows
about ROMs, databases or credentials — if it did, it would belong in the module
that does.

**Why the JSON mode is a function and not a variable.** `--json` must put JSON
and NOTHING else on stdout, so human-readable lines go to stderr in that mode:
without it, `gamescrape.py --json | jq` broke on the "Title / Console" header
and the download progress landing in the middle of the document.

That used to be a module global the CLI rebound directly. Once `out()` lives
here and its callers import it from four other modules, rebinding a name in one
of them would change nothing — every module would keep reading the value bound
at import. `set_json_mode()` mutates the one piece of state this module owns,
so there is exactly one answer to "is this run in JSON mode".
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

METADATA_URL = "https://gamesdb.launchbox-app.com/Metadata.zip"
IMAGE_CDN = "https://images.launchbox-app.com/"
# Where the LaunchBox index lives. NOT a constant: services/gamemedia/__init__.py
# moves it to GAMECORE_ROOT/emu/gamescrape at import, so a box keeps its 234 MB
# index inside the installation rather than in the service user's ~/.cache.
#
# It is rebound through `set_index_dir()` rather than by assignment, and that is
# the whole reason this module exists. While everything was one file, assigning
# `gamescrape.DB_PATH` reached every reader because there was only one. Split
# across five modules, a `from .common import DB_PATH` binds the value at import
# and a later assignment reaches nobody — the index quietly resolved back to
# ~/.cache and the box reported a media source it did not have. Read these
# through the module (`common.DB_PATH`), never by from-import.
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "gamescrape"
DB_PATH = CACHE_DIR / "launchbox.sqlite"
MAX_AGE_DAYS = 30
# SQLite schema version. Bump it whenever a column moves: a database built by
# an earlier version would fail every query with "no such column", and an
# unusable index must be rebuilt rather than endured.
SCHEMA_VERSION = 2
TIMEOUT = 60
UA = "gamescrape/2.0"

_JSON_MODE = False


def set_json_mode(enabled: bool) -> None:
    global _JSON_MODE
    _JSON_MODE = enabled


def json_mode() -> bool:
    return _JSON_MODE


def out(*a, **kw) -> None:
    print(*a, file=sys.stderr if _JSON_MODE else sys.stdout, **kw)


def slug(text: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", text.lower())).strip("-")


def set_index_dir(directory: Path) -> None:
    """Move the LaunchBox index, and everything derived from it, in one call."""
    global CACHE_DIR, DB_PATH
    CACHE_DIR = Path(directory)
    DB_PATH = CACHE_DIR / "launchbox.sqlite"
