"""Config generation: apply a pack's seed, then run its generator.

One generator per emulator, living in `catalog/<id>/generator.py`, behind a
common controller abstraction. That structure is taken from Batocera's
configgen; the CONTENT of each generator is this project's, and where the two
disagreed the measurements on the reference box decided — see
`backend/tests/characterisation.py` for the pads and the GUIDs they produced.

**The deliberate divergence.** Batocera regenerates every config at launch and
overwrites the owner's edits. GameCore does the opposite: a generator writes
ONLY the sections GameCore owns and leaves the rest of the file intact, to the
byte. That is what makes `.bak-preinstall` and the snapshot mechanism coherent.

Nothing here decides WHEN to run. `gamepad_monitor._reconcile()` does, on every
roster change, and re-profiles every slot whose `(vendor, product, resolved
name, dup)` footprint moved — those counters describe the ROSTER, so one pad
leaving invalidates the others.
"""
from __future__ import annotations

import importlib.util
import logging
from collections.abc import Collection
from pathlib import Path

from ..catalog import load_catalog
from . import snapshots
from .controllers import SDL3_TRUSTED, Pad, detect_pads, display_name, resolve_name
from .helpers.base import Skip

log = logging.getLogger(__name__)

_generator_cache: dict[str, object] = {}


def load_generator(pack):
    """Import `catalog/<id>/generator.py`, or None.

    A pack in `config/catalog.d/` never reaches here with a generator: the
    loader strips it unless the operator opted in. Executing a generator is
    exactly the "drop a directory = arbitrary code execution" the data-only
    rule exists to prevent.
    """
    if pack.id in _generator_cache:
        return _generator_cache[pack.id]
    path = pack.generator
    module = None
    if path is not None:
        try:
            spec = importlib.util.spec_from_file_location(
                f"gamecore_generator_{pack.id}", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception:
            log.exception("configgen: %s/generator.py failed to import", pack.id)
            module = None
    _generator_cache[pack.id] = module
    return module


def launches_flatpak(pack) -> bool:
    """Whether THIS box starts this pack's Flatpak, or a native binary.

    `pack.launcher(prefer_existing=True)` is the same answer the tile is built
    from, resolved against what is on the box right now — so this asks the
    question by consulting the decision rather than by guessing at it again.

    Defaults to True, because that is what a pack with no `preferIfPresent`
    means and what every failure to answer should degrade to: `dest` is the
    declared home and `nativeDest` is the exception.
    """
    launch = pack.data.get("launch")
    if not launch:
        return True
    try:
        path, _args = pack.launcher(prefer_existing=True)
    except Exception:
        log.warning("configgen: could not resolve %s's launcher — assuming the "
                    "flatpak", pack.id, exc_info=True)
        return True
    return Path(path).name == "flatpak"


def resolve_config_dir(pack, home: Path) -> Path | None:
    """Where this emulator's config actually lives on THIS box.

    `@FLATPAK_CONFIG@` expands from the same `install.appIds` entry the box
    installs — that is what makes a phantom config directory unexpressible.

    `nativeDest` exists for the emulators a box can run outside Flatpak (mgba,
    melonds). **What the box LAUNCHES decides, not which directory exists.**

    It used to be the second, and the reference box is the counter-example the
    rule was missing. `io.mgba.mGBA` is not installed there; mGBA runs natively
    through `preferIfPresent: /usr/bin/mgba-qt` and reads
    `~/.config/mgba/config.ini`. But `~/.var/app/io.mgba.mGBA/` was still on
    disk from an install months earlier — the flatpak was removed, its data
    directory was not — so the "tree that exists" test chose the flatpak's, and
    every mapping the pipeline wrote for a year went into a file nothing reads.
    Both defences the old rule was built on survive the change, because they
    were both really about which binary runs: a native tree kept as a
    post-migration backup does not shadow a live flatpak (the box launches the
    flatpak), and a config written next to an uninstalled flatpak cannot happen
    at all (the box launches the native binary).
    """
    cfg = pack.data.get("config")
    if not cfg:
        return None

    def expand(value: str) -> Path:
        return pack.expand(value, home)

    native = cfg.get("nativeDest")
    if native and not launches_flatpak(pack):
        return expand(native)
    return expand(cfg["dest"])


def generator_opts(pack, home: Path, snap_dir: Path) -> dict | None:
    """What a generator receives besides the player index and the pad."""
    config_dir = resolve_config_dir(pack, home)
    if config_dir is None:
        return None
    ctl = pack.data.get("controllers") or {}
    target = ctl.get("target")
    if isinstance(target, list):
        target = target[0]
    return {
        "config_dir": config_dir,
        "target": config_dir / target if target else config_dir,
        "controllers": ctl,
        # Empty when the box runs the native binary, and that is the same
        # correction `resolve_config_dir` makes one line up: an app id is how a
        # consumer reaches THAT EMULATOR'S OWN SDL2 — `Pad.guid_for` and
        # `inputs.for_pad` both take it — and an emulator running outside its
        # flatpak does not have one. Passing the declared id anyway made
        # `guid_for` refuse to answer at all for mGBA ("cannot locate
        # io.mgba.mGBA"), when the truthful answer is that the host's SDL2 is
        # the one it links.
        "app_id": pack.app_id if launches_flatpak(pack) else "",
        "snap_dir": snap_dir,
        "home": home,
    }


def profilable_packs(packs: dict) -> list:
    """Packs that profile controllers at all, in the order they declare.

    The order decides what the player reads in the toast when a pad is plugged
    in, so it is deliberate rather than alphabetical — but it belongs to the
    pack, under `controllers.order`, and not to a tuple in this file.

    It WAS a tuple in this file, and `packs.get(pid)` meant a pack missing from
    it was not profiled at all: a new emulator shipping a generator.py and a
    controllers block had its bindings silently never written, and the only
    symptom was a pad that did nothing in that one emulator.

    No order means last, never absent.
    """
    profilable = []
    for pack in packs.values():
        ctl = pack.data.get("controllers") or {}
        if ctl.get("strategy", "none") == "none" or ctl.get("maxPlayers", 0) < 1:
            continue
        profilable.append(pack)
    return sorted(profilable,
                  key=lambda p: (p.data["controllers"].get("order", 10_000), p.id))


# Patched by the characterisation harness, and by nothing else at runtime.
HOME = Path.home()
SNAP_DIR = HOME / ".local/share/gamecore/controller-snapshots"

# How many player slots this box profiles at all. The pack schema caps
# `controllers.maxPlayers` at the same number, and apply_profile /
# release_profile share this one name so the two halves of the pair can never
# drift apart — the write side once knew a ceiling the un-write side did not.
MAX_PLAYERS = 4


class ProfileResult(list):
    """What a profiling pass wrote, plus whether any step gave up.

    A `list` subclass because every caller — the toast, the log line, the
    tests — already treats the return value as the list of messages, and only
    the monitor needs the extra bit.

    That bit matters: a pass that skipped an emulator is not finished, and the
    monitor used to have no way to tell. A transient failure looked exactly
    like a clean pass — which is how a DualShock 4's Ryujinx slot went missing
    for good after SDL simply had not caught up with a fresh Bluetooth
    connection.
    """

    def __init__(self, results=(), skipped=(), skipped_labels=()):
        super().__init__(results)
        self.skipped: list[str] = list(skipped)
        # The same give-ups named the way the player names them. `skipped`
        # holds diagnostics — "ryujinx: SDL2 would not report a GUID for
        # 045e:02fd" — which belong in the journal and read as noise on a TV;
        # this holds "Nintendo Switch". Collected here rather than parsed back
        # out of the messages, because a pack id is not a system name and the
        # prefix of a Skip string is not a promise.
        self.skipped_labels: list[str] = list(skipped_labels)

    @property
    def complete(self) -> bool:
        return not self.skipped


def apply_profile(player_index: int, vendor: str, product: str, evdev_name: str,
                  dup_index: int = 0) -> ProfileResult:
    """Write every emulator's native config for `player_index`, live.

    Called by gamepad_monitor on every new slot. Never raises — each emulator
    is isolated so one bad config does not block the others.
    """
    if player_index < 1 or player_index > MAX_PLAYERS:
        # The slot cap is deliberate, but a 5th pad used to get a player
        # number, a TV toast, and no config at all, without a word anywhere.
        # Not a Skip: a decision, not a failure, and retrying every three
        # seconds would never produce anything.
        log.warning("configgen: player %d is outside the 1-4 slots this box "
                    "profiles — %s:%s left unconfigured",
                    player_index, vendor, product)
        return ProfileResult()

    pad = Pad(vendor=vendor, product=product, evdev_name=evdev_name,
              dup_index=dup_index)
    results: list[str] = []
    skipped: list[str] = []
    skipped_labels: list[str] = []

    for pack in profilable_packs(load_catalog()):
        ctl = pack.data.get("controllers") or {}
        strategy = ctl.get("strategy")
        # Single-player hardware: only slot 1 is ever touched, whatever player
        # index arrives. melonDS lacked this guard once, so plugging in a
        # second pad rewrote its one and only player config for the wrong pad.
        if player_index > ctl.get("maxPlayers", 4):
            continue

        opts = generator_opts(pack, HOME, SNAP_DIR)
        if opts is None:
            continue
        module = load_generator(pack)
        if module is None:
            continue

        try:
            if strategy == "snapshot-or-synth":
                # A saved snapshot ALWAYS wins over the synthesis, and the test
                # is `exists()`, never a falsy return: restore() answers None
                # for two different reasons — no snapshot, or already applied —
                # and conflating them made the synthesis overwrite the owner's
                # captured mapping every other session.
                if snapshots.exists(SNAP_DIR, pack.id, vendor, product):
                    msg = snapshots.restore(
                        SNAP_DIR, pack.id, opts["target"],
                        module.extract, module.replace, vendor, product)
                else:
                    msg = module.generate(player_index, pad, opts)
            else:
                msg = module.generate(player_index, pad, opts)
        except Exception:
            log.exception("configgen: %s failed for player %d (%s:%s)",
                          pack.id, player_index, vendor, product)
            skipped.append(f"{pack.id}: internal error (see traceback)")
            skipped_labels.append(pack.data.get("label") or pack.id)
            continue

        if isinstance(msg, Skip):
            skipped.append(str(msg))
            skipped_labels.append(pack.data.get("label") or pack.id)
        elif msg:
            results.append(msg)

    if skipped:
        log.warning("configgen: player %d (%s:%s) — not configured: %s",
                    player_index, vendor, product, "; ".join(skipped))
    return ProfileResult(results, skipped, skipped_labels)


def release_profile(player_index: int,
                    occupied: Collection[int] = (),
                    pack_ids: Collection[str] | None = None) -> list[str]:
    """Un-write the slot a pad no longer holds — the inverse of apply_profile.

    This docstring used to say "only Dolphin needs it today; role/device bound
    emulators just go input-less when a pad leaves". The reference box proved
    that false. They do not go input-less: they keep NAMING an absent device.
    With one DualShock 4 connected, RPCS3 still presented "Xbox One Wireless
    Controller 3" as Player 4 and Ryujinx still held indexes 2 and 3. A PS3
    game at four then sees four players, two of whom cannot move — which is not
    the same thing as receiving no input.

    `occupied` is the set of slots a pad still holds AFTER this release, and it
    is not decoration. Some of what apply_profile writes belongs to the ROSTER
    and not to a slot: the multitap PCSX2 and DuckStation need before slot 3
    exists at all is the measured case. A release knowing only its own index
    can never decide those — it cannot tell whether player 3 is still sitting
    there. Empty means nobody is left, which is what the last pad leaving
    looks like.

    `pack_ids` narrows the pass to named packs. The hotplug path passes None
    and sweeps everything, because a pad leaving concerns every emulator. The
    launch path passes the one emulator about to start: rewriting Cemu's config
    because someone launched PCSX2 is a side effect nobody asked for, and it is
    also what would make the pass too slow to sit in front of a launch.

    Never raises: an emulator whose config cannot be un-written must not stop
    the others from being.
    """
    if player_index < 1 or player_index > MAX_PLAYERS:
        # Its twin logs the same ceiling eight lines up, and the comment there
        # says what the silence cost: "a 5th pad used to get a player number, a
        # TV toast, and no config at all, without a word anywhere". The lesson
        # had been applied to one half of the pair only. It matters here for a
        # different reason: the day MAX_PLAYERS rises, a release that stays
        # mute leaves the new slots permanently stale and says nothing.
        log.warning("configgen: player %d is outside the 1-%d slots this box "
                    "profiles — nothing released", player_index, MAX_PLAYERS)
        return []
    results: list[str] = []
    for pack in profilable_packs(load_catalog()):
        if pack_ids is not None and pack.id not in pack_ids:
            continue
        ctl = pack.data.get("controllers") or {}
        # Same guard apply_profile applies, for the same reason: a slot a pack
        # never writes is a slot it has nothing to un-write, and calling into
        # it would ask a single-player generator about a player it has no
        # concept of.
        if player_index > ctl.get("maxPlayers", MAX_PLAYERS):
            continue
        module = load_generator(pack)
        if module is None or not hasattr(module, "release"):
            continue
        opts = generator_opts(pack, HOME, SNAP_DIR)
        if opts is None:
            continue
        try:
            results.extend(module.release(player_index, opts, occupied))
        except Exception:
            log.exception("configgen: %s release failed for player %d",
                          pack.id, player_index)
    return results


def identification(vendor: str, product: str, evdev_name: str) -> dict:
    """Whether we know what an SDL3 emulator will call this pad.

    This is the give-up surfacing at the API, which is the point: a pad libSDL3
    does not enumerate gets no RPCS3 and no Dolphin config at all, and until now
    the only sign of that was a line in the EMULATOR's log. "Scan mapping" is
    exactly the moment the owner is holding the pad and asking what we know
    about it, so it is where the answer belongs.

    `identified: false` is not a failure of the scan — the snapshot emulators
    bind by GUID and work fine — so it rides alongside `ok`, not instead of it.
    """
    resolved = resolve_name(vendor, product, evdev_name)
    if resolved.source in SDL3_TRUSTED:
        return {"identified": True}
    return {
        "identified": False,
        "detail": (f"libSDL3 does not enumerate {vendor}:{product} and it is "
                   f"not in the known-pads table, so the name the SDL3-based "
                   f"emulators expect is unknown. Their configs are left "
                   f"untouched: writing the kernel's name instead gives a pad "
                   f"that is dead in game with a config that looks correct."),
    }


def scan_mapping() -> dict:
    """"Scan mapping": remember the ONE connected pad's current input config
    across the snapshot emulators, so it auto-restores on every future connect.

    `refused` is the emulators whose config describes a different pad — the
    user mapped one controller and pressed the button holding another, or never
    mapped that emulator at all. Saying so beats a green "ok" that quietly
    stores the wrong mapping under this pad's name.
    """
    pads = detect_pads()
    if len(pads) != 1:
        return {"ok": False,
                "error": ("connect exactly one controller (the one you just "
                          f"configured) — found {len(pads)}")}
    vendor, product, evdev = pads[0]
    saved: list[str] = []
    refused: list[str] = []
    for pack in profilable_packs(load_catalog()):
        module = load_generator(pack)
        if module is None or not hasattr(module, "extract"):
            continue
        opts = generator_opts(pack, HOME, SNAP_DIR)
        if opts is None:
            continue
        try:
            got = snapshots.capture(SNAP_DIR, pack.id, opts["target"],
                                    module.extract, vendor, product)
            if got:
                saved.append(got)
        except snapshots.Refused:
            refused.append(pack.id)
        except Exception:
            log.exception("configgen: capture failed for %s", pack.id)
    return {"ok": True, "controller": display_name(vendor, product, evdev),
            "saved": saved, "refused": refused,
            **identification(vendor, product, evdev)}


def forget_mapping() -> dict:
    """The inverse of "Scan mapping": drop the connected pad's saved configs.

    restore() refuses a snapshot whose GUID names another controller, and the
    box already carries one of those (cemu/045e_02fd.snap, a DualShock 4's
    config filed under an Xbox pad). Refusing without offering this would leave
    the owner informed and stuck: the file is not reachable from the couch, and
    the only other way out is a shell.

    Deliberately per-connected-pad and not per-emulator-id: the gesture the
    owner makes is "forget what you think you know about THIS controller",
    which is the same shape as the scan that created it.
    """
    pads = detect_pads()
    if len(pads) != 1:
        return {"ok": False,
                "error": ("connect exactly one controller (the one to forget) "
                          f"— found {len(pads)}")}
    vendor, product, evdev = pads[0]
    forgotten: list[str] = []
    for pack in profilable_packs(load_catalog()):
        try:
            if snapshots.forget(SNAP_DIR, pack.id, vendor, product):
                forgotten.append(pack.id)
        except OSError:
            log.exception("configgen: could not forget %s snapshot", pack.id)
    if forgotten:
        log.info("configgen: forgot saved mapping for %s:%s — %s",
                 vendor, product, ", ".join(forgotten))
    return {"ok": True, "controller": display_name(vendor, product, evdev),
            "forgotten": forgotten,
            **identification(vendor, product, evdev)}
