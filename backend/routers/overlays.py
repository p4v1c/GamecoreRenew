"""Overlay bezel management — upload/serve per-system PNG, and resolve per game."""
import os
import re
import tempfile
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
from ..services import bezel_capture, bezels, consoles
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


class PackSource(BaseModel):
    """Where the addon put the pack it downloaded, under `<DATA>/addons/`."""
    source: str


@router.post("/overlays/packs/{system_id}")
async def install_pack(system_id: str, body: PackSource):
    """File a downloaded bezel pack where the cascade looks for it.

    The download itself is an addon's job, not core's: a Bezel Project pack is
    gigabytes of other people's box art, and GameCore does not host it, ship it
    in the ISO, or fetch it unasked. Only the last step is here, because where
    files may be written is not a decision to leave to third-party code.
    """
    if not _SYSTEM_ID_RE.match(system_id):
        raise HTTPException(400, "Invalid system id")
    try:
        return bezels.install_pack(system_id, Path(body.source))
    except ValueError as e:
        raise HTTPException(400, str(e))


class Measured(BaseModel):
    """What the overlay monitor saw the emulator draw, in window coordinates."""
    announced: dict           # the hole that was in force — the cache key
    measured: dict            # x/y/w/h of the drawn region
    window: dict              # the size the measurement was taken in
    # Which console of the pack, echoed back from the resolve answer. Optional
    # so an Electron that predates this field still records something, under
    # the pack's undetermined key rather than under nothing.
    console: str | None = None


@router.post("/overlays/measured/{system_id}")
async def record_measurement(system_id: str, body: Measured):
    """Learn that this system draws somewhere other than its hole says.

    The monitor does the looking because it is the process holding the X11
    display and the window id; the decision to believe it is here, where the
    cache lives and where it can be tested without a screen.

    `applied: false` is a normal answer, not a failure — it is what a
    measurement that was implausible, or too small to matter, gets. Nothing is
    written, so the next launch simply looks again.
    """
    if not _SYSTEM_ID_RE.match(system_id):
        raise HTTPException(400, "Invalid system id")
    try:
        announced = {k: int(body.announced[k]) for k in ("x", "y", "w", "h")}
        box = tuple(int(body.measured[k]) for k in ("x", "y", "w", "h"))
        win_w, win_h = int(body.window["w"]), int(body.window["h"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(400, "Malformed measurement")

    if not bezel_capture.is_plausible(box, win_w, win_h):
        return {"ok": True, "applied": False, "reason": "implausible"}
    # Only a console this pack actually declares. The field arrives over the
    # LAN like the rest of the body, and an arbitrary string here would let a
    # caller write cache keys of its choosing into the corrections file.
    console = body.console
    if console and console not in {c["id"] for c in consoles.declared(system_id)}:
        raise HTTPException(400, "No such console for this system")
    applied = bezel_capture.record(system_id, announced, box, console)
    return {"ok": True, "applied": applied,
            "reason": None if applied else "within tolerance"}


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


@router.post("/overlays/{system_id}/consoles/{console_id}")
async def upload_console_overlay(system_id: str, console_id: str,
                                 file: UploadFile = File(...)):
    """A bezel for one console of a pack that runs several.

    A route on the core rather than a widening of the addon contract. ROM
    Manager is where a player is already looking at their Game Boy games, so it
    is the natural place to offer this — but `api: 1` says an addon writes
    inside its own data directory and nowhere else, and overlays belong to the
    core. Extending the contract to let an addon write into `assets/overlays/`
    would open that directory to every addon, for one feature. So the addon
    POSTs here and the core decides the name and the destination.

    `docs/SECURITY.md`: the core is never exposed to the LAN — Caddy answers
    `/api/*` with a 403 — so this is reachable from the box's own UI and from an
    addon running on it, not from a phone on the network.
    """
    if not _SYSTEM_ID_RE.match(system_id):
        raise HTTPException(400, "Invalid system id")
    # Against what the pack declares, not against a character class: the file
    # is named `<system>.<console>.png` and the cascade only ever looks for the
    # consoles in `roms.consoles`. A file under any other name would be written
    # successfully and then never resolved by anything — a save that silently
    # does nothing, which is the failure this codebase keeps refusing to ship.
    if console_id not in {c["id"] for c in consoles.declared(system_id)}:
        raise HTTPException(404, "No such console for this system")
    return await _receive_bezel(file, bezels.console_png(system_id, console_id))


@router.post("/overlays/{system_id}")
async def upload_overlay(system_id: str, file: UploadFile = File(...)):
    return await _receive_bezel(file, _overlay_path(system_id))


async def _receive_bezel(file: UploadFile, p: Path) -> dict:
    if file.content_type not in ("image/png", "image/jpeg", "image/webp"):
        raise HTTPException(400, "Only PNG/JPEG/WebP images are accepted")
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

        # The case nothing used to catch, and the most insidious of the lot: a
        # perfectly valid image with no transparent area is a rectangle painted
        # over the entire game. Every other check here passes it — the magic
        # bytes are right, the size is right, the upload completes — and the
        # only symptom is a black screen with artwork on it, which reads as the
        # emulator failing to start rather than as the bezel.
        #
        # `_HOLE_MAX_COVERAGE` covers the other end: an image that is ALL hole
        # decorates nothing, and is also the shape a truncated download leaves.
        hole = bezels.hole_of(tmp)
        if hole is None:
            raise HTTPException(
                422, "A bezel needs a transparent area for the game to show "
                     "through, and this image has none the decoder can read. "
                     "Save it as a PNG with an alpha channel — JPEG cannot "
                     "carry one at all.")

        os.replace(tmp, p)
    finally:
        tmp.unlink(missing_ok=True)
    # The hole is handed back so the caller can show what was understood.
    # A bezel whose hole is not the shape the uploader expected is the failure
    # that is invisible until a game is running.
    return {"ok": True, "path": str(p), "size": written, "hole": hole}


@router.delete("/overlays/{system_id}")
async def delete_overlay(system_id: str):
    p = _overlay_path(system_id)
    if not p.exists():
        raise HTTPException(404, "No overlay to delete")
    p.unlink()
    return {"ok": True}
