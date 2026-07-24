"""Controller mapping snapshots — the "Scan mapping" action.

The GUID-based emulators (3DS/azahar, DS/melonDS, GBA/mgba, Wii U/Cemu,
Switch/Ryujinx) bind a pad by a device GUID + raw button indices that can't be
synthesized reliably. Instead the user configures the pad once in each
emulator's own input UI, then hits "Scan mapping" — this remembers that config
per controller so it's restored automatically on every future connect.
"""
from fastapi import APIRouter

from ..services import controller_profiles

router = APIRouter(tags=["controllers"])


@router.post("/controllers/scan-mapping")
def scan_mapping():
    return controller_profiles.scan_mapping()
