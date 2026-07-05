"""System information — IP, storage, version, controller batteries."""
import glob
import shutil
import socket
from pathlib import Path
from fastapi import APIRouter
from ..config import APP_VERSION, GAMECORE_ROOT

router = APIRouter(tags=["sysinfo"])

# Power supply name prefixes that are NOT controllers
_SKIP = ("BAT", "AC", "USB", "UCSI", "ADP", "MACSMC", "axp", "bq")


def _primary_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "—"


def _controller_batteries() -> list[dict]:
    """Read controller battery levels directly from sysfs — no subprocess needed."""
    result = []
    for supply in sorted(glob.glob("/sys/class/power_supply/*")):
        name = Path(supply).name
        if any(name.upper().startswith(p.upper()) for p in _SKIP):
            continue
        cap_path = Path(supply) / "capacity"
        if not cap_path.exists():
            continue
        try:
            level = int(cap_path.read_text().strip())
        except (ValueError, OSError):
            continue
        # "Charging" while plugged into the box; "Full" = plugged, done charging.
        charging = False
        try:
            charging = (Path(supply) / "status").read_text().strip() in ("Charging", "Full")
        except OSError:
            pass
        result.append({"level": level, "charging": charging})
    return result


@router.get("/sysinfo")
def get_sysinfo():
    total, used, free = shutil.disk_usage(GAMECORE_ROOT)
    return {
        "ip": _primary_ip(),
        "storage_used_gb": round(used / 1e9, 1),
        "storage_total_gb": round(total / 1e9, 1),
        "storage_free_gb": round(free / 1e9, 1),
        "version": APP_VERSION,
        "controllers": _controller_batteries(),
    }
