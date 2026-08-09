"""Resolve a tile's launcher against what is installed, at the moment of launch.

A tile in `config/systems.json` says `flatpak run @APPID@ -f`. It says that and
not an application id because a tile is written once — by an installer, or by
an OTA merge — and the set of installed Flatpaks goes on changing afterwards.
Baking the id in is what tied the launcher to the install: the day an upstream
disappeared, the installer moved to the fallback and the tile did not, so the
box installed one emulator and went on trying to start another. Nothing said
so; flatpak just reported an app that was not installed.

This is the other half of `install.appIds`. The catalogue decides WHICH ids are
acceptable; this decides which one is here, one launch at a time.

Cheap on purpose: `appid.probe()` is one `flatpak list`, and it is only reached
by a tile that actually carries the token. A tile with a literal path — every
native emulator, every browser kiosk — never gets here at all.
"""
from __future__ import annotations

import logging

from . import appid
from .loader import load_catalog
from .tiles import APPID_TOKEN, expand_app_id

log = logging.getLogger(__name__)


def resolve_args(system_id: str, args: str) -> str:
    """The tile's args with `@APPID@` substituted, or unchanged without it.

    Raises `LookupError` when the token cannot be resolved. Deliberate: the
    alternative is handing `flatpak run @APPID@` to the shell, which fails with
    a message about an app id nobody typed. A refusal that names the pack is
    the difference between a bug report and a shrug.
    """
    if APPID_TOKEN not in args:
        return args

    pack = load_catalog().get(system_id)
    if pack is None or not pack.app_ids:
        raise LookupError(
            f"{system_id}: its launcher defers to the catalogue ({APPID_TOKEN}) but "
            f"no pack declares an app id for it — the tile and the catalogue "
            f"have come apart")

    appid.probe()
    resolved = appid.resolve(pack.app_ids)
    if appid.installed() is not None and resolved not in appid.installed():
        # Resolution fell through to the first candidate because none is
        # installed. Launching anyway would produce flatpak's own error, which
        # does not mention that other candidates exist.
        raise LookupError(
            f"{system_id}: none of {', '.join(pack.app_ids)} is installed — "
            f"run `gamecore-emu install {system_id}`")

    if pack.app_ids and resolved != pack.app_ids[0]:
        log.info("launch: %s resolves to %s (fallback from %s)",
                 system_id, resolved, pack.app_ids[0])
    return expand_app_id(args, resolved)
