"""The BIOS screen's data: one row per system that needs a system file."""
from fastapi import APIRouter

from ..services import bios as bios_service
# The grid, not the Flatpak: whether a tile is live is already answered in one
# place and re-implementing it here would be a second answer to drift from.
from .catalog import _live_ids

router = APIRouter(tags=["bios"])


@router.get("/bios")
def get_bios():
    """Every system declaring a `bios` block, with its verdict.

    `installed` rather than a filter. A system the owner has not added is still
    worth listing — it is how they learn, before installing PCSX2, that a file
    will be needed — but it must not be painted as a fault, and the page dims
    it. Hiding the row entirely would make the screen answer a question nobody
    asked ("what is broken right now") instead of the one they came with
    ("what does this box still need").
    """
    live = _live_ids()
    rows = bios_service.report()
    for row in rows:
        row["installed"] = row["id"] in live
    return rows
