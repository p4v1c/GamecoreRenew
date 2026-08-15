"""Live per-slot controller profiling — the public face of the configgen.

The 1700 lines that used to live here are now one generator per emulator, in
`catalog/<id>/generator.py`, behind the shared layer in
`backend/services/configgen/`. **The logic was moved, not changed**: a
characterisation suite of fourteen pad × slot scenarios locks the output down
byte for byte (backend/tests/test_controller_characterisation.py).

This module stays because the rest of the project imports it — `gamepad_monitor`
calls `apply_profile()` on every new slot and `release_profile()` on unplug, and
that hotplug path must keep working exactly as it did.

Where each piece went:

    controllers.py              SDL/GUID resolution, the `Pad` object
    snapshots.py                capture/restore for the GUID-bound emulators
    helpers/base.py             Skip, backup(), atomic_write(), the protocol
    helpers/ini.py              INI section surgery
    helpers/tier0.py            PCSX2 + DuckStation (shared, not duplicated)
    catalog/<id>/generator.py   one emulator's own format

The reasoning that used to be in this docstring travels with the code: each
generator carries the comments explaining what its emulator does and which
failure taught us. `docs/architecture/08-controller-pipeline.md` is the map.
"""
from __future__ import annotations

import logging

from .configgen import (
    HOME,
    MAX_PLAYERS,
    SNAP_DIR,
    ProfileResult,
    apply_profile,
    forget_mapping,
    autoconfigured_packs,
    identification,
    profilable_packs,
    release_owned_slots,
    release_profile,
    scan_mapping,
    set_autoconfig,
)
from .configgen.controllers import (
    DB_FILE,
    SDL3_FALLBACK_NAMES,
    SDL3_TRUSTED,
    Pad,
    ResolvedName,
    bundled_sdl2,
    db_name_for,
    detect_pads,
    display_name,
    flatpak_location,
    pad_has_hat,
    resolve_name,
    ryu_guid_from_sdl2,
    ryu_guid_vidpid,
    sdl2_probe,
    sdl3_names,
    vidpid_of,
)
from .configgen.helpers.base import Skip, atomic_write, backup
from .configgen.helpers.ini import section, set_section
from .configgen.snapshots import block_disagrees

log = logging.getLogger(__name__)

__all__ = [
    # the hotplug path — gamepad_monitor.py
    "apply_profile", "release_profile", "ProfileResult", "MAX_PLAYERS",
    # the Power-menu actions — routers/controllers.py
    "scan_mapping", "forget_mapping", "detect_pads",
    # the autoconfig switch — routers/controllers.py. `release_owned_slots` is
    # the clean-up it runs before it turns itself off; the two pack lists are
    # what the settings screen lists and what it shows as effectively off.
    "set_autoconfig", "release_owned_slots", "autoconfigured_packs",
    "profilable_packs",
    # "can this pad be named at all" — the toast asks it on every arrival, so
    # the wizard is offered exactly where the player notices the pad is dead
    "identification",
    # the controller abstraction
    "Pad", "resolve_name", "display_name", "ResolvedName", "SDL3_TRUSTED",
    "sdl3_names", "sdl2_probe", "bundled_sdl2",
    "flatpak_location", "pad_has_hat", "db_name_for", "vidpid_of",
    "ryu_guid_from_sdl2", "ryu_guid_vidpid", "SDL3_FALLBACK_NAMES", "DB_FILE",
    # format helpers other modules and tests still reach for
    "section", "set_section", "backup", "atomic_write", "Skip",
    "block_disagrees", "HOME", "SNAP_DIR",
]


def _main() -> None:
    """install/steps/apply-controller-model.sh — a rescue tool, not the live path.

    Useful only for retargeting pads that are ALREADY connected without
    unplugging them. Day to day this is fully automatic via gamepad_monitor.
    """
    import sys

    if len(sys.argv) > 1:
        vendor, _, product = sys.argv[1].lower().partition(":")
        name = sys.argv[2] if len(sys.argv) > 2 else resolve_name(
            vendor, product, "Generic Controller")
        pads = [(vendor, product, name)]
    else:
        pads = detect_pads()
        if not pads:
            sys.exit("No connected gamepad found (checked evdev for a BTN_SOUTH "
                     "device). Pass VID:PID explicitly, or check permissions "
                     "(input group).")
    print(f"{'Auto-detected' if len(sys.argv) <= 1 else 'Forced'} "
          f"{len(pads)} controller(s):")
    for i, (v, p, n) in enumerate(pads, 1):
        print(f"  Player {i}: {resolve_name(v, p, n)}  ({v}:{p})")
    print()
    model_counts: dict[tuple[str, str], int] = {}
    for i, (v, p, n) in enumerate(pads, 1):
        dup = model_counts.get((v, p), 0)
        results = apply_profile(i, v, p, n, dup)
        model_counts[(v, p)] = dup + 1
        print(f"Player {i}: " + ("; ".join(results) if results else "nothing to do"))
    print("\nDone. This also happens automatically, live, whenever a controller "
          "connects (backend/services/gamepad_monitor.py).")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    _main()
