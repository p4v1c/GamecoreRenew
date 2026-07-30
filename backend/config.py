"""Central configuration — all paths derived from GAMECORE_ROOT."""
import os
from pathlib import Path

DEBUG = False

# Version is read from the VERSION file at the repo root so OTA updates
# only need to change that one file, not config.py.
_VERSION_FILE = Path(__file__).parent.parent / "VERSION"
APP_VERSION = _VERSION_FILE.read_text().strip() if _VERSION_FILE.exists() else "v1.0.0"
GITHUB_REPO = "p4v1c/GamecoreRenew"
UPDATE_ASSET = "gamecore-ota.tar.gz"

GAMECORE_ROOT = Path(os.environ.get("GAMECORE_PATH", str(Path(__file__).parent.parent)))

SYSTEMS_FILE  = GAMECORE_ROOT / "config" / "systems.json"
APPS_FILE     = GAMECORE_ROOT / "config" / "apps.json"
PLAYTIME_DB   = GAMECORE_ROOT / "config" / "playtime.db"
COVERS_DIR    = GAMECORE_ROOT / "emu" / "covers"
ASSETS_DIR    = GAMECORE_ROOT / "assets"

BACKEND_PORT  = int(os.environ.get("GAMECORE_BACKEND_PORT", 8765))

THEGAMESDB_API_KEY = os.environ.get("THEGAMESDB_API_KEY", "")

# Language of the scraped text — synopses and genre names, which ScreenScraper
# localises. English by default because the interface is: a library whose
# buttons read "PLAY TIME" and whose synopses are in French is not a choice
# anyone made. Comma-separated, most preferred first, e.g. "fr,en".
#
# It is read at scrape time, not at display time: the chosen text is what lands
# in the cache. Changing it therefore only affects games scraped afterwards —
# see docs/architecture/04-backend-services.md for how to re-scrape a library.
SCRAPER_LANG = [c.strip().lower() for c
                in os.environ.get("GAMECORE_SCRAPER_LANG", "en,fr").split(",")
                if c.strip()] or ["en"]

# ScreenScraper — read straight from the environment by the vendored
# gamescrape (services/gamemedia), which is why nothing here imports them.
# They are listed for the reader and for /api/sysinfo: two credential levels are
# needed, and confusing them is the usual cause of a 403.
#
#   SCREENSCRAPER_DEV_ID / SCREENSCRAPER_DEV_PASSWORD
#       developer credentials, granted per software on the ScreenScraper forum.
#       DEV_ID is the developer's pseudonym, not the number in the devinfos URL.
#   SCREENSCRAPER_USER / SCREENSCRAPER_PASSWORD
#       a member account. It carries the daily quota and the thread count.
#
# Both are required: jeuInfos.php answers 403 without the first, and a level-0
# quota without the second. The installer writes them into the same systemd
# drop-in as THEGAMESDB_API_KEY (0600, never in git). Absent, the gamemedia
# tier is simply skipped and covers resolve exactly as they did before.


def resolve_path(raw: str) -> Path | None:
    if not raw:
        return None
    p = Path(raw)
    return p if p.is_absolute() else GAMECORE_ROOT / p
