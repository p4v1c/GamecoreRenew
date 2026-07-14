"""Local-first game media — icons, titles and disc IDs read from the game
files themselves, like the emulators do. Offline and exact: no filename
guessing involved.

Three entry points, all keyed by system id:
  extract_icon(system_id, rom, dest) — copy/extract the game's own icon
  get_title(system_id, rom)          — real title from embedded metadata
  disc_id(system_id, rom)            — (kind, id) for online ID-based lookup
"""
import re
import shutil
from pathlib import Path

from . import sfo
from .iso9660 import Iso9660

_ID6_RE = re.compile(r"[A-Z0-9]{6}")
# BOOT2 = cdrom0:\SLUS_209.46;1  (PS2)  /  BOOT = cdrom:\SLUS_005.94;1  (PS1)
_BOOT_RE = re.compile(rb"BOOT2?\s*=\s*cdrom0?:\\?([A-Za-z]{4})[_-]?(\d{3})\.?(\d{2})")


# ── PS3 (rpcs3) — game folders carry PS3_GAME/ICON0.PNG + PARAM.SFO ──────────

def _ps3_icon(rom: Path) -> Path | None:
    for c in (rom / "PS3_GAME" / "ICON0.PNG", rom / "ICON0.PNG"):
        if c.is_file():
            return c
    return None


def _ps3_sfo(rom: Path) -> dict:
    return sfo.parse(rom / "PS3_GAME" / "PARAM.SFO") or sfo.parse(rom / "PARAM.SFO")


# ── PS4 (shadps4) — game folders carry sce_sys/icon0.png + param.sfo ─────────

def _ps4_icon(rom: Path) -> Path | None:
    c = rom / "sce_sys" / "icon0.png"
    return c if c.is_file() else None


def _ps4_sfo(rom: Path) -> dict:
    return sfo.parse(rom / "sce_sys" / "param.sfo")


# ── PSP (ppsspp) — ICON0.PNG and PARAM.SFO live inside the ISO ────────────────

def _psp_read(rom: Path, inner: str) -> bytes | None:
    if rom.suffix.lower() != ".iso":
        return None  # .cso is compressed — let the name scraper handle it
    iso = Iso9660.open(rom)
    if not iso:
        return None
    with iso:
        return iso.read_file(inner)


def _psp_sfo(rom: Path) -> dict:
    data = _psp_read(rom, "PSP_GAME/PARAM.SFO")
    return sfo.parse_bytes(data) if data else {}


# ── Disc IDs ──────────────────────────────────────────────────────────────────

def _gc_wii_id(rom: Path) -> str | None:
    """6-char game ID from a GameCube/Wii image header (.iso/.gcm/.rvz/.wia)."""
    try:
        with open(rom, "rb") as f:
            if rom.suffix.lower() in (".rvz", ".wia"):
                if f.read(4) not in (b"RVZ\x01", b"WIA\x01"):
                    return None
                f.seek(0x58)  # dhead (copy of the disc header) in the WIA/RVZ header
            id6 = f.read(6).decode("ascii", "replace")
    except OSError:
        return None
    return id6 if _ID6_RE.fullmatch(id6) else None


def _playstation_serial(rom: Path) -> str | None:
    """PS1/PS2 serial (e.g. 'SLUS-20946') from SYSTEM.CNF inside the image."""
    iso = Iso9660.open(rom)
    if not iso:
        return None
    with iso:
        data = iso.read_file("SYSTEM.CNF")
    if not data:
        return None
    m = _BOOT_RE.search(data)
    if not m:
        return None
    return f"{m.group(1).decode().upper()}-{m.group(2).decode()}{m.group(3).decode()}"


# ── Public API ────────────────────────────────────────────────────────────────

def extract_icon(system_id: str, rom: Path, dest: Path) -> Path | None:
    """Write the game's embedded icon to dest (PNG). None if the system has
    no local icon or the game doesn't carry one."""
    sid = system_id.lower()
    try:
        if sid == "rpcs3":
            src = _ps3_icon(rom)
            if src:
                shutil.copyfile(src, dest)
                return dest
        elif sid == "shadps4":
            src = _ps4_icon(rom)
            if src:
                shutil.copyfile(src, dest)
                return dest
        elif sid == "ppsspp":
            data = _psp_read(rom, "PSP_GAME/ICON0.PNG")
            if data:
                dest.write_bytes(data)
                return dest
    except OSError:
        return None
    return None


def get_title(system_id: str, rom: Path) -> str | None:
    """Real game title from embedded metadata (whitespace-normalized)."""
    sid = system_id.lower()
    meta = {}
    if sid == "rpcs3":
        meta = _ps3_sfo(rom)
    elif sid == "shadps4":
        meta = _ps4_sfo(rom)
    elif sid == "ppsspp":
        meta = _psp_sfo(rom)
    title = meta.get("TITLE", "")
    return " ".join(str(title).split()) or None


def disc_id(system_id: str, rom: Path) -> tuple[str, str] | None:
    """(kind, id) usable for an exact online lookup, e.g. ("wii", "GALE01")."""
    sid = system_id.lower()
    if sid == "dolphin":
        id6 = _gc_wii_id(rom)
        return ("wii", id6) if id6 else None
    if sid == "rpcs3":
        serial = str(_ps3_sfo(rom).get("TITLE_ID", "")).strip()
        return ("ps3", serial) if re.fullmatch(r"[A-Z0-9]{9}", serial) else None
    if sid == "duckstation":
        serial = _playstation_serial(rom)
        return ("psx", serial) if serial else None
    if sid == "pcsx2":
        serial = _playstation_serial(rom)
        return ("ps2", serial) if serial else None
    return None
