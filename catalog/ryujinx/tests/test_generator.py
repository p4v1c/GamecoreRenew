"""Switch — the GUID must be the exact one Ryujinx's own SDL2 computes.

Moved out of backend/tests/test_controller_profiles.py in phase 4: a pack's
tests arrive with the pack. The assertions are unchanged — each still encodes
the failure that taught us the rule.
"""
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from backend.services.configgen import controllers as cc        # noqa: E402
from backend.services.configgen.controllers import Pad          # noqa: E402
from backend.services.configgen.helpers.base import Skip        # noqa: E402


def _load(pack_id):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        f"gen_{pack_id}", ROOT / "catalog" / pack_id / "generator.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


gen = _load("ryujinx")

_CFG = [None]
DS4_SDL_GUID = "05008fe54c050000cc09000000006800"
DS4_RYU_ID   = "0-00000005-054c-0000-cc09-000000006800"


def _ryujinx(i, dup, vendor, product, name):
    """The pre-phase-4 call shape, so the assertions below are untouched."""
    return gen.generate(i, Pad(vendor, product, name, dup),
                        {"target": _CFG[0], "app_id": "io.github.ryubing.Ryujinx"})


def test_ryujinx_leaves_the_slot_alone_when_sdl_says_nothing(tmp_path, monkeypatch):
    cfg = tmp_path / "Config.json"
    cfg.write_text(json.dumps({"input_config": [
        {"player_index": "Player1", "backend": "GamepadSDL2",
         "id": "0-00000003-054c-0000-cc09-000000006800", "name": "PS4 Controller (0)"}]}))
    _CFG[0] = cfg
    monkeypatch.setattr(cc, "sdl2_probe", lambda v, p, lib="": {})

    before = cfg.read_text()
    msg = _ryujinx(2, 0, "045e", "02fd", "Xbox One Controller")

    assert isinstance(msg, Skip), "a give-up has to be reported, not swallowed"
    assert cfg.read_text() == before, "an invented id is worse than an untouched slot"
    # The wording belongs to THIS branch — SDL was asked and had no GUID. The
    # test below exists because it used to be said for the other branch too.
    assert "SDL2 would not report a GUID" in str(msg)


def test_ryujinx_does_not_blame_sdl_when_the_probe_never_ran(tmp_path, monkeypatch):
    """The reference box's actual failure, and the sentence it produced.

    `sdl2_probe` answered `{}` for two unrelated facts — "SDL ran, and this pad
    is not one of its joysticks" and "the probe subprocess never ran" — so the
    give-up said *SDL2 would not report a GUID* for a probe SDL was never
    asked. Three journal lines over several days therefore read as a permanent
    SDL problem, and the diagnosis went to gamecontrollerdb and to /dev/input
    permissions. Neither was involved: measured minutes later, that same SDL2
    returned the GUID ten times out of ten in 0.85 s, and the real fault was
    transient, at the instant a Bluetooth pad connected.

    The refusal itself is correct and stays — only the sentence changes.
    """
    cfg = tmp_path / "Config.json"
    cfg.write_text(json.dumps({"input_config": [
        {"player_index": "Player1", "backend": "GamepadSDL2",
         "id": "0-00000003-054c-0000-cc09-000000006800", "name": "PS4 Controller (0)"}]}))
    _CFG[0] = cfg
    monkeypatch.setattr(cc, "sdl2_probe",
                        lambda v, p, lib="": {"error": "TimeoutExpired"})

    before = cfg.read_text()
    msg = _ryujinx(2, 0, "045e", "02fd", "Xbox One Controller")

    assert isinstance(msg, Skip), "still a refusal — an invented id is worse"
    assert cfg.read_text() == before
    assert "would not report a GUID" not in str(msg), (
        "SDL was never asked, so it did not decline to answer")
    assert "could not be run" in str(msg)


def test_ryujinx_names_the_emulator_when_the_flatpak_is_gone(tmp_path, monkeypatch):
    """The third cause, which also arrived as "SDL2 would not report a GUID".

    It is not about SDL at all: the flatpak could not be located, so the
    emulator's own SDL2 was never reachable and the host's must not stand in
    for it. Told the old way, the owner would look at the pad; told this way,
    at the install.
    """
    cfg = tmp_path / "Config.json"
    cfg.write_text(json.dumps({"input_config": [
        {"player_index": "Player1", "backend": "GamepadSDL2",
         "id": "0-00000003-054c-0000-cc09-000000006800", "name": "PS4 Controller (0)"}]}))
    _CFG[0] = cfg
    monkeypatch.setattr(cc, "flatpak_location", lambda app_id: "")

    before = cfg.read_text()
    msg = _ryujinx(2, 0, "045e", "02fd", "Xbox One Controller")

    assert isinstance(msg, Skip)
    assert cfg.read_text() == before
    assert "could not be located" in str(msg)
    assert "would not report a GUID" not in str(msg)

def test_ryujinx_does_not_rewrite_a_slot_that_is_already_right(tmp_path, monkeypatch):
    """This was the only writer that rewrote its whole 11 KB config on every
    single connection, battery warnings included."""
    cfg = tmp_path / "Config.json"
    cfg.write_text(json.dumps({"input_config": [
        {"player_index": "Player1", "backend": "GamepadSDL2",
         "id": "0-00000003-054c-0000-cc09-000000006800", "name": "PS4 Controller (0)"}]}, indent=2))
    _CFG[0] = cfg
    monkeypatch.setattr(cc, "sdl2_probe",
                        lambda v, p, lib="": {"guid": "030000004c050000cc09000000006800"})

    before = cfg.read_text()
    assert _ryujinx(1, 0, "054c", "09cc", "PS4 Controller") is None
    assert cfg.read_text() == before

def test_ryujinx_replaces_a_keyboard_slot_instead_of_mutating_it(tmp_path, monkeypatch):
    """Mutating the id of a keyboard config left it claiming to be an SDL
    device: the pad did not work and neither did the keyboard."""
    cfg = tmp_path / "Config.json"
    cfg.write_text(json.dumps({"input_config": [
        {"player_index": "Player1", "backend": "GamepadSDL2", "controller_type": "ProController",
         "id": "0-00000003-054c-0000-cc09-000000006800", "name": "PS4 Controller (0)"},
        {"player_index": "Player2", "backend": "WindowKeyboard", "id": "0"}]}))
    _CFG[0] = cfg
    monkeypatch.setattr(cc, "sdl2_probe",
                        lambda v, p, lib="": {"guid": "050000005e040000fd02000003090000"})

    _ryujinx(2, 0, "045e", "02fd", "Xbox One Controller")

    slot = [e for e in json.loads(cfg.read_text())["input_config"]
            if e["player_index"] == "Player2"][0]
    assert slot["backend"] == "GamepadSDL2"
    assert slot["id"] == "0-00000005-045e-0000-fd02-000003090000"
    assert slot["controller_type"] == "ProController", "cloned from the gamepad slot"


# ── RPCS3: a Null slot is the case that needs repairing ──────────────────────

_RPCS3_BOUND = """\
Player {n} Input:
  Handler: SDL
  Device: PS4 Controller 1
  Config:
    Cross: South
    Circle: East
    Start: Start
"""
_RPCS3_NULL = """\
Player {n} Input:
  Handler: "Null"
  Device: Xbox One Wireless Controller 1
  Config:
    Cross: ""
    Circle: ""
    Start: ""
"""

def test_a_stale_slot_holding_this_pads_id_is_removed(tmp_path, monkeypatch):
    """The exact state found on the box: Player1 right, Player2 its twin."""
    cfg = tmp_path / "Config.json"
    cfg.write_text(json.dumps({"input_config": [
        {"player_index": "Player1", "backend": "GamepadSDL2",
         "id": DS4_RYU_ID, "name": "PS4 Controller (0)"},
        {"player_index": "Player2", "backend": "GamepadSDL2",
         "id": DS4_RYU_ID, "name": "PS4 Controller (0)"},
        # A fossil of the old fabricated-GUID era: resolves to nothing, so it
        # is Ryujinx's problem to dispose of, not ours to delete.
        {"player_index": "Player3", "backend": "GamepadSDL2",
         "id": "2-00000003-054c-0000-cc09-000000006800", "name": "PS4 Controller (2)"},
    ]}, indent=2))
    _CFG[0] = cfg
    monkeypatch.setattr(cc, "sdl2_probe", lambda v, p, lib="": {"guid": DS4_SDL_GUID})

    msg = _ryujinx(1, 0, "054c", "09cc", "PS4 Controller")

    ic = json.loads(cfg.read_text())["input_config"]
    ids = [e["id"] for e in ic]
    assert len(ids) == len(set(ids)), "one pad drove two players"
    assert [e["player_index"] for e in ic] == ["Player1", "Player3"]
    assert msg and "freed Player2" in msg, "a silent removal is a removal nobody can debug"

def test_being_already_correct_does_not_hide_a_duplicate(tmp_path, monkeypatch):
    """The early return exists to avoid rewriting 11 KB for nothing.

    On a box that already has the duplicate, the slot being profiled is the one
    that is *right* — so returning early there left the phantom in place for
    good, which is exactly how it survived on the reference box.
    """
    cfg = tmp_path / "Config.json"
    cfg.write_text(json.dumps({"input_config": [
        {"player_index": "Player1", "backend": "GamepadSDL2",
         "id": DS4_RYU_ID, "name": "PS4 Controller (0)"},
        {"player_index": "Player4", "backend": "GamepadSDL2",
         "id": DS4_RYU_ID, "name": "PS4 Controller (0)"},
    ]}, indent=2))
    _CFG[0] = cfg
    monkeypatch.setattr(cc, "sdl2_probe", lambda v, p, lib="": {"guid": DS4_SDL_GUID})

    assert _ryujinx(1, 0, "054c", "09cc", "PS4 Controller") is not None
    ic = json.loads(cfg.read_text())["input_config"]
    assert [e["player_index"] for e in ic] == ["Player1"]

def test_two_real_pads_keep_their_two_slots(tmp_path, monkeypatch):
    """Deduplication must not eat a genuine second controller.

    Two identical pads share a GUID and are told apart by <dup>, so their ids
    differ and neither is stale.
    """
    cfg = tmp_path / "Config.json"
    cfg.write_text(json.dumps({"input_config": [
        {"player_index": "Player1", "backend": "GamepadSDL2",
         "id": DS4_RYU_ID, "name": "PS4 Controller (0)"},
        {"player_index": "Player2", "backend": "GamepadSDL2",
         "id": "1-00000005-054c-0000-cc09-000000006800", "name": "PS4 Controller (1)"},
    ]}, indent=2))
    _CFG[0] = cfg
    monkeypatch.setattr(cc, "sdl2_probe", lambda v, p, lib="": {"guid": DS4_SDL_GUID})

    assert _ryujinx(2, 1, "054c", "09cc", "PS4 Controller") is None
    ic = json.loads(cfg.read_text())["input_config"]
    assert [e["player_index"] for e in ic] == ["Player1", "Player2"]


# ── the GUID has to come from the emulator's own SDL ─────────────────────────
# Same DualShock 4, same instant, two libraries:
#   host libSDL2-2.0.so.0 (sdl2-compat 2.32.70 over SDL3) -> 05008fe5...  bus 5
#   Ryujinx's bundled libSDL2.so (real SDL 2.30.0)        -> 03008fe5...  bus 3
# SDL3 reports the transport; SDL2 2.30 reports USB for anything HIDAPI drives.
# Writing the host's answer made Ryujinx's IndexOf(id) return -1 and dispose
# the slot in silence — "Hid Remap: No matching controllers found", 352 times
# in one session log, and the controller applet on screen.

def test_ryujinx_asks_its_own_sdl_not_the_hosts(tmp_path, monkeypatch):
    cfg = tmp_path / "Config.json"
    cfg.write_text(json.dumps({"input_config": [
        {"player_index": "Player1", "backend": "GamepadSDL2",
         "id": "0-00000003-054c-0000-cc09-000000006800", "name": "PS4 Controller (0)"}]}, indent=2))
    _CFG[0] = cfg
    monkeypatch.setattr(cc, "bundled_sdl2", lambda app: "/ryujinx/libSDL2.so")

    asked = []

    def probe(vendor, product, lib=""):
        asked.append(lib)
        # The host and the emulator disagree; only one of these is usable.
        return {"guid": "03008fe54c050000cc09000000006800" if lib
                else "05008fe54c050000cc09000000006800"}

    monkeypatch.setattr(cc, "sdl2_probe", probe)
    _ryujinx(1, 0, "054c", "09cc", "PS4 Controller")

    assert asked == ["/ryujinx/libSDL2.so"], "the host's SDL2 answer does not go in Ryujinx's config"
    slot = json.loads(cfg.read_text())["input_config"][0]
    assert slot["id"] == "0-00000003-054c-0000-cc09-000000006800"

def test_a_native_install_still_gets_an_answer(tmp_path, monkeypatch):
    """No flatpak means no bundled SDL — fall back to the host's rather than
    give up, which is what every non-flatpak install would otherwise do."""
    cfg = tmp_path / "Config.json"
    cfg.write_text(json.dumps({"input_config": [
        {"player_index": "Player1", "backend": "GamepadSDL2",
         "id": "0-deadbeef-054c-0000-cc09-000000006800", "name": "PS4 Controller (0)"}]}, indent=2))
    _CFG[0] = cfg
    monkeypatch.setattr(cc, "bundled_sdl2", lambda app: "")
    monkeypatch.setattr(cc, "sdl2_probe",
                        lambda v, p, lib="": {"guid": "05008fe54c050000cc09000000006800"})

    assert _ryujinx(1, 0, "054c", "09cc", "PS4 Controller") is not None
    slot = json.loads(cfg.read_text())["input_config"][0]
    assert slot["id"] == "0-00000005-054c-0000-cc09-000000006800"


# ── the silent fallback, found by running the backend for real ─────────────

def test_an_unreachable_flatpak_produces_a_skip_not_the_hosts_guid(tmp_path, monkeypatch):
    """`bundled_sdl2()` used to degrade to the host's SDL2 without a word.

    The host and Ryujinx's own SDL2 disagree on the bus byte — 0x05 against
    0x03 for a Bluetooth DualShock 4, measured on the reference box. Ryujinx
    resolves ids with `_gamepadsIds.IndexOf(id)`, so the host's answer gives
    -1 and the slot is disposed in silence. A wrong id is worse than an
    unchanged slot, which is what `Skip` is for.
    """
    cfg = tmp_path / "Config.json"
    cfg.write_text(json.dumps({"input_config": [
        {"player_index": "Player1", "backend": "GamepadSDL2", "id": "", "name": ""}]}))
    _CFG[0] = cfg

    # flatpak cannot be asked — a busy daemon, a timeout, a user/system split.
    monkeypatch.setattr(cc, "flatpak_location", lambda app_id: "")
    monkeypatch.setattr(cc, "sdl2_probe",
                        lambda v, p, lib="": {"guid": DS4_SDL_GUID})   # host's answer

    result = _ryujinx(1, 0, "054c", "09cc", "PS4 Controller")

    assert isinstance(result, Skip), f"expected a Skip, got {result!r}"
    assert "SDL2" in str(result)
    # And nothing was written: the slot keeps whatever it had.
    assert json.loads(cfg.read_text())["input_config"][0]["id"] == ""


def test_a_reachable_flatpak_still_writes(tmp_path, monkeypatch):
    """The fix must not turn every install into a Skip."""
    cfg = tmp_path / "Config.json"
    cfg.write_text(json.dumps({"input_config": [
        {"player_index": "Player1", "backend": "GamepadSDL2", "id": "", "name": ""}]}))
    _CFG[0] = cfg

    monkeypatch.setattr(cc, "flatpak_location", lambda app_id: "/somewhere")
    monkeypatch.setattr(cc, "bundled_sdl2", lambda app_id: "/somewhere/libSDL2.so")
    monkeypatch.setattr(cc, "sdl2_probe", lambda v, p, lib="": {"guid": DS4_SDL_GUID})

    result = _ryujinx(1, 0, "054c", "09cc", "PS4 Controller")

    assert not isinstance(result, Skip), result
    assert json.loads(cfg.read_text())["input_config"][0]["id"].startswith("0-")
