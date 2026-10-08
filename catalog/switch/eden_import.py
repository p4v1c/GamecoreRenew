"""Install-time half of the Eden import: keys, firmware, then the primary's saves.

Run by steps/import-eden.sh after `gamecore-emu install switch`, before the
first launch: the BIOS gate refuses a Switch launch without prod.keys, so the
keys cannot wait for `prepare_launch`. Nothing Ryujinx already has is replaced.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import eden_saves
import title_updates

KEY_FILES = ("prod.keys", "title.keys")
FIRMWARE = Path("bis/system/Contents/registered")
EDEN_FIRMWARE = Path("nand/system/Contents/registered")


def import_system_files(ryujinx: Path, eden_data: Path) -> list[str]:
    """Eden's keys and firmware where Ryujinx has none. One line per decision."""
    notes = []
    for name in KEY_FILES:
        src, dst = eden_data / "keys" / name, ryujinx / "system" / name
        if src.is_file() and not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            notes.append(f"{name}: copied from Eden")
    src, dst = eden_data / EDEN_FIRMWARE, ryujinx / FIRMWARE
    if dst.is_dir() and any(dst.iterdir()):
        notes.append("firmware: Ryujinx has its own, Eden's left alone")
    elif src.is_dir() and any(src.iterdir()):
        # Same layout (<id>.nca/00); staged so a cut copy is never "installed".
        staging = dst.with_name(dst.name + ".gamecore-tmp")
        shutil.rmtree(staging, ignore_errors=True)
        shutil.copytree(src, staging)
        if dst.is_dir():
            dst.rmdir()
        staging.rename(dst)
        notes.append(f"firmware: {len(list(dst.iterdir()))} files copied from Eden")
    return notes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--home", type=Path, required=True)
    ap.add_argument("--gamecore-path", type=Path, required=True)
    ap.add_argument("--gamecore-data", type=Path, required=True)
    args = ap.parse_args(argv)
    from backend.services import configgen, paths
    from backend.services.catalog import load_catalog

    paths.use_roots(args.gamecore_path, args.gamecore_data)
    packs = load_catalog(args.gamecore_path / "catalog", args.gamecore_data / "config" / "catalog.d")
    ryujinx = configgen.resolve_config_dir(packs["switch"], args.home)
    eden_data = args.home / ".var/app" / eden_saves.EDEN_APP_ID / "data/eden"
    if ryujinx is None or not eden_data.is_dir():
        print("no Eden data or no Ryujinx: nothing to copy")
        return 0
    try:
        notes = import_system_files(ryujinx, eden_data) + title_updates.write_missing(ryujinx)
        source = eden_saves.eden_source(ryujinx, eden_data, paths.profile_saves_dir())
        notes += eden_saves.import_saves(ryujinx, source, eden_data)
    except eden_saves.ImportRefused as e:
        notes = [f"refused: {e}"]
    eden_saves.log_notes(notes, paths.logs_dir() / "packs" / "switch")
    print("\n".join(notes) or "nothing to copy")
    return 1 if notes and notes[-1].startswith("refused") else 0


if __name__ == "__main__":
    sys.exit(main())
