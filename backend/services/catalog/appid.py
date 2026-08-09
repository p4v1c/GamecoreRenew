"""Which Flatpak app id a pack actually means, on THIS box.

A pack declares `install.appIds`: an ordered list of candidates, best first.
One list, because an upstream can vanish. Ryujinx original went from Flathub
with no warning; Ryubing is one maintainer's decision away from the same. The
day it happens, a pack that had spelled a single id in `install.appId` and
again in `launch.args` broke twice — the install could not find it, and the
tile went on launching a name that no longer existed. Neither said so.

Resolution has two moments and they are NOT the same question:

    installing   which candidate does the REMOTE still offer?   providers.py
    everything   which candidate is on this disk RIGHT NOW?     here
    else

This module answers the second. It is what `@FLATPAK_CONFIG@`, `@FLATPAK_DATA@`
and the `@APPID@` in a launcher expand through, so a box that fell back to the
second candidate at install time keeps its config directory, its BIOS directory
and its launcher pointing at the same application — instead of installing one
emulator and configuring another.

Why the probe is opt-in
-----------------------
`resolve()` with nothing recorded returns the FIRST declared id. That is not a
placeholder, it is the honest answer: with no information about the box, the
pack's own preference order is all there is, and it is exactly what the single
`appId` field used to give.

The alternative — probing `flatpak list` lazily on first access — was rejected.
It would make `Pack.app_id` shell out from inside `gen-catalog.py`, from the
schema checker and from every test that loads the catalogue, and it would make
the generated `.dist` files depend on which emulators happen to be installed on
the machine that ran the build. A build artefact that differs per developer is
not a build artefact.

So the box opts in: a process that has a box to look at calls `probe()` once
and every later `resolve()` is informed. A process that does not — the build,
CI, the test suite — never touches flatpak and gets deterministic output.
"""
from __future__ import annotations

import logging
import subprocess

log = logging.getLogger(__name__)

# None = never probed, "we do not know what is installed".
# Deliberately distinct from frozenset(): "probed, and nothing is installed" is
# a different fact, and only the second one justifies reporting a pack missing.
_installed: frozenset[str] | None = None


def installed() -> frozenset[str] | None:
    return _installed


def set_installed(app_ids: set[str] | None) -> None:
    """Record what is on this box. `None` puts it back to unknown.

    Public because the test suite needs to describe a box without one, and
    because `gamecore-emu` already runs `flatpak list` for its own output and
    should not run it twice.
    """
    global _installed
    _installed = None if app_ids is None else frozenset(app_ids)


def probe(timeout: int = 60) -> frozenset[str] | None:
    """Ask flatpak what is installed, and remember it.

    A failed or unreadable query stays `None`. It means we cannot SEE the
    installation — wrong scope, flatpak not initialised, a sandbox — not that
    nothing is installed, and the difference decides whether a tile gets pruned
    off the grid. Same rule as flatpakify's prune.
    """
    try:
        r = subprocess.run(["flatpak", "list", "--app", "--columns=application"],
                           capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            log.warning("appid: flatpak list exited %s — app ids stay unresolved",
                        r.returncode)
            set_installed(None)
            return None
        set_installed({line.strip() for line in r.stdout.splitlines() if line.strip()})
    except (OSError, subprocess.SubprocessError) as e:
        log.warning("appid: flatpak could not be queried (%s) — app ids stay "
                    "unresolved", e)
        set_installed(None)
    return _installed


def resolve(app_ids: list[str], installed_ids: frozenset[str] | None = None) -> str:
    """The candidate this box means, or the first declared one.

    Falling back to `app_ids[0]` when nothing matches is deliberate: a pack
    whose emulator is not installed yet still has to name a config directory
    and a launcher, and "the one we would install" is the only defensible
    answer. It is also what makes a fresh box, where nothing is installed at
    all, behave exactly as it did before this field existed.
    """
    if not app_ids:
        return ""
    have = _installed if installed_ids is None else installed_ids
    if have is not None:
        for candidate in app_ids:
            if candidate in have:
                return candidate
    return app_ids[0]


def declared(pack_data: dict) -> list[str]:
    """`install.appIds` for a Flatpak pack, [] for anything else.

    A pack whose provider is not flatpak has no app id at all, and returning
    the list anyway would let a github-asset pack express a `@FLATPAK_CONFIG@`
    that resolves against something it never installs — the gopher64 class of
    bug this whole field exists under.
    """
    install = pack_data.get("install") or {}
    if install.get("provider") != "flatpak":
        return []
    return list(install.get("appIds") or [])
