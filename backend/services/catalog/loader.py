"""Load the pack catalogue: shipped packs, then local ones on top.

Two locations, merged, local wins:

    catalog/<id>/              shipped with the project, overwritten by every OTA
    config/catalog.d/<id>/     the operator's own, excluded from the OTA rsync

An id present on both sides is a **replacement**, not a field-by-field merge:
"the local pack wins entirely" is the rule that can be reasoned about at 2 am
with a box that will not boot. The origin of every pack is logged at load time,
so `journalctl -u gamecore-backend | grep catalog` answers "which pack.json is
this box actually running" without guessing.

Code vs data — the security rule
--------------------------------
A pack shipped in `catalog/` may carry `generator.py`: it is project code, it
goes through review and CI.

A pack dropped in `config/catalog.d/` is **data only** by default. Five blocks
are ignored, with a warning at every load: `generator.py`, `postInstall`,
`services`, `sources` and `packages`. They execute code or change the system
outside the pack directory — without this rule, "drop a directory" becomes
arbitrary code execution, and the phase-5 install CLI turns it into something
triggerable from the UI.

The operator can lift it on their own machine with
`GAMECORE_TRUST_LOCAL_PACKS=1`, which is logged on every load rather than once.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from ...config import GAMECORE_ROOT
from .schema import load_schema, validate

log = logging.getLogger(__name__)

CATALOG_DIR = GAMECORE_ROOT / "catalog"
LOCAL_DIR = GAMECORE_ROOT / "config" / "catalog.d"
SCHEMA_FILE = CATALOG_DIR / "_schema" / "pack.schema.json"

# Blocks a local pack may not use unless the operator opts in explicitly.
PRIVILEGED_BLOCKS = ("postInstall", "services", "sources", "packages")
PRIVILEGED_FILES = ("generator.py",)

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


@dataclass
class Pack:
    id: str
    data: dict
    path: Path
    origin: str                      # "shipped" | "local"
    stripped: list[str] = field(default_factory=list)

    # ── implicit-by-presence content ──────────────────────────────────────
    @property
    def seed_dir(self) -> Path | None:
        d = self.path / "seed"
        return d if d.is_dir() else None

    @property
    def logo(self) -> Path | None:
        for name in ("logo.png", "logo.svg"):
            p = self.path / name
            if p.is_file():
                return p
        return None

    @property
    def generator(self) -> Path | None:
        if self.origin == "local" and not _trust_local():
            return None
        p = self.path / "generator.py"
        return p if p.is_file() else None

    @property
    def tests_dir(self) -> Path | None:
        d = self.path / "tests"
        return d if d.is_dir() else None

    # ── convenience ───────────────────────────────────────────────────────
    @property
    def kind(self) -> str:
        return self.data.get("kind", "emulator")

    @property
    def app_id(self) -> str:
        install = self.data.get("install") or {}
        return install.get("appId", "") if install.get("provider") == "flatpak" else ""

    def launcher(self, *, prefer_existing: bool = False, root: Path | None = None
                 ) -> tuple[str, str]:
        """(path, args). `prefer_existing` resolves `preferIfPresent`, which is
        what absorbs the REWRITE pass of flatpakify-systems.sh."""
        launch = self.data["launch"]
        prefer = launch.get("preferIfPresent")
        if prefer_existing and prefer:
            base = root or GAMECORE_ROOT
            candidate = Path(prefer["path"])
            resolved = candidate if candidate.is_absolute() else base / candidate
            if resolved.exists():
                return prefer["path"], prefer.get("args", "")
        return launch["path"], launch.get("args", "")


def _trust_local() -> bool:
    return os.environ.get("GAMECORE_TRUST_LOCAL_PACKS", "") == "1"


def _strip_privileged(data: dict, pack_id: str) -> list[str]:
    """Remove the code-executing blocks from a local pack. Returns what went."""
    removed = []
    for block in PRIVILEGED_BLOCKS:
        if block in data:
            data.pop(block)
            removed.append(block)
    return removed


def _read_pack(directory: Path, origin: str, schema: dict) -> Pack | None:
    manifest = directory / "pack.json"
    if not manifest.is_file():
        log.warning("catalog: %s has no pack.json — ignored", directory)
        return None
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        log.error("catalog: %s unreadable (%s) — ignored", manifest, e)
        return None

    if data.get("id") != directory.name:
        log.error("catalog: %s declares id=%r but lives in %r — ignored",
                  manifest, data.get("id"), directory.name)
        return None

    problems = validate(data, schema, name=f"{origin}:{directory.name}")
    if problems:
        for p in problems[:5]:
            log.error("catalog: %s", p)
        log.error("catalog: %s failed schema validation (%d problem(s)) — ignored",
                  manifest, len(problems))
        return None

    stripped: list[str] = []
    if origin == "local":
        if _trust_local():
            # Deliberately logged on EVERY load, not once: an operator who
            # turned this on months ago must keep being told.
            log.warning("catalog: GAMECORE_TRUST_LOCAL_PACKS=1 — local pack %r "
                        "may run code (generator.py, postInstall, services, "
                        "sources, packages)", directory.name)
        else:
            stripped = _strip_privileged(data, directory.name)
            if (directory / "generator.py").is_file():
                stripped.append("generator.py")
            if stripped:
                log.warning("catalog: local pack %r is data-only — ignored %s "
                            "(set GAMECORE_TRUST_LOCAL_PACKS=1 to allow)",
                            directory.name, ", ".join(sorted(stripped)))

    return Pack(id=data["id"], data=data, path=directory, origin=origin,
                stripped=stripped)


def _scan(base: Path, origin: str, schema: dict) -> dict[str, Pack]:
    out: dict[str, Pack] = {}
    if not base.is_dir():
        return out
    for directory in sorted(base.iterdir()):
        # `_schema` and anything else underscore-prefixed is not a pack; the
        # prefix is what keeps it out of the pack glob.
        if not directory.is_dir() or directory.name.startswith((".", "_")):
            continue
        if not _ID_RE.match(directory.name):
            log.warning("catalog: %r is not a valid pack id — ignored", directory.name)
            continue
        pack = _read_pack(directory, origin, schema)
        if pack is not None:
            out[pack.id] = pack
    return out


def load_catalog(catalog_dir: Path | None = None,
                 local_dir: Path | None = None) -> dict[str, Pack]:
    """Every pack, local overriding shipped, keyed by id."""
    shipped_dir = catalog_dir or CATALOG_DIR
    # The schema ships INSIDE catalog/, so it is read from the directory being
    # loaded rather than from a module constant. Otherwise a caller pointing at
    # another tree — the test suite, which aims GAMECORE_PATH at a throwaway
    # root — would validate it against a schema that is not there.
    schema = load_schema(shipped_dir / "_schema" / "pack.schema.json")
    shipped = _scan(shipped_dir, "shipped", schema)
    local = _scan(local_dir or LOCAL_DIR, "local", schema)

    merged = dict(shipped)
    for pid, pack in local.items():
        if pid in shipped:
            log.info("catalog: %r overridden by the local pack in %s", pid, pack.path)
        merged[pid] = pack

    log.info("catalog: %d pack(s) — %d shipped, %d local",
             len(merged), len(shipped), len(local))
    return merged
