"""Local-first game media — icons, titles and disc IDs read from the game
files themselves, like the emulators do. Offline and exact: no filename
guessing involved.

Three entry points, all keyed by system id:
  extract_icon(system_id, rom, dest) — copy/extract the game's own icon
  get_title(system_id, rom)          — real title from embedded metadata
  disc_id(system_id, rom)            — (kind, id) for online ID-based lookup

Code and data, and where the line is
------------------------------------
The PARSERS below are code. A new dump layout is a new reader for a new
container: nothing declarative invents one, and the `format` enum in
catalog/_schema/pack.schema.json only grows alongside this file.

WHICH parser a system uses is data, and it lives in the pack, under
`localMedia`. It used to be a chain of `if sid == …` on six emulator ids,
repeated across all three functions — eighteen lines saying one thing. The
PlayStation pair was the tell: two of them called the identical parser and
differed only by the string it is reported under, "psx" against "ps2". That is
a catalogue entry wearing an `if`.

Same mechanism as `controllers.strategy` and `install.provider`, deliberately:
an enum in the schema, resolved here against a registry.

A pack with no `localMedia` block has no local media and falls back to online
scraping — which is exactly what an emulator missing from the old `if` chain
already got, so nothing changes for the eleven packs that never had one.
"""
import logging
import re
import shutil
from pathlib import Path

from . import sfo
from .iso9660 import Iso9660

log = logging.getLogger(__name__)

_ID6_RE = re.compile(r"[A-Z0-9]{6}")
_PS3_TITLE_ID_RE = re.compile(r"[A-Z0-9]{9}")
# BOOT2 = cdrom0:\SLUS_209.46;1  (PS2)  /  BOOT = cdrom:\SLUS_005.94;1  (PS1)
_BOOT_RE = re.compile(rb"BOOT2?\s*=\s*cdrom0?:\\?([A-Za-z]{4})[_-]?(\d{3})\.?(\d{2})")


# ── PS3 — game folders carry PS3_GAME/ICON0.PNG + PARAM.SFO ─────────────────

def _ps3_icon(rom: Path) -> Path | None:
    for c in (rom / "PS3_GAME" / "ICON0.PNG", rom / "ICON0.PNG"):
        if c.is_file():
            return c
    return None


def _ps3_sfo(rom: Path) -> dict:
    return sfo.parse(rom / "PS3_GAME" / "PARAM.SFO") or sfo.parse(rom / "PARAM.SFO")


def _ps3_title_id(rom: Path) -> str | None:
    serial = str(_ps3_sfo(rom).get("TITLE_ID", "")).strip()
    return serial if _PS3_TITLE_ID_RE.fullmatch(serial) else None


# ── PS4 — game folders carry sce_sys/icon0.png + param.sfo ──────────────────

def _ps4_icon(rom: Path) -> Path | None:
    c = rom / "sce_sys" / "icon0.png"
    return c if c.is_file() else None


def _ps4_sfo(rom: Path) -> dict:
    return sfo.parse(rom / "sce_sys" / "param.sfo")


# ── PSP — ICON0.PNG and PARAM.SFO live inside the ISO ───────────────────────

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


def _psp_icon(rom: Path) -> bytes | None:
    return _psp_read(rom, "PSP_GAME/ICON0.PNG")


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


# ── format → parsers ──────────────────────────────────────────────────────────

class _Format:
    """The three readers a dump layout has, `None` where it has none.

    An absent reader is a property of the FORMAT, not of the emulator reading
    it: a GameCube image carries a game id and no embedded title, however it is
    opened. That is why this table is keyed by format and not by system.
    """

    __slots__ = ("icon", "title", "disc")

    def __init__(self, *, icon=None, title=None, disc=None):
        self.icon = icon        # (rom) -> Path | bytes | None
        self.title = title      # (rom) -> dict   (embedded metadata)
        self.disc = disc        # (rom) -> str | None


# `icon` is either a file to copy or the bytes to write: the console-folder
# formats keep their icon as a real file on disk, the ISO-based one only has it
# inside the image. Both end up as the same PNG at `dest`.
_FORMATS: dict[str, _Format] = {
    "ps3":         _Format(icon=_ps3_icon, title=_ps3_sfo, disc=_ps3_title_id),
    "ps4":         _Format(icon=_ps4_icon, title=_ps4_sfo),
    "psp":         _Format(icon=_psp_icon, title=_psp_sfo),
    "gcwii":       _Format(disc=_gc_wii_id),
    "playstation": _Format(disc=_playstation_serial),
}


def _catalog_local_media() -> dict[str, tuple[str, str]]:
    """system id → (format, disc tag), declared by the packs.

    Built once at import, like scraper.py's platform maps and gamemedia.py's
    aliases — the catalogue is shipped code, not box state, so a pack added at
    runtime is seen at the next backend start, exactly as it is by those two.

    Never fatal: a catalogue this cannot read costs local media and nothing
    else, and every system then resolves the way an unlisted one always has.
    """
    out: dict[str, tuple[str, str]] = {}
    try:
        from .catalog import load_catalog
        for pack in load_catalog().values():
            block = pack.data.get("localMedia")
            if not block:
                continue
            fmt = block["format"]
            # The tag defaults to the format name and is declared only when it
            # differs: the GameCube/Wii format reports "wii", and the one
            # PlayStation parser reports "psx" for one system and "ps2" for the
            # other. That single string was the whole difference between two
            # branches of the old chain.
            out[pack.id] = (fmt, block.get("discTag", fmt))
    except Exception:
        log.warning("local_media: catalogue unreadable — no system has local "
                    "media, everything falls back to online scraping",
                    exc_info=True)
    return out


SYSTEM_FORMATS: dict[str, tuple[str, str]] = _catalog_local_media()


def _resolve(system_id: str) -> tuple[_Format, str] | None:
    """(parsers, disc tag) for a system, or None when it declares no format."""
    declared = SYSTEM_FORMATS.get(system_id.lower())
    if declared is None:
        return None
    name, tag = declared
    fmt = _FORMATS.get(name)
    if fmt is None:
        # A pack from a newer release than this backend — mid-OTA, or a local
        # pack written against a later schema. It degrades to online scraping,
        # which is survivable, but it must not do so in silence: "the covers
        # stopped being exact" is otherwise unattributable.
        log.warning("local_media: %s declares format %r, which this backend has "
                    "no parser for — falling back to online scraping",
                    system_id, name)
        return None
    return fmt, tag


# ── Public API ────────────────────────────────────────────────────────────────

def extract_icon(system_id: str, rom: Path, dest: Path) -> Path | None:
    """Write the game's embedded icon to dest (PNG). None if the system has
    no local icon or the game doesn't carry one."""
    resolved = _resolve(system_id)
    if resolved is None or resolved[0].icon is None:
        return None
    try:
        src = resolved[0].icon(rom)
        if src is None:
            return None
        if isinstance(src, bytes):
            dest.write_bytes(src)
        else:
            shutil.copyfile(src, dest)
        return dest
    except OSError:
        return None


def get_title(system_id: str, rom: Path) -> str | None:
    """Real game title from embedded metadata (whitespace-normalized)."""
    resolved = _resolve(system_id)
    meta = {} if resolved is None or resolved[0].title is None \
        else resolved[0].title(rom)
    title = meta.get("TITLE", "")
    return " ".join(str(title).split()) or None


def disc_id(system_id: str, rom: Path) -> tuple[str, str] | None:
    """(kind, id) usable for an exact online lookup, e.g. ("wii", "GALE01")."""
    resolved = _resolve(system_id)
    if resolved is None or resolved[0].disc is None:
        return None
    fmt, tag = resolved
    serial = fmt.disc(rom)
    return (tag, serial) if serial else None
