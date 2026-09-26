"""The home grid's rows: config/systems.json + config/apps.json, hot-reloaded."""
import json
from pathlib import Path

from ..config import SYSTEMS_FILE, APPS_FILE, GAMECORE_ROOT
from .paths import GAMECORE_DATA

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
        raise RuntimeError(f"Failed to load {path.name}: {e}") from e
    return data


def _expand(rows: list) -> list:
    """Resolve the pack tokens in launcher fields, at READ time.

    `install/arch.sh` substitutes @HOME@ when it copies install/generated/apps.json.dist
    into config/, and that used to be the only place it happened — so a
    config/apps.json that arrived any other way (restored from a backup, copied
    from the repository, written by hand) kept the literal, and the tile
    launched `firefox --profile '@HOME@/.mozilla/...'`. Which fails in the one
    way that is hardest to read: an emulator that starts and finds nothing.

    Doing it here as well costs one pass over a dozen rows and makes the token
    safe wherever the file came from. An absolute path already in the file is
    untouched, so a box that predates the token is unaffected.
    """
    home = str(Path.home())
    root = str(GAMECORE_ROOT)
    data = str(GAMECORE_DATA)

    def fix(row: dict) -> dict:
        out = dict(row)
        for key in ("path", "args"):
            v = out.get(key)
            if isinstance(v, str) and "@" in v:
                out[key] = (v.replace("@HOME@", home)
                             .replace("@GAMECORE_DATA@", data)
                             .replace("@GAMECORE_PATH@", root))
        return out

    return [fix(r) if isinstance(r, dict) else r for r in rows]


def get_systems() -> list:
    return _expand(_hot_load(SYSTEMS_FILE))


def get_apps() -> list:
    return _expand(_hot_load(APPS_FILE))


def list_all() -> list:
    """Merged systems + apps for the home grid."""
    items = [{**s, "kind": "emulator"} for s in get_systems()]
    items += [{**a, "kind": "app"} for a in get_apps()]
    return items


def find(system_id: str) -> dict | None:
    """The row for `system_id`, case-insensitive, or None."""
    wanted = system_id.lower()
    return next((s for s in list_all() if s["id"].lower() == wanted), None)
