"""Overlay bezel management — upload/serve per-system PNG, and resolve per game."""
import os
import re
import tempfile
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
from ..services import bezels
from ..services.paths import overlays_dir

router = APIRouter(tags=["overlays"])

OVERLAYS_DIR = overlays_dir()
_MAX_OVERLAY_BYTES = 10 * 1024 * 1024  # 10 MB hard cap

# A system id names a directory and a file under the overlays root. Anything
# outside this alphabet is not a system, and `..` in particular would make
# `resolve` read PNGs from anywhere the backend user can reach.
_SYSTEM_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _overlay_path(system_id: str) -> Path:
    OVERLAYS_DIR.mkdir(parents=True, exist_ok=True)
    return OVERLAYS_DIR / f"{system_id}.png"


@router.get("/overlays/resolve/{system_id}")
async def resolve_overlay(system_id: str, rom: str = ""):
    """Which bezel this launch should draw, and where its hole falls.

    Answered by the backend rather than by Electron because the hole is
    measured out of the PNG's alpha channel, and a second decoder in JavaScript
    would be a second set of numbers to keep in agreement with this one.

    Never 404s. A system with no bezel is a normal, frequent answer — the five
    16:9 systems have no black bars to hide and want no overlay at all — and an
    error status here would put a failed request in the log of every launch on
    a box that is behaving correctly.
    """
    if not _SYSTEM_ID_RE.match(system_id):
        raise HTTPException(400, "Invalid system id")
    # Only the filename: `rom` arrives as the launcher's `game_key`, and a
    # directory component in it would let the pack index be pointed elsewhere.
    return bezels.for_launch(system_id, Path(rom).name or None)


@router.get("/overlays/choices/{system_id}")
async def overlay_choices(system_id: str, rom: str = ""):
    """What the game's options screen may offer, and what is set today.

    `options` lists only bezels that exist on this box. A menu entry that
    resolves to nothing when picked is indistinguishable, from a sofa, from a
    setting that did not save.
    """
    if not _SYSTEM_ID_RE.match(system_id):
        raise HTTPException(400, "Invalid system id")
    name = Path(rom).name or None
    return {
        "system_id": system_id,
        "rom": name,
        "current": bezels.preference(system_id, name),   # None = automatic
        "resolved": bezels.for_launch(system_id, name),
        "options": bezels.available(system_id, name),
    }


class OverlayChoice(BaseModel):
    rom: str
    # None → back to automatic, "off" → draw nothing, otherwise a bezel
    # filename taken from `options` above.
    choice: str | None = None


@router.put("/overlays/choices/{system_id}")
async def set_overlay_choice(system_id: str, body: OverlayChoice):
    if not _SYSTEM_ID_RE.match(system_id):
        raise HTTPException(400, "Invalid system id")
    name = Path(body.rom).name
    if not name:
        raise HTTPException(400, "A choice belongs to a game")
    choice = body.choice
    if choice not in (None, "off"):
        # Checked against what actually exists, so a stored preference can
        # only ever name a bezel this box has. The alternative is a setting
        # that saves happily and does nothing at launch.
        if choice not in {o["id"] for o in bezels.available(system_id, name)}:
            raise HTTPException(404, "No such bezel for this game")
    bezels.set_preference(system_id, name, choice)
    return {"ok": True, "current": bezels.preference(system_id, name),
            "resolved": bezels.for_launch(system_id, name)}


@router.get("/overlays/{system_id}")
async def get_overlay(system_id: str):
    p = _overlay_path(system_id)
    if not p.exists():
        raise HTTPException(404, "No overlay for this system")
    return FileResponse(p, media_type="image/png")


def _looks_like_image(head: bytes) -> bool:
    """Magic-byte check — the client Content-Type header proves nothing."""
    return (
        head.startswith(b"\x89PNG\r\n\x1a\n")
        or head.startswith(b"\xff\xd8\xff")
        or (head[:4] == b"RIFF" and head[8:12] == b"WEBP")
    )


@router.post("/overlays/{system_id}")
async def upload_overlay(system_id: str, file: UploadFile = File(...)):
    if file.content_type not in ("image/png", "image/jpeg", "image/webp"):
        raise HTTPException(400, "Only PNG/JPEG/WebP images are accepted")
    p = _overlay_path(system_id)
    # Write to a temp file, then swap atomically — an interrupted or oversize
    # upload must never destroy the existing overlay. The name is unique: it
    # used to be a fixed "<name>.part", so two uploads at once wrote into the
    # same file and whichever finished second published a mixture of both.
    # Same directory, so os.replace stays on one filesystem and is atomic.
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=p.name + ".", suffix=".part", dir=str(p.parent))
    tmp = Path(tmp_name)
    written = 0
    try:
        with os.fdopen(fd, "wb") as f:
            while True:
                chunk = await file.read(1 << 20)  # 1 MB chunks
                if not chunk:
                    break
                if written == 0 and not _looks_like_image(chunk):
                    raise HTTPException(400, "File content is not a PNG/JPEG/WebP image")
                written += len(chunk)
                if written > _MAX_OVERLAY_BYTES:
                    raise HTTPException(413, f"Overlay exceeds {_MAX_OVERLAY_BYTES // (1024 * 1024)} MB limit")
                f.write(chunk)
        # An empty upload never entered the loop body, so it never met the
        # magic-byte test — and then replaced a perfectly good bezel with zero
        # bytes. Nothing is published unless something was actually checked.
        if written == 0:
            raise HTTPException(400, "Empty file")
        os.replace(tmp, p)
    finally:
        tmp.unlink(missing_ok=True)
    return {"ok": True, "path": str(p), "size": written}


@router.delete("/overlays/{system_id}")
async def delete_overlay(system_id: str):
    p = _overlay_path(system_id)
    if not p.exists():
        raise HTTPException(404, "No overlay to delete")
    p.unlink()
    return {"ok": True}
