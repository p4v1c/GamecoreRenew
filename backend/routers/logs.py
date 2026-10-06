"""Settings → System → Purge logs: what the logs directory holds, and emptying it."""
from fastapi import APIRouter

from ..services import logs

router = APIRouter(tags=["logs"])


@router.get("/logs")
def logs_usage():
    return logs.usage()


@router.delete("/logs")
def purge_logs():
    """Delete every log file. The directories come back on the next write."""
    return {"ok": True, "freed": logs.purge()}
