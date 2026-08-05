#!/usr/bin/env python3
"""Install what a pack declares, from the shell installer.

    gamecore-provider.py install duckstation --user pavic --gamecore-path /opt/GameCore
    gamecore-provider.py install --kind emulator --select "rpcs3 pcsx2" …
    gamecore-provider.py install xenia --dry-run

Exit code is 0 when every selected pack was handled, 1 when at least one
failed — but a failure here is never meant to end the install. `arch.sh` calls
it with `|| true` and reports the missing tile in its closing summary, because
the alternative is a machine left neither installed nor clean.

Output is one line per pack, prefixed so the caller can colour it:

    OK   duckstation installed → bin/duckstation.AppImage
    SAME xenia already present
    FAIL rpcs3 could not be downloaded — its tile will be missing.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.services.catalog import load_catalog          # noqa: E402
from backend.services.installer import AppContext, apply, enabled_units  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["install"])
    ap.add_argument("ids", nargs="*", help="pack ids; empty means --select")
    ap.add_argument("--select", default="",
                    help="'all' or a space-separated list of ids")
    ap.add_argument("--kind", choices=["emulator", "app"])
    ap.add_argument("--user", default="", help="owner of the installed files")
    ap.add_argument("--user-home", default="",
                    help="that user's home; @HOME@ in a pack resolves to it")
    ap.add_argument("--gamecore-path", type=Path, default=Path("/opt/GameCore"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--catalog", type=Path, default=ROOT / "catalog")
    ap.add_argument("--local", type=Path, default=ROOT / "config" / "catalog.d")
    args = ap.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(message)s")

    try:
        packs = load_catalog(args.catalog, args.local)
    except OSError as e:
        print(f"FAIL cannot read the catalogue at {args.catalog} — {e}",
              file=sys.stderr)
        return 1

    wanted = set(args.ids) if args.ids else None
    if wanted is None and args.select and args.select.strip() != "all":
        wanted = set(args.select.split())

    chosen = [p for p in sorted(packs.values(), key=lambda p: p.id)
              if (wanted is None or p.id in wanted)
              and (args.kind is None or p.kind == args.kind)]

    if wanted:
        for missing in sorted(wanted - {p.id for p in chosen}):
            print(f"FAIL {missing}: no such pack in the catalogue")

    # Secrets come from the environment, never from argv: /proc/<pid>/cmdline is
    # world-readable and one of these is a Twitch client secret. arch.sh exports
    # them for the length of this call.
    secrets = {spec["key"]: os.environ.get(spec["key"], "")
               for pack in chosen for spec in pack.data.get("secrets", [])}
    ctx = AppContext(gamecore_path=args.gamecore_path, user=args.user,
                     dry_run=args.dry_run,
                     user_home=Path(args.user_home) if args.user_home
                               else Path.home(),
                     secrets=secrets)
    failed = bool(wanted) and bool(wanted - {p.id for p in chosen})
    for pack in chosen:
        for result in apply(pack, ctx):
            tag = "SAME" if result.already else ("OK" if result.ok else "FAIL")
            print(f"{tag} {result.message}")
            failed = failed or not result.ok
        # The caller has to daemon-reload and restart these: a user unit that was
        # symlinked by hand is invisible to a running user manager until it does,
        # so the service would sit dead until the next boot.
        for unit in enabled_units(pack, ctx):
            print(f"UNIT {unit}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
