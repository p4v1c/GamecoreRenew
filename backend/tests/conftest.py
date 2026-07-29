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
