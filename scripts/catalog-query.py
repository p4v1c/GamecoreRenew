#!/usr/bin/env python3
"""Query the catalogue from a shell script.

The bash installers used to each carry their own copy of "which app id does
this emulator use", "where does its config live", "which ROM directory does it
need". Four copies of the config-path map alone, and the N64 migration updated
one of them. This is the single answer they all read now.

Stdlib only, and the import chain stays stdlib only on purpose: `arch.sh` calls
this at 25%, long before `pip install -r backend/requirements.txt` has run.

Output is tab-separated, one record per line, so a caller does:

    while IFS=$'\\t' read -r id app_id; do … done < <(catalog-query.py flatpaks)

Every subcommand is a projection of catalog/<id>/pack.json — nothing here
decides anything.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.services.catalog import appid, load_catalog  # noqa: E402


def _resolve(value: str, home: str, gamecore: str, app_id: str) -> str:
    """Expand the pack tokens. @FLATPAK_CONFIG@ derives from the SAME app id
    the box has installed — that is what makes a phantom config directory
    impossible to express."""
    return (value
            .replace("@FLATPAK_CONFIG@", f"{home}/.var/app/{app_id}/config")
            .replace("@GAMECORE_PATH@", gamecore)
            .replace("@HOME@", home))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=[
        "ids", "flatpaks", "config-dest", "rom-dirs", "launchers",
        "sandbox", "packages", "app-ids", "app-id-candidates",
    ])
    ap.add_argument("--no-probe", action="store_true",
                    help="do not ask flatpak what is installed; answer from the "
                         "packs' declared order alone (for a build, not a box)")
    ap.add_argument("--kind", choices=["emulator", "app"],
                    help="restrict to emulators or applications")
    ap.add_argument("--select", default="all",
                    help="'all' (default) or a space-separated list of ids")
    ap.add_argument("--home", default=str(Path.home()))
    ap.add_argument("--gamecore-path", default="/opt/GameCore")
    ap.add_argument("--gamecore-data", default=os.environ.get("GAMECORE_DATA") or "",
                    help="the data root, when it is not the install — the "
                         "sandbox has to be able to see the ROMs")
    # Default to the catalogue in THIS tree, not the one GAMECORE_PATH points
    # at. This script ships alongside the packs it describes: resolving through
    # the environment instead meant a caller with GAMECORE_PATH set elsewhere
    # silently read a different catalogue — or none, and every installer map
    # came back empty.
    ap.add_argument("--catalog", type=Path, default=ROOT / "catalog")
    ap.add_argument("--local", type=Path, default=ROOT / "config" / "catalog.d")
    args = ap.parse_args()

    # A box, so the answer follows what is actually installed: a machine that
    # fell back to the second candidate must be told where ITS config lives,
    # not where the preferred candidate's would have been.
    if not args.no_probe:
        appid.probe()

    try:
        packs = load_catalog(args.catalog, args.local)
    except OSError as e:
        print(f"catalog-query: cannot read the catalogue at {args.catalog} — {e}",
              file=sys.stderr)
        return 1

    chosen = None if args.select.strip() == "all" else set(args.select.split())
    items = [p for p in packs.values()
             if (args.kind is None or p.kind == args.kind)
             and (chosen is None or p.id in chosen)]
    # Stable output: a caller diffing two runs must not see reordering.
    items.sort(key=lambda p: p.id)

    out: list[str] = []
    for p in items:
        if args.command == "ids":
            out.append(p.id)

        elif args.command in ("flatpaks", "app-ids"):
            # The RESOLVED id — one line per pack, the id this box means. A
            # caller running `flatpak override` or `flatpak kill` wants the one
            # that is there, never the whole candidate list.
            if p.app_id:
                out.append(p.id + "\t" + p.app_id if args.command == "flatpaks"
                           else p.app_id)

        elif args.command == "app-id-candidates":
            # Every candidate, for the caller that has to consider them all:
            # the weekly upstream check, and an uninstaller that must find the
            # emulator it installed even if the catalogue has moved on since.
            for candidate in p.app_ids:
                out.append(f"{p.id}\t{candidate}")

        elif args.command == "config-dest":
            cfg = p.data.get("config")
            if not cfg:
                continue
            # `nativeDest` exists for the two emulators a box can run natively
            # (mgba, melonds). The installer picks by what is on disk; both are
            # emitted so it does not have to know which.
            dest = _resolve(cfg["dest"], args.home, args.gamecore_path, p.app_id)
            native = cfg.get("nativeDest")
            native = _resolve(native, args.home, args.gamecore_path, p.app_id) if native else ""
            out.append(f"{p.id}\t{dest}\t{native}")

        elif args.command == "rom-dirs":
            roms = p.data.get("roms")
            if roms:
                out.append(roms["dir"].split("/", 1)[1])

        elif args.command == "launchers":
            path, launch_args = p.launcher()
            out.append(f"{p.id}\t{path}\t{launch_args}")

        elif args.command == "sandbox":
            if not p.app_id:
                continue
            sb = p.data.get("sandbox")
            if sb is None:
                # The emulator policy, and the reason it is the default: a pack
                # that says nothing wants ROM access and a gamepad on X11. The
                # ROMs are under the data root — granted as well when it is
                # not the install, or a launch hands the emulator a path its
                # sandbox cannot see and the game reads as missing.
                roots = [args.gamecore_path]
                if args.gamecore_data and args.gamecore_data != args.gamecore_path:
                    roots.append(args.gamecore_data)
                flags = [*(f"--filesystem={r}" for r in roots), "--device=all",
                         "--socket=x11"]
            else:
                flags = ([f"--filesystem={v}" for v in sb.get("filesystem", [])]
                         + [f"--device={v}" for v in sb.get("device", [])]
                         + [f"--socket={v}" for v in sb.get("socket", [])])
            out.append(p.app_id + "\t" + " ".join(flags))

        elif args.command == "packages":
            for pkg in (p.data.get("packages") or {}).get("pacman", []):
                out.append(pkg)

    if args.command == "packages":       # aggregated across packs, deduplicated
        seen, uniq = set(), []
        for pkg in out:
            if pkg not in seen:
                seen.add(pkg); uniq.append(pkg)
        out = uniq

    print("\n".join(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
