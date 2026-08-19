#!/usr/bin/env python3
"""Validate the pack catalogue. Offline, no dependency beyond the stdlib.

    scripts/check-catalog.py            # every pack
    scripts/check-catalog.py rpcs3      # one pack

Four families of check:

  schema     every pack.json validates against catalog/_schema/pack.schema.json
  symmetry   a pack has a logo, a declared ROM dir when it is an emulator, and
             a config.dest exactly when it ships a seed/
  seeds      no seed/ carries an SDL GUID that decodes to a real pad, no seed/
             matches its own `seedMustNotContain`, and no seed carries a
             harvest-box absolute path
  coherence  no two packs claim the same ROM directory or any of the same
             Flatpak app ids, no launcher spells an app id out instead of
             using @APPID@, and @FLATPAK_CONFIG@ is only used by a Flatpak pack

The last one is what makes the gopher64 class of bug structurally impossible:
`@FLATPAK_CONFIG@` resolves from the SAME `install.appIds` entry the box has
installed, so the config directory and the installed application cannot drift
apart.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.services.catalog import appid, tiles                  # noqa: E402
from backend.services.catalog.schema import load_schema, validate  # noqa: E402
from backend.services.configgen.controllers import (                # noqa: E402
    SDL3_FALLBACK_NAMES, db_name_for, vidpid_of,
)
from backend.services.configgen.snapshots import (                  # noqa: E402
    _ANY_GUID_RE as ANY_GUID_RE, guid_scannable,
)

CATALOG = ROOT / "catalog"
SCHEMA = CATALOG / "_schema" / "pack.schema.json"

# Absolute paths that only make sense on the box a config was harvested from.
HARVEST_PATHS = (re.compile(r"/home/[a-z][a-z0-9_-]*/"),)

_pad_name_memo: dict[tuple[str, str], str | None] = {}


def named_pad(guid: str) -> str | None:
    """The pad this GUID designates, or None if it designates nothing known.

    `seedMustNotContain` catches only what a pack thought to declare, so two
    seeds shipped a DualShock 4 GUID for months under `17 pack(s) OK`. This
    decodes instead of matching: any seed carrying a GUID whose vendor:product
    is a pad SDL can name is refused, whether or not the pack asked for it.

    A GUID whose vendor:product is in no table is NOT a hit — that would be
    noise (a hash, a session id), not a pinned pad.
    """
    vendor, product = vidpid_of(guid)
    if (vendor, product) not in _pad_name_memo:
        # gamecontrollerdb.txt is 2000+ lines re-read per lookup, and a single
        # seed can carry dozens of GUIDs.
        _pad_name_memo[(vendor, product)] = (
            SDL3_FALLBACK_NAMES.get((vendor, product)) or db_name_for(vendor, product))
    return _pad_name_memo[(vendor, product)]

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
        schema_problems = validate(pack, schema, pid)
        problems += [f"{pid}: {p}" for p in schema_problems]

        if pack.get("id") != pid:
            problems.append(f"{pid}: declares id={pack.get('id')!r} but lives in {pid!r}")

        if schema_problems:
            # Everything below assumes a schema-valid pack — a bios entry
            # missing its `file` key would turn the report into a traceback,
            # and the report is the deliverable: the authoring loop
            # (10-catalog-and-install.md §10) pastes it back to whoever
            # drafted the JSON. Fix the schema lines first, re-run, and the
            # deeper checks get their turn.
            continue

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

        # A console list that does not agree with the extension list it sits
        # next to. Caught here rather than at launch because the symptom is a
        # bezel that quietly stays at the system level for one console of a
        # pack — no error anywhere, just the wrong frame on one machine.
        roms = pack.get("roms") or {}
        exts = {e.lower() for e in roms.get("extensions") or []}
        claimed: dict[str, str] = {}
        for console in roms.get("consoles") or []:
            cid = console.get("id")
            for ext in console.get("extensions") or []:
                low = ext.lower()
                if low not in exts:
                    problems.append(
                        f"{pid}: console {cid!r} claims {ext} but roms.extensions "
                        f"does not list it — the pack would never see that file")
                # An extension under two consoles cannot name one, so the
                # cascade would silently drop back to the system level for
                # every game with it. Refused here, where it is visible, rather
                # than degraded at launch where it is not.
                if low in claimed:
                    problems.append(
                        f"{pid}: {ext} is claimed by both {claimed[low]!r} and "
                        f"{cid!r} — an extension names one console or none")
                claimed[low] = cid

        # ── coherence ─────────────────────────────────────────────────────
        app_ids = appid.declared(pack)
        app_id = app_ids[0] if app_ids else None
        dest = (cfg or {}).get("dest", "")
        if "@FLATPAK_CONFIG@" in dest and not app_id:
            problems.append(
                f"{pid}: uses @FLATPAK_CONFIG@ but install.provider is not flatpak — "
                f"the config dir would resolve against nothing")
        # EVERY candidate, not just the first. Two packs that share a fallback
        # would both install it and then both claim its ~/.var/app directory —
        # the second one's seed overwriting the first one's config, on the day
        # the primary dies and nowhere before it. Uniqueness has to hold across
        # the whole list or it does not hold at all.
        for candidate in app_ids:
            if candidate in seen_appids:
                problems.append(f"{pid}: Flatpak app id {candidate} already claimed "
                                f"by {seen_appids[candidate]}")
            seen_appids[candidate] = pid

        # A launcher may name the token or nothing, never a literal id: a
        # hardcoded id is the half of the bug that survives a corrected
        # catalogue, because the tile keeps launching it after the install has
        # already moved on.
        launch = pack.get("launch") or {}
        for where, block in (("launch", launch), ("launch.preferIfPresent",
                                                  launch.get("preferIfPresent") or {})):
            largs = block.get("args", "")
            for candidate in app_ids:
                if candidate in largs:
                    problems.append(
                        f"{pid}: {where}.args spells out {candidate} — use "
                        f"{tiles.APPID_TOKEN}, or the tile goes on launching this id "
                        f"after install.appIds has moved past it")

        bios = pack.get("bios")
        if bios:
            bdir = bios["dir"]
            if ("@FLATPAK_CONFIG@" in bdir or "@FLATPAK_DATA@" in bdir) and not app_id:
                problems.append(
                    f"{pid}: bios.dir uses a Flatpak token but install.provider is "
                    f"not flatpak — the BIOS directory would resolve against nothing")
            if not bios.get("files") and not bios.get("anyFile"):
                problems.append(
                    f"{pid}: bios declares neither files nor anyFile — the block "
                    f"says a directory exists and checks nothing in it")
            if bios.get("files") and bios.get("anyFile"):
                problems.append(
                    f"{pid}: bios declares both files and anyFile — anyFile means "
                    f"the emulator scans the directory, which makes named files a "
                    f"second, contradictory answer")
            for entry in bios.get("files", []):
                name = entry["file"]
                # `file` is joined onto bios.dir and stat'd. An absolute name or
                # a '..' segment would make the checker report on a path the
                # catalogue does not own — and a red BIOS line pointing at
                # someone's home directory is worse than no line at all.
                if name.startswith("/") or ".." in Path(name).parts:
                    problems.append(
                        f"{pid}: bios file {name!r} escapes bios.dir — names are "
                        f"relative to it, subdirectories allowed, nothing above")

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
                # Scanned through the same normalisation the runtime guard uses,
                # or a GUID inside an azahar stick binding stays invisible here
                # too — 2 of this seed's 17 were.
                for m in ANY_GUID_RE.finditer(guid_scannable(text)):
                    name = named_pad(m.group(1))
                    if not name:
                        continue
                    vendor, product = vidpid_of(m.group(1))
                    line = text[: m.start()].count("\n") + 1
                    problems.append(
                        f"{pid}: {rel}:{line} carries the SDL GUID {m.group(1)} "
                        f"— {vendor}:{product} ({name}). A seed is what a NEW box "
                        f"receives: a GUID in it describes the pad of the machine "
                        f"the config was harvested from and nobody else's. Clear "
                        f"the value and let the generator fill it in.")
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
