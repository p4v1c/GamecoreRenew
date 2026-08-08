"""The suite must not be able to write the developer's own emulator configs.

Measured, not hypothetical: a `pytest` run rewrote Player 1 of this machine's
RPCS3 `Default.yml` and emptied Ryujinx's `input_config`. `TestClient(main.app)`
runs the app lifespan, the lifespan starts `gamepad_monitor.run()`, and the
monitor scans the REAL `/dev/input`, finds whatever pad the developer left
plugged in, and profiles it against `configgen.HOME` — `Path.home()`, read at
import time. `conftest.py` now points `HOME` at the throwaway root before any
import; nothing guarded that it stays pointed there.

AUDIT pass 6 asked this exact question and cleared it. Its evidence was a run
under a sentinel `HOME` that came back empty — but the write only happens when a
pad is connected, and none was: an experiment that could not fail whatever the
code did. Neither test below depends on what is plugged in.
"""
from __future__ import annotations

import os
import pwd
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.services import configgen  # noqa: E402


def test_the_home_the_generators_write_to_is_not_the_developers():
    """`pwd`, not `$HOME`: the environment variable is the thing under test, so
    reading it back would only prove conftest agrees with itself."""
    real = Path(pwd.getpwuid(os.getuid()).pw_dir).resolve()
    home = configgen.HOME.resolve()

    assert home != real, (
        f"configgen.HOME is the real account home ({real}). Every emulator "
        f"config this suite touches is the box's own.")
    assert real not in home.parents, (
        f"configgen.HOME ({home}) sits inside the real account home ({real}).")


def test_every_profilable_pack_writes_below_that_home():
    """What makes the single line in conftest sufficient rather than lucky.

    `HOME` is the root every generator's target is built from, so redirecting it
    redirects all of them at once. A pack that resolved its config dir some
    other way would be a second door, and this is the test that would find it.
    """
    packs = configgen.profilable_packs(configgen.load_catalog())
    assert packs, "no pack profiles controllers — the loop below would assert nothing"

    home = configgen.HOME.resolve()
    for pack in packs:
        opts = configgen.generator_opts(pack, configgen.HOME, configgen.SNAP_DIR)
        assert opts is not None, f"{pack.id}: no config dir resolved"
        target = opts["target"].resolve()
        assert home in target.parents, (
            f"{pack.id} writes to {target}, outside the throwaway home {home}")
