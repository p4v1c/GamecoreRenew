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

# ── the guard capture() had and restore() did not ────────────────────────────
# capture() learned to refuse a block naming another pad only AFTER the box had
# filed cemu/045e_02fd.snap holding a DualShock 4's config. So the guard covered
# future captures while the poisoned file stayed on disk, and restore() applied
# it on every connect — overwriting whatever the owner had remapped by hand.
# The identity extract/replace of a whole-file config keeps these on the shared
# mechanism rather than on any one pack's format.

DS4_UUID = "<uuid>0_05009b514c050000cc09000000810000</uuid>\n"
XBOX = ("045e", "02fd")


def _whole_file(text):
    return text


def _overwrite(_text, block):
    return block


# The DeviceName branch is dead in this suite unless the SDL database is
# stubbed: conftest redirects GAMECORE_ROOT to a fake root, gamecontrollerdb.txt
# is not there, and `db_name_for` returns None — on which the branch declines to
# judge. Without these monkeypatches both tests below pass while executing
# nothing, which is the exact shape of a test that guards nothing.
_NAMES = {("054c", "09cc"): "PS4 Controller", ("045e", "02fd"): "Xbox One Controller"}


@pytest.fixture
def sdl_names(monkeypatch):
    monkeypatch.setattr(snapshots, "db_name_for",
                        lambda v, p: _NAMES.get((v, p)))


def test_a_guid_inside_a_compound_binding_is_seen(sdl_names):
    """azahar escapes `:` as `$0` inside a compound binding, so a stick's GUID
    reads `guid$00300…` — and the `0` of that escape is a hex digit, which made
    the lookbehind refuse the match. Every stick binding was invisible to this
    check, in capture() as well as restore().

    Measured on the reference box: 045e_02fd.snap (the Xbox's) had circle_pad
    `left` on the Xbox and `right`/`up`/`down` still on the DualShock 4. It was
    declared coherent, saved, restored — and the stick only answered to the
    left. capture()'s blindness is how such a file got written at all.
    """
    ds4 = "03008fe54c050000cc09000000006800"
    block = ("profiles\\1\\circle_pad=\"left:axis$00$1direction$0-$1engine$0sdl"
             f"$1guid$0{ds4}$1port$00$1threshold$0-0.5\"\n")

    assert snapshots.block_disagrees(block, *XBOX) == ds4


def test_neutralising_the_escapes_does_not_move_offsets():
    """check-catalog.py turns a match offset into a line number, so the
    substitution must not change the text's length."""
    raw = 'a$0b$1c\nd\n'
    assert len(snapshots.guid_scannable(raw)) == len(raw)
    assert snapshots.guid_scannable(raw).count("\n") == raw.count("\n")


def test_an_unassigned_slot_is_not_a_disagreement(sdl_names):
    """Rosalie's Mupen GUI writes `DeviceName = "None"` with `PluggedIn = False`
    for every slot nobody assigned — three of its four profiles on a one-pad
    box. Counting those as "this config is for another controller" rejected an
    entirely ordinary N64 config on the strength of its empty slots.

    Harmless while only capture() asked; the moment restore() started asking
    too, it would have refused the owner's saved N64 mapping on every connect.
    """
    block = ('[Profile 0]\nPluggedIn = True\nDeviceName = "PS4 Controller"\n'
             '[Profile 1]\nPluggedIn = False\nDeviceName = "None"\n'
             '[Profile 2]\nPluggedIn = False\nDeviceName = "None"\n')

    assert snapshots.block_disagrees(block, "054c", "09cc") is None


def test_a_named_slot_still_disagrees(sdl_names):
    """The other half: skipping "None" must not blind the check to a real
    mismatch, which is the whole reason the DeviceName branch exists."""
    block = ('[Profile 0]\nPluggedIn = True\nDeviceName = "PS4 Controller"\n'
             '[Profile 1]\nPluggedIn = False\nDeviceName = "None"\n')

    assert snapshots.block_disagrees(block, *XBOX) == "PS4 Controller"


def test_restore_refuses_a_snapshot_that_names_another_controller(tmp_path):
    """The owner's own mapping must survive a poisoned snapshot."""
    cfg = tmp_path / "controller0.xml"
    owner = "<emulated_controller>\n<uuid>0_xbox_mapping_by_hand</uuid>\n</emulated_controller>\n"
    cfg.write_text(owner)

    snaps = tmp_path / "snaps"
    snap = snapshots.snap_path(snaps, "cemu", *XBOX)
    snap.parent.mkdir(parents=True)
    snap.write_text(f"<emulated_controller>\n{DS4_UUID}</emulated_controller>\n")

    msg = snapshots.restore(snaps, "cemu", cfg, _whole_file, _overwrite, *XBOX)

    assert cfg.read_text() == owner, "restore() overwrote the owner's mapping"
    # Refusing silently would trade a silent overwrite for a silent deadlock:
    # the pad misbehaves and the journal explains nothing.
    assert msg and "ignored" in msg


def test_restore_still_applies_a_snapshot_that_agrees(tmp_path):
    """The other half: the guard must not break the feature it protects."""
    cfg = tmp_path / "controller0.xml"
    cfg.write_text("<emulated_controller>\n<uuid>0_stale</uuid>\n</emulated_controller>\n")

    snaps = tmp_path / "snaps"
    snap = snapshots.snap_path(snaps, "cemu", "054c", "09cc")
    snap.parent.mkdir(parents=True)
    saved = f"<emulated_controller>\n{DS4_UUID}</emulated_controller>\n"
    snap.write_text(saved)

    msg = snapshots.restore(snaps, "cemu", cfg, _whole_file, _overwrite,
                            "054c", "09cc")

    assert cfg.read_text() == saved
    assert msg and "restored" in msg


def test_a_restore_that_would_change_nothing_says_nothing(tmp_path):
    """"Already applied" is a question about the RESULT, not about the snapshot.

    It used to be asked as "is the file byte-identical to what was captured",
    which is a different question the moment a `replace` is anything but a
    verbatim swap. Two packs answer it differently: gopher64 rewrites a restored
    profile's DevicePath to where the pad sits on this boot, so its file can
    never equal the snapshot; mgba's replace applies nothing at all, and the
    reference box recorded it rewriting the file at 08:59:51 with an identical
    md5 while announcing "restored saved mapping".

    A write that changes nothing, announced as if it had, is the same defect in
    both. The monitor reprofiles every three seconds — this is what stops it
    from touching the file and filing a success each time.
    """
    cfg = tmp_path / "controller0.xml"
    saved = f"<emulated_controller>\n{DS4_UUID}</emulated_controller>\n"
    cfg.write_text(saved)

    snaps = tmp_path / "snaps"
    snap = snapshots.snap_path(snaps, "cemu", "054c", "09cc")
    snap.parent.mkdir(parents=True)
    snap.write_text(saved)

    def _replace_that_does_nothing(text, block):
        return text

    assert snapshots.restore(snaps, "cemu", cfg, _whole_file,
                             _replace_that_does_nothing, "054c", "09cc") is None
    assert not cfg.with_name(cfg.name + ".bak-ctrlmodel").exists(), (
        "a no-op restore took a backup of a file it was not going to change")


def test_a_saved_mapping_can_be_forgotten(tmp_path):
    """The inverse that did not exist. A refused snapshot is unreachable from a
    sofa, and without this the only way out of one is a shell."""
    snaps = tmp_path / "snaps"
    snap = snapshots.snap_path(snaps, "cemu", *XBOX)
    snap.parent.mkdir(parents=True)
    snap.write_text("anything")

    assert snapshots.forget(snaps, "cemu", *XBOX) is True
    assert not snap.exists()
    # Idempotent: forgetting twice is the owner pressing the button twice, not
    # an error to show them.
    assert snapshots.forget(snaps, "cemu", *XBOX) is False


def test_azahar_follows_the_active_profile(tmp_path):
    """Qt stores the selected index 0-based in `profile=` and writes the array
    1-based, so `profiles\\1\\` is only right while profile=0."""
    one = "[Controls]\nprofile=0\nprofiles\\1\\button_a=\"button:0\"\n"
    two = "[Controls]\nprofile=1\nprofiles\\2\\button_a=\"button:0\"\n"
    assert gens["azahar"]._az_prefix(one) == "profiles\\1\\"
    assert gens["azahar"]._az_prefix(two) == "profiles\\2\\"
    assert gens["azahar"].extract(two).strip() == 'profiles\\2\\button_a="button:0"'


# ── a config built from a captured mapping ───────────────────────────────────
#
# `snapshots.py` opens by saying nothing here can be synthesised, and that was
# right: a vendor:product says nothing about raw button indices. The wizard
# changes THAT premise and only that one — a pad mapped button by button has
# had those indices measured.
#
# Every shape asserted below has a measured original in the snapshots this box
# already carries (azahar/054c_09cc.snap for a button and a trigger axis,
# azahar/045e_02fd.snap for a hat D-pad, ~/.config/mgba/config.ini for the
# whole [gba.input.SDLB] section). Nothing here is a guess about a format.

from backend.services.configgen import controllers, derive       # noqa: E402

DERIVE_GUID = "03000325adde0000efbe000011010000"

# A generic pad as the wizard records one: face buttons, a hat D-pad, analogue
# triggers and two sticks.
CAPTURED = (f"{DERIVE_GUID},Generic USB Gamepad,"
            "a:b0,b:b1,x:b2,y:b3,"
            "dpup:h0.1,dpdown:h0.4,dpleft:h0.8,dpright:h0.2,"
            "leftshoulder:b4,rightshoulder:b5,"
            "lefttrigger:+a2,righttrigger:+a5,"
            "back:b6,start:b7,guide:b8,"
            "leftx:a0,lefty:a1,rightx:a3,righty:a4,platform:Linux,")


@pytest.fixture
def wizard_mapped(monkeypatch, tmp_path):
    """A box where the wizard has run, and SDL reads the pad through evdev."""
    from backend.services.configgen import mapping_db
    user = tmp_path / "user.txt"
    user.write_text(CAPTURED + "\n")
    monkeypatch.setattr(mapping_db, "USER_DB", user)
    monkeypatch.setattr(controllers, "sdl2_probe",
                        lambda v, p, lib="": {"guid": DERIVE_GUID})
    monkeypatch.setattr(derive, "evdev_driven", lambda v, p: True)
    return tmp_path


class _Pad:
    # The vendor:product DERIVE_GUID actually encodes. Not decoration: the
    # snapshot guard decodes the GUID and refuses a block naming another pad,
    # so a mismatch here would be refused before any assertion below ran — as
    # it was, on the first run of these tests.
    vendor, product = "dead", "beef"


def test_the_tokens_the_wizard_writes_are_understood():
    """`b3`, `+a2` and `h0.1` are the whole vocabulary. A token misread here is
    a binding written to the wrong kind of input."""
    assert derive.parse_token("b3") == derive.Input("button", 3)
    assert derive.parse_token("+a2") == derive.Input("axis", 2, "+")
    assert derive.parse_token("-a2") == derive.Input("axis", 2, "-")
    assert derive.parse_token("a2") == derive.Input("axis", 2, "+")
    assert derive.parse_token("h0.1") == derive.Input("hat", 0, "up")
    assert derive.parse_token("h0.8") == derive.Input("hat", 0, "left")
    # A diagonal is two bits and no emulator here has a binding for one.
    assert derive.parse_token("h0.3") is None
    assert derive.parse_token("rubbish") is None


def test_azahar_is_built_in_the_shape_azahar_itself_wrote(wizard_mapped):
    """Compared against the real snapshot on this box, not against itself."""
    block = gens["azahar"]._derive_block(_Pad(), "profiles\\1\\")

    # A button — azahar/054c_09cc.snap: button:0,engine:sdl,guid:…,port:0
    assert (f'profiles\\1\\button_a="button:0,engine:sdl,guid:{DERIVE_GUID},'
            f'port:0"\n') in block
    # A hat D-pad — azahar/045e_02fd.snap, keys alphabetical, hat after guid
    assert (f'profiles\\1\\button_up="direction:up,engine:sdl,'
            f'guid:{DERIVE_GUID},hat:0,port:0"\n') in block
    # A trigger axis, with its threshold
    assert (f'profiles\\1\\button_zl="axis:2,direction:+,engine:sdl,'
            f'guid:{DERIVE_GUID},port:0,threshold:0.5"\n') in block
    # Every binding needs its \default companion or azahar's UI shows it unset
    assert block.count("\\default=false") == block.count('="')


def test_azahar_is_asked_of_azahars_own_sdl(monkeypatch):
    """Why azahar could not be synthesised, and why it now can.

    `snapshots.py` records azahar writing `button_up = 11` for a DualShock 4
    and calls it unexplainable next to SDL's own mapping, "which claims a hat
    and calls button 11 the touchpad". Measured on this box, same pad, same
    instant, it is simply two libraries:

        host sdl2-compat 2.32.70    dpup:h0.1 … touchpad:b11
        org.kde.Platform 6.9's
        real SDL 2.32.10            dpup:b11  … touchpad:b15

    azahar links the second. Deriving from the first would write a hat where
    azahar wants button 11 — a config of plausible numbers binding the wrong
    things, which is worse than the untouched file it replaces.
    """
    from backend.services.configgen import inputs, mapping_db

    host = (f"{DERIVE_GUID},A Pad,a:b0,dpup:h0.1,dpdown:h0.4,dpleft:h0.8,"
            f"dpright:h0.2,touchpad:b11,platform:Linux,")
    azahars = (f"{DERIVE_GUID},A Pad,a:b0,dpup:b11,dpdown:b12,dpleft:b13,"
               f"dpright:b14,touchpad:b15,platform:Linux,")
    monkeypatch.setattr(mapping_db, "read_user", list)   # the wizard never ran
    monkeypatch.setattr(controllers, "bundled_sdl2",
                        lambda app_id: "/azahar/libSDL2.so" if app_id else "")
    monkeypatch.setattr(
        controllers, "sdl2_probe",
        lambda v, p, lib="": {"guid": DERIVE_GUID,
                              "map": azahars if lib else host})

    block = gens["azahar"]._derive_block(_Pad(), "profiles\\1\\",
                                         "org.azahar_emu.Azahar")
    assert f'button_up="button:11,engine:sdl,guid:{DERIVE_GUID},port:0"' in block

    # And with no app id, the host answers — which is the WRONG source for
    # azahar, and the test says so rather than pretending the two agree.
    assert "direction:up,engine:sdl" in gens["azahar"]._derive_block(
        _Pad(), "profiles\\1\\", "")

    # One probe for both halves: an id from one library beside indices from
    # another binds nothing.
    model = inputs.for_pad(_Pad(), "org.azahar_emu.Azahar")
    assert model.guid == DERIVE_GUID and model.button("dpup") == 11


def test_azahars_sticks_carry_the_escaped_compound_form(wizard_mapped):
    """azahar escapes `:` as `$0` and `,` as `$1` inside a compound binding.
    Getting this wrong is not cosmetic: the `0` of `$0` is a hex digit, which
    is what hid every stick binding from `block_disagrees` until it was
    measured."""
    block = gens["azahar"]._derive_block(_Pad(), "profiles\\1\\")

    line = next(l for l in block.splitlines() if "circle_pad=" in l)
    assert "engine:analog_from_button" in line
    assert "modifier_scale:0.680000" in line
    assert f"left:axis$00$1direction$0-$1engine$0sdl$1guid$0{DERIVE_GUID}" in line
    assert "$1threshold$0-0.5" in line, "the negative half carries a signed threshold"
    # The check that guards the whole snapshot mechanism must still see it.
    assert snapshots.block_disagrees(block, "9999", "9999") == DERIVE_GUID


def test_mgba_writes_its_two_halves_in_opposite_directions(wizard_mapped):
    """mGBA's format, confirmed by ~/.config/mgba/config.ini on this box:
    `key<Name>=<sdl button>` names the GBA key and stores the pad's button,
    while `hat0<Dir>=<gba key id>` is the other way round. Writing one in the
    other's shape gives a file mGBA loads in silence and ignores."""
    keys = gens["mgba"]._bindings_for(_Pad(), "")

    assert keys["keyA"] == "0" and keys["keyB"] == "1"
    assert keys["keyL"] == "4" and keys["keyR"] == "5"
    assert keys["keySelect"] == "6" and keys["keyStart"] == "7"
    # The hat half: hat0Up carries the GBA key id for Up, which is 6.
    assert keys["hat0Up"] == "6"
    assert keys["hat0Down"] == "7" and keys["hat0Left"] == "5"
    assert keys["hat0Right"] == "4"
    assert keys["device0"] == DERIVE_GUID


def test_mgba_unbinds_what_the_pad_does_not_have(wizard_mapped):
    """Every owned key is cleared before the new ones land, so a key simply
    left out would KEEP whatever the previous controller — or the seed — put
    there. The box's own config still carries `keyUp=11` from an Xbox pad next
    to a DualShock 4's hat."""
    keys = gens["mgba"]._bindings_for(_Pad(), "")

    assert keys["keyUp"] == "-1", "a hat D-pad must clear the button form"


def test_mgba_binds_the_stick_as_well_as_the_dpad(wizard_mapped, monkeypatch):
    """Not "instead of", and the difference is a regression that nearly
    shipped. This used to be a fallback for a pad with no D-pad at all, which
    reads sensibly — but the seed binds both, so the DualShock 4 the owner
    reported working moves the character with the stick too, and a synthesis
    that emitted the axis lines only when there was no hat would have taken
    that away from every pad that has one."""
    keys = gens["mgba"]._bindings_for(_Pad(), "")

    assert keys["axisLeftAxis"] == "-0" and keys["axisLeftValue"] == "-12288"
    assert keys["axisRightAxis"] == "+0" and keys["axisRightValue"] == "12288"
    assert keys["axisUpAxis"] == "-1" and keys["axisDownAxis"] == "+1"
    assert keys["hat0Up"] == "6", "and the hat is still bound"


def test_the_wizards_indices_are_still_refused_for_a_hidapi_pad(wizard_mapped, monkeypatch):
    """The sharp rule, unchanged. The capture's indices come from SDL's LINUX
    joystick driver; a HIDAPI-driven pad reports a completely different button
    order for the same controller — measured in snapshots.py, where azahar
    wrote `button_up = 11` for a DualShock 4 whose SDL mapping calls button 11
    the touchpad.

    What CHANGED is what happens next. azahar still writes nothing. mGBA no
    longer stops there: a pad SDL drives through HIDAPI is a pad SDL ships a
    mapping for, and that mapping is the right source for exactly the case the
    capture is wrong about. Refusing the capture and asking SDL are the same
    decision seen from two sides — see `configgen/inputs.py`.
    """
    monkeypatch.setattr(derive, "evdev_driven", lambda v, p: False)
    monkeypatch.setattr(controllers, "sdl2_probe", lambda v, p, lib="": {})

    assert gens["azahar"]._derive_block(_Pad(), "profiles\\1\\") is None
    assert derive.bindings_for("dead", "beef") is None, (
        "the capture must still be refused — it is the indices that are wrong")

    # And with SDL able to answer, mGBA is written from SDL instead.
    hidapi = (f"{DERIVE_GUID},A HIDAPI Pad,a:b0,b:b1,back:b8,start:b9,"
              f"leftshoulder:b9,rightshoulder:b10,dpup:h0.1,dpdown:h0.4,"
              f"dpleft:h0.8,dpright:h0.2,platform:Linux,")
    monkeypatch.setattr(controllers, "sdl2_probe",
                        lambda v, p, lib="": {"guid": DERIVE_GUID, "map": hidapi})

    keys = gens["mgba"]._bindings_for(_Pad(), "")
    assert keys["keyL"] == "9" and keys["keyR"] == "10", (
        f"mGBA fell back to the capture's 4/5 rather than SDL's own: {keys}")


def test_a_pad_no_source_can_describe_is_refused(wizard_mapped, monkeypatch):
    """None is not a yes. An untouched config is recoverable; one full of
    another driver's indices looks correct and is not."""
    monkeypatch.setattr(derive, "evdev_driven", lambda v, p: None)
    monkeypatch.setattr(controllers, "sdl2_probe", lambda v, p, lib="": {})

    assert gens["mgba"]._bindings_for(_Pad(), "") is None


def test_a_capture_under_another_guid_is_not_this_emulators(wizard_mapped, monkeypatch):
    """The wizard files one line per SDL identity the pad has. azahar must be
    written from the line matching the GUID ITS SDL computes — matching on
    vendor:product instead would hand it the host SDL3 line, whose indices are
    a different driver's."""
    monkeypatch.setattr(controllers, "sdl2_probe",
                        lambda v, p, lib="": {"guid": "05008fe54c050000cc09000000006800"})

    assert derive.bindings_for("dead", "beef") is None


def test_a_hand_made_snapshot_always_beats_a_derivation(wizard_mapped, tmp_path):
    """The owner configured the pad inside the emulator and pressed "Scan
    mapping". That is their work, and a derivation that overwrote it would be
    this pipeline destroying exactly what it exists to preserve."""
    cfg = tmp_path / "qt-config.ini"
    cfg.write_text("[Controls]\nprofile=0\nprofiles\\1\\button_a=\"stale\"\n")
    snaps = tmp_path / "snaps"
    snap = snapshots.snap_path(snaps, "azahar", "dead", "beef")
    snap.parent.mkdir(parents=True)
    saved = f'profiles\\1\\button_a="button:9,engine:sdl,guid:{DERIVE_GUID},port:0"\n'
    snap.write_text(saved)

    msg = gens["azahar"].generate(1, _Pad(), {"snap_dir": snaps, "target": cfg})

    assert "button:9" in cfg.read_text(), "the derivation overwrote the owner's snapshot"
    assert msg and "restored" in msg


def test_the_derivation_reaches_the_file_and_is_idempotent(wizard_mapped, tmp_path):
    """The second call must write NOTHING. A generator that rewrites on every
    connect is how _ryujinx used to churn 11 KB a plug."""
    cfg = tmp_path / "qt-config.ini"
    cfg.write_text("[Controls]\nprofile=0\nsomethingElse=1\n")
    opts = {"snap_dir": tmp_path / "snaps", "target": cfg}

    first = gens["azahar"].generate(1, _Pad(), opts)
    written = cfg.read_text()
    second = gens["azahar"].generate(1, _Pad(), opts)

    assert first and "built for" in first
    assert "button_a=" in written
    assert "somethingElse=1" in written, "the rest of the file must survive"
    assert second is None, "the second pass rewrote an identical block"
    assert cfg.read_text() == written


def test_a_box_that_never_ran_the_wizard_pays_nothing(monkeypatch, tmp_path):
    """The hotplug path, which is every box until the day it is not.

    `bindings_for` runs once per generator on every pad connection, and
    `sdl2_probe` is a subprocess with an eight-second timeout. Finding out there
    is nothing to derive from must cost a stat of one absent file, not an SDL
    launch per emulator.
    """
    from backend.services.configgen import mapping_db
    monkeypatch.setattr(mapping_db, "USER_DB", tmp_path / "never-written.txt")

    def must_not_run(*_a, **_k):
        raise AssertionError("an SDL subprocess ran for a box with no captures")

    monkeypatch.setattr(controllers, "sdl2_probe", must_not_run)
    monkeypatch.setattr(derive, "evdev_driven", must_not_run)

    assert derive.bindings_for("054c", "09cc") is None


def test_cemu_is_still_refused():
    """Two unknowns, both of which produce a config that looks right: its
    <uuid> is not an identity anything here can compute (measured: the name CRC
    and the driver tail both differ from every SDL we can ask), and its
    <button> ids for axes are internal to Cemu. "Scan mapping" stays the way to
    teach Cemu a pad."""
    assert not hasattr(gens["cemu"], "_derive_block")
    assert "not an identity" in derive.cemu_is_not_derivable


