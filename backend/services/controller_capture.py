"""Live pad capture — turning "the owner pressed this" into an SDL mapping line.

The wizard shows one button at a time and waits. What arrives from the kernel is
an evdev event: a key code like `BTN_SOUTH` (0x130), or an absolute axis. What
has to be WRITTEN is SDL's own vocabulary — `b0`, `a3`, `h0.1` — where the
numbers are SDL's joystick indices, not the kernel's codes.

Nothing bridges those two by inspection. SDL assigns its indices by walking the
device's declared capabilities in a fixed order, so index 0 is "the first button
this device declares", and the same physical button is a different number on a
pad that declares one extra key. `sdl_layout()` reproduces that walk.

**Reproducing it is a claim about someone else's code, so it is measured rather
than trusted.** `scripts/verify-sdl-layout.py` creates a virtual pad through
/dev/uinput, asks the real SDL how many buttons, axes and hats it sees and which
GUID it computed, and compares. It is not in the suite — CI has no /dev/uinput —
but `test_controller_capture.py` replays the layouts that script measured, so
the derivation is locked against real answers rather than against itself.

## Why a session, and why it is keyed by controller and not by node

A Bluetooth pad publishes several `event*` nodes. Reading one picked by
convention gives a wizard where some buttons never register, and it is not even
stable between boots. The session opens every node
`controller_registry.nodes_by_key()` groups under the pad's MAC, and merges
them.
"""
from __future__ import annotations

import asyncio
import glob
import logging
import time
from dataclasses import dataclass, field

from . import controller_registry
from .configgen import mapping_db
from .configgen.controllers import (
    bundled_sdl2,
    detect_pads,
    display_name,
    flatpak_location,
    sdl2_probe,
)

log = logging.getLogger(__name__)

# evdev constants. Spelled out rather than imported from `evdev`, because this
# half of the module must stay importable — and testable — on a box where
# python-evdev is not installed, which is every CI runner.
EV_KEY, EV_ABS = 0x01, 0x03
BTN_JOYSTICK = 0x120
KEY_MAX = 0x2FF
ABS_HAT0X, ABS_HAT3Y = 0x10, 0x17
ABS_MAX = 0x40

# The SDL hat bitmask, which is NOT the kernel's representation: evdev reports a
# hat as two signed axes and SDL folds them into one bitfield per hat.
HAT_UP, HAT_RIGHT, HAT_DOWN, HAT_LEFT = 1, 2, 4, 8


@dataclass(frozen=True)
class Layout:
    """SDL's view of one device's inputs, derived from its evdev capabilities.

    Each map is `evdev code → SDL index`. A code the device does not declare is
    simply absent, which is what makes a press on an undeclared input
    unmappable rather than mapped to something plausible and wrong.
    """
    buttons: dict[int, int] = field(default_factory=dict)
    axes: dict[int, int] = field(default_factory=dict)
    hats: dict[int, int] = field(default_factory=dict)

    @property
    def counts(self) -> tuple[int, int, int]:
        """(buttons, axes, hats) — what SDL reports through its Num* calls, and
        the cheapest thing to compare a derivation against."""
        return len(self.buttons), len(self.axes), len(set(self.hats.values()))


def sdl_layout(key_codes, abs_codes) -> Layout:
    """SDL's joystick indices for a device declaring these evdev codes.

    The walk is SDL's, from its Linux joystick driver, and the ORDER is the
    whole content of this function:

      1. buttons from BTN_JOYSTICK (0x120) up to KEY_MAX, ascending;
      2. then buttons BELOW BTN_JOYSTICK, ascending. Keyboard-range keys on a
         pad — some arcade sticks and clones declare them — land after the
         real buttons rather than before, and getting this backwards shifts
         every index a gamepad actually uses;
      3. axes from 0 to ABS_MAX ascending, SKIPPING the hat range entirely;
      4. hats, in pairs, from ABS_HAT0X.

    Identical in SDL2 and SDL3 — both were measured through /dev/uinput, see
    the module docstring.
    """
    keys = sorted(set(key_codes))
    absolutes = sorted(set(abs_codes))

    buttons: dict[int, int] = {}
    for code in keys:
        if BTN_JOYSTICK <= code < KEY_MAX:
            buttons[code] = len(buttons)
    for code in keys:
        if code < BTN_JOYSTICK:
            buttons[code] = len(buttons)

    axes: dict[int, int] = {}
    for code in absolutes:
        if ABS_HAT0X <= code <= ABS_HAT3Y or code >= ABS_MAX:
            continue
        axes[code] = len(axes)

    hats: dict[int, int] = {}
    for base in range(ABS_HAT0X, ABS_HAT3Y + 1, 2):
        if base in absolutes or base + 1 in absolutes:
            index = len(set(hats.values()))
            for code in (base, base + 1):
                if code in absolutes:
                    hats[code] = index

    return Layout(buttons=buttons, axes=axes, hats=hats)


def binding_for(layout: Layout, ev_type: int, code: int, value: int,
                flat: int = 0) -> str | None:
    """The SDL token for one event, or None when it says nothing.

    `flat` is the axis's rest zone as the kernel reports it; anything inside is
    noise. A resting analogue stick drifts by a few counts continuously, and
    without this the wizard binds the first button to whichever stick happened
    to twitch — measured as the single most common way a naive capture loop
    produces a garbage mapping.
    """
    if ev_type == EV_KEY:
        if value != 1:                       # presses only, never the release
            return None
        index = layout.buttons.get(code)
        return f"b{index}" if index is not None else None

    if ev_type != EV_ABS:
        return None

    if code in layout.hats:
        hat = layout.hats[code]
        if value == 0:
            return None
        horizontal = (code - ABS_HAT0X) % 2 == 0
        if horizontal:
            mask = HAT_RIGHT if value > 0 else HAT_LEFT
        else:
            mask = HAT_DOWN if value > 0 else HAT_UP
        return f"h{hat}.{mask}"

    index = layout.axes.get(code)
    if index is None:
        return None
    if abs(value) <= max(flat, 0):
        return None
    # A full axis, signed. The wizard tells the two halves apart itself: a
    # stick step keeps `a3`, a trigger step narrows it to `+a3`, because a
    # trigger that rests at its minimum and a stick that rests at centre are
    # the same event here and only the caller knows which was asked for.
    return f"a{index}"


def half_axis(binding: str, value: int) -> str:
    """`a3` → `+a3` or `-a3`. For the steps where the direction is the point —
    a trigger, or a stick direction bound to a d-pad."""
    if not binding.startswith("a"):
        return binding
    return ("+" if value > 0 else "-") + binding


# ── what the wizard asks for, in order ───────────────────────────────────────
# SDL's own output names. The order is the order the buttons are asked for on
# screen, chosen so the face buttons — the ones every pad has — come first and a
# session abandoned halfway still produced something usable.
STEPS: tuple[tuple[str, str, str], ...] = (
    ("a",             "button", "A / Cross — the confirm button"),
    ("b",             "button", "B / Circle — the back button"),
    ("x",             "button", "X / Square"),
    ("y",             "button", "Y / Triangle"),
    ("dpup",          "button", "D-pad up"),
    ("dpdown",        "button", "D-pad down"),
    ("dpleft",        "button", "D-pad left"),
    ("dpright",       "button", "D-pad right"),
    ("leftshoulder",  "button", "Left shoulder (L1 / LB)"),
    ("rightshoulder", "button", "Right shoulder (R1 / RB)"),
    ("lefttrigger",   "axis",   "Left trigger (L2 / LT)"),
    ("righttrigger",  "axis",   "Right trigger (R2 / RT)"),
    ("back",          "button", "Select / Share / View"),
    ("start",         "button", "Start / Options / Menu"),
    ("guide",         "button", "The big centre button (PS / Xbox / Home)"),
    ("leftstick",     "button", "Press the LEFT stick down (L3)"),
    ("rightstick",    "button", "Press the RIGHT stick down (R3)"),
    ("leftx",         "axis",   "Left stick — push RIGHT"),
    ("lefty",         "axis",   "Left stick — push DOWN"),
    ("rightx",        "axis",   "Right stick — push RIGHT"),
    ("righty",        "axis",   "Right stick — push DOWN"),
)

# Steps a pad may legitimately not have. The wizard lets any step be skipped,
# but only these produce a mapping that is complete rather than crippled — the
# distinction the UI needs to decide whether to warn.
OPTIONAL = frozenset({"guide", "leftstick", "rightstick",
                      "rightx", "righty", "lefttrigger", "righttrigger"})


def mapping_line(guid: str, name: str, bindings: dict[str, str],
                 platform: str = "Linux") -> str:
    """One SDL_GameControllerDB line.

    Fields are emitted in STEPS order rather than in whatever order the wizard
    filled them, so the same pad mapped twice produces the same line and a diff
    between two captures is readable.
    """
    if not name.strip():
        raise ValueError("a mapping line needs a device name")
    parts = [guid.lower(), name.strip().replace(",", " ")]
    for field_name, _kind, _label in STEPS:
        token = bindings.get(field_name)
        if token:
            parts.append(f"{field_name}:{token}")
    if len(parts) <= 2:
        raise ValueError("a mapping line needs at least one binding")
    parts.append(f"platform:{platform}")
    return ",".join(parts) + ","


# ── which GUIDs to write the line for ────────────────────────────────────────

def sdl_guids(vendor: str, product: str, app_ids=()) -> list[str]:
    """Every distinct GUID an SDL on this box computes for this pad.

    Not one GUID, several, and that is the same fact `Pad.guid_for()` is built
    around: each Flatpak brings its own SDL and the same pad therefore has
    several simultaneous identities — a DualShock 4 is `0500…` to the host's
    SDL3 and `0300…` to Ryujinx's bundled SDL2, one byte of bus type apart.

    A mapping filed under one of them is invisible to the emulators that
    compute another. Since a `gamecontrollerdb` file may carry as many lines as
    it likes and SDL only ever looks up the GUID it computed itself, writing one
    line per identity costs a few hundred bytes and removes the entire class of
    "it works in RPCS3 and not in Ryujinx".

    Ordered, deduplicated, host first.
    """
    found: list[str] = []

    def add(guid: str | None) -> None:
        if guid and len(guid) == 32 and guid.lower() not in found:
            found.append(guid.lower())

    add(sdl2_probe(vendor, product).get("guid"))
    for app_id in app_ids:
        if not app_id or not flatpak_location(app_id):
            continue
        lib = bundled_sdl2(app_id)
        if lib:
            add(sdl2_probe(vendor, product, lib).get("guid"))
    return found


def _profilable_app_ids() -> list[str]:
    """The app ids of the packs that profile controllers.

    Read from the catalogue rather than listed here: a hardcoded tuple in this
    file is exactly the single-source-of-truth break that made
    `profilable_packs()` miss a new emulator entirely.
    """
    try:
        from .catalog import load_catalog
        from .configgen import profilable_packs
        return [p.app_id for p in profilable_packs(load_catalog()) if p.app_id]
    except Exception:
        log.warning("controller_capture: could not read the catalogue for "
                    "bundled-SDL ids", exc_info=True)
        return []


# ── the session ──────────────────────────────────────────────────────────────

# A session left open holds file descriptors on /dev/input and keeps the pad's
# events away from nothing at all — reading is non-exclusive — but it is still
# state, and the UI it belongs to is one a player can walk away from. Ten
# minutes is long enough for the slowest pass through 21 buttons.
SESSION_TTL = 600.0


@dataclass
class Session:
    """One pad being mapped. Never more than one at a time.

    A session is keyed by CONTROLLER (`controller_registry.key_for`), never by
    devnode — see the module docstring.
    """
    id: str
    key: str
    vendor: str
    product: str
    name: str
    nodes: list[str]
    layouts: dict[str, Layout]
    guids: list[str]
    started: float

    @property
    def expired(self) -> bool:
        return time.monotonic() - self.started > SESSION_TTL


_session: Session | None = None


def current() -> Session | None:
    global _session
    if _session is not None and _session.expired:
        log.info("controller_capture: session %s expired", _session.id)
        _session = None
    return _session


def cancel() -> bool:
    """Drop the open session. True when there was one."""
    global _session
    had = _session is not None
    _session = None
    return had


def _pad_nodes(vendor: str, product: str) -> tuple[str, dict[str, Layout]]:
    """(registry key, {devnode: layout}) for the pad with this vendor:product.

    Every node the pad owns, grouped by `nodes_by_key` — the whole reason this
    is not a single `InputDevice` — and each with its OWN layout: the touchpad
    node of a DualShock 4 declares different capabilities from its gamepad
    node, so one shared layout would number the buttons of one from the
    capabilities of the other.
    """
    import evdev

    candidates: list[tuple[str | None, str]] = []
    caps: dict[str, tuple[list[int], list[int]]] = {}
    for path in sorted(glob.glob("/dev/input/event*")):
        try:
            dev = evdev.InputDevice(path)
        except (PermissionError, OSError):
            continue
        try:
            info = dev.info
            if (f"{info.vendor:04x}", f"{info.product:04x}") != (vendor, product):
                continue
            capabilities = dev.capabilities()
            keys = list(capabilities.get(EV_KEY, []))
            absolutes = [a[0] if isinstance(a, tuple) else a
                         for a in capabilities.get(EV_ABS, [])]
            candidates.append((dev.uniq or None, path))
            caps[path] = (keys, absolutes)
        finally:
            dev.close()

    if not candidates:
        return "", {}
    grouped = controller_registry.nodes_by_key(candidates)
    # One vendor:product, so one key in all but the case where two identical
    # pads are connected — and then the wizard has already refused to start.
    key, paths = next(iter(grouped.items()))
    return key, {p: sdl_layout(*caps[p]) for p in paths}


def start() -> dict:
    """Open a capture session on the one connected pad.

    Exactly one, deliberately, and it is the same rule "Scan mapping" applies
    next door: with two pads connected there is no way to know which one the
    owner is holding, and a mapping filed under the wrong GUID is worse than no
    mapping — it is a wrong answer that survives reboots.
    """
    global _session
    pads = detect_pads()
    if len(pads) != 1:
        return {"ok": False,
                "error": ("connect exactly one controller — the one you want "
                          f"to map — and disconnect the others (found {len(pads)})")}
    vendor, product, evdev_name = pads[0]

    try:
        key, layouts = _pad_nodes(vendor, product)
    except ImportError:
        return {"ok": False,
                "error": "python-evdev is not installed — no pad can be read"}
    if not layouts:
        return {"ok": False,
                "error": (f"{vendor}:{product} was detected but none of its "
                          f"/dev/input nodes could be opened. Is the backend's "
                          f"account in the `input` group?")}

    guids = sdl_guids(vendor, product, _profilable_app_ids())
    if not guids:
        return {"ok": False,
                "error": ("no SDL on this box could name a GUID for this pad, "
                          "so there is nothing to file a mapping under")}

    _session = Session(
        id=f"{key}-{int(time.time())}",
        key=key, vendor=vendor, product=product,
        name=display_name(vendor, product, evdev_name),
        nodes=sorted(layouts), layouts=layouts, guids=guids,
        started=time.monotonic())
    log.info("controller_capture: mapping %s (%s:%s) over %d node(s), %d GUID(s)",
             _session.name, vendor, product, len(layouts), len(guids))
    return {"ok": True, "session": _session.id, "controller": _session.name,
            "vendor": vendor, "product": product, "guids": guids,
            "nodes": _session.nodes,
            "steps": [{"field": f, "kind": k, "label": lbl}
                      for f, k, lbl in STEPS],
            "optional": sorted(OPTIONAL)}


async def events(session: Session):
    """Yield `{binding, kind, code, value}` for every press on the pad.

    Reads all of the pad's nodes at once. Read-only on /dev/input, which is
    what the whole capture path is: no ioctl that writes, no grab. Grabbing
    would take the pad away from the running UI, and the owner would have no
    way to cancel the wizard.
    """
    import evdev

    devices = []
    for path in session.nodes:
        try:
            devices.append(evdev.InputDevice(path))
        except (PermissionError, OSError):
            log.debug("controller_capture: cannot open %s", path)
    if not devices:
        return

    flats: dict[tuple[str, int], int] = {}
    for dev in devices:
        for entry in dev.capabilities().get(EV_ABS, []):
            if isinstance(entry, tuple):
                code, info = entry
                flats[(dev.path, code)] = getattr(info, "flat", 0) or 0

    queue: asyncio.Queue = asyncio.Queue()

    async def pump(dev) -> None:
        try:
            async for event in dev.async_read_loop():
                await queue.put((dev.path, event))
        except asyncio.CancelledError:
            raise
        except Exception:
            log.debug("controller_capture: %s stopped", dev.path)

    tasks = [asyncio.create_task(pump(d), name=f"capture:{d.path}")
             for d in devices]
    try:
        while True:
            path, event = await queue.get()
            layout = session.layouts.get(path)
            if layout is None:
                continue
            flat = flats.get((path, event.code), 0)
            token = binding_for(layout, event.type, event.code, event.value, flat)
            if token is None:
                continue
            yield {"binding": token,
                   "kind": "button" if event.type == EV_KEY else "axis",
                   "signed": half_axis(token, event.value),
                   "code": event.code, "value": event.value, "node": path}
    finally:
        for task in tasks:
            task.cancel()
        for dev in devices:
            try:
                dev.close()
            except Exception:
                pass


def commit(bindings: dict[str, str], name: str = "") -> dict:
    """Write the captured mapping — one line per GUID — and rebuild the DB.

    Returns the lines written, so the UI can put one on the clipboard for
    SDL_GameControllerDB. A mapping that only ever lives on this box helps this
    box; contributed upstream it reaches everyone with the same pad, which is
    how the community file the box already ships got written.
    """
    session = current()
    if session is None:
        return {"ok": False, "error": "no capture session is open — start one first"}
    usable = {f: t for f, t in bindings.items()
              if t and f in {step[0] for step in STEPS}}
    if not usable:
        return {"ok": False, "error": "nothing was captured"}

    label = (name or session.name).strip()
    lines = []
    for guid in session.guids:
        try:
            line = mapping_line(guid, label, usable)
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        mapping_db.upsert(line)
        lines.append(line)

    missing = sorted({step[0] for step in STEPS} - set(usable) - OPTIONAL)
    cancel()
    log.info("controller_capture: saved %d line(s) for %s (%d bindings)",
             len(lines), label, len(usable))
    return {"ok": True, "controller": label, "lines": lines,
            "bindings": len(usable), "missing": missing,
            "database": str(mapping_db.USER_DB)}
