"""Whether GameCore is allowed to write emulator controller configs at all.

One switch for the whole box, plus a per-emulator exception for "I configure
Dolphin by hand, the rest can look after itself". Nothing else in the pipeline
knows this module exists: `configgen.autoconfigured_packs()` is the only caller
on the write path, which is what makes a pack added tomorrow obey the switch
without doing anything at all.

## What the two answers mean

`enabled()` is the global switch. `enabled_for(pack_id)` is the question the
pipeline actually asks, and the global one WINS: a per-emulator exception is a
way to carve a hole in an autoconfig that is running, not a way to keep one
emulator running while the rest is off. Anything else would need the settings
screen to explain that a row reading "on" means off, and a switch nobody can
read is the failure this feature is trying not to become.

## An unreadable file means ON

A lost or half-written state file must not leave a box where plugging a pad in
does nothing. The failure of the setting has to be the harmless direction, and
the harmless direction is the behaviour every box had before this file existed.

## tmp + os.replace

Same as `themes.set_active` and `auth._write_private`, for the same measured
reason: `write_text` truncates before it writes, so a power cut mid-write left a
half-written JSON that the reader could not parse. There it silently reverted a
theme; here it would silently revert the owner's decision to take the pads over
by hand — and then quietly overwrite their work on the next connect.

## Where it lives

Under the DATA root with the rest of the player's settings, never under the
installation: it is a choice the owner made, so an OTA must not be able to erase
it and a backup must already be copying it.
"""
from __future__ import annotations

import json
import logging
import os

from . import paths

log = logging.getLogger(__name__)


def state_file():
    """Resolved per call, not at import.

    `paths.use_roots()` is the supported seam for pointing the box at a
    throwaway data root, and a module-level constant would be computed before
    any test could move it — the same trap `test_playtime_repair` fell into.
    """
    return paths.config_dir() / "controller-autoconfig.json"


def _read() -> dict:
    try:
        raw = json.loads(state_file().read_text())
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def state() -> dict:
    """`{"enabled": bool, "packs": {pack_id: bool}}`, always well formed.

    `packs` holds only what the owner has said something about. An emulator
    that is not in it follows the global switch, which is why turning the
    global one off and on again does not resurrect exceptions nobody remembers
    setting — they were never deleted, and they were never in force either.
    """
    raw = _read()
    packs = raw.get("packs")
    if not isinstance(packs, dict):
        packs = {}
    return {
        "enabled": raw.get("enabled", True) is not False,
        "packs": {str(k): v is not False for k, v in packs.items()},
    }


def enabled() -> bool:
    """The global switch. True when the file is missing, empty or unparseable."""
    return state()["enabled"]


def enabled_for(pack_id: str) -> bool:
    """Whether this ONE emulator's config may be written.

    The single question the pipeline asks. The global switch wins, so an
    exception left over from before it was turned off cannot make one emulator
    look active while the box as a whole is not.
    """
    st = state()
    if not st["enabled"]:
        return False
    return st["packs"].get(pack_id, True)


def _write(st: dict) -> dict:
    path = state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(st, indent=2))
    os.replace(tmp, path)
    return st


def set_enabled(value: bool) -> dict:
    st = state()
    st["enabled"] = bool(value)
    log.info("controller autoconfig: global switch %s",
             "on" if st["enabled"] else "OFF — no emulator config will be written")
    return _write(st)


def set_pack(pack_id: str, value: bool) -> dict:
    """Add or clear one emulator's exception.

    Turning an exception back ON deletes the entry rather than storing `true`:
    the file then describes only the holes the owner punched, and the default —
    "follow the global switch" — stays the absence of a record instead of
    becoming a value that has to agree with one.
    """
    st = state()
    if value:
        st["packs"].pop(pack_id, None)
    else:
        st["packs"][pack_id] = False
    log.info("controller autoconfig: %s %s", pack_id,
             "follows the global switch" if value
             else "OFF — its config is the owner's from now on")
    return _write(st)
