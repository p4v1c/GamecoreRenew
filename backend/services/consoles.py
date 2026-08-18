"""Which console inside a pack a ROM belongs to.

Most emulators are one console and this module answers `None` for them, which
is the whole point: `mgba` is three consoles behind one system id — Game Boy
and Game Boy Color in 10:9, Game Boy Advance in 3:2 — and `dolphin` is two.
Everything downstream of a system id treated those as one thing, and for a
bezel that is a frame cut for a shape the game is not.

Why this is not `libretroSystems`
---------------------------------
`scraper.libretro` is the obvious candidate and it is the wrong one. It is a
list of names in libretro's database, and the database does not enumerate
consoles — `melonds` declares two of them, "Nintendo - Nintendo DS" and
"Nintendo - Nintendo DS (Download Play)", for a machine that exists once. Keyed
on that, melonDS would grow a second console with no hardware behind it, and
every one of those keys would move the day libretro renamed an entry.

`scraper.mediaAlias` is closer — it really is one entry per console — but it is
a ScreenScraper-facing name (`"nintendo 64"`, `"xbox 360"`, spaces included),
so it is somebody else's vocabulary too, and it is not filename-safe.

So a pack declares its consoles outright, in `roms.consoles`, next to the
`roms.extensions` they refer to. The identity is a short id chosen here and
answerable to nothing outside this repository, which is what lets it be part
of a filename and of a cache key without a rename somewhere else breaking both.

Why the extension, and why an extension may decline to answer
-------------------------------------------------------------
The mapping is declared rather than derived. Deriving it from the extension
list was the tempting version and it cannot work: `.zip` is declared by nearly
every pack and says nothing about what is inside it, `.iso` serves GameCube and
Wii alike, and `.rvz` is Dolphin's own container which holds either — the
scraper already learned that one the expensive way (see
`gamemedia/registry.py`: every Dolphin game was looked up as a GameCube game
and Mario Kart Wii quietly matched Double Dash).

An extension a pack lists under no console therefore resolves to `None`, and
`None` means the cascade skips the console level and behaves exactly as it did
before. That is the deliberate choice: `dolphin` claims `.gcm` for GameCube and
`.wbfs`/`.wad` for Wii, and leaves `.iso`, `.rvz` and `.zip` unclaimed rather
than guessing. Reading the disc header would answer them — `gameid.identify()`
already knows how — but that is I/O in front of a game starting, for a level
that degrades gracefully without it.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from .paths import config_dir

log = logging.getLogger(__name__)

# path → (rows, mtime). systems.json is read on every launch, and the file is
# the player's: it can be edited by hand between two games.
_cache: tuple[list, float] | None = None


def forget() -> None:
    """Drop the cached systems.json. For tests, and for the roots moving."""
    global _cache
    _cache = None


def _systems() -> list:
    global _cache
    p = config_dir() / "systems.json"
    try:
        mtime = p.stat().st_mtime
    except OSError:
        _cache = None
        return []
    if _cache is not None and _cache[1] == mtime:
        return _cache[0]
    try:
        loaded = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError) as e:
        # Never fatal. A systems.json that will not parse is a box with bigger
        # problems than a bezel, and this level degrading to "no consoles" is
        # exactly the behaviour every pack had before it existed.
        log.warning("consoles: config/systems.json unreadable — %s", e)
        return []
    rows = loaded if isinstance(loaded, list) else []
    _cache = (rows, mtime)
    return rows


def declared(system_id: str) -> list[dict]:
    """This pack's consoles, in the order it declared them. `[]` for most."""
    for row in _systems():
        if isinstance(row, dict) and row.get("id") == system_id:
            got = row.get("consoles")
            return [c for c in got if isinstance(c, dict) and c.get("id")] \
                if isinstance(got, list) else []
    return []


def for_rom(system_id: str, rom_name: str | None) -> str | None:
    """The console id this ROM belongs to, or None when nothing says.

    None is a normal answer in three different situations that the caller must
    treat identically: the pack has one console, the extension is shared, or
    the file is not one this pack claims at all. In all three the honest thing
    is to stay at the system level.
    """
    if not rom_name:
        return None
    ext = Path(rom_name).suffix.lower()
    if not ext:
        return None
    want = f"*{ext}"

    hit = None
    for console in declared(system_id):
        exts = console.get("extensions")
        if not isinstance(exts, list):
            continue
        if any(isinstance(e, str) and e.lower() == want for e in exts):
            if hit is not None:
                # Two consoles claim it. `check-catalog.py` refuses this at
                # build time, so reaching it means a hand-edited systems.json —
                # and the safe reading of an ambiguous declaration is the one
                # that changes nothing.
                log.warning("consoles: %s — %s is claimed by both %s and %s, "
                            "staying at the system level", system_id, ext, hit,
                            console["id"])
                return None
            hit = console["id"]
    return hit
