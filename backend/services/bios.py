"""Is the system file this emulator needs on the box, and is it the right one.

The support ticket this exists to delete: a BIOS that is missing or corrupt
produces no message a player can act on. The emulator refuses to start, or
starts on a black screen. Nothing on screen names a file, so every case costs
three round trips before anyone knows what is being talked about.

What a pack declares is in `catalog/<id>/pack.json` under `bios`; how it is
checked is here. Three verdicts per file, and they are deliberately distinct:

    absent      the path does not exist
    mismatch    it exists and its md5 is not the declared one
    ok          it exists, and either matched or carries no declared md5

`mismatch` is worth its own state rather than being folded into `absent`: they
are different phone calls. "Copy this file" and "the file you copied is not the
one" send the owner to two different places.

**Read-only, always.** The BIOS files on a box are the owner's own dumps. This
module stats them and hashes them and does nothing else — no copy, no move, no
rename, no repair. Nothing here, or anywhere else in the project, ever says
where to obtain one.

**A required file is not the same as a useful one.** `required` comes from the
pack, and the only thing that turns a line red or refuses a launch is a
REQUIRED file that is absent. Regional firmwares and per-title keys are
declared `required: false` precisely so that a perfectly working installation
does not display red — that would manufacture the tickets this screen removes.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from .catalog import load_catalog

log = logging.getLogger(__name__)

OK = "ok"
ABSENT = "absent"
MISMATCH = "mismatch"

# Worst-first, so a system's verdict is a max() over its required files.
_SEVERITY = {OK: 0, MISMATCH: 1, ABSENT: 2}

# Hashing is cheap (a PS2 boot ROM is 4 MB) but this is read from a settings
# screen that repaints, and from the sysinfo endpoint the top bar polls. Keyed
# on identity-and-mtime rather than path alone: an owner who replaces a bad
# dump must see the new verdict without restarting the backend.
_md5_cache: dict[tuple[str, int, int], str] = {}


def _md5(path: Path) -> str:
    """The file's md5, or "" if it could not be read."""
    try:
        st = path.stat()
        key = (str(path), st.st_size, st.st_mtime_ns)
        if key in _md5_cache:
            return _md5_cache[key]
        digest = hashlib.md5()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                digest.update(chunk)
        _md5_cache[key] = digest.hexdigest()
        return _md5_cache[key]
    except OSError:
        # Unreadable is not corrupt. Saying "wrong md5" about a file whose
        # permissions are simply wrong would send the owner to replace a good
        # dump.
        log.warning("bios: cannot read %s", path, exc_info=True)
        return ""


def _entry(spec: dict, directory: Path, *, hash_files: bool) -> dict:
    name = spec["file"]
    path = directory / name
    expected = spec.get("md5", "")
    row = {
        "file": name,
        "path": str(path),
        "required": spec["required"],
        "note": spec["note"],
        "expected_md5": expected,
        "actual_md5": "",
        "verified": False,
        "status": ABSENT,
    }
    if not path.is_file():
        return row
    row["status"] = OK
    if expected and hash_files:
        actual = _md5(path)
        if not actual:
            return row                       # unreadable: present, unverified
        row["verified"] = True
        if actual != expected:
            row["status"] = MISMATCH
            row["actual_md5"] = actual
    return row


def _any_file_entry(spec: dict, directory: Path) -> dict:
    """The verdict for an emulator that scans its BIOS directory.

    DuckStation takes whatever image it recognises, so the pack legitimately
    names none and the only honest answer is whether the directory holds
    anything. Top level only, matching what `[BIOS] SearchDirectory` reads: a
    dump filed away in a subfolder is not a dump DuckStation will find, and
    reporting it as installed would be worse than reporting nothing.
    """
    try:
        found = any(p.is_file() for p in directory.iterdir())
    except OSError:
        found = False
    return {
        "file": "",
        "path": str(directory),
        "required": spec["required"],
        "note": spec["note"],
        "expected_md5": "",
        "actual_md5": "",
        "verified": False,
        "any_file": True,
        "status": OK if found else ABSENT,
    }


def check_pack(pack, home: Path | None = None, *, hash_files: bool = True) -> dict | None:
    """One system's BIOS report, or None if the pack declares no `bios`.

    `hash_files=False` answers the only question a launch asks — is the
    required file there — without reading a single byte. A launch must not wait
    on I/O it does not need.
    """
    bios = pack.data.get("bios")
    if not bios:
        return None
    home = home or Path.home()
    directory = pack.expand(bios["dir"], home)

    files = [_entry(spec, directory, hash_files=hash_files)
             for spec in bios.get("files", [])]
    if any_spec := bios.get("anyFile"):
        files.append(_any_file_entry(any_spec, directory))

    required = [f for f in files if f["required"]]
    status = max((f["status"] for f in required), key=_SEVERITY.get, default=OK)
    return {
        "id": pack.id,
        "label": pack.data["label"],
        "platform": pack.data["platform"],
        "color": pack.data["color"],
        "dir": str(directory),
        "status": status,
        "files": files,
    }


def report(home: Path | None = None, *, packs: dict | None = None,
           hash_files: bool = True) -> list[dict]:
    """Every system that declares a `bios` block, in catalogue order."""
    packs = load_catalog() if packs is None else packs
    ordered = sorted(packs.values(), key=lambda p: (p.data.get("order", 10_000), p.id))
    out = []
    for pack in ordered:
        entry = check_pack(pack, home, hash_files=hash_files)
        if entry is not None:
            out.append(entry)
    return out


def summary(home: Path | None = None, *, packs: dict | None = None) -> dict:
    """One glance, for a diagnostic dump: which systems, and what state.

    Hashes, unlike the launch gate. A diagnostic that cannot see a corrupt file
    is the wrong diagnostic — "everything is fine" is the answer that sent the
    ticket round again. It is affordable because `_md5` caches on identity and
    mtime, so the second reader of the same unchanged file pays a dict lookup.

    Never raises. This rides on `/api/sysinfo`, which the top bar polls the
    whole time the box is on: a home screen that cannot draw its own header
    looks like a box that did not boot.
    """
    try:
        rows = report(home, packs=packs)
        return {"ok": all(r["status"] == OK for r in rows),
                "systems": {r["id"]: r["status"] for r in rows}}
    except Exception:
        log.exception("bios: summary failed")
        return {"ok": None, "systems": {}}


def missing_required(system_id: str, home: Path | None = None, *,
                     packs: dict | None = None) -> list[dict]:
    """The required files this system has not got. Empty means launch.

    Only ABSENT counts, never MISMATCH. An owner running a regional dump whose
    md5 is not the one the pack records still has a working emulator, and a
    launch refused on a hash would be this screen inventing a fault. The BIOS
    page says so in its own words; the launch gate answers the narrower
    question of whether the file is there at all.

    Never raises. A check that cannot run is a game that starts, not a game
    that does not.
    """
    try:
        packs = load_catalog() if packs is None else packs
        pack = packs.get(system_id)
        if pack is None:
            return []
        entry = check_pack(pack, home, hash_files=False)
        if entry is None:
            return []
        return [f for f in entry["files"]
                if f["required"] and f["status"] == ABSENT]
    except Exception:
        log.exception("bios: check for %r failed — launching anyway", system_id)
        return []


def launch_blocker(system_id: str, home: Path | None = None, *,
                   packs: dict | None = None) -> str:
    """One sentence to show instead of starting the emulator, or "".

    The sentence lives here rather than in the router because it is the whole
    value of the check: a launch refused without naming the file is the black
    screen again, with an extra step. Same philosophy as the generators' `Skip`
    — say what did not happen and why, in words the player can act on.

    Never raises, for the same reason `missing_required` does not: a check that
    cannot run must cost a game that starts, never a game that does not.
    """
    try:
        missing = missing_required(system_id, home, packs=packs)
        if not missing:
            return ""
        packs = load_catalog() if packs is None else packs
        pack = packs.get(system_id)
        label = pack.data["label"] if pack else system_id
        parts = []
        for f in missing:
            if f.get("any_file"):
                parts.append(f"a BIOS image is missing — copy one into {f['path']}")
            else:
                parts.append(f"{f['file']} is missing — copy it to {f['path']}")
        return f"{label} cannot start: " + "; ".join(parts)
    except Exception:
        log.exception("bios: refusal message for %r failed", system_id)
        return ""
