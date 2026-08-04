"""Capture and restore, for the emulators whose bindings cannot be synthesised.

azahar (3DS), mgba (GBA), Cemu (Wii U), gopher64/RMG (N64) and melonDS (DS)
bind by a device GUID plus RAW BUTTON INDICES, and neither can be derived from
a vendor:product. Measured, on the reference box, for one DualShock 4:

    azahar wrote  guid:03008fe54c050000cc09000000006800  button_up = 11
    Cemu wrote    0_05009b514c050000cc09000000810000

Two different GUIDs for the same pad, and neither matches what the host's SDL3
reports. Substituting the host's answer would write a device the emulator never
sees. And azahar's `button_up = 11` is a raw joystick index — the same 11/12/13/14
melonDS records for a DS4's D-pad, while SDL's own GameController mapping claims
a hat and calls button 11 the touchpad.

So nothing is synthesised. The real model is:

  1. the owner maps the pad once, inside the emulator, then presses
     "Scan mapping";
  2. `capture()` stores that config block, indexed by vendor:product —
     REFUSING it when the block's own GUID names another controller;
  3. `restore()` puts it back when a pad of the same model reconnects.

GUID-substituting versions of the mgba and Cemu profilers used to exist and
were never called by apply_profile. They were removed rather than kept as
reference: dead code that looks like the mechanism is worse than no code.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from .controllers import db_name_for, vidpid_of
from .helpers.base import atomic_write, backup

log = logging.getLogger(__name__)

# A 32-hex SDL GUID wherever it appears — after `guid:` in azahar, after `0_`
# in Cemu's <uuid>, bare after `device0=` in mgba. A \b would not fire after an
# underscore, which is a word character, so Cemu's `0_0500…` would be missed.
_ANY_GUID_RE = re.compile(r"(?<![0-9a-fA-F])([0-9a-fA-F]{32})(?![0-9a-fA-F])")


def snap_path(snap_dir: Path, emu_id: str, vendor: str, product: str) -> Path:
    return snap_dir / emu_id / f"{vendor.lower()}_{product.lower()}.snap"


def exists(snap_dir: Path, emu_id: str, vendor: str, product: str) -> bool:
    return snap_path(snap_dir, emu_id, vendor, product).is_file()


def block_disagrees(block: str, vendor: str, product: str) -> str | None:
    """The first GUID in `block` that belongs to another controller, if any.

    Cemu's controller0.xml carries the pad's <uuid> and azahar's profile carries
    a `guid:` per binding, so a captured block states which controller it is
    for. Nothing checked that against the pad the user said they had just
    mapped, and the box ended up with cemu/045e_02fd.snap byte-identical to
    cemu/054c_09cc.snap — both the DualShock 4's config, because "Scan mapping"
    was pressed with the Xbox pad connected while the file still held the DS4.
    Restoring it is a no-op today, but the moment the owner maps the Xbox by
    hand, the next connection overwrites their work with the DS4's config.
    """
    want = (vendor.lower(), product.lower())
    for guid in _ANY_GUID_RE.findall(block):
        if vidpid_of(guid) != want:
            return guid

    # RMG names the device instead of carrying a GUID, so the loop above finds
    # nothing in its config and would wave through any pad's mapping saved
    # under any other pad's name — the exact accident this function exists to
    # stop, just spelled differently.
    for line in block.splitlines():
        if not line.startswith("DeviceName"):
            continue
        _k, _sep, raw = line.partition("=")
        said = raw.strip().strip('"')
        expected = db_name_for(vendor, product)
        # No entry in the SDL database is not a disagreement: an unknown pad is
        # exactly the case where a captured mapping is most needed.
        if said and expected and said != expected:
            return said
    return None


def capture(snap_dir: Path, emu_id: str, path: Path, extract, vendor: str,
            product: str) -> str | None:
    """Save this emulator's CURRENT input config for this controller.

    Returns the emulator id when saved, None when there was nothing to save,
    and raises nothing. A block that plainly describes a different controller
    is REFUSED rather than saved under this one's name — the caller reports it.
    """
    if not path.is_file():
        return None
    block = extract(path.read_text())
    if not block.strip():
        return None
    wrong = block_disagrees(block, vendor, product)
    if wrong:
        log.warning("configgen: %s config describes %s, not %s:%s — refusing to "
                    "save it as this pad's mapping", emu_id, wrong, vendor, product)
        raise Refused(emu_id)
    snap = snap_path(snap_dir, emu_id, vendor, product)
    snap.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(snap, block)
    return emu_id


class Refused(Exception):
    """The emulator's config names a different controller."""


def restore(snap_dir: Path, emu_id: str, path: Path, extract, replace,
            vendor: str, product: str) -> str | None:
    """Swap this controller's saved input config back in, on connect.

    Returns None for TWO distinct reasons — there is no snapshot, or the
    snapshot is ALREADY in place. Conflating them is what broke melonDS: the
    caller used `restore(...) or _synth(...)`, so the synthesis ran every other
    connection and overwrote the mapping the owner had captured, which the next
    connection then restored. One session in two was wrong. Callers must ask
    `exists()` first rather than lean on a falsy return.
    """
    snap = snap_path(snap_dir, emu_id, vendor, product)
    if not path.is_file() or not snap.is_file():
        return None
    block, text = snap.read_text(), path.read_text()
    if extract(text).strip() == block.strip():
        return None                                   # already applied
    backup(path)
    atomic_write(path, replace(text, block))
    return f"{emu_id}: restored saved mapping ({vendor}:{product})"
