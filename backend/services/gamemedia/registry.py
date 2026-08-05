"""Which ScreenScraper system a ROM belongs to, discovered rather than declared.

Split out of gamemedia.py. ScreenScraper declares some 250 systems through
systemesListe.php, and this asks it rather than carrying a table — the table
would be wrong the day the API gains a system, and wrong silently.

`_EXTRA_ALIASES` below is the deliberate exception and is kept separate for
that reason: emulator ids GameCore ships no pack for, plus the short names the
API does not know. Everything else comes from `catalog/<id>/pack.json` via
`scraper.mediaAlias`, so an emulator's console names are declared once, in the
pack, and not a fourth time here.

Imported by gamemedia.py, which re-exports every public name below — no caller
outside this package changes an import.
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

try:
    from . import gamescrape as gs
    from . import paths
    from .helpers import write_json
    from .ss_client import (
        ScreenScraperClosed,
        ScreenScraperUnreachable,
        ss_request,
    )
except ImportError:                                    # plain-script CLI
    import gamescrape as gs
    import paths
    from helpers import write_json
    from ss_client import (
        ScreenScraperClosed,
        ScreenScraperUnreachable,
        ss_request,
    )

log = logging.getLogger(__name__)

# ── System registry: built from the API, not hardcoded ───────────────────────
#
# ScreenScraper declares 250 systems through systemesListe.php, each with its
# extensions AND its names under every frontend (nom_eu, nom_us, nom_recalbox,
# nom_retropie, nom_launchbox, noms_commun). Everything is derived from there and
# cached: adding a console takes no code change, just a `--refresh-systems` the
# day ScreenScraper adds one.
#
# The only hand-written table is EMULATOR_ALIASES below, because an EMULATOR
# name ("rpcs3", "duckstation") is not a console name and appears nowhere in the
# API.

# SYSTEMS_CACHE itself lives in paths.py: it moves with the cache root, and a
# definition here would rebind it back to ~/.cache at import.

# GameCore: a value may be a LIST when one emulator covers several consoles.
#
# The extension was supposed to settle those cases, and it does when the
# extension is a real dump format the registry knows — .wbfs is Wii, .gcz is
# GameCube. It cannot when the format belongs to the emulator itself: .rvz is
# Dolphin's own container and ScreenScraper lists it under no system at all, so
# `by_ext` came back empty and only the alias spoke.
#
# The alias said "gamecube", so every Dolphin game was looked up as a GameCube
# game. Measured on the reference box: Ocarina, Wind Waker and the Mario Partys
# resolved because they really are GameCube games; Skyward Sword, New Super
# Mario Bros. Wii and Super Smash Bros. Brawl are Wii only and came back "not in
# the database" — and Mario Kart Wii quietly matched *Mario Kart: Double Dash*,
# which is worse than nothing.
# Emulators GameCore does not ship a pack for, plus the short ids gamescrape
# accepts on the command line. Kept by hand because nothing declares them.
_EXTRA_ALIASES: dict[str, str | list[str]] = {
    "vita3k": "vita", "yuzu": "switch", "citron": "switch", "citra": "3ds",
    "desmume": "nds", "mupen64plus": "nintendo 64", "xemu": "xbox",
    "flycast": "dreamcast", "mednafen": "psx", "snes9x": "super nintendo",
    "mesen": "nes",
    # "arcade" is not a system on ScreenScraper: more than 50 boards share
    # nom_launchbox="arcade". The convention (Skyscraper's too) is to aim at Mame
    # (id 75) and let the zip hash designate the board.
    "arcade": "mame", "fbneo": "mame", "fba": "mame", "mame4all": "mame",
    # short ids specific to GameCore / gamescrape, absent from the API.
    "mastersys": "master system", "virtualboy": "virtual boy",
    "segacd": "mega cd", "x360": "xbox 360", "xone": "xbox one",
    "psx": "playstation", "ps1": "playstation", "gc": "gamecube",
}


def _catalog_aliases() -> dict[str, str | list[str]]:
    """`scraper.mediaAlias` from every pack.

    Hand-maintaining this alongside scraper.py's two platform maps meant three
    tables to keep in step for one fact. Never fatal: an unreadable catalogue
    degrades to the extras above rather than breaking media lookup entirely.
    """
    out: dict[str, str | list[str]] = {}
    try:
        from ..catalog import load_catalog
        for pack in load_catalog().values():
            names = (pack.data.get("scraper") or {}).get("mediaAlias")
            if names:
                out[pack.id] = names[0] if len(names) == 1 else list(names)
    except Exception:
        log.warning("gamemedia: catalogue unreadable — emulator aliases limited "
                    "to the built-in extras", exc_info=True)
    return out


EMULATOR_ALIASES: dict[str, str | list[str]] = {**_EXTRA_ALIASES, **_catalog_aliases()}


# GameCore: the alias table maps one emulator to one *or several* consoles.
def _alias_names(key: str) -> list[str]:
    """The console names an emulator id stands for, most likely first."""
    v = EMULATOR_ALIASES.get(key, key)
    return [v] if isinstance(v, str) else list(v)


def _slug_name(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def fetch_systems(force: bool = False) -> list[dict]:
    """The official system list, cached (4 MB, rarely changes)."""
    if not force:
        try:
            return json.loads(paths.SYSTEMS_CACHE.read_text("utf-8"))["systemes"]
        except (OSError, ValueError, KeyError):
            pass
    creds = gs.ss_credentials()
    if not creds:
        return []
    try:
        data = ss_request("systemesListe.php", creds)
    except (ScreenScraperClosed, ScreenScraperUnreachable):
        return []
    systemes = ((data or {}).get("response") or {}).get("systemes") or []
    if systemes:
        write_json(paths.SYSTEMS_CACHE, {"fetched_at": datetime.now(timezone.utc).isoformat(),
                                   "systemes": systemes})
    return systemes


_registry: dict | None = None


def registry() -> dict:
    """{by_name: {alias→id}, by_ext: {ext→[id…]}, info: {id→{…}}}."""
    global _registry
    if _registry is not None:
        return _registry
    by_name: dict[str, int] = {}
    by_ext: dict[str, list[int]] = {}
    info: dict[int, dict] = {}
    # 3 levels: the system's own name > a frontend slug > category/synonym.
    tiers: list[list[tuple[int, list]]] = [[], [], []]
    for s in fetch_systems():
        try:
            sid = int(s["id"])
        except (KeyError, TypeError, ValueError):
            continue
        noms = s.get("noms") or {}
        label = noms.get("nom_eu") or noms.get("nom_us") or noms.get("noms_commun") or str(sid)
        info[sid] = {"id": sid, "name": label,
                     "launchbox": noms.get("nom_launchbox") or "",
                     "company": (s.get("compagnie") or ""),
                     "type": s.get("type") or ""}
        # Every known name becomes an alias, BUT in two precedence passes.
        # nom_launchbox is a category, not an identity: more than 50 arcade
        # boards all read "arcade" there. So the system's own names come first,
        # categories and synonyms after.
        tiers[0].append((sid, [noms.get("nom_eu"), noms.get("nom_us")]))
        tiers[1].append((sid, [noms.get("nom_recalbox"), noms.get("nom_retropie")]))
        tiers[2].append((sid, [noms.get("nom_launchbox"), noms.get("nom_hyperspin"),
                               noms.get("noms_commun")]))
        for ext in str(s.get("extensions") or "").split(","):
            if ext := ext.strip().lower().lstrip("."):
                by_ext.setdefault(ext, []).append(sid)

    for group in tiers:
        for sid, fields in group:
            for field in fields:
                for part in str(field or "").split(","):
                    if alias := _slug_name(part):
                        by_name.setdefault(alias, sid)

    _registry = {"by_name": by_name, "by_ext": by_ext, "info": info}
    return _registry


def system_candidates(filename: str, hint: str = "") -> list[int]:
    """The systemeid values to try, most likely first.

    An emulator id sometimes covers several consoles — mgba reads gba, gbc AND
    gb, dolphin reads gamecube and wii. Sending a single systemeid made a GBC
    game filed under emu/mgba/ fail. The extension is often more precise than
    the emulator (.gbc leaves no doubt) but useless when shared (.iso exists on
    twenty machines) — hence this order.
    """
    reg = registry()
    ext = Path(filename).suffix.lower().lstrip(".")
    by_ext = reg["by_ext"].get(ext, [])
    hinted, _ = detect_system(filename, hint)

    # GameCore: every console the emulator covers, not just the primary one.
    # This is what the extension was meant to supply and cannot when the format
    # belongs to the emulator rather than to the console — .rvz is listed under
    # no system at all, so a Wii game under Dolphin was only ever asked about
    # as a GameCube game.
    from_alias: list[int] = []
    for raw in (hint, Path(filename).parent.name):
        key = _slug_name(raw)
        if not key:
            continue
        for name in _alias_names(key):
            if sid := reg["by_name"].get(_slug_name(name)):
                from_alias.append(sid)
        if from_alias:
            break

    ordered: list[int] = []
    if 0 < len(by_ext) <= 3:          # discriminating extension: it goes first
        ordered += by_ext
    if hinted:
        ordered.append(hinted)
    ordered += from_alias              # the emulator's other consoles
    ordered += by_ext                  # the rest of the extension, last resort
    seen: set[int] = set()
    return [s for s in ordered if not (s in seen or seen.add(s))][:4]


def detect_system(filename: str, hint: str = "") -> tuple[int | None, dict]:
    """(systemeid, info) for this game. An explicit hint always wins.

    The extension alone is ambiguous — .bin exists on Megadrive, PS1 and Master
    System, .iso on about twenty machines — so a hint (`-s`, or the parent
    directory name, which on a GameCore box is the emulator id) is what decides.
    With no hint we take the extension's first candidate.
    """
    reg = registry()
    for raw in (hint, Path(filename).parent.name):
        key = _slug_name(raw)
        if not key:
            continue
        # GameCore: an alias may name several consoles. The first that the
        # registry knows is the primary — the one reported as `ss_systemeid`
        # and used for the LaunchBox platform. The others come back through
        # system_candidates() and are what actually get tried.
        for name in _alias_names(key):
            if sid := reg["by_name"].get(_slug_name(name)):
                return sid, reg["info"].get(sid, {})
    ext = Path(filename).suffix.lower().lstrip(".")
    if cands := reg["by_ext"].get(ext):
        return cands[0], reg["info"].get(cands[0], {})
    return None, {}
