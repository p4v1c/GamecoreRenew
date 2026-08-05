"""Where the media cache lives.

Split out of gamemedia.py so the modules around it can be imported in any
order, and — more importantly — so this location can MOVE.

It does move: `services/gamemedia/__init__.py` points it at
GAMECORE_ROOT/emu/gamemedia, because a box keeps its covers inside the
installation and not in the service user's ~/.cache, where the OTA rsync would
never see them and a cleaner would.

It is moved through `set_cache_root()` rather than by assignment, and that is
the whole reason this module exists. While gamemedia.py was one 1 605-line
file, assigning `gm.CACHE_ROOT` reached every reader because there was only
one. Split across five modules, a `from .paths import CACHE_ROOT` binds the
value at import and a later assignment reaches nobody — `entry_dir` would go on
writing covers under ~/.cache while everything else reported them as being in
the installation. The same shape cost four failing tests when gamescrape.py was
split; this is that lesson applied before it could happen twice.

Read these through the module (`paths.CACHE_ROOT`), never by from-import.
"""
from __future__ import annotations

import os
from pathlib import Path

CACHE_ROOT = Path(os.environ.get("GAMEMEDIA_CACHE",
                                 Path.home() / ".cache" / "gamemedia"))
# A game does not change. We only re-query when the entry is empty or explicitly
# refreshed — a TTL would fire 20,000 requests a month for nothing.
MANIFEST = "game.json"
SYSTEMS_CACHE = CACHE_ROOT / "systems.json"


def set_cache_root(directory: Path) -> None:
    """Move the media cache, and everything derived from it, in one call."""
    global CACHE_ROOT, SYSTEMS_CACHE
    CACHE_ROOT = Path(directory)
    SYSTEMS_CACHE = CACHE_ROOT / "systems.json"
