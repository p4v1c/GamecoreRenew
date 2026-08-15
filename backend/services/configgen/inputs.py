"""The abstract input model — "this control, on this pad, has this shape".

Four generators out of nine could synthesise nothing and fell back to copying a
file (`snapshot-restore`), because nothing in this package could answer one
question: *which raw index is this pad's L1, and is it even a button?* Without
that answer azahar and gopher64 still send the owner out to the emulator's own
settings, and mgba shipped a seed whose numbers were one particular
DualShock 4's — which is why it worked on a Sony pad and put Zelda's map on Y
for an Xbox one.

Recalbox's configgen names the missing piece exactly: an `Input(name, type, id,
value, code)` where `type` is `button`, `hat`, `axis` or `key`. A semantic name
carries its PHYSICAL FORM, and each generator translates that into its own
file format. Batocera's covers more emulators the same way. The idea is theirs;
none of the code is, and neither is the convention — Recalbox's model is shaped
for EmulationStation, its names are SNES names, and it carries decisions that
have outlived their reason ("Force dpad 0 until ES handles others").

**What GameCore keeps that they do not have.** Batocera and Recalbox REGENERATE
the whole config at every launch and overwrite whatever the owner changed. This
package does the opposite: a generator writes only the sections GameCore owns
and leaves the rest intact to the byte, which is what makes `.bak-preinstall`
and the snapshot mechanism coherent. Nothing here lifts that. This module hands
a generator facts about a pad; the generator still decides what few lines it is
entitled to write.

## Where the indices come from

That is the hard question, and getting it wrong produces the worst possible
output: a config full of plausible numbers that binds the wrong things. Two
sources exist on this box and they are NOT interchangeable.

    the wizard's capture     read through SDL's LINUX JOYSTICK driver, because
                             that is what reads /dev/input
    SDL's own mapping        read through whichever driver SDL uses for the pad
                             — HIDAPI for the Sony, Microsoft and Nintendo
                             families

The two orders differ for the same physical controller. `derive.evdev_driven()`
exists to detect that and refuse, and it is right to: measured on a DualShock 4,
azahar had written `button_up = 11` while SDL's own mapping calls that pad's
D-pad a hat and button 11 the touchpad.

The refusal was read as the wizard being pointless for modern pads. It is the
opposite — the two sources are COMPLEMENTARY, and each is authoritative exactly
where the other is silent:

  · a pad SDL has a HIDAPI driver for is a pad SDL also ships a built-in mapping
    for. The wizard is refused, and does not need to answer: `sdl2_mapping()`
    already knows. Measured, one DualShock 4 over USB:

        a:b0  b:b1  x:b2  y:b3  back:b4  guide:b5  start:b6
        leftshoulder:b9  rightshoulder:b10  leftstick:b7  rightstick:b8
        dpup:h0.1  dpright:h0.2  dpdown:h0.4  dpleft:h0.8
        leftx:a0  lefty:a1  rightx:a2  righty:a3  lefttrigger:a4  righttrigger:a5

    Every number in mgba's seed is in that list. The seed is not a mapping, it
    is one pad's mapping written out by hand.

  · a pad SDL has NO driver for gets no mapping — and SDL reads it through the
    linux joystick driver, which is the driver the wizard captured with. So the
    capture is valid precisely there, which is the case the wizard was built
    for.

So: the wizard first when it is offered (the owner measured that pad by hand,
and `bindings_for` only offers it when the driver agrees), SDL's own mapping
otherwise. Neither is ever used in the other's territory.

**How that separation was breached, measured rather than reasoned.** The first
box to run this shipped a DualShock 4 config with `start` on the driver's L1, a
D-pad bound to a hat that SDL calls buttons 11-14, and nothing on R1 — while
`evdev_driven('054c','09cc')` still answered `False` every time it was asked.
The guard was intact and simply no longer on the road: the capture arrived
through `_from_sdl`, because SDL had been handed the SERVED mapping table on
its way in and read the owner's own line back out. SDL keeps the LAST line for
a GUID, so the capture beat SDL's built-in, and `source` said "sdl" about a
number the wizard had measured.

The table came from `os.environ.setdefault` in `controllers._sdl3_live_names`,
inherited by every probe subprocess started afterwards — which made the answer
depend on whether a pad had been enumerated earlier in that process. The same
pad, the same code, two different configs. `controllers.probe_env()` is what
holds the two sources apart now: a probe asking what SDL knows runs with no
mapping table at all. **A source is not a source if something else can speak
into it.**

## The invariant

A GUID and a set of indices must come from the SAME SDL. Mixing them is the
failure `controllers.py` documents at length — the host's SDL3 says bus `0x05`
for a Bluetooth DualShock 4 and Ryujinx's bundled SDL2 says `0x03` — reached by
a different road. `for_pad()` therefore takes both from one probe and returns
them together, and a caller writing a device id next to a button index must use
the pair it was handed rather than fetching either separately.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from . import controllers

log = logging.getLogger(__name__)


# ── the model ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Input:
    """One control, in the emulators' vocabulary rather than SDL's.

    `kind` is "button", "hat" or "axis"; `index` is the raw SDL joystick index;
    `direction` is "+"/"-" for an axis and "up"/"down"/"left"/"right" for a hat.

    Three kinds and not Recalbox's four: there is no `key` here because nothing
    in this package writes a keyboard binding — the seeds carry the keyboard
    section and generators leave it alone, which is the whole "only the sections
    GameCore owns" rule.

    The kind is not decoration. mgba stores a button as `keyA=<index>` and a hat
    direction the other way round as `hat0Up=<gba key id>`; melonDS folds a hat
    into `0x100 | hat<<4 | dir` and a button into the bare index. A model that
    carried only a number would make both of those unwritable, which is exactly
    why those generators had nothing to write.
    """
    kind: str
    index: int
    direction: str = ""


# SDL's own output names, which are the names this model uses. Taken from SDL
# rather than invented: they are what `sdl2_mapping()` returns, what the wizard
# records, and what a mapping line in gamecontrollerdb is keyed by — three
# vocabularies collapsed into one by not inventing a fourth.
CONTROLS: tuple[str, ...] = (
    "a", "b", "x", "y",
    "back", "guide", "start",
    "leftstick", "rightstick", "leftshoulder", "rightshoulder",
    "lefttrigger", "righttrigger",
    "dpup", "dpdown", "dpleft", "dpright",
    "leftx", "lefty", "rightx", "righty",
)

_TOKEN_RE = re.compile(r"^(?P<sign>[-+])?(?:(?P<b>b)(?P<bi>\d+)"
                       r"|(?P<a>a)(?P<ai>\d+)"
                       r"|h(?P<hi>\d+)\.(?P<hm>\d+))$")

# SDL's hat bitmask. Only the four cardinals are ever bound: a diagonal is two
# bits and no emulator here has a binding for one.
_HAT_DIRECTION = {1: "up", 2: "right", 4: "down", 8: "left"}


def parse_token(token: str) -> Input | None:
    """`b3` / `+a2` / `h0.1` → an Input, or None when it is not one of those.

    SDL's own token grammar, which both sources speak: the wizard writes it into
    gamecontrollerdb and SDL prints it back out of `SDL_GameControllerMapping`.
    Parsing it once here is what lets the two sources produce the same model.
    """
    m = _TOKEN_RE.match(token.strip())
    if not m:
        return None
    if m.group("b"):
        return Input("button", int(m.group("bi")))
    if m.group("a"):
        return Input("axis", int(m.group("ai")), m.group("sign") or "+")
    direction = _HAT_DIRECTION.get(int(m.group("hm")))
    if not direction:
        return None
    return Input("hat", int(m.group("hi")), direction)


@dataclass(frozen=True)
class PadInputs:
    """What one SDL knows about one pad: a device id and the shape of each
    control, taken together — see "The invariant" above.

    `source` is "wizard" or "sdl". Kept rather than dropped once the model is
    built, because a generator may legitimately care: a capture describes the
    pad the owner measured by hand, an SDL mapping describes the driver's idea
    of it, and a log line that cannot say which is a log line that cannot
    explain a wrong binding.
    """
    guid: str
    source: str
    inputs: dict[str, Input]

    def get(self, control: str) -> Input | None:
        return self.inputs.get(control)

    def button(self, control: str) -> int | None:
        """The raw index, but ONLY when the control really is a button.

        A generator that writes `keyL=<n>` needs a button and nothing else: a
        DualShock 4's D-pad is a hat, and writing its hat number where a button
        index belongs gives a file the emulator loads in silence and ignores.
        Answering None makes that unwritable rather than plausible.
        """
        inp = self.inputs.get(control)
        return inp.index if inp is not None and inp.kind == "button" else None

    def has_digital_dpad(self) -> bool:
        """Whether the D-pad can be bound at all without falling back to a stick."""
        return any(i.kind in ("button", "hat")
                   for i in (self.get(d) for d in
                             ("dpup", "dpdown", "dpleft", "dpright"))
                   if i is not None)


# ── building it ──────────────────────────────────────────────────────────────

def _from_sdl(vendor: str, product: str, lib: str = "") -> PadInputs | None:
    """The model SDL itself reports for this pad, from ONE probe.

    `lib` picks which SDL2 answers — pass the emulator's own when it ships one.

    **Not the refusal `Pad.guid_for` makes, and the asymmetry is deliberate.**
    That one declines to answer with the host's SDL2 when an emulator's own
    cannot be reached, because a GUID encodes the BUS BYTE and the two disagree:
    `0x05` against `0x03` for the same Bluetooth pad, and Ryujinx resolves ids
    by equality, so the wrong one silently disposes the slot. A button ORDER is
    a property of the DRIVER, not of the enumerating library — every SDL2 with
    HIDAPI enabled reads a DualShock 4 through the same PS4 driver and reports
    the same b0..b11. So the host's answer is a fair proxy for the indices where
    it is not one for the id, and the pair returned here is still internally
    consistent because both halves come from the same call.
    """
    # Through the module, never `from .controllers import sdl2_probe`. Both of
    # these shell out to an SDL, so every test that is not about SDL replaces
    # them — and a name bound at import time is a second seam a stub does not
    # reach. The characterisation harness patches exactly this one, and its own
    # comment says why: a scenario declares its environment, it does not
    # inherit the machine's.
    answer = controllers.sdl2_probe(vendor, product, lib)
    guid, line = answer.get("guid", ""), answer.get("map", "")
    if not guid or "," not in line:
        return None
    found: dict[str, Input] = {}
    # Fields 0 and 1 are the GUID and the device name; the rest are bindings.
    for token in line.split(",")[2:]:
        control, _, value = token.partition(":")
        control = control.strip()
        if control not in CONTROLS:
            # `platform:Linux`, `crc:e58f`, `touchpad:b11` — real fields that
            # are not controls. Skipped rather than parsed, so a future SDL
            # field cannot arrive as a binding for something nobody asked for.
            continue
        parsed = parse_token(value)
        if parsed is not None:
            found[control] = parsed
    return PadInputs(guid=guid, source="sdl", inputs=found) if found else None


def _from_wizard(vendor: str, product: str, app_id: str = "") -> PadInputs | None:
    """The model the owner measured by hand, when it is safe to use.

    Thin on purpose: `derive.bindings_for` already holds the rule that decides
    it — a capture is only handed over when SDL reads the pad through the same
    driver the capture came from — and that rule was measured, is correct, and
    is not being restated here in a second place where the two could drift.

    Imported inside the function because `derive` imports the model FROM here:
    this module is the lower layer, and a module-level import either way round
    would make that a cycle.
    """
    from . import derive

    got = derive.bindings_for(vendor, product, app_id)
    if not got:
        return None
    guid, bindings = got
    return PadInputs(guid=guid, source="wizard",
                     inputs={control: inp for control, inp in bindings.items()
                             if control in CONTROLS})


def for_pad(pad, app_id: str = "") -> PadInputs | None:
    """Everything a generator needs to write bindings for `pad`, or None.

    None means neither source could answer, and a generator that gets it must
    write nothing at all. That is not a gap to be filled with a plausible
    default: a config of invented indices looks correct, survives reboots, and
    is undiagnosable from a sofa, which is the exact failure every refusal in
    this package exists to prevent.

    Ordered wizard-first. A capture is the owner's own work and it is more
    specific than a driver's table — and by the time it is offered at all,
    `evdev_driven()` has already established that it describes the driver SDL
    is really using. Where it is refused, SDL's own mapping is not a fallback
    but the right answer: it is the pad's mapping as the emulator will read it.
    """
    from_wizard = _from_wizard(pad.vendor, pad.product, app_id)
    if from_wizard is not None:
        return from_wizard
    # `app_id` is empty for an emulator this box runs natively — see
    # `configgen.generator_opts`, where "what does the box actually launch"
    # decides it — and then the host's SDL2 IS that emulator's SDL2.
    return _from_sdl(pad.vendor, pad.product,
                     controllers.bundled_sdl2(app_id) if app_id else "")
