"""Overlay bezel management — a default per system, and one per game.

Layout on disk:

    assets/overlays/<system>.png            the system's default bezel
    assets/overlays/<system>/<stem>.png     one game's own bezel

The per-game file wins when it exists. `<stem>` is the ROM filename without
its extension, which is the same key the covers and metadata caches use, so a
game keeps its bezel across a rename of nothing and loses it on a real rename
— consistent with everything else keyed that way.
"""
import os
import re
import tempfile
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from .. import ws
from ..config import ASSETS_DIR

router = APIRouter(tags=["overlays"])

OVERLAYS_DIR = ASSETS_DIR / "overlays"
_MAX_OVERLAY_BYTES = 10 * 1024 * 1024  # 10 MB hard cap


# `system_id` and `game` both become path segments, and both arrive from a
# URL. Anything outside this alphabet is refused rather than sanitised: a
# silently rewritten name would store a bezel under a key nothing else uses,
# and the game would never get it back.
_SAFE_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._'()\[\]&+-]{0,127}\Z")


def _key(raw: str, what: str) -> str:
    # The raw value is checked BEFORE the extension is dropped. Taking
    # Path(raw).stem first would turn "../../etc/passwd.z64" into "passwd" and
    # accept it — safe by accident, and exactly the silent rewrite this refuses
    # to do. A separator in a ROM filename is a bug or an attack, never a name.
    if "/" in raw or "\\" in raw or ".." in raw:
        raise HTTPException(400, f"Unusable {what} name")
    key = Path(raw).stem if what == "game" else raw
    if not _SAFE_KEY.match(key):
        raise HTTPException(400, f"Unusable {what} name")
    return key


def _overlay_path(system_id: str, game: str | None = None) -> Path:
    sid = _key(system_id, "system")
    if game:
        return OVERLAYS_DIR / sid / f"{_key(game, 'game')}.png"
    return OVERLAYS_DIR / f"{sid}.png"


def _resolve(system_id: str, game: str | None) -> Path | None:
    """The bezel to show: the game's own, else the system's, else nothing."""
    if game:
        own = _overlay_path(system_id, game)
        if own.exists():
            return own
    default = _overlay_path(system_id)
    return default if default.exists() else None


@router.get("/overlays/current")
async def get_current_overlay():
    """The bezel for whatever is running right now.

    The overlay window asks for this rather than building a path itself: only
    the backend knows which game is up (process_manager tells ws), and putting
    the choice here means the frontend, Electron and the overlay monitor all
    stay unaware that per-game bezels exist at all.
    """
    game = ws.current_game()
    if not game:
        raise HTTPException(404, "No game running")
    p = _resolve(game.get("system_id", ""), game.get("game_key") or None)
    if p is None:
        raise HTTPException(404, "No overlay for this game or system")
    return FileResponse(p, media_type="image/png")


@router.get("/overlays/{system_id}")
async def get_overlay(system_id: str, game: str | None = None):
    p = _resolve(system_id, game) if game else _overlay_path(system_id)
    if p is None or not p.exists():
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
async def upload_overlay(system_id: str, file: UploadFile = File(...),
                         game: str | None = None):
    if file.content_type not in ("image/png", "image/jpeg", "image/webp"):
        raise HTTPException(400, "Only PNG/JPEG/WebP images are accepted")
    p = _overlay_path(system_id, game)
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
async def delete_overlay(system_id: str, game: str | None = None):
    p = _overlay_path(system_id, game)
    if not p.exists():
        raise HTTPException(404, "No overlay to delete")
    p.unlink()
    # Deleting the last per-game bezel leaves an empty directory that would
    # otherwise sit next to the system PNGs for ever.
    if game:
        try:
            p.parent.rmdir()
        except OSError:
            pass
    return {"ok": True}
