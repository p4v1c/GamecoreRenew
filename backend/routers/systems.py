"""Systems + apps listing."""
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from ..config import SYSTEMS_FILE, APPS_FILE, GAMECORE_ROOT
from ..services import http_cache
from ..services.paths import GAMECORE_DATA, logos_dir

router = APIRouter(tags=["systems"])

# A SECOND router, mounted without the /api prefix. The grid asks for the
# `iconPath` recorded in systems.json — `assets/logos/3ds.png` — so the logo
# endpoint has to answer at that exact path, not under /api.
#
# It used to be a StaticFiles mount on assets/logos/. That broke the day the
# logos moved into the packs: the directory went nearly empty and every tile
# on a fresh install lost its image. An upgraded box did not notice, because
# assets/logos/ is excluded from the OTA rsync and kept its old files — which
# is exactly the kind of bug that ships.
#
# Registered before the static mounts in main.py, so it wins the match.
public_router = APIRouter(tags=["systems"])

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


@router.get("/systems")
def list_systems():
    return list_all()


@router.get("/systems/{system_id}")
def get_system(system_id: str):
    for item in list_all():
        if item["id"].lower() == system_id.lower():
            return item
    raise HTTPException(404, "System not found")


# The logo a pack ships, keyed by the historical assets/logos/ file name that
# systems.json still records. Built from the catalogue, so adding a pack is
# still "drop a directory" — nothing here is hand-maintained.
def _pack_logos() -> dict[str, Path]:
    logos: dict[str, Path] = {}
    try:
        from ..services.catalog import load_catalog
        for pack in load_catalog().values():
            logo = pack.logo
            if logo is not None:
                logos[pack.id] = logo
    except Exception:                       # a broken catalogue must not 500 the grid
        pass
    return logos


@public_router.get("/assets/logos/{filename}")
def serve_logo(request: Request, filename: str):
    """Serve a system logo, operator override first.

    Two locations, in this order:

      assets/logos/<filename>     the operator's own, uploaded from the ROM
                                  manager. Excluded from the OTA rsync, so it
                                  survives every update — that is the point.
      catalog/<id>/logo.png       the one shipped with the pack. NOT excluded
                                  from the OTA, so a corrected logo finally
                                  reaches an installed box.

    The file name is matched against the pack ids rather than joined into a
    path, and the guard below rejects anything with a separator in it before
    that: `filename` comes straight from the URL, and `..%2f..%2fetc%2fshadow`
    is what a path parameter is for.
    """
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise HTTPException(404)

    override = logos_dir() / filename
    if override.is_file():
        return _logo_response(request, override)

    stem = Path(filename).stem.lower()
    logos = _pack_logos()
    # Either the pack id itself (catalog/youtube/logo.png -> "youtube.png") or
    # the legacy platform name systems.json records ("3ds.png" -> azahar).
    for pack_id, logo in logos.items():
        if stem == pack_id.lower():
            return _logo_response(request, logo)
    for item in list_all():
        icon = item.get("iconPath", "")
        if icon and Path(icon).name.lower() == filename.lower():
            logo = logos.get(item["id"])
            if logo is not None:
                return _logo_response(request, logo)
    raise HTTPException(404)


def _logo_response(request: Request, path: Path):
    """A logo, kept by the browser but never reused without asking.

    These are the only images on the box served under a name that does not
    change when the picture does: `gamecube.png` is `gamecube.png` forever,
    while `catalog/<id>/logo.png` IS carried by the OTA rsync and a corrected
    logo is expected to arrive with an update. Give them the long lifetime the
    hash-named bundle assets get and that correction never lands — the tile
    keeps the old drawing until someone clears the cache by hand, which is the
    failure mode this whole change is otherwise removing the need for.

    So: revalidate, and answer 304 when nothing moved.
    """
    return http_cache.conditional_file_response(request, path)
