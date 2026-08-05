"""One tile entry, built from one pack. The only implementation.

A tile in `config/systems.json` or `config/apps.json` is a contract: the exact
set of fields `backend/routers/games.py` reads to launch something and
`frontend/` reads to draw it. That contract used to be written down twice —

    scripts/gen-catalog.py            _launcher()  system_entry()  app_entry()
    backend/services/catalog/merge.py nominal_launcher()  system_entry_from_pack()

— because the two run at moments that know different things: the first in the
repository at build time, with no box to inspect, producing
`install/generated/*.dist`; the second on the box during an OTA, adding a tile
the box does not have yet.

That difference is real and is the parameter below. Everything else was
duplication, and it had already drifted three ways:

  · `fullscreen` / `gamepadTrigger` existed in one and not the other, so a tile
    installed fresh got Stremio's fullscreen and the same tile added later by an
    update did not;
  · `iconPath` was `ps1.png` in one and `duckstation.png` in the other. Both
    resolve — `serve_logo` has two lookup passes — so nobody noticed, and a box
    accumulated a mix of the two conventions in one file;
  · one read `pack.data["roms"]` and the other `pack.data.get("roms") or {}`,
    so a valid pack with no `roms` block crashed the build and merged fine.

Add a field here and both paths get it. That is the whole point.
"""
from __future__ import annotations

from collections.abc import Callable

# The file name systems.json records for a pack's logo. These are platform
# names, not pack ids, because that is what installed boxes already have in
# their catalogues — `serve_logo` resolves them back to `catalog/<id>/logo.png`.
# Renaming them would be a migration for no gain.
LOGO_NAME = {
    "azahar": "3ds.png", "cemu": "wiiu.png", "dolphin": "gamecube.png",
    "ryujinx": "switch.png", "duckstation": "ps1.png", "pcsx2": "ps2.png",
    "rpcs3": "ps3.png", "ppsspp": "psp.png", "gopher64": "n64.png",
    "melonds": "ds.png", "mgba": "gba.png", "xenia": "xenia.png",
    "shadps4": "shadps4.png", "steam": "steam.png", "twitch": "twitch.png",
    "stremio": "stremio.png", "youtube": "youtube.png",
}

# (path, args) for a pack. The default is "whatever the pack prefers", which is
# what a .dist records: it describes the reference box, not this one.
LauncherResolver = Callable[[object], "tuple[str, str]"]


def preferred_launcher(pack) -> tuple[str, str]:
    launch = pack.data["launch"]
    prefer = launch.get("preferIfPresent")
    if prefer:
        return prefer["path"], prefer.get("args", "")
    return launch["path"], launch.get("args", "")


def logo_path(pack) -> str:
    return f"assets/logos/{LOGO_NAME.get(pack.id, pack.id + '.png')}"


def tile_entry(pack, *, resolve_launcher: LauncherResolver | None = None) -> dict:
    """The tile for `pack`, emulator or app.

    `resolve_launcher` is the one thing that legitimately differs by caller:
    `merge.py` passes a resolver that only honours `preferIfPresent` when that
    binary is actually on this box, because it has a box to look at.
    """
    resolve = resolve_launcher or preferred_launcher
    path, args = resolve(pack)
    is_app = pack.kind == "app"

    entry: dict = {"id": pack.id}
    if is_app:
        entry["kind"] = "app"
    entry["type"] = "application" if is_app else "emulator"
    entry["label"] = pack.data["label"]
    entry["platform"] = pack.data["platform"]
    entry["color"] = pack.data["color"]
    entry["iconPath"] = logo_path(pack)
    entry["path"] = path
    entry["args"] = args

    if not is_app:
        roms = pack.data.get("roms") or {}
        entry["romsPath"] = roms.get("dir", f"emu/{pack.id}") + "/"
        if roms.get("scanDirs"):
            entry["scanDirs"] = True
        entry["extensions"] = list(roms.get("extensions", []))
        entry["libretroSystems"] = list((pack.data.get("scraper") or {}).get("libretro", []))

    # Launch-time behaviour, read by games.py right after a successful launch.
    # The pack spells these in camelCase like the rest of the schema; the tile
    # keeps the snake_case names fullscreen_enforcer.py has always read.
    launch = pack.data["launch"]
    if fs := launch.get("fullscreen"):
        entry["fullscreen"] = {"wm_class": list(fs["wmClass"]),
                               "timeout_s": fs.get("timeoutSec", 45)}
    if launch.get("gamepadTrigger"):
        entry["gamepadTrigger"] = True

    return entry
