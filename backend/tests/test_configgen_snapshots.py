"""Snapshot capture/restore — the emulators whose bindings cannot be synthesised.

Shared by azahar, mgba, Cemu and gopher64/RMG, so the tests live with the
mechanism rather than with any one pack. Moved out of
backend/tests/test_controller_profiles.py in phase 4, assertions unchanged.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.services.configgen import snapshots               # noqa: E402


def _load(pack_id):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        f"gen_{pack_id}", ROOT / "catalog" / pack_id / "generator.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


gens = {p: _load(p) for p in ("azahar", "mgba", "cemu", "gopher64")}


def test_a_snapshot_of_the_wrong_controller_is_refused(tmp_path):
    """cemu/045e_02fd.snap and cemu/054c_09cc.snap on the box are
    byte-identical, both the DualShock 4's config: "Scan mapping" was pressed
    with the Xbox pad connected while the file still held the DS4."""
    xml = tmp_path / "controller0.xml"
    xml.write_text("<emulated_controller>\n"
                   "<uuid>0_05009b514c050000cc09000000810000</uuid>\n"
                   "</emulated_controller>\n")
    snaps = tmp_path / "snaps"
    cemu = gens["cemu"]

    with pytest.raises(snapshots.Refused):
        snapshots.capture(snaps, "cemu", xml, cemu.extract, "045e", "02fd")

    assert snapshots.capture(snaps, "cemu", xml, cemu.extract,
                             "054c", "09cc") == "cemu"

def test_mgba_captures_the_section_that_binds_buttons(tmp_path, monkeypatch):
    """The old extractor took [gba.input-profile.<GUID>], which holds tilt and
    gyro axes and not one button — 180 bytes of gyroSensitivity, saved and
    restored with a success message, while nothing moved."""
    ini = ("[gba.input.SDLB]\n"
           "keyA=0\nkeyB=1\nkeyL=9\nkeyR=10\n"
           "device0=05008fe54c050000cc09000000006800\n\n"
           "[gba.input-profile.05008fe54c050000cc09000000006800]\n"
           "gyroSensitivity=2,2e+09\n\n"
           "[ports.qt]\nsomething=1\n")

    block = gens["mgba"].extract(ini)
    assert "keyA=0" in block and "keyL=9" in block, "the buttons must be in there"
    assert "gyroSensitivity" in block, "and the motion axes alongside"
    assert gens["mgba"].replace(ini, block) == ini, "round-trip must not disturb the file"
    assert "something=1" in gens["mgba"].replace(ini, block.replace("keyA=0", "keyA=2"))



# ── two slots must never claim one pad ───────────────────────────────────────
# Ryujinx resolves every slot through _gamepadsIds.IndexOf(id), so a duplicate
# id is not inert: both slots resolve to the one physical pad and the game sees
# two controllers connected. Found on the reference box, where a DualShock 4
# had been profiled into slot 2 in one session and slot 1 in a later one.

# The real values that box reports, so the test breaks if the derivation does.
DS4_SDL_GUID = "05008fe54c050000cc09000000006800"
DS4_RYU_ID   = "0-00000005-054c-0000-cc09-000000006800"

def test_azahar_follows_the_active_profile(tmp_path):
    """Qt stores the selected index 0-based in `profile=` and writes the array
    1-based, so `profiles\\1\\` is only right while profile=0."""
    one = "[Controls]\nprofile=0\nprofiles\\1\\button_a=\"button:0\"\n"
    two = "[Controls]\nprofile=1\nprofiles\\2\\button_a=\"button:0\"\n"
    assert gens["azahar"]._az_prefix(one) == "profiles\\1\\"
    assert gens["azahar"]._az_prefix(two) == "profiles\\2\\"
    assert gens["azahar"].extract(two).strip() == 'profiles\\2\\button_a="button:0"'


