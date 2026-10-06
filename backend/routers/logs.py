"""Settings → System → Purge logs: what the logs directory holds, and emptying it."""
import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..services import logs

router = APIRouter(tags=["logs"])
ui_log = logging.getLogger(logs.UI_LOGGER)


class UiReport(BaseModel):
    message: str = Field(max_length=logs.UI_MESSAGE_MAX)
    source: str = Field("", max_length=300)


@router.get("/logs")
def logs_usage():
    return logs.usage()


@router.delete("/logs")
def purge_logs():
    """Delete every log file. The directories come back on the next write."""
    return {"ok": True, "freed": logs.purge()}


@router.post("/logs/ui")
def report_ui_error(report: UiReport):
    """An error the interface caught (uncaught, rejected promise, render)."""
    source = f" ({logs.one_line(report.source)})" if report.source else ""
    ui_log.error("%s%s", logs.one_line(report.message), source)
    return {"ok": True}
