"""Controller mapping snapshots — the "Scan mapping" action.

Four emulators (3DS/azahar, DS/melonDS, GBA/mgba, Wii U/Cemu) bind a pad by a
device GUID plus raw button indices that can't be synthesized reliably. Instead
the user configures the pad once in each emulator's own input UI, then hits
"Scan mapping" — this remembers that config per controller so it's restored
automatically on every future connect.

Ryujinx used to be listed here and never was: it has no snapshot adapter, and
it does not need one. Its GUID is read live from SDL2 and converted exactly
(controller_profiles.ryu_guid_from_sdl2), and its bindings are role names that
carry from one controller to the next.

An emulator whose current config plainly describes a DIFFERENT controller is
refused rather than filed under the connected one, and comes back in
`refused` — the box already holds a Cemu snapshot named for an Xbox pad that
contains a DualShock 4's config, saved when this returned a flat "ok".

That same snapshot is why DELETE exists. `restore()` now refuses to apply a
snapshot whose GUID names another pad, and a refusal with no way to act on it
is only a nicer dead end: the file sits in a directory no one can reach from a
sofa. Scan and forget are the two halves of one gesture, so they live on one
path and differ by verb.
"""
from fastapi import APIRouter

from ..services import controller_profiles

router = APIRouter(tags=["controllers"])


@router.post("/controllers/scan-mapping")
def scan_mapping():
    return controller_profiles.scan_mapping()


@router.delete("/controllers/scan-mapping")
def forget_mapping():
    return controller_profiles.forget_mapping()
