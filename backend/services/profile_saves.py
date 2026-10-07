"""Per-profile saves: which folder each player's saves go to at launch.

A pack opts in with `profileSaves` in its pack.json, in one of two forms:

- an object listing the emulator's save options and folders
  (`profile_save_paths`): GameCore points them at the profile's folder, with
  no code in the pack. Most emulators;
- `per-instance` or `p1`, with a `place_saves(...)` hook in generator.py, for
  an emulator whose layout needs code (melonDS: one instance per player).

A pack that declares nothing keeps one save for every profile. A pack that
`sharesEmulator` uses its owner's declaration and folder: gb, gbc and gba are
one mGBA and one set of saves per profile.

The primary profile owns every save made before profiles existed and keeps
today's locations: its entry is None, which tells the pack "the emulator's
default", so nothing changes on disk for it. Saves are never moved or copied.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path

from . import configgen, paths, profile_save_paths, profiles
from .catalog import load_catalog
from .configgen import MAX_PLAYERS
from .errors import ServiceError

log = logging.getLogger(__name__)


def _owner(pack, packs: dict | None = None):
    """The pack that owns the emulator: itself, or the one it `sharesEmulator` with."""
    if pack is None or not pack.data.get("sharesEmulator"):
        return pack
    return (packs if packs is not None else load_catalog()).get(pack.data["sharesEmulator"])


def mode(pack, packs: dict | None = None) -> str | None:
    """`per-instance` or `p1` when the pack separates saves, else None (shared).
    An object declaration is `p1`: one emulator, player 1's profile."""
    spec = (_owner(pack, packs).data.get("profileSaves") if _owner(pack, packs) else None)
    if isinstance(spec, dict):
        return "p1" if spec.get("supported", True) else None
    return spec

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
    return sorted(p.data.get("label", p.id) for p in packs.values() if mode(p, packs))


def shared_systems(packs: dict) -> list[str]:
    """Labels of the emulators whose saves every profile shares."""
    return sorted(p.data.get("label", p.id) for p in packs.values()
                  if p.data.get("kind") == "emulator" and not mode(p, packs))


def _declared(owner, opts: dict | None):
    """`place_saves` for an object declaration: player 1's folder only."""
    spec = owner.data["profileSaves"]
    config_dir = opts["config_dir"] if opts else None

    def resolve(entry: dict) -> Path:
        if "config" in entry:
            if config_dir is None:
                raise ServiceError(500, f"{owner.id}: no config directory to find {entry['config']} in.")
            return Path(os.path.normpath(config_dir / entry["config"]))
        return Path(owner.expand(entry["path"], configgen.HOME))

    def place_saves(*, dirs, root, opts):
        folder = dirs[0]
        keys = [(resolve(e), e) for e in spec.get("keys", [])]
        profile_save_paths.apply_keys(keys, folder, root)
        for e in spec.get("dirs", []):
            path = resolve(e)
            target = folder / (e.get("as") or path.name) if folder is not None else None
            profile_save_paths.apply_dir(path, target)
    return place_saves


def _hook(system_id: str):
    """(emulator id, place_saves, opts), or None for a pack that shares its saves."""
    packs = load_catalog()
    pack = packs.get(system_id.lower())
    owner = _owner(pack, packs)
    if not mode(pack, packs) or owner is None:
        return None
    opts = configgen.generator_opts(owner, configgen.HOME, configgen.SNAP_DIR)
    if isinstance(owner.data["profileSaves"], dict):
        return owner.id, _declared(owner, opts), opts
    hook = getattr(configgen.load_generator(owner), "place_saves", None)
    if hook is None or opts is None:
        raise ServiceError(500, f"{owner.id} declares profileSaves but cannot place them.")
    return owner.id, hook, opts


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
    emulator, hook, opts = found
    dirs = player_dirs([profiles.active()], emulator, mode(load_catalog().get(emulator)))
    with _lock:
        _placed_at[emulator] = time.time()
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
    emulator, hook, opts = found
    with _lock:
        if _placed_at.get(emulator, 0.0) > started:
            return False
        hook(dirs=[None] * MAX_PLAYERS, root=paths.profile_saves_dir(), opts=opts)
    return True


def release_session(session) -> None:
    """`release` for a process-manager session that has ended. Never raises:
    a session's end must still be recorded when this cannot be done."""
    if session.is_app or not session.system_id:
        return    # an app keeps no save that follows a profile
    try:
        release(session.system_id, session.start_time)
    except Exception:
        log.exception("profile saves: could not release %s", session.system_id)
