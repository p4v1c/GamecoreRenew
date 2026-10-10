"""What a pack adds to its system's library listing.

Two things, both declared by the pack and read here at listing time:

- `sync_library(roms_dir, covers_dir, home)` in generator.py, for a system
  whose games live in another program's library (Lutris). It brings the ROM
  folder in line with that library just before the folder is scanned, so the
  rest of GameCore (covers, playtime, favourites, themes) sees ordinary files.
- `roms.showExtension: false`, for entries whose extension means nothing to
  the player: the listing sends an empty `ext` and the views print nothing.

The pack table is read once, like local_media's: the catalogue is shipped
code, and a listing runs every time a grid opens.
"""
import logging
from pathlib import Path

from . import configgen
from .paths import covers_dir

log = logging.getLogger(__name__)

_packs: dict | None = None


def _pack(system_id: str):
    global _packs
    if _packs is None:
        try:
            from .catalog import load_catalog
            _packs = load_catalog()
        except Exception:
            log.warning("pack_library: catalogue unreadable — listings unchanged",
                        exc_info=True)
            _packs = {}
    return _packs.get(system_id.lower())


def sync(system_id: str, roms_path: Path) -> None:
    """Run the pack's `sync_library` hook, if it has one. Never raises."""
    pack = _pack(system_id)
    module = configgen.load_generator(pack) if pack is not None else None
    hook = getattr(module, "sync_library", None)
    if hook is None:
        return
    try:
        # Keyed like cover_pipeline's cache: emu/covers/<system id>/<stem>.
        hook(roms_dir=roms_path, covers_dir=covers_dir() / system_id.lower(),
             home=configgen.HOME)
    except Exception:
        # The stubs already on disk are still listed; only new changes wait.
        log.exception("pack_library: %s sync_library failed", system_id)


def shows_extension(system_id: str) -> bool:
    pack = _pack(system_id)
    if pack is None:
        return True
    return (pack.data.get("roms") or {}).get("showExtension", True) is not False
