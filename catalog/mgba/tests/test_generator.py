"""GBA — the seed was one pad's numbers, and this is what replaces them.

Every mapping below is a real one. The DualShock 4's was read live from this
box's own libSDL2 with the pad connected; the Xbox pad's is the vendored
`gamecontrollerdb.txt` line for `050000005e040000fd02000003090000`, which is
the GUID mGBA itself wrote into this box's snapshot for that controller.

Those two lines are the whole of D7. Put the seed's numbers next to the Xbox
mapping and the owner's report decodes word for word:

    keySelect=4  → the Xbox pad's b4 is Y      → "Y ouvre la map"
    keyStart=6   → its b6 is the left shoulder → "L1 c'est mon inventaire"
    keyL=9 keyR=10 → b9/b10 are the stick clicks — the GBA's shoulders landed
                     on L3/R3, which is exactly what was reported
    keyA=0 keyB=1  → b0/b1 really are A and B  → "A et B fonctionne"

Nothing is stubbed here except SDL and the wizard's database. `flatpak_location`
and `sdl2_probe` shell out, and a test whose result depends on what the machine
happens to have installed is not testing the code — see catalog/ryujinx/tests.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from backend.services.configgen import controllers as cc     # noqa: E402
from backend.services.configgen import mapping_db            # noqa: E402
from backend.services.configgen.controllers import Pad       # noqa: E402
from backend.services.configgen.helpers.ini import section   # noqa: E402


def _load(pack_id):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        f"gen_{pack_id}", ROOT / "catalog" / pack_id / "generator.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


gen = _load("mgba")

SEED = (ROOT / "catalog" / "mgba" / "seed" / "config.ini").read_text()

DS4 = ("054c", "09cc")
XBOX = ("045e", "02fd")

# Measured on this box, `sdl2_probe('054c','09cc')` with the pad plugged in.
DS4_GUID = "03008fe54c050000cc09000000016800"
DS4_MAP = (
    "a:b0,b:b1,back:b4,dpdown:h0.4,dpleft:h0.8,dpright:h0.2,dpup:h0.1,"
    "guide:b5,leftshoulder:b9,leftstick:b7,lefttrigger:a4,leftx:a0,lefty:a1,"
    "rightshoulder:b10,rightstick:b8,righttrigger:a5,rightx:a2,righty:a3,"
    "start:b6,x:b2,y:b3,touchpad:b11,crc:e58f")

# backend/data/gamecontrollerdb.txt, the Bluetooth Xbox One entry.
XBOX_GUID = "050018dc5e040000fd02000003090000"
XBOX_MAP = (
    "a:b0,b:b1,back:b15,dpdown:h0.4,dpleft:h0.8,dpright:h0.2,dpup:h0.1,"
    "guide:b16,leftshoulder:b6,leftstick:b13,lefttrigger:a5,leftx:a0,lefty:a1,"
    "rightshoulder:b7,rightstick:b14,righttrigger:a4,rightx:a2,righty:a3,"
    "start:b11,x:b3,y:b4,platform:Linux")

PADS = {DS4: (DS4_GUID, DS4_MAP), XBOX: (XBOX_GUID, XBOX_MAP)}


@pytest.fixture(autouse=True)
def sdl(monkeypatch):
    """SDL answers for the two pads above, and the wizard has never run."""
    def probe(vendor, product, lib=""):
        got = PADS.get((vendor.lower(), product.lower()))
        if got is None:
            return {}
        guid, mapping = got
        return {"guid": guid, "map": f"{guid},A Pad,{mapping},"}

    monkeypatch.setattr(cc, "sdl2_probe", probe)
    monkeypatch.setattr(cc, "_sdl2_cache", {}, raising=False)
    # No captured mapping: `derive.bindings_for` returns on the first line, so
    # nothing here reaches `evdev_driven()` and its subprocesses.
    monkeypatch.setattr(mapping_db, "read_user", list)


@pytest.fixture
def box(tmp_path):
    """A fresh install's mGBA config, and the opts a generator receives."""
    target = tmp_path / "config.ini"
    target.write_text(SEED)
    return target, {"target": target, "snap_dir": tmp_path / "snapshots",
                    "app_id": ""}


def _keys(target) -> dict[str, str]:
    body = section(target.read_text(), "gba.input.SDLB") or ""
    return dict(line.split("=", 1) for line in body.splitlines() if "=" in line)


def _run(target, opts, vendor, product):
    return gen.generate(1, Pad(vendor=vendor, product=product,
                               evdev_name="a pad"), opts)


# ── the fault ────────────────────────────────────────────────────────────────

def test_an_xbox_pad_no_longer_gets_a_dualshock_4s_numbers(box):
    """D7 itself. Every one of these was measured in game as a wrong button."""
    target, opts = box
    assert _run(target, opts, *XBOX)

    keys = _keys(target)
    assert keys["keySelect"] == "15", (
        "Select is still on the DS4's b4, which is Y on this pad — the owner "
        "reported 'Y ouvre la map'")
    assert keys["keyStart"] == "11", (
        "Start is still on b6, the Xbox pad's left shoulder — 'L1 c'est mon "
        "inventaire'")
    assert keys["keyL"] == "6" and keys["keyR"] == "7", (
        f"the GBA's shoulders are on {keys['keyL']}/{keys['keyR']}; the DS4's "
        f"9/10 are this pad's stick clicks")
    assert keys["keyA"] == "0" and keys["keyB"] == "1", (
        "A and B are the two the owner reported working — they must not move")


def test_a_dualshock_4_gets_exactly_what_the_seed_hand_wrote(box):
    """The other half of the same claim, and the proof the synthesis is right
    rather than merely different: the seed IS a DualShock 4's mapping, so
    deriving one from the pad has to land on the same numbers."""
    target, opts = box
    seed_keys = _keys(target)
    assert _run(target, opts, *DS4)

    keys = _keys(target)
    for key in ("keyA", "keyB", "keyL", "keyR", "keySelect", "keyStart",
                "keyUp", "keyDown", "keyLeft", "keyRight",
                "hat0Up", "hat0Down", "hat0Left", "hat0Right",
                "axisLeftAxis", "axisRightAxis", "axisUpAxis", "axisDownAxis",
                "axisLeftValue", "axisRightValue", "axisUpValue", "axisDownValue"):
        assert keys[key] == seed_keys[key], (
            f"{key} came out {keys[key]}, the seed says {seed_keys[key]} — the "
            f"seed was measured working on this exact pad")


# ── what a wholesale section rewrite would have cost ─────────────────────────

def test_the_stick_still_drives_the_d_pad(box):
    """A pad with a perfectly good hat gets the stick bound as well.

    The derivation this replaces emitted the axis lines only as a FALLBACK for
    a pad with no D-pad at all, which reads sensibly and would have been a
    regression: the seed binds both, so on the box the owner reported working
    the left stick moves Link. Taking that away is not a fix.
    """
    target, opts = box
    assert _run(target, opts, *XBOX)

    keys = _keys(target)
    assert keys["axisLeftAxis"] == "-0" and keys["axisRightAxis"] == "+0"
    assert keys["axisUpAxis"] == "-1" and keys["axisDownAxis"] == "+1"
    assert keys["hat0Up"] == "6", "and the hat is still bound too"


def test_the_gyro_settings_survive(box):
    """mGBA keeps bindings and motion settings in the SAME section, so
    replacing it wholesale would take the owner's tilt configuration with it on
    every single pad connection."""
    target, opts = box
    assert _run(target, opts, *XBOX)

    keys = _keys(target)
    assert keys["gyroSensitivity"] == "2,2e+09"
    assert keys["tiltAxisX"] == "2" and keys["tiltAxisY"] == "3"
    assert keys["gyroAxisX"] == "0" and keys["gyroAxisZ"] == "-1"


def test_the_keyboard_section_is_untouched(box):
    """The package's rule: write only what GameCore owns."""
    target, opts = box
    assert _run(target, opts, *XBOX)
    assert section(target.read_text(), "gba.input.QT_K") == \
        section(SEED, "gba.input.QT_K")


def test_the_device_the_bindings_belong_to_is_named(box):
    """The seed leaves `device0=` empty. mGBA writes the pad's GUID there
    itself — the snapshot this box carries proves it — and the GUID must come
    from the same probe the indices did, never from a second source."""
    target, opts = box
    assert _run(target, opts, *XBOX)
    assert _keys(target)["device0"] == XBOX_GUID


def test_writing_twice_writes_once(box):
    """Idempotence, which the validation session measured and must keep: a
    config rewritten on every connect is how a no-op looked like a success."""
    target, opts = box
    assert _run(target, opts, *DS4)
    after = target.read_text()
    assert _run(target, opts, *DS4) is None
    assert target.read_text() == after


def test_a_pad_sdl_cannot_describe_is_left_alone(box):
    """No source, no write. A config of invented indices looks correct,
    survives reboots and is undiagnosable from a sofa."""
    target, opts = box
    assert _run(target, opts, "1d79", "0f0f") is None
    assert target.read_text() == SEED


def test_only_player_one(box):
    """maxPlayers is 1; a second pad must not rewrite the only config."""
    target, opts = box
    assert gen.generate(2, Pad(vendor=XBOX[0], product=XBOX[1]), opts) is None
    assert target.read_text() == SEED


# ── the snapshots (D6) ───────────────────────────────────────────────────────

# What this box actually carries: 180 bytes, six gyro keys, not one button —
# captured by an extract that read `device0=` plus the per-GUID profile section
# and nothing else.
EMPTY_SNAP = f"""\
device0={XBOX_GUID}
[gba.input-profile.{XBOX_GUID}]
tiltAxisY=3
gyroAxisX=0
gyroAxisZ=-1
gyroSensitivity=2,2e+09
tiltAxisX=2
gyroAxisY=1
"""


def _save(opts, vendor, product, text):
    snap = opts["snap_dir"] / "mgba" / f"{vendor}_{product}.snap"
    snap.parent.mkdir(parents=True, exist_ok=True)
    snap.write_text(text)
    return snap


def test_a_snapshot_with_no_bindings_does_not_block_the_synthesis(box):
    """The defect that hid every other one. `exists()` found these files, the
    restore reported "restored saved mapping", the md5 never changed, and the
    pad kept the seed's numbers for ever."""
    target, opts = box
    _save(opts, *XBOX, EMPTY_SNAP)

    assert _run(target, opts, *XBOX), "the empty snapshot short-circuited it"
    assert _keys(target)["keySelect"] == "15"


def test_a_real_snapshot_still_wins(box):
    """Rule one, and it is not weakened: a mapping the owner made by hand
    inside mGBA is theirs, and a derivation must not replace it."""
    target, opts = box
    mine = ("[gba.input.SDLB]\n"
            f"device0={XBOX_GUID}\n"
            "keyA=3\nkeyB=2\nkeySelect=15\nkeyStart=11\nkeyL=6\nkeyR=7\n")
    _save(opts, *XBOX, mine)

    assert _run(target, opts, *XBOX)
    keys = _keys(target)
    assert keys["keyA"] == "3" and keys["keyB"] == "2", (
        f"the owner's own mapping was overwritten by the synthesis: {keys}")


def test_a_leading_key_in_a_snapshot_is_applied(box):
    """`iter_sections` starts at the first `[header]` and drops what precedes
    it — silently. A snapshot beginning with a bare `device0=` therefore lost
    the one field that says which pad it is for."""
    target, opts = box
    block = ("device0=deadbeef\n"
             "[gba.input-profile.deadbeef]\n"
             "gyroAxisX=1\n")
    assert "device0=deadbeef" in gen.replace(SEED, block)
