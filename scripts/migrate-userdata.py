#!/usr/bin/env python3
"""Copy a box's data out of the installation and into its own tree.

    scripts/migrate-userdata.py --to /userdata                 # plan only
    scripts/migrate-userdata.py --to /userdata --i-know-what-i-am-doing

This moves somebody's ROM library, their saves' neighbours, their playtime and
their credentials. It is the most destructive thing in the repository, so it is
built to be hard to fire by accident and impossible to fire by surprise:

  · **Dry run by default.** No flag, no writes. The plan goes to the terminal
    and a human reads it before anything happens.
  · **It copies. It never deletes, and never overwrites.** The originals stay
    exactly where they are, so a migration that turns out wrong costs disk
    space and nothing else. Deleting the old copy is a separate decision, made
    later, by a person who has seen the box work.
  · **No default destination.** `--to` is required. There is no way to run this
    bare and have it do something.
  · **Nothing calls it.** Not `update/linux.sh`, not an `install/steps/` script
    the OTA invokes, not the backend at startup, not a systemd unit. It is a
    command a human types, and `backend/tests/test_migration.py` fails the
    build if that ever stops being true.

Why it does not finish the job
------------------------------
Copying the bytes is not the migration. The box only starts reading the new
tree once `GAMECORE_DATA` is set in the backend's systemd unit, and this script
does not touch that either — it prints what to do and stops. Two reversible
steps with a human between them, rather than one irreversible one.

That ordering is deliberate: the pointer moved first (the release that split
the paths defaults `GAMECORE_DATA` to the installation, so nothing changed),
and the bytes move here, later, by hand.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.services.paths import _LAYOUT  # noqa: E402

# The sections worth carrying over, in the order a reader wants them: the small
# irreplaceable things first, the enormous re-downloadable ones last.
#
# Read out of paths._LAYOUT rather than retyped — that table is what the
# backend resolves against, and a migration that disagreed with it would put
# the data somewhere the box does not look.
_SECTIONS = ["config", "roms", "overlays", "logos", "addons"]


def _human(n: int) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if n < 1024 or unit == "TiB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024.0
    return f"{n} B"


class Section:
    def __init__(self, name: str, src: Path, dest: Path):
        self.name, self.src, self.dest = name, src, dest
        self.files: list[Path] = []      # relative to src
        self.collisions: list[Path] = []
        self.bytes = 0
        if not src.is_dir():
            return
        for p in sorted(src.rglob("*")):
            if p.is_symlink() or not p.is_file():
                continue
            rel = p.relative_to(src)
            self.files.append(rel)
            self.bytes += p.stat().st_size
            if (dest / rel).exists():
                self.collisions.append(rel)

    @property
    def present(self) -> bool:
        return self.src.is_dir()


def plan(src_root: Path, dest_root: Path) -> list[Section]:
    """What would be copied. Reads only — this is the dry run's whole job."""
    out = []
    for name in _SECTIONS:
        rel = _LAYOUT[name]
        out.append(Section(name, src_root / rel, dest_root / rel))
    return out


def report(sections: list[Section], src_root: Path, dest_root: Path) -> None:
    print(f"\n  {src_root}  →  {dest_root}\n")
    print(f"  {'section':<10} {'files':>7} {'size':>11}   source")
    print("  " + "-" * 68)
    for s in sections:
        if not s.present:
            print(f"  {s.name:<10} {'—':>7} {'absent':>11}   {s.src}")
            continue
        print(f"  {s.name:<10} {len(s.files):>7} {_human(s.bytes):>11}   {s.src}")
    total_files = sum(len(s.files) for s in sections)
    total_bytes = sum(s.bytes for s in sections)
    print("  " + "-" * 68)
    print(f"  {'TOTAL':<10} {total_files:>7} {_human(total_bytes):>11}")

    collisions = [(s, rel) for s in sections for rel in s.collisions]
    if collisions:
        print(f"\n  {len(collisions)} file(s) already exist at the destination "
              "and will be LEFT ALONE:")
        for s, rel in collisions[:20]:
            print(f"    {s.dest / rel}")
        if len(collisions) > 20:
            print(f"    … and {len(collisions) - 20} more")

    try:
        free = shutil.disk_usage(_existing_ancestor(dest_root)).free
        print(f"\n  Free at the destination: {_human(free)}")
        if free < total_bytes:
            print("  *** NOT ENOUGH SPACE — this would fail partway through. ***")
    except OSError as e:
        print(f"\n  Could not measure free space at {dest_root}: {e}")


def _existing_ancestor(p: Path) -> Path:
    """disk_usage needs something that exists; the destination may not yet."""
    for candidate in [p, *p.parents]:
        if candidate.exists():
            return candidate
    return Path("/")


def apply(sections: list[Section]) -> int:
    """Copy, verify, and leave every source in place. Returns files copied."""
    copied = 0
    for s in sections:
        if not s.present:
            continue
        skip = set(s.collisions)
        print(f"\n  {s.name}: {len(s.files) - len(skip)} file(s) → {s.dest}")
        for rel in s.files:
            if rel in skip:
                continue
            src, dest = s.src / rel, s.dest / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            # copy2 keeps mtime and mode. The temp-name-then-rename is what
            # makes an interrupted run leave no half-file that a later pass
            # would mistake for an already-migrated one and skip.
            tmp = dest.with_name(dest.name + ".migrating")
            shutil.copy2(src, tmp)
            expected = src.stat().st_size
            got = tmp.stat().st_size
            if got != expected:
                tmp.unlink(missing_ok=True)
                raise SystemExit(
                    f"\nERROR: {src} copied as {got} bytes, expected {expected}."
                    "\nNothing was deleted; the source is untouched. Fix the "
                    "destination and run again.")
            tmp.replace(dest)
            copied += 1
    return copied


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Copy GameCore's data out of the installation.",
        epilog="Dry run unless --i-know-what-i-am-doing is given. "
               "Sources are never deleted or overwritten.")
    ap.add_argument("--from", dest="src", metavar="DIR",
                    default=os.environ.get("GAMECORE_PATH", "/opt/GameCore"),
                    help="the installation (default: $GAMECORE_PATH or /opt/GameCore)")
    ap.add_argument("--to", dest="dest", metavar="DIR", required=True,
                    help="the new data root, e.g. /userdata")
    ap.add_argument("--i-know-what-i-am-doing", dest="write", action="store_true",
                    help="actually copy. Without this, nothing is written.")
    args = ap.parse_args(argv)

    src_root = Path(args.src).resolve()
    dest_root = Path(args.dest).resolve()

    if not src_root.is_dir():
        print(f"ERROR: no installation at {src_root}", file=sys.stderr)
        return 2
    if src_root == dest_root:
        print("ERROR: --from and --to are the same directory.", file=sys.stderr)
        return 2
    # Nesting either way would have the copy walking into its own output, or
    # writing into the tree it is reading.
    if dest_root in src_root.parents or src_root in dest_root.parents:
        print(f"ERROR: {src_root} and {dest_root} are nested — refusing.",
              file=sys.stderr)
        return 2

    sections = plan(src_root, dest_root)
    report(sections, src_root, dest_root)

    if not args.write:
        print("\n  DRY RUN — nothing was written.")
        print("  Read the plan above. To carry it out:")
        print(f"    {sys.argv[0]} --from {src_root} --to {dest_root} "
              "--i-know-what-i-am-doing\n")
        return 0

    copied = apply(sections)
    print(f"\n  Copied {copied} file(s). Every source is still in place.\n")
    print("  The box does NOT use the new tree yet. To switch it over:")
    print(f"    1. Add  Environment=GAMECORE_DATA={dest_root}  to")
    print("       /etc/systemd/system/gamecore-backend.service.d/override.conf")
    print("    2. systemctl daemon-reload && systemctl restart gamecore-backend")
    print("    3. Check the library, the settings and the addons on the TV.")
    print("    4. Only then, and only by hand, delete the old copies under")
    print(f"       {src_root}.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
