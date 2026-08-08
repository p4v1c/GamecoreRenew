"""Shared pytest setup for the backend test suite.

The one thing that must happen before anything else: point GAMECORE_PATH at a
throwaway directory. `backend.config` reads it at import time and every other
path — covers cache, config/, playtime.db — is derived from it, so whichever
test module pytest imports first would otherwise bind the suite to the real
checkout (or worse, to whatever GAMECORE_PATH the shell already exported) and
the cover tests would scribble their .miss markers into it.

conftest.py is imported before any test module, which makes this the only place
the override is guaranteed to land in time. GAMECORE_TEST_ROOT is the handshake:
test_covers.py builds its fake game tree there instead of minting its own root.
"""
import os
import tempfile
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

_ROOT = Path(tempfile.mkdtemp(prefix="gamecore-test-")) / "fake_root"
_ROOT.mkdir(parents=True, exist_ok=True)

# Set, never defaulted: inheriting a GAMECORE_PATH from the environment would
# aim the suite at a real installation.
os.environ["GAMECORE_PATH"] = str(_ROOT)
os.environ["GAMECORE_TEST_ROOT"] = str(_ROOT)

# Same rule for the ScreenScraper account. gamescrape reads the four variables
# below, then falls back to ~/.config/gamescrape/credentials — a developer's own
# file, which would make the suite behave differently on their machine than in
# CI. It matters more than it looks: with credentials present, the gamemedia
# tier is enabled, cannot reach the network from a test, and correctly reports
# "unreachable" — which suppresses the .miss marker test_covers asserts on. The
# suite's baseline is an unconfigured box; a test that wants the tier enables it
# itself.
for _var in ("SCREENSCRAPER_DEV_ID", "SCREENSCRAPER_DEV_PASSWORD",
             "SCREENSCRAPER_USER", "SCREENSCRAPER_PASSWORD"):
    os.environ.pop(_var, None)
os.environ["XDG_CONFIG_HOME"] = str(_ROOT / "config-home")

# HOME, for the same reason and with a sharper edge. `configgen.HOME` is
# `Path.home()` evaluated at IMPORT time, and it is the root of every emulator
# config path the generators write to: ~/.var/app/<appId>/config/…
#
# Nothing calls a generator directly under test — the characterisation harness
# patches `configgen.HOME` at a fake tree. But `TestClient(main.app)` runs the
# app's lifespan, and the lifespan starts `gamepad_monitor.run()`, which scans
# the REAL /dev/input, finds whatever pad the developer has plugged in, and
# profiles it against the REAL home. Measured on this machine: a test-suite run
# rewrote Player 1 of ~/.var/app/net.rpcs3.RPCS3/…/Default.yml and emptied
# Ryujinx's input_config. The developer's own console, edited by pytest.
#
# The seam is one line because the damage is one line. Set before any import,
# like GAMECORE_PATH above, since Path.home() is read at module scope.
os.environ["HOME"] = str(_ROOT / "home")
(_ROOT / "home").mkdir(parents=True, exist_ok=True)

# The catalogue is SHIPPED CODE, not box state: catalog/<id>/pack.json is the
# single source scraper.py, gamemedia.py and the installers read. The throwaway
# root above exists to keep writable data (covers, playtime.db, config/) out of
# the checkout — it must not also hide the catalogue, or every consumer that
# builds its tables at import time would come up empty under test and the
# suite would be green about maps that are simply absent.
_REPO = Path(__file__).resolve().parents[2]
(_ROOT / "catalog").symlink_to(_REPO / "catalog")
