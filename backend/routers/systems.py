"""Systems + apps listing."""
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from ..config import SYSTEMS_FILE, APPS_FILE, ASSETS_DIR

router = APIRouter(tags=["systems"])

# path → (data, mtime)
_file_cache: dict[str, tuple[list, float]] = {}


def _hot_load(path: Path) -> list:
    key = str(path)
    data, mtime = _file_cache.get(key, ([], 0.0))
    try:
        current_mtime = path.stat().st_mtime
        if current_mtime != mtime:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            _file_cache[key] = (data, current_mtime)
    except FileNotFoundError:
        pass
    except Exception as e:
        raise HTTPException(500, f"Failed to load {path.name}: {e}")
    return data


def get_systems() -> list:
    return _hot_load(SYSTEMS_FILE)


def get_apps() -> list:
    return _hot_load(APPS_FILE)


def list_all() -> list:
    """Merged systems + apps for the home grid."""
    items = [{**s, "kind": "emulator"} for s in get_systems()]
    items += [{**a, "kind": "app"} for a in get_apps()]
    return items


@router.get("/systems")
def list_systems():
    return list_all()


@router.get("/systems/{system_id}")
def get_system(system_id: str):
    for item in list_all():
        if item["id"].lower() == system_id.lower():
            return item
    raise HTTPException(404, "System not found")


@router.get("/assets/logos/{filename}")
def serve_logo(filename: str):
    path = ASSETS_DIR / "logos" / filename
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path)
