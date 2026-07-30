"""Shared ROM scanning logic — used by /api/systems/{id}/games (and the rom-manager addon keeps a mirrored copy)."""
import fnmatch
import re
from pathlib import Path
from typing import Iterator

from ..utils import TAG_RE

# ── Disc images: one game, several files ─────────────────────────────────────
#
# A PS1 dump is a descriptor plus its tracks. Both extensions have to be
# scannable — the descriptor is the only launchable file of a multi-track dump,
# and plenty of single-track dumps ship as a bare .bin — but listing both makes
# one game appear twice in the library, which is what the player sees.
#
# The descriptor wins: it is what an emulator wants, and it carries the track
# layout a raw .bin does not.
_DISC_DESCRIPTORS = {".cue", ".gdi", ".m3u", ".ccd", ".mds", ".toc"}
_DISC_TRACKS = {".bin", ".img", ".iso", ".raw"}

# What a descriptor names: quoted in a .cue (`FILE "game.bin" BINARY`), bare in
# a .gdi. A .m3u is read line by line instead — its entries are unquoted paths
# that routinely contain spaces (`FF IX (Disc 1).cue`), and any token-based
# pattern would match only the tail after the last space.
_REF_RE = re.compile(
    r'"([^"]+)"|([^\s"]+\.(?:bin|img|iso|raw|cue|chd|wav|mp3|ogg|flac))',
    re.IGNORECASE)


def _references(descriptor: Path, text: str) -> Iterator[str]:
    if descriptor.suffix.lower() == ".m3u":
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                yield line
        return
    for m in _REF_RE.finditer(text):
        yield m.group(1) or m.group(2) or ""


def _shadowed_by_a_descriptor(entries: list[Path]) -> set[str]:
    """Lowercased names of files that are part of another entry, not games.

    Two rules, because either one alone leaves duplicates on a real library:

    · **what the descriptor names.** Handles a multi-track dump, where the
      tracks are `Game (Track 01).bin` … and share no stem with `Game.cue`.
      Transitive by construction: an .m3u naming its .cue files hides them, and
      those .cue files' own tracks are collected in the same pass.
    · **what shares its stem.** Handles the far more common case of a dump
      whose files were renamed while the descriptor kept pointing at the
      original name — measured on this very library: `Dragon Ball Z .cue`
      contains `FILE "Dragon Ball Z (Europe).bin"`, a file that does not exist,
      while `Dragon Ball Z .bin` sits right next to it.
    """
    descriptors = [p for p in entries if p.suffix.lower() in _DISC_DESCRIPTORS]
    if not descriptors:
        return set()

    hidden: set[str] = set()
    stems: set[str] = set()
    for d in descriptors:
        stems.add(d.stem.strip().lower())
        try:
            text = d.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue  # unreadable descriptor — hide nothing on its account
        for ref in _references(d, text):
            ref = ref.strip()
            if ref:
                # .name: an .m3u may point into a subdirectory.
                hidden.add(Path(ref).name.lower())

    for p in entries:
        if p.suffix.lower() in _DISC_TRACKS and p.stem.strip().lower() in stems:
            hidden.add(p.name.lower())

    # A descriptor can only be hidden by being named in another one (an .m3u
    # listing its discs) — the stem rule above only ever adds track files, so
    # a .cue is never hidden by its own stem.
    return hidden


def clean_name(filename: str) -> str:
    """Strip extension and bracketed tags (e.g. '[!]', '(USA)') from a ROM name."""
    return TAG_RE.sub("", Path(filename).stem).strip()


def matches_ext(filename: str, extensions: list[str]) -> bool:
    name = filename.lower()
    return any(fnmatch.fnmatch(name, p.lower()) for p in extensions)


def iter_rom_files(roms_path: Path, extensions: list[str], scan_dirs: bool = False) -> Iterator[Path]:
    """Yield ROM file/folder paths in alphabetical order, applying common filters."""
    if not roms_path.exists():
        return
    try:
        entries = sorted(roms_path.iterdir(), key=lambda x: x.name.lower())
    except OSError:
        return

    # One game, one entry: a .bin that belongs to a .cue is not a second game.
    hidden = set() if scan_dirs else _shadowed_by_a_descriptor(entries)

    for f in entries:
        if f.name.startswith(".") or "example" in f.name.lower():
            continue
        if scan_dirs:
            if f.is_dir():
                yield f
        else:
            if not f.is_file():
                continue
            if extensions and not matches_ext(f.name, extensions):
                continue
            if f.name.lower() in hidden:
                continue
            yield f
