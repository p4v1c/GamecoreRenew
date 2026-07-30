"""Game media — every artwork a game has, not just its jacket.

`/api/covers` answers one question ("give me a cover") and answers it the same
way it always has. This router answers the other one: *what does this game
have?* — 3D box, clear logo, gameplay screenshot, title screen, ready-made
mixes, trailer, manual — so a theme can be built on something other than a flat
box front.

    GET /api/media/{system}/{filename}          → the catalogue, as JSON
    GET /api/media/{system}/{filename}/{type}   → one file

The catalogue is what makes this usable: a theme asks what exists, then asks
for what it wants. Guessing a type name and getting a 404 would push every
theme into hardcoding the list of 54 slugs, which is exactly what `category`
and `kind` exist to prevent.

Nothing is downloaded until it is asked for. A scrape fetches the cover and
records the rest with its URL, so the first request for a 3D box costs one HTTP
call and no ScreenScraper quota, and every request after it costs a stat().
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..services import gamemedia
from ..utils import rom_in_root
from .systems import list_all

router = APIRouter(tags=["media"])

_MEDIA_TYPES = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
    ".mp4": "video/mp4", ".webm": "video/webm", ".pdf": "application/pdf",
    ".zip": "application/zip",
}


def _system_or_404(system_id: str) -> dict:
    system = next((s for s in list_all() if s["id"].lower() == system_id.lower()), None)
    if not system:
        raise HTTPException(404, "System not found")
    return system


def _target(system: dict, filename: str) -> str:
    """What to identify the game by: its path when it is really there.

    The path is what unlocks the two exact methods — the file hash, and the
    title a PS3/PS4/PSP directory carries in its PARAM.SFO. `rom_in_root`
    confines it first: `filename` is a {path} parameter and accepts '..'.
    """
    rom = rom_in_root(system, filename)
    return str(rom) if rom else filename


@router.get("/media/{system_id}/{filename:path}/media/{media_type}")
async def get_media(system_id: str, filename: str, media_type: str):
    """One media file, fetched on first request and cached from then on."""
    system = _system_or_404(system_id)
    sid = system["id"].lower()
    target = _target(system, filename)

    manifest = gamemedia.cached(sid, target)
    if manifest is None or not manifest.get("found"):
        manifest = await gamemedia.resolve(sid, target)
    if manifest is None:
        raise HTTPException(404, "No media source configured")
    if not manifest.get("found"):
        raise HTTPException(404, "Game not found by any source")

    if media_type not in (manifest.get("media") or {}):
        # The list travels with the 404: a theme asking for a type this game
        # does not have gets told what it does have, instead of having to walk
        # the catalogue endpoint to find out.
        raise HTTPException(404, {
            "detail": f"No media of type {media_type!r} for this game",
            "available": sorted((manifest.get("media") or {}).keys()),
        })

    path = await gamemedia.media_file(sid, target, media_type)
    if not path:
        raise HTTPException(502, f"Could not fetch {media_type!r}")

    return FileResponse(
        path,
        media_type=_MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream"),
        # Same reasoning as the covers route: the content behind a given type
        # for a given game never changes, and these files are large.
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.get("/media/{system_id}/{filename:path}")
async def list_media(system_id: str, filename: str, refresh: bool = False):
    """Everything known about one game: metadata plus the media catalogue."""
    system = _system_or_404(system_id)
    sid = system["id"].lower()
    target = _target(system, filename)

    manifest = None if refresh else gamemedia.cached(sid, target)
    if manifest is None or not manifest.get("found"):
        manifest = await gamemedia.resolve(sid, target, refresh=refresh)

    if manifest is None:
        # Not an error: a box with no ScreenScraper account and no LaunchBox
        # index is a supported configuration. A theme must be able to tell that
        # from "this game is unknown", or it will show "no artwork" where the
        # honest message is "no source configured".
        return {"found": False, "available": False, "media": {}, "meta": {},
                "notes": ["no media source configured"]}

    if not manifest.get("found"):
        return {
            "found": False, "available": True, "media": {}, "meta": {},
            # The distinction the whole cache design rests on: `unreachable`
            # means the question could not be asked (quota, network), so a
            # retry later is worth something. Without it, false and false look
            # alike.
            "unreachable": bool(manifest.get("unreachable")),
            "notes": list(manifest.get("notes") or []),
        }

    return {
        "found": True,
        "available": True,
        "source": manifest.get("source", ""),
        "matched_by": manifest.get("matched_by", ""),
        "meta": gamemedia.to_game_meta(manifest),
        "media": gamemedia.media_index(manifest),
    }
