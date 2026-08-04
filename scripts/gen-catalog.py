#!/usr/bin/env python3
"""Generate install/systems.json.dist and install/apps.json.dist from the packs.

    scripts/gen-catalog.py            # write the .dist files
    scripts/gen-catalog.py --check    # fail if the committed .dist are stale

The .dist files stop being hand-maintained catalogues and become build output.
`--check` is what the CI runs, so a pack.json edited without regenerating is a
red build rather than a box that quietly disagrees with itself.

Key order matters. These files are compared byte-for-byte against what the
repository already ships, so the emitted key order is the order the committed
files use, not the order the pack declares.

Phase 1 keeps behaviour identical, which drives two deliberate choices:

  · `path`/`args` come from `preferIfPresent` when a pack declares one. That is
    what `install/systems.json.dist` says today (`lib/duck`, `lib/rpcs3`, …):
    the reference box's native binaries. flatpakify-systems.sh still rewrites
    them to Flatpak launchers at install time on a fresh box, exactly as
    before.
  · `@HOME@` is emitted as-is in apps.json.dist. `install/arch.sh` substitutes
    it at deploy time, alongside the `/home/pavic` pass it already had.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.services.catalog import load_catalog  # noqa: E402

SYSTEMS_DIST   = ROOT / "install" / "systems.json.dist"
APPS_DIST      = ROOT / "install" / "apps.json.dist"
COLOURS_TS     = ROOT / "frontend" / "src" / "lib" / "systemColors.ts"
INSTALLER_DATA = ROOT / "install" / "installer-gui" / "catalog_data.py"
OVERLAYS       = ROOT / "config" / "overlays.json"

# Logos keep their historical file names in assets/logos/ so that a box that
# has hand-replaced one keeps it (assets/logos/ stays out of the OTA rsync).
# The pack owns the image; this map owns the legacy name.
LOGO_NAME = {
    "azahar": "3ds.png", "cemu": "wiiu.png", "dolphin": "gamecube.png",
    "ryujinx": "switch.png", "duckstation": "ps1.png", "pcsx2": "ps2.png",
    "rpcs3": "ps3.png", "ppsspp": "psp.png", "gopher64": "n64.png",
    "melonds": "ds.png", "mgba": "gba.png", "xenia": "xenia.png",
    "shadps4": "shadps4.png", "steam": "steam.png", "twitch": "twitch.png",
    "stremio": "stremio.png",
    # youtube had no icon at all before the migration: the tile rendered with
    # no image. The pack now ships one, so the entry gains an iconPath - the
    # single intentional addition to apps.json.dist.
    "youtube": "youtube.png",
}

# The order emulators appear in the grid. Taken from the committed
# systems.json.dist: it is a curated running order, not alphabetical.
SYSTEM_ORDER = ["azahar", "cemu", "dolphin", "ryujinx", "duckstation", "pcsx2",
                "rpcs3", "ppsspp", "gopher64", "melonds", "mgba", "xenia",
                "shadps4"]
APP_ORDER = ["steam", "youtube", "twitch", "stremio"]


def _launcher(pack) -> tuple[str, str]:
    """What the .dist records: the reference box's preference when there is
    one, otherwise the nominal launcher."""
    launch = pack.data["launch"]
    prefer = launch.get("preferIfPresent")
    if prefer:
        return prefer["path"], prefer.get("args", "")
    return launch["path"], launch.get("args", "")


def system_entry(pack) -> dict:
    path, args = _launcher(pack)
    roms = pack.data["roms"]
    entry = {
        "id": pack.id,
        "type": "emulator",
        "label": pack.data["label"],
        "platform": pack.data["platform"],
        "color": pack.data["color"],
    }
    if pack.id in LOGO_NAME:
        entry["iconPath"] = f"assets/logos/{LOGO_NAME[pack.id]}"
    entry["path"] = path
    entry["args"] = args
    entry["romsPath"] = roms["dir"] + "/"
    if roms.get("scanDirs"):
        entry["scanDirs"] = True
    entry["extensions"] = roms.get("extensions", [])
    entry["libretroSystems"] = (pack.data.get("scraper") or {}).get("libretro", [])
    return entry


def app_entry(pack) -> dict:
    path, args = _launcher(pack)
    entry = {
        "id": pack.id,
        "kind": "app",
        "type": "application",
        "label": pack.data["label"],
        "platform": pack.data["platform"],
        "color": pack.data["color"],
    }
    if pack.id in LOGO_NAME:
        entry["iconPath"] = f"assets/logos/{LOGO_NAME[pack.id]}"
    entry["path"] = path
    entry["args"] = args
    return entry


def render(packs: dict) -> tuple[str, str]:
    systems = [system_entry(packs[i]) for i in SYSTEM_ORDER if i in packs]
    apps = [app_entry(packs[i]) for i in APP_ORDER if i in packs]
    dump = lambda d: json.dumps(d, indent=2, ensure_ascii=False) + "\n"
    return dump(systems), dump(apps)


# ── the three other derived artefacts ───────────────────────────────────────

def render_system_colours(packs: dict) -> str:
    """frontend/src/lib/systemColors.ts.

    It was hand-written and had already drifted: pcsx2 and rpcs3 carried
    #0046ff where the catalogue says #003087 and #00439c, and five ids were
    missing entirely. Latent only because SystemCard.tsx reads it as a fallback
    (`system.color || SYSTEM_COLORS[id]`) — it bites the moment an entry has no
    colour, which is exactly why `color` is required by the schema.

    The non-pack ids below are console short names the library screen can be
    asked for without a pack existing.
    """
    extra = {
        "snes": "#7c3aed", "nes": "#dc2626", "ps1": "#1d4ed8", "n64": "#15803d",
        "gba": "#b45309", "genesis": "#0369a1", "mame": "#be185d", "nds": "#0891b2",
    }
    rows = {p.id: p.data["color"] for p in sorted(packs.values(), key=lambda p: p.id)}
    lines = ["// GENERATED by scripts/gen-catalog.py — do not edit.",
             "// Source: catalog/<id>/pack.json. Run the script and commit the result.",
             "export const SYSTEM_COLORS: Record<string, string> = {"]
    for pid, colour in rows.items():
        lines.append(f"  {pid}: '{colour}',")
    lines.append("  // Console short names with no pack of their own.")
    for pid, colour in extra.items():
        lines.append(f"  {pid}: '{colour}',")
    lines.append("}")
    return "\n".join(lines) + "\n"


def render_installer_data(packs: dict) -> str:
    """install/installer-gui/catalog_data.py.

    The wizard is a PyInstaller onefile binary: it is downloaded and run BEFORE
    the repository exists on the machine, so it cannot read catalog/ at runtime.
    Its list is therefore generated into a module the binary bundles, rather
    than hand-maintained in gamecore_installer.py — which is how it came to
    offer "gopher64" as the N64 emulator long after that slot started launching
    Rosalie's Mupen GUI.
    """
    def rows(kind, order):
        out = []
        for pid in order:
            p = packs.get(pid)
            if p is None or p.kind != kind:
                continue
            name = p.data.get("emulatorName", p.data["label"])
            desc = p.data.get("description", p.data["label"])
            out.append(f"    ({pid!r}, {name!r}, {desc!r}),")
        return out

    return "\n".join([
        '"""GENERATED by scripts/gen-catalog.py — do not edit.',
        "",
        "Source: catalog/<id>/pack.json. The installer binary is built before the",
        "repository is on the machine, so this list is baked in rather than read.",
        '"""',
        "",
        "EMULATORS = [",
        *rows("emulator", SYSTEM_ORDER),
        "]",
        "",
        "APPS = [",
        *rows("app", APP_ORDER),
        "]",
        "",
    ])


def render_overlays(packs: dict, current: dict) -> str:
    """config/overlays.json — the fields the PACK owns, nothing else.

    Deliberately a partial rewrite, the same "only the sections we own"
    contract the config generators follow. `window_rect`, `hole` and
    `watch_timeout_s` are tuning tied to the image and the resolution, not
    properties of the emulator: they stay hand-maintained and are copied
    through untouched. The pack owns `wm_class` and `overlay_asset`, and
    nothing else.

    `label` is hand-maintained too, and that is not an oversight: here it names
    the BEZEL, not the system. mgba's reads "Game Boy Advance (Cadre Total)" —
    the full-frame variant — where the pack's label is plain "Game Boy
    Advance". Generating it from the pack silently threw that distinction away.
    """
    out = {}
    for pid, entry in current.items():
        pack = packs.get(pid)
        merged = dict(entry)
        if pack and (ov := pack.data.get("overlay")):
            merged["wm_class"] = ov["wmClass"]
            if asset := ov.get("asset"):
                merged["overlay_asset"] = f"assets/overlays/{asset}"
        out[pid] = merged
    return json.dumps(out, indent=4, ensure_ascii=False) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="exit non-zero if the committed .dist are out of date")
    args = ap.parse_args()

    # The catalogue in THIS tree — never the one GAMECORE_PATH points at.
    packs = load_catalog(ROOT / "catalog", ROOT / "config" / "catalog.d")
    systems_text, apps_text = render(packs)
    overlays_current = json.loads(OVERLAYS.read_text(encoding="utf-8")) \
        if OVERLAYS.is_file() else {}

    targets = [
        (SYSTEMS_DIST, systems_text),
        (APPS_DIST, apps_text),
        (COLOURS_TS, render_system_colours(packs)),
        (INSTALLER_DATA, render_installer_data(packs)),
        (OVERLAYS, render_overlays(packs, overlays_current)),
    ]
    if args.check:
        stale = []
        for path, text in targets:
            current = path.read_text(encoding="utf-8") if path.is_file() else ""
            if current != text:
                stale.append(path.relative_to(ROOT))
        if stale:
            print("gen-catalog: out of date: " + ", ".join(map(str, stale)),
                  file=sys.stderr)
            print("gen-catalog: run scripts/gen-catalog.py and commit the result",
                  file=sys.stderr)
            return 1
        print(f"gen-catalog: {len(packs)} pack(s), .dist up to date")
        return 0

    for path, text in targets:
        path.write_text(text, encoding="utf-8")
        print(f"gen-catalog: wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
