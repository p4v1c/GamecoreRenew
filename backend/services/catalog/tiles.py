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

# (path, args) for a pack. The default is "whatever the pack prefers", which is
# what a .dist records: it describes the reference box, not this one.
LauncherResolver = Callable[[object], "tuple[str, str]"]

# What a flatpak launcher writes instead of an application id. The tile says
# "the app this pack resolves to", not "io.github.ryubing.Ryujinx", so the day
# a candidate dies the tile is still correct and only the catalogue changes.
#
# It is expanded at LAUNCH, not when the tile is written: a tile is written
# once, by an installer or an OTA, and the set of installed Flatpaks changes
# after that. Baking the id in is what tied a launcher to an install for good.
APPID_TOKEN = "@APPID@"


def expand_app_id(args: str, app_id: str) -> str:
    """Substitute the launcher token. A no-op on args that do not carry it."""
    return args.replace(APPID_TOKEN, app_id) if app_id else args


def flatpak_app_id(args: str) -> str:
    """The application id out of a `flatpak run …` argument string, or "".

    The id is the first argument that is not an option — NOT simply the token
    after `run`. Flatpak takes its own flags there, and a tile that needs one
    reads `run --nosocket=wayland --socket=x11 com.nvidia.geforcenow`.

    Both readers used to take `args[1]` and therefore read `--nosocket=wayland`
    as the application id. That was silent in both:

      · `process_manager._flatpak_kill` ran `flatpak kill --nosocket=wayland`,
        which kills nothing. It only warns when `run` is absent, and `run` was
        there — so quitting that app left its sandbox running, and the log said
        the kill had been issued;
      · `merge.launcher_is_stale` compared it against the declared app ids,
        found no pack declaring `--nosocket=wayland`, and would have rewritten
        the launcher as stale. Latent only because no pack ships flags today —
        the first one to need `--socket=x11` would have had its launcher
        silently replaced on the next update.

    One reader now, so the next caller cannot get it wrong a third way.
    """
    parts = args.split()
    if not parts or parts[0] != "run":
        return ""
    for token in parts[1:]:
        if not token.startswith("-"):
            return token
    return ""


def preferred_launcher(pack) -> tuple[str, str]:
    launch = pack.data["launch"]
    prefer = launch.get("preferIfPresent")
    if prefer:
        return prefer["path"], prefer.get("args", "")
    return launch["path"], launch.get("args", "")


def logo_path(pack) -> str:
    """One rule: a pack's logo is named after the pack.

    There used to be a table here mapping eleven ids to the platform names
    installed boxes record — `duckstation` to `ps1.png`. Nothing depended on
    it: no test, and `serve_logo` resolves an iconPath back to its pack either
    way, which is what keeps already-installed boxes working. All it bought was
    a second naming rule and a list to consult to know which one applied.
    """
    return f"assets/logos/{pack.id}.png"


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
        # Only when the pack declares any. An empty list in the tile would be
        # indistinguishable from "this box's systems.json predates the field",
        # which is exactly the case `merge.py` has to be able to fill in.
        if consoles := roms.get("consoles"):
            entry["consoles"] = [{"id": c["id"], "label": c["label"],
                                  **({"ratio": c["ratio"]} if c.get("ratio") else {}),
                                  "extensions": list(c["extensions"])}
                                 for c in consoles]
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

    # The accessories that are not pads. Only what a LAUNCH needs to know:
    # which device, what to call it, and what to say when it is not there.
    # `udevRule` is deliberately not carried — it is install-time text, it
    # needs root to mean anything, and a tile is a file the backend reads on
    # every launch. Copying a permission rule into it would put the widest
    # thing a pack can ask for into the most-read file on the box.
    if usb := pack.data.get("usb"):
        entry["usb"] = [{"vidPid": d["vidPid"], "class": d["class"],
                         "label": d.get("label", ""), "note": d["note"]}
                        for d in usb]

    return entry
