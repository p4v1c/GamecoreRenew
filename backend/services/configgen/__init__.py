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
from pathlib import Path

from ..catalog import load_catalog
from . import snapshots
from .controllers import Pad, detect_pads, resolve_name
from .helpers.base import Skip

log = logging.getLogger(__name__)

# The order emulators are profiled in. Not a catalogue fact — it is the order
# the pre-refactor `apply_profile` used, and it decides the order of the
# messages in the TV toast. Kept explicit so a refactor that was supposed to
# move code does not quietly reorder what the player sees.
STEP_ORDER = ("ryujinx", "azahar", "mgba", "cemu", "gopher64",
              "dolphin", "rpcs3", "pcsx2", "duckstation", "melonds")

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


def resolve_config_dir(pack, home: Path) -> Path | None:
    """Where this emulator's config actually lives on THIS box.

    `@FLATPAK_CONFIG@` expands from the same `install.appId` the installer
    installs — that is what makes a phantom config directory unexpressible.

    `nativeDest` exists for the emulators a box can run outside Flatpak (mgba,
    melonds). The tree that EXISTS wins, native first: a native tree kept as a
    post-migration backup must not shadow a live flatpak, and a curated config
    written next to an uninstalled flatpak is never read by anything.
    """
    cfg = pack.data.get("config")
    if not cfg:
        return None
    app_id = pack.app_id

    def expand(value: str) -> Path:
        return Path(value
                    .replace("@FLATPAK_CONFIG@", f"{home}/.var/app/{app_id}/config")
                    .replace("@HOME@", str(home)))

    flatpak_dir = expand(cfg["dest"])
    native = cfg.get("nativeDest")
    if native:
        native_dir = expand(native)
        # The flatpak app directory, not the config subdir: it exists as soon
        # as the app is installed, even before it has written a config.
        if not (home / ".var/app" / app_id).is_dir() and native_dir.is_dir():
            return native_dir
    return flatpak_dir


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
        "app_id": pack.app_id,
        "snap_dir": snap_dir,
        "home": home,
    }


def profilable_packs(packs: dict) -> list:
    """Packs that profile controllers at all, in the documented order."""
    out = []
    for pid in STEP_ORDER:
        pack = packs.get(pid)
        if pack is None:
            continue
        ctl = pack.data.get("controllers") or {}
        if ctl.get("strategy", "none") == "none" or ctl.get("maxPlayers", 0) < 1:
            continue
        out.append(pack)
    return out


# Patched by the characterisation harness, and by nothing else at runtime.
HOME = Path.home()
SNAP_DIR = HOME / ".local/share/gamecore/controller-snapshots"


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

    def __init__(self, results=(), skipped=()):
        super().__init__(results)
        self.skipped: list[str] = list(skipped)

    @property
    def complete(self) -> bool:
        return not self.skipped


def apply_profile(player_index: int, vendor: str, product: str, evdev_name: str,
                  dup_index: int = 0) -> ProfileResult:
    """Write every emulator's native config for `player_index`, live.

    Called by gamepad_monitor on every new slot. Never raises — each emulator
    is isolated so one bad config does not block the others.
    """
    if player_index < 1 or player_index > 4:
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
            continue

        if isinstance(msg, Skip):
            skipped.append(str(msg))
        elif msg:
            results.append(msg)

    if skipped:
        log.warning("configgen: player %d (%s:%s) — not configured: %s",
                    player_index, vendor, product, "; ".join(skipped))
    return ProfileResult(results, skipped)


def release_profile(player_index: int) -> list[str]:
    """Undo the "connected player" state a disconnected pad leaves behind.

    Only Dolphin needs it today — its emulated Wii Remote stays presented to
    the game as connected. Role/device bound emulators just go input-less when
    a pad leaves. Never raises.
    """
    if player_index < 1 or player_index > 4:
        return []
    results: list[str] = []
    for pack in profilable_packs(load_catalog()):
        module = load_generator(pack)
        if module is None or not hasattr(module, "release"):
            continue
        opts = generator_opts(pack, HOME, SNAP_DIR)
        if opts is None:
            continue
        try:
            results.extend(module.release(player_index, opts))
        except Exception:
            log.exception("configgen: %s release failed for player %d",
                          pack.id, player_index)
    return results


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
    return {"ok": True, "controller": resolve_name(vendor, product, evdev),
            "saved": saved, "refused": refused}
