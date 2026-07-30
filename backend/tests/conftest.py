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
