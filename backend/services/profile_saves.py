"""Per-profile saves: which folder each player's saves go to at launch.

A pack opts in with `profileSaves` in its pack.json and a `place_saves(...)`
hook in its generator.py that points the emulator at the folders, with its own
option names. A pack that declares nothing keeps one save for every profile.

The primary profile owns every save made before profiles existed and keeps
today's locations: its entry is None, which tells the pack "the emulator's
default", so nothing changes on disk for it. Saves are never moved or copied.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

from . import configgen, paths, profiles
from .catalog import load_catalog
from .configgen import MAX_PLAYERS
from .errors import ServiceError


def mode(pack) -> str | None:
    """`per-instance` or `p1` when the pack separates saves, else None (shared)."""
    return pack.data.get("profileSaves") if pack else None


def save_dir(profile_id: str, system_id: str) -> Path:
    # profiles.json is hand-editable: an id must not climb out of the root.
    if not profile_id.isalnum():
        raise ServiceError(500, "A profile id in profiles.json is not valid.")
    return paths.profile_saves_dir() / profile_id / system_id.lower()


def player_dirs(players: list[dict | None], system_id: str, save_mode: str) -> list[Path | None]:
    """One entry per player slot: that player's folder, created if missing, or
    None for the emulator's default location (the primary profile, or no
    profile). `players[0]` is the active profile; the rest stay None until
    controllers carry profiles. `p1` mode ignores players 2-4."""
    out: list[Path | None] = []
    for slot in range(MAX_PLAYERS):
        profile = players[slot] if slot < len(players) else None
        if profile is None or profile.get("primary") or (save_mode == "p1" and slot > 0):
            out.append(None)
            continue
        folder = save_dir(profile["id"], system_id)
        folder.mkdir(parents=True, exist_ok=True)
        out.append(folder)
    return out


def separate_systems(packs: dict) -> list[str]:
    """Labels of the systems whose saves follow the profile, for Settings → Profiles."""
    return sorted(p.data.get("label", p.id) for p in packs.values() if mode(p))


def _hook(system_id: str):
    """(pack, place_saves, opts), or None for a pack that shares its saves."""
    pack = load_catalog().get(system_id.lower())
    if not mode(pack):
        return None
    hook = getattr(configgen.load_generator(pack), "place_saves", None)
    opts = configgen.generator_opts(pack, configgen.HOME, configgen.SNAP_DIR)
    if hook is None or opts is None:
        raise ServiceError(500, f"{pack.id} declares profileSaves but cannot place them.")
    return pack, hook, opts


# Place and release write the same file from two threads, and the end of one
# game can be noticed after the next launch of that emulator already placed its
# saves: the process manager frees a dead slot before its watcher runs.
_lock = threading.Lock()
_placed_at: dict[str, float] = {}


def place(system_id: str) -> list[Path | None] | None:
    """Point the pack at the active profile's folders before the spawn.

    Returns what the hook got, or None for a pack that shares its saves.
    Raises when the pack opted in but could not be told: launching then
    would write one profile's progress into another's save.
    """
    found = _hook(system_id)
    if found is None:
        return None
    pack, hook, opts = found
    dirs = player_dirs([profiles.active()], system_id, mode(pack))
    with _lock:
        _placed_at[system_id.lower()] = time.time()
        hook(dirs=dirs, root=paths.profile_saves_dir(), opts=opts)
    return dirs


def release(system_id: str, started: float) -> bool:
    """After the game that started at `started` (wall clock): every player back
    on the emulator's default paths, so the emulator started outside GameCore
    saves where it always did.

    Skipped, False, when a later launch of the same emulator has placed its
    saves since: resetting them would send that game's progress to the
    primary profile."""
    found = _hook(system_id)
    if found is None:
        return False
    _pack, hook, opts = found
    with _lock:
        if _placed_at.get(system_id.lower(), 0.0) > started:
            return False
        hook(dirs=[None] * MAX_PLAYERS, root=paths.profile_saves_dir(), opts=opts)
    return True
