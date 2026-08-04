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
    path = root / "config" / REMOVED_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".gamecore-tmp")
    tmp.write_text(json.dumps(sorted(ids), indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


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


def _flatpak_app_id(args: str) -> str:
    """The app id out of `run <app-id> <flags…>`, or ""."""
    parts = args.split()
    return parts[1] if len(parts) > 1 and parts[0] == "run" else ""


def launcher_is_stale(entry: dict, pack, known_app_ids: set[str], root: Path) -> str:
    """"" when the launcher is fine, otherwise why it is not."""
    path, args = entry.get("path", ""), entry.get("args", "")
    if path == "flatpak":
        app_id = _flatpak_app_id(args)
        if app_id and app_id not in known_app_ids:
            return (f"launches {app_id}, which no pack declares "
                    f"(the installer installs {pack.app_id or 'something else'})")
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


def system_entry_from_pack(pack, root: Path) -> dict:
    """A fresh systems.json entry, for an emulator the box does not have yet."""
    path, args = nominal_launcher(pack, root)
    roms = pack.data.get("roms") or {}
    entry = {
        "id": pack.id,
        "type": "emulator",
        "label": pack.data["label"],
        "platform": pack.data["platform"],
        "color": pack.data["color"],
        "iconPath": f"assets/logos/{pack.id}.png",
        "path": path,
        "args": args,
        "romsPath": roms.get("dir", f"emu/{pack.id}") + "/",
    }
    if roms.get("scanDirs"):
        entry["scanDirs"] = True
    entry["extensions"] = list(roms.get("extensions", []))
    entry["libretroSystems"] = list((pack.data.get("scraper") or {}).get("libretro", []))
    return entry


def app_entry_from_pack(pack) -> dict:
    """A fresh apps.json entry. Apps have no ROM directory and no extensions."""
    launch = pack.data["launch"]
    return {
        "id": pack.id,
        "kind": "app",
        "type": "application",
        "label": pack.data["label"],
        "platform": pack.data["platform"],
        "color": pack.data["color"],
        "iconPath": f"assets/logos/{pack.id}.png",
        "path": launch["path"],
        "args": launch.get("args", ""),
    }


def merge_systems(live: list[dict], packs: dict, root: Path,
                  add_missing: bool = True,
                  removed: set[str] | None = None,
                  kind: str = "emulator") -> tuple[list[dict], list[str]]:
    """(merged entries, human-readable notes). Pure — writes nothing.

    `removed` is what the operator took off the grid on purpose; those ids are
    never added back. `kind` picks which half of the catalogue this file holds.
    """
    removed = removed or set()
    known_app_ids = {p.app_id for p in packs.values() if p.app_id}
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

        out.append(merged)

    if add_missing:
        for pack in packs.values():
            if pack.kind != kind or pack.id in seen:
                continue
            if pack.id in removed:
                # Taken off deliberately. Not "missing" — declined.
                continue
            out.append(system_entry_from_pack(pack, root) if kind == "emulator"
                       else app_entry_from_pack(pack))
            notes.append(f"{pack.id}: added — new in this release")

    return out, notes


def merge_file(systems_file: Path, packs: dict, root: Path,
               dry_run: bool = False, kind: str = "emulator") -> list[str]:
    """Apply the merge to a real systems.json. Returns the notes.

    Never raises on a malformed file: an update must not take the grid down
    because a hand edit left a trailing comma. It reports and changes nothing.
    """
    try:
        live = json.loads(systems_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return [f"systems.json unreadable ({e.__class__.__name__}) — left untouched"]
    if not isinstance(live, list):
        return ["systems.json is not a list — left untouched"]

    merged, notes = merge_systems(live, packs, root,
                                  removed=load_removed(root), kind=kind)
    if not notes:
        return []
    if dry_run:
        return notes + ["(dry run — nothing written)"]

    # Same atomic shape the rest of the project uses: a grid caught half-written
    # is a box with no interface.
    tmp = systems_file.with_name(systems_file.name + ".gamecore-tmp")
    backup = systems_file.with_name(systems_file.name + ".bak-merge")
    try:
        if systems_file.is_file() and not backup.exists():
            shutil.copy2(systems_file, backup)
        tmp.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
        tmp.replace(systems_file)
    except OSError as e:
        tmp.unlink(missing_ok=True)
        return notes + [f"could not write systems.json ({e}) — left untouched"]
    return notes
