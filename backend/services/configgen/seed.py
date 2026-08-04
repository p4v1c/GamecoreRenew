"""Deploy a pack's `seed/` into the emulator's real config directory.

The Python side of what `install/install-emu-configs.sh` does, so the hot
install path of phase 5 and the shell installer share one implementation.

Two things this owns:

  · **Token substitution.** A seed carries `@HOME@` and `@GAMECORE_PATH@`, not
    absolute paths. The tree used to be harvested on a box where HOME was
    /home/pavic, and two independent `sed` passes chased that literal — one in
    arch.sh, one in install-emu-configs.sh. A personal username shipped in a
    public repository for as long as that lasted.

  · **The backup decision, made against the exact bytes about to land.** That
    is what makes a re-run safe:

        target absent              no backup, we are introducing the file
        target == what we install  no backup, it is already our own copy.
                                   Backing it up here would record GameCore's
                                   config as if it were the user's, and
                                   uninstall would then "restore" our file
                                   instead of deleting it.
        target differs, no backup  back it up, it is theirs
        a backup already exists    never touch it, it holds the real original
"""
from __future__ import annotations

import filecmp
import logging
import shutil
from pathlib import Path

log = logging.getLogger(__name__)

BACKUP_SUFFIX = ".bak-preinstall"
STAGED_SUFFIX = ".gamecore-staged"

# Binary formats are copied verbatim: substituting tokens in a sqlite database
# would corrupt it, and none of them carry a path anyway.
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".sqlite3", ".db", ".bin", ".dat"}


def substitute(text: str, *, home: Path, gamecore_path: Path) -> str:
    return (text.replace("@HOME@", str(home))
                .replace("@GAMECORE_PATH@", str(gamecore_path)))


def deploy(seed_dir: Path, dest: Path, *, home: Path, gamecore_path: Path,
           dry_run: bool = False) -> list[str]:
    """Copy seed_dir/** into dest, substituting tokens. Returns what changed."""
    if not seed_dir.is_dir():
        return []
    changed: list[str] = []
    dest.mkdir(parents=True, exist_ok=True)

    # A run interrupted mid-copy leaves *.gamecore-staged behind; they would be
    # mistaken for emulator config files by anything that scans the directory.
    for stale in dest.rglob(f"*{STAGED_SUFFIX}"):
        stale.unlink(missing_ok=True)

    for src in sorted(seed_dir.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(seed_dir)
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)

        if src.suffix.lower() in BINARY_SUFFIXES:
            payload = src.read_bytes()
        else:
            try:
                payload = substitute(src.read_text(encoding="utf-8"),
                                     home=home, gamecore_path=gamecore_path
                                     ).encode("utf-8")
            except UnicodeDecodeError:
                payload = src.read_bytes()

        if target.is_file() and target.read_bytes() == payload:
            continue                      # already our own copy — nothing to do
        if dry_run:
            changed.append(str(rel))
            continue

        staged = target.with_name(target.name + STAGED_SUFFIX)
        staged.write_bytes(payload)
        backup = target.with_name(target.name + BACKUP_SUFFIX)
        if target.is_file() and not backup.exists() and not filecmp.cmp(staged, target, shallow=False):
            shutil.copy2(target, backup)
        staged.replace(target)
        changed.append(str(rel))

    return changed
