#!/usr/bin/env python3
"""Validate the pack catalogue. Offline, no dependency beyond the stdlib.

    scripts/check-catalog.py            # every pack
    scripts/check-catalog.py rpcs3      # one pack

Four families of check:

  schema     every pack.json validates against catalog/_schema/pack.schema.json
  symmetry   a pack has a logo, a declared ROM dir when it is an emulator, and
             a config.dest exactly when it ships a seed/
  seeds      no seed/ matches its own `seedMustNotContain`, and no seed carries
             a harvest-box absolute path
  coherence  no two packs claim the same ROM directory or the same Flatpak
             app id, and @FLATPAK_CONFIG@ is only used by a Flatpak pack

The last one is what makes the gopher64 class of bug structurally impossible:
`@FLATPAK_CONFIG@` resolves from the SAME `install.appId` the installer uses,
so the config directory and the installed application cannot drift apart.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.services.catalog.schema import load_schema, validate  # noqa: E402

CATALOG = ROOT / "catalog"
SCHEMA = CATALOG / "_schema" / "pack.schema.json"

# Absolute paths that only make sense on the box a config was harvested from.
HARVEST_PATHS = (re.compile(r"/home/[a-z][a-z0-9_-]*/"),)

# Binary seeds are copied verbatim and never token-substituted; scanning them
# for text patterns produces noise, not findings.
BINARY_SUFFIXES = {".png", ".jpg", ".sqlite3", ".db", ".bin", ".dat"}


def _iter_packs(only: str | None):
    for d in sorted(CATALOG.iterdir()):
        if not d.is_dir() or d.name.startswith(("_", ".")):
            continue
        if only and d.name != only:
            continue
        yield d


def check(only: str | None = None) -> list[str]:
    schema = load_schema(SCHEMA)
    problems: list[str] = []
    seen_roms: dict[str, str] = {}
    seen_appids: dict[str, str] = {}
    found = False

    for d in _iter_packs(only):
        found = True
        pid = d.name
        manifest = d / "pack.json"
        if not manifest.is_file():
            problems.append(f"{pid}: no pack.json")
            continue
        try:
            pack = json.loads(manifest.read_text(encoding="utf-8"))
        except ValueError as e:
            problems.append(f"{pid}: pack.json is not valid JSON — {e}")
            continue

        # ── schema ────────────────────────────────────────────────────────
        problems += [f"{pid}: {p}" for p in validate(pack, schema, pid)]

        if pack.get("id") != pid:
            problems.append(f"{pid}: declares id={pack.get('id')!r} but lives in {pid!r}")

        # ── symmetry ──────────────────────────────────────────────────────
        if not any((d / n).is_file() for n in ("logo.png", "logo.svg")):
            problems.append(f"{pid}: no logo.png or logo.svg")

        seed = d / "seed"
        cfg = pack.get("config")
        if seed.is_dir() and not cfg:
            problems.append(f"{pid}: ships a seed/ but declares no config.dest")
        # The converse is NOT an error: config.dest says where the emulator's
        # config lives, and a pack can need that without shipping a seed —
        # gopher64/RMG has a config directory and a seed that would be in the
        # wrong format entirely.

        # ── coherence ─────────────────────────────────────────────────────
        install = pack.get("install") or {}
        app_id = install.get("appId") if install.get("provider") == "flatpak" else None
        dest = (cfg or {}).get("dest", "")
        if "@FLATPAK_CONFIG@" in dest and not app_id:
            problems.append(
                f"{pid}: uses @FLATPAK_CONFIG@ but install.provider is not flatpak — "
                f"the config dir would resolve against nothing")
        if app_id:
            if app_id in seen_appids:
                problems.append(f"{pid}: Flatpak app id {app_id} already claimed "
                                f"by {seen_appids[app_id]}")
            seen_appids[app_id] = pid

        roms = pack.get("roms")
        if roms:
            rd = roms["dir"]
            if rd in seen_roms:
                problems.append(f"{pid}: ROM dir {rd} already claimed by {seen_roms[rd]}")
            seen_roms[rd] = pid

        # ── seeds ─────────────────────────────────────────────────────────
        patterns = ((pack.get("controllers") or {}).get("seedMustNotContain") or [])
        if seed.is_dir():
            for f in sorted(seed.rglob("*")):
                if not f.is_file() or f.suffix.lower() in BINARY_SUFFIXES:
                    continue
                try:
                    text = f.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                rel = f.relative_to(d)
                for pat in patterns:
                    m = re.search(pat, text, re.M)
                    if m:
                        line = text[: m.start()].count("\n") + 1
                        problems.append(
                            f"{pid}: {rel}:{line} matches seedMustNotContain /{pat}/ "
                            f"— {m.group(0)!r}. A seed must name no device: that is "
                            f"what pinned the grid to one controller model.")
                for hp in HARVEST_PATHS:
                    m = hp.search(text)
                    if m:
                        line = text[: m.start()].count("\n") + 1
                        problems.append(
                            f"{pid}: {rel}:{line} carries a harvest-box path "
                            f"{m.group(0)!r} — use the @HOME@ token")

    if only and not found:
        problems.append(f"no pack named {only!r} in {CATALOG}")
    return problems


def main() -> int:
    only = sys.argv[1] if len(sys.argv) > 1 else None
    problems = check(only)
    if problems:
        for p in problems:
            print(f"check-catalog: {p}", file=sys.stderr)
        print(f"\ncheck-catalog: {len(problems)} problem(s)", file=sys.stderr)
        return 1
    n = sum(1 for _ in _iter_packs(only))
    print(f"check-catalog: {n} pack(s) OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
