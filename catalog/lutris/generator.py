"""The PC system's library hook: the games installed in Lutris, as stubs.

No controller strategy: Wine reads the pads through SDL itself. The one hook
here is `sync_library`, called by `backend/services/pack_library.py` before
each listing of this system, so a game installed or removed in Lutris shows
up (or goes) the next time the library opens. The rules live in
`files/lutris_library.py`.
"""
from __future__ import annotations

import importlib.util
import json
import logging
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
_lock = threading.Lock()
log = logging.getLogger(__name__)


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"gamecore_lutris_{name}",
                                                  HERE / "files" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


paths = _load("lutris_paths")
library = _load("lutris_library")


def _app_ids() -> list[str]:
    return json.loads((HERE / "pack.json").read_text(encoding="utf-8"))["install"]["appIds"]


def lutris_app_id(home: Path) -> str | None:
    """The first declared Flatpak whose Lutris library exists on this box."""
    return next((a for a in _app_ids() if paths.db_path(home, a).is_file()), None)


def sync_library(*, roms_dir: Path, covers_dir: Path, home: Path) -> dict | None:
    """Make `roms_dir` hold one stub per installed Lutris game.

    Returns the change report, or None when Lutris's library could not be
    read; nothing is removed then.
    """
    app_id = lutris_app_id(home)
    if app_id is None:
        return None
    games = library.installed_games(paths.db_path(home, app_id))
    if games is None:
        return None
    with _lock:
        report = library.sync(roms_dir, games, covers_dir=covers_dir,
                              coverart_dir=paths.coverart_dir(home, app_id))
    if any(report.values()):
        log.info("lutris: library synced — %s",
                 "; ".join(f"{k}: {len(v)}" for k, v in report.items() if v))
    return report
