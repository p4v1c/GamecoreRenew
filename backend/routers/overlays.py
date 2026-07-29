"""Overlay bezel management — upload/serve per-system PNG."""
import os
import tempfile
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from ..config import ASSETS_DIR

router = APIRouter(tags=["overlays"])

OVERLAYS_DIR = ASSETS_DIR / "overlays"
_MAX_OVERLAY_BYTES = 10 * 1024 * 1024  # 10 MB hard cap


def _overlay_path(system_id: str) -> Path:
    OVERLAYS_DIR.mkdir(parents=True, exist_ok=True)
    return OVERLAYS_DIR / f"{system_id}.png"


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
