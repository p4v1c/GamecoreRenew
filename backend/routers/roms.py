"""ROM upload / delete — absorbed from existing Flask web server."""
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File

from .systems import list_all
from ..config import resolve_path
from ..services.rom_scanner import iter_rom_files, matches_ext
from ..utils import fmt_size
from ..ws import broadcast

router = APIRouter(tags=["roms"])


def safe_filename(filename: str) -> str:
    """Sanitize filename — removes only truly dangerous characters (/, \\0)
    to preserve exact ROM names for save-file matching on Linux."""
    filename = Path(filename).name
    filename = filename.replace('\x00', '').replace('/', '_')
    filename = filename.strip('. ')
    return filename or "unknown"


def _get_system(system_id: str) -> dict:
    s = next((x for x in list_all() if x["id"].lower() == system_id.lower()), None)
    if not s:
        raise HTTPException(404, "System not found")
    return s


# ── /api/emulators — summary list used by the web ROM manager ────────────────

@router.get("/emulators")
def list_emulators():
    result = []
    for s in list_all():
        if s.get("type") != "emulator":
            continue
        roms_path  = resolve_path(s.get("romsPath", ""))
        extensions = s.get("extensions", [])
        rom_count  = 0
        total_size = 0
        if roms_path and roms_path.exists():
            for f in iter_rom_files(roms_path, extensions):
                rom_count  += 1
                total_size += f.stat().st_size
        result.append({
            "id":         s["id"],
            "platform":   s.get("label", s["id"]),
            "iconPath":   s.get("iconPath", ""),
            "color":      s.get("color", "#5c7cfa"),
            "type":       "emulator",
            "extensions": extensions,
            "romCount":   rom_count,
            "totalSize":  fmt_size(total_size) if total_size else None,
        })
    return result


# ── /api/roms/{system_id} ─────────────────────────────────────────────────────

@router.get("/roms/{system_id}")
def list_roms(system_id: str):
    system = _get_system(system_id)
    roms_path = resolve_path(system.get("romsPath", ""))
    if not roms_path or not roms_path.exists():
        return []
    files = []
    for f in iter_rom_files(roms_path, system.get("extensions", [])):
        stat = f.stat()
        files.append({
            "name":      f.name,
            "size":      stat.st_size,
            "sizeHuman": fmt_size(stat.st_size),
            "ext":       f.suffix.lstrip(".").upper(),
        })
    return files


@router.post("/roms/{system_id}/upload")
async def upload_rom(system_id: str, file: UploadFile = File(...)):
    system = _get_system(system_id)
    roms_path = resolve_path(system.get("romsPath", ""))
    if not roms_path:
        raise HTTPException(400, "No ROM path configured")

    filename = safe_filename(file.filename or "")
    if not filename:
        raise HTTPException(400, "Invalid filename")

    exts = system.get("extensions", [])
    if exts and not matches_ext(filename, exts):
        raise HTTPException(415, f"Extension not allowed. Accepted: {', '.join(exts)}")

    roms_path.mkdir(parents=True, exist_ok=True)
    dest = roms_path / filename

    size = 0
    with dest.open("wb") as out:
        while True:
            chunk = await file.read(1 << 20)  # 1 MB chunks — avoids loading large ROMs into RAM
            if not chunk:
                break
            out.write(chunk)
            size += len(chunk)

    await broadcast("rom_uploaded", {"system_id": system_id, "filename": filename})
    return {"name": filename, "size": size, "sizeHuman": fmt_size(size)}


@router.delete("/roms/{system_id}/{filename}")
def delete_rom(system_id: str, filename: str):
    system = _get_system(system_id)
    roms_path = resolve_path(system.get("romsPath", ""))
    if not roms_path:
        raise HTTPException(404)

    safe = safe_filename(filename)
    target = roms_path / safe
    try:
        target.resolve().relative_to(roms_path.resolve())
    except ValueError:
        raise HTTPException(403)

    if not target.is_file():
        raise HTTPException(404)
    target.unlink()
    return {"ok": True}
