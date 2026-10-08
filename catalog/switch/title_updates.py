"""Updates and DLC from emu/Switch DLC & Updates, chosen before Ryujinx's first start.

Ryujinx picks them up itself (seed: `game_dirs` + `autoload_dirs`), but only in
a library scan that runs beside the launch: on its first start the game ran
in v1.0.0, and Mario Kart 8 rewrote its imported v3.0.4 save in the old format
(measured). So games/<title>/updates.json and dlc.json are written here when
absent, in Ryujinx's own format. The title ids come from the tickets' names
inside each NSP (`<rights id>.tik`, rights id = title id + key generation),
which needs no decryption.
"""
from __future__ import annotations

import json
import struct
from pathlib import Path

from backend.utils import atomic_write

UPDATE_BIT = 0x800
DLC_BASE_STEP = 0x1000
TITLE_MASK = ~0xFFF & 0xFFFFFFFFFFFFFFFF


def nsp_entries(path: Path) -> list[str]:
    """The file names in an NSP's PFS0 header, [] when it is not one."""
    try:
        with open(path, "rb") as f:
            head = f.read(16)
            if len(head) < 16 or head[:4] != b"PFS0":
                return []
            count, strings = struct.unpack_from("<II", head, 4)
            table = f.read(count * 0x18)
            names = f.read(strings)
    except OSError:
        return []
    out = []
    for i in range(count):
        at = struct.unpack_from("<I", table, i * 0x18 + 16)[0]
        out.append(names[at:names.index(b"\0", at)].decode(errors="replace"))
    return out


def classify(path: Path) -> tuple[str, int, dict | None] | None:
    """("update" | "dlc", base title, DLC entry) for one NSP, None when unclear."""
    names = nsp_entries(path)
    titles = {int(n[:16], 16) for n in names if n.endswith(".tik") and len(n) >= 36}
    if len(titles) != 1:
        return None
    title = titles.pop()
    if title & 0xFFF == UPDATE_BIT:
        return "update", title & TITLE_MASK, None
    content = [n for n in names if n.endswith(".nca") and not n.endswith(".cnmt.nca")]
    if title & 0xFFF and len(content) == 1:
        entry = {"path": "/" + content[0], "title_id": title, "is_enabled": True}
        return "dlc", (title - DLC_BASE_STEP) & TITLE_MASK, entry
    return None


def autoload_dirs(ryujinx: Path) -> list[Path]:
    """Where Ryujinx looks for updates and DLC: Config.json, set by the seed."""
    try:
        dirs = json.loads((ryujinx / "Config.json").read_text(encoding="utf-8")).get("autoload_dirs")
    except (OSError, ValueError, AttributeError):
        return []
    return [Path(d) for d in dirs or [] if isinstance(d, str)]


def write_missing(ryujinx: Path) -> list[str]:
    """updates.json / dlc.json for the titles that have none. One note per file."""
    updates: dict[int, list[str]] = {}
    dlcs: dict[int, list[dict]] = {}
    nsps = sorted(n for d in autoload_dirs(ryujinx) if d.is_dir() for n in d.rglob("*.nsp"))
    for nsp in nsps:
        found = classify(nsp)
        if found is None:
            continue
        kind, base, entry = found
        if kind == "update":
            updates.setdefault(base, []).append(str(nsp))
        else:
            dlcs.setdefault(base, []).append({"path": str(nsp), "dlc_nca_list": [entry]})
    notes = []
    for base, paths in updates.items():
        target = ryujinx / "games" / f"{base:016x}" / "updates.json"
        # Two updates for one game: which is newer needs the NCA. Ryujinx decides.
        if not target.exists() and len(paths) == 1:
            atomic_write(target, json.dumps({"selected": paths[0], "paths": paths}, indent=2))
            notes.append(f"{base:016X}: update {Path(paths[0]).name}")
    for base, entries in dlcs.items():
        target = ryujinx / "games" / f"{base:016x}" / "dlc.json"
        if not target.exists():
            atomic_write(target, json.dumps(entries, indent=2))
            notes.append(f"{base:016X}: {len(entries)} DLC")
    return notes
