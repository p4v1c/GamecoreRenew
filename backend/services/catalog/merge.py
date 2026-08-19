"""Merge the shipped catalogue into a box's own `config/systems.json`.

`config/` is excluded from the OTA rsync — deliberately, it is the box's
identity — so nothing shipped in a release ever reached `systems.json`. Until
now `update/linux.sh` handled that by **printing** the commands the owner was
expected to type by hand to migrate the N64 slot. Nobody types those.

This does it instead, and the rules are conservative on purpose: this runs
unattended, on a machine whose state it does not know, against a file the owner
may have edited.

    an id only the box has        KEPT, untouched. A tile someone added by
                                  hand is theirs; the catalogue says nothing
                                  about it.
    an id only the catalogue has  ADDED. That is how a new emulator reaches an
                                  installed box at all.
    an id both have               the launcher is repaired ONLY when it is
                                  stale (see below), `extensions` gains what it
                                  is missing, and everything else is left alone.

**When is a launcher stale?** Not "different from the catalogue" — that would
undo `flatpakify-systems.sh`, which rewrites launchers to what the box actually
has, and would break a box legitimately running a native binary from `lib/`.
Two cases only:

  · it launches `flatpak run <app-id>` and NO pack declares that app id. This
    is the gopher64 case exactly: the box says
    `run io.github.gopher64.gopher64` while the installer installs
    com.github.Rosalie241.RMG. `launcher_exists()` in flatpakify cannot catch
    it, because the *path* is `flatpak` and that always exists.
  · the launcher path does not resolve on disk at all.

**Why `extensions` is merged and not just the launcher.** A machine installed
before `*.cue` was added to duckstation keeps a catalogue that scans `*.bin`
and not `*.cue`. The `.cue` was on disk so it shadowed the `.bin`, and it was
not in `extensions` so it was filtered out right after — the library went from
one PS1 game to none (services/rom_scanner.py). The merge is additive: an
extension the operator added by hand is never dropped.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from ...utils import atomic_write
from .tiles import APPID_TOKEN, flatpak_app_id, tile_entry

REMOVED_FILE = "catalog-removed.json"


def load_removed(root: Path) -> set[str]:
    """Ids the operator deliberately took off the grid.

    Without this, `gamecore-emu remove X` was undone by the very next merge:
    the merge adds every catalogue emulator the grid is missing — which is
    right for "a new emulator shipped in this release" and exactly wrong for
    "I do not want this tile". The two rules were in direct contradiction and
    the merge always won.

    Lives in config/, so it is excluded from the OTA rsync and a removal
    survives updates. Written only by `gamecore-emu`.
    """
    try:
        data = json.loads((root / "config" / REMOVED_FILE).read_text(encoding="utf-8"))
        return set(data) if isinstance(data, list) else set()
    except (OSError, ValueError):
        return set()


def save_removed(root: Path, ids: set[str]) -> None:
    atomic_write(root / "config" / REMOVED_FILE,
                 json.dumps(sorted(ids), indent=2) + "\n")


def _launcher_resolves(path: str, root: Path) -> bool:
    """The same question flatpakify-systems.sh asks, and the same answers."""
    if not path:
        return False
    if path == "flatpak":
        return True
    p = Path(path)
    if p.is_absolute():
        return p.exists()
    if "/" in path:
        return (root / path).exists()
    return shutil.which(path) is not None


# The app id is read by tiles.py, which owns the shape of a launcher — see the
# failure both copies of this used to produce.


def launcher_is_stale(entry: dict, pack, known_app_ids: set[str], root: Path) -> str:
    """"" when the launcher is fine, otherwise why it is not."""
    path, args = entry.get("path", ""), entry.get("args", "")
    if path == "flatpak":
        app_id = flatpak_app_id(args)
        if app_id == APPID_TOKEN:
            return ""                    # defers to the catalogue — never stale
        if app_id and app_id not in known_app_ids:
            return (f"launches {app_id}, which no pack declares "
                    f"(the installer installs {pack.app_id or 'something else'})")
        # A literal id where the pack now defers to @APPID@. Not broken today —
        # this is the id the box installed — but it is the half of the fallback
        # that does not move: when the catalogue drops this candidate, the tile
        # goes on launching it and the player gets "app not installed" from
        # flatpak instead of the emulator. This is the ONLY moment an installed
        # box gets migrated, so it has to count as stale before it breaks.
        if app_id and APPID_TOKEN in (pack.data.get("launch") or {}).get("args", ""):
            return (f"hardcodes {app_id}; the pack resolves its app id at launch "
                    f"now, so this tile could not follow a fallback")
        return ""
    if not _launcher_resolves(path, root):
        return f"launcher {path!r} does not exist on this box"
    return ""


def nominal_launcher(pack, root: Path) -> tuple[str, str]:
    """What this box should launch: the reference-box preference when that
    binary is actually here, the nominal launcher otherwise."""
    launch = pack.data["launch"]
    prefer = launch.get("preferIfPresent")
    if prefer and _launcher_resolves(prefer["path"], root):
        return prefer["path"], prefer.get("args", "")
    return launch["path"], launch.get("args", "")


def entry_from_pack(pack, root: Path) -> dict:
    """A fresh tile for a pack this box does not have yet.

    The shape is `catalog/tiles.py`'s and nowhere else — see its header for what
    that duplication used to cost. All this adds is the box: `preferIfPresent`
    is honoured only when that binary is really here.
    """
    return tile_entry(pack, resolve_launcher=lambda p: nominal_launcher(p, root))


def merge_systems(live: list[dict], packs: dict, root: Path,
                  add_missing: bool = True,
                  removed: set[str] | None = None,
                  kind: str = "emulator") -> tuple[list[dict], list[str]]:
    """(merged entries, human-readable notes). Pure — writes nothing.

    `removed` is what the operator took off the grid on purpose; those ids are
    never added back. `kind` picks which half of the catalogue this file holds.
    """
    removed = removed or set()
    # Every candidate, not just the resolved one: a box legitimately running a
    # fallback must not have its working launcher called stale and rewritten.
    known_app_ids = {a for p in packs.values() for a in p.app_ids}
    notes: list[str] = []
    out: list[dict] = []
    seen: set[str] = set()

    for entry in live:
        sid = entry.get("id", "")
        seen.add(sid)
        pack = packs.get(sid)
        if pack is None or pack.kind != kind:
            # A tile the operator added by hand. Not ours to touch.
            out.append(entry)
            continue

        merged = dict(entry)
        why = launcher_is_stale(entry, pack, known_app_ids, root)
        if why:
            path, args = nominal_launcher(pack, root)
            if (path, args) != (entry.get("path"), entry.get("args")):
                merged["path"], merged["args"] = path, args
                notes.append(f"{sid}: launcher updated — {why}")

        # Additive: an extension the operator added by hand is never dropped.
        want = list((pack.data.get("roms") or {}).get("extensions", []))
        have = list(entry.get("extensions", []))
        missing = [e for e in want if e not in have]
        if missing:
            merged["extensions"] = have + missing
            notes.append(f"{sid}: extensions gained {', '.join(missing)}")

        # Only when the box has none at all — an empty list means the entry
        # predates the field, not that the operator cleared it.
        if not entry.get("libretroSystems"):
            libretro = list((pack.data.get("scraper") or {}).get("libretro", []))
            if libretro:
                merged["libretroSystems"] = libretro
                notes.append(f"{sid}: libretro systems filled in")

        # Same rule, and it is the only way this reaches an existing box:
        # `config/` is excluded from the OTA rsync, so a release that adds
        # `roms.consoles` to a pack changes nothing in a systems.json that is
        # already there. Filled in rather than overwritten — a console list the
        # operator edited is a list they meant.
        declared = list((pack.data.get("roms") or {}).get("consoles", []))
        if not entry.get("consoles"):
            if declared:
                merged["consoles"] = [{"id": c["id"], "label": c["label"],
                                       **({"ratio": c["ratio"]} if c.get("ratio") else {}),
                                       "extensions": list(c["extensions"])}
                                      for c in declared]
                notes.append(f"{sid}: consoles filled in "
                             f"({', '.join(c['id'] for c in declared)})")
        else:
            # The gentler half of the same rule: a box that already carries the
            # console list gains a MISSING ratio and nothing else. Adding an
            # absent key cannot undo an operator's edit; rewriting a present
            # one could, so a ratio someone set by hand is left alone.
            gained = []
            by_id = {c["id"]: c for c in declared if c.get("id")}
            for c in merged.get("consoles", []):
                packed = by_id.get(c.get("id"))
                if packed and packed.get("ratio") and "ratio" not in c:
                    c["ratio"] = packed["ratio"]
                    gained.append(c["id"])
            if gained:
                merged["consoles"] = list(merged["consoles"])
                notes.append(f"{sid}: console ratio filled in ({', '.join(gained)})")

        out.append(merged)

    if add_missing:
        for pack in packs.values():
            if pack.kind != kind or pack.id in seen:
                continue
            if pack.id in removed:
                # Taken off deliberately. Not "missing" — declined.
                continue
            out.append(entry_from_pack(pack, root))
            notes.append(f"{pack.id}: added — new in this release")

    return out, notes


def merge_file(systems_file: Path, packs: dict, root: Path,
               dry_run: bool = False, kind: str = "emulator",
               data_root: Path | None = None) -> list[str]:
    """Apply the merge to a real systems.json. Returns the notes.

    Never raises on a malformed file: an update must not take the grid down
    because a hand edit left a trailing comma. It reports and changes nothing.

    `root` is the installation — where `lib/` and the catalogue live, what a
    launcher path resolves against. `data_root` is where the player's files
    are, and it is where `catalog-removed.json` is read from. They are one
    directory on every box installed so far, which is why the second defaults
    to the first; but once the data has moved they are not, and reading the
    removed list from the install root would read a stale copy that says
    nothing was removed — and every system the operator took off the grid
    would come back on the next update.
    """
    try:
        live = json.loads(systems_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return [f"systems.json unreadable ({e.__class__.__name__}) — left untouched"]
    if not isinstance(live, list):
        return ["systems.json is not a list — left untouched"]

    merged, notes = merge_systems(live, packs, root,
                                  removed=load_removed(data_root or root), kind=kind)
    if not notes:
        return []
    if dry_run:
        return notes + ["(dry run — nothing written)"]

    # Atomic (backend/utils.py): a grid caught half-written is a box with no
    # interface.
    backup = systems_file.with_name(systems_file.name + ".bak-merge")
    try:
        if systems_file.is_file() and not backup.exists():
            shutil.copy2(systems_file, backup)
        atomic_write(systems_file,
                     json.dumps(merged, indent=2, ensure_ascii=False) + "\n")
    except OSError as e:
        return notes + [f"could not write systems.json ({e}) — left untouched"]
    return notes
