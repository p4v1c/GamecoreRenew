"""`GET /api/ready` — is GameCore usable yet?

Separate from `/api/sysinfo`, which the Electron shell used to poll for this
and which answers with the box's IP address, its disk usage, its controller
batteries and its BIOS inventory. That endpoint exists to describe a running
box to a person; this one exists to be asked every 100 ms by a program during
the one minute when the box has the least to spare.

The HTTP status carries the answer as well as the body, so a caller that reads
neither JSON nor this file still gets it right: **200 when ready, 503 while
starting or degraded**. A 503 here is not an error to log and give up on — it
is "not yet", and the body says which step is outstanding.
"""
from fastapi import APIRouter, Response

from ..services import boot

router = APIRouter(tags=["ready"])


@router.get("/ready")
def get_ready(response: Response):
    state = boot.snapshot()
    if not state["ready"]:
        response.status_code = 503
    return state
