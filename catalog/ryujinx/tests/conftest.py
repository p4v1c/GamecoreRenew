"""A Ryujinx test states which flatpak world it runs in — it never inherits ours.

`Pad.guid_for` asks `flatpak_location()` whether the emulator can be reached,
and refuses to answer with the host's SDL2 GUID when it cannot: the host and
Ryujinx's bundled SDL2 disagree on the bus byte (0x05 against 0x03 for a
Bluetooth DualShock 4), and Ryujinx resolves ids with `IndexOf`, so a wrong id
means the slot is disposed in silence.

That call shells out to `flatpak info`. Most tests here patch only
`sdl2_probe`, so before this fixture existed they passed on a workstation with
Ryujinx installed and failed on a clean CI runner — 36 red tests on a commit
that was green locally. The answer is not to install Ryujinx on the runner:
a test whose result depends on what the machine happens to have installed is
not testing the code. So the default here is "the flatpak is reachable", and
the two tests that exercise the unreachable case override it explicitly.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.services.configgen import controllers as cc  # noqa: E402


@pytest.fixture(autouse=True)
def reachable_flatpak(monkeypatch):
    monkeypatch.setattr(cc, "flatpak_location", lambda app_id: "/stub/flatpak")
    # The lookup memoises per process, so a real answer captured by an earlier
    # test would outlive its monkeypatch and leak into the next one.
    monkeypatch.setattr(cc, "_flatpak_loc_cache", {}, raising=False)
