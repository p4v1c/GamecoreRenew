"""Central configuration — all paths derived from GAMECORE_ROOT."""
import os
from pathlib import Path

DEBUG = False  # ← flip to True on dev

APP_VERSION = "v1.0.0"
GITHUB_REPO = "p4v1c/GamecoreRenew"
UPDATE_ASSET = "gamecore-ota.tar.gz"

GAMECORE_ROOT = Path(os.environ.get("GAMECORE_PATH", str(Path(__file__).parent.parent)))

SYSTEMS_FILE  = GAMECORE_ROOT / "config" / "systems.json"
APPS_FILE     = GAMECORE_ROOT / "config" / "apps.json"
PLAYTIME_DB   = GAMECORE_ROOT / "config" / "playtime.db"
CTRL_MAP_FILE = GAMECORE_ROOT / "config" / "controller_mappings.json"
COVERS_DIR    = GAMECORE_ROOT / "emu" / "covers"
ASSETS_DIR    = GAMECORE_ROOT / "assets"
EMU_DIR       = GAMECORE_ROOT / "emu"

BACKEND_PORT  = int(os.environ.get("GAMECORE_BACKEND_PORT", 8765))
ROM_WEB_PORT  = int(os.environ.get("GAMECORE_WEB_PORT", 8080))


def resolve_path(raw: str) -> Path | None:
    if not raw:
        return None
    p = Path(raw)
    return p if p.is_absolute() else GAMECORE_ROOT / p
