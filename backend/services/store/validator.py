"""Judge whether the shape a transformation produced is really playable.

The class was decided by `inspector.py`, the shape was produced by
`transformer.py`, and this is the last thing that looks at either before import
(17) puts bytes where the library scan finds them.  Matrix §5.1's *validate*
column, read off the persisted verdict:

    A  one member with a declared extension   D  header readable
    B  magic bytes                            E  descriptor + every file it names
    C  the archive opens; the name preserved  F  the identity file

── It changes nothing ─────────────────────────────────────────────────────
Not the download, not the shape.  Every path here is opened `"rb"`, every
directory is listed, and the module contains no `mkdir`, no `unlink`, no
`rename` and no `open` in any writing mode.  A refusal therefore leaves the
work area exactly as the transformation left it, which is what makes a failed
validation cost nothing but a sentence: the bytes are still there for the next
attempt, and `test_store_validator.py` fingerprints the source **and** the
produced shape before and after, in success and in failure alike.

── It reads little ────────────────────────────────────────────────────────
A signature is a handful of bytes at a known offset, so that is what is read:
`seek`, then `read(len(magic))`, never a head buffer "just in case" and never
a checksum of the file.  An 8 GB `.xci` is judged by a few hundred bytes, and
`.cdi` is judged by its *last* eight — the one format here whose version word
sits at the end.  The cost of validating a shape is therefore the number of
files in it, not the number of gigabytes.

A whole-file hash was the obvious alternative and is worthless here: there is
nothing to compare it to.  `AcquiredTarget.info_hash` hashes torrent metadata,
not this file's content (`jobs.AcquiredTarget`), so a digest of 12 GB would
take minutes to produce an answer nothing can check.

──────────────────────────────────────────────────────────────────────────────
What is verified, what is merely plausible, and what cannot be checked at all
──────────────────────────────────────────────────────────────────────────────
§5.1 says "magic bytes" for B and "header readable" for D without saying which
bytes, for which format — because there is no single answer.  A `.nes` has a
famous four-byte header; a `.sfc` has none at all, which is exactly why §5.1
records that the SNES has no exclusive suffix usable as proof.  So the table
below is keyed on the **format**, never on the system (§0, §5.2: a new pack
declaring `*.chd` is validated without an edit here), and every entry carries
one of two strengths:

  **proof** — the format's own readers require the field, and the extension
  names exactly one format.  A file that does not carry it is not that thing,
  so a miss is a **refusal**.

  **hint** — the extension legitimately names several formats, or there is
  material evidence of a variant without the field.  A match is evidence; a
  miss proves nothing and the verdict is `unverified`, never a refusal.

And a format with no entry at all is **unverifiable**: `.sfc` `.smc` `.sms`
`.gg` `.pce` `.sgx` `.sg` `.md` `.smd` `.bin` are raw memory or track dumps
with no field any reader checks.  Inventing a check for one of those would be
worse than having none, because it would look like a filter and catch nothing.

**The floor applies to all three.** A file the library would list must not be
empty, and a set must carry every file its descriptor names.  So no class can
end in a check that cannot fail, which is the failure mode this whole module
exists to avoid — a validation that always passes is a lie about a safety net.

**What a signature never proves.** That this is the *right* game: the region,
the revision, that it is not a bad dump of a real cartridge.  Those are
questions about content, not about format, and no header answers them.  The
claim here is exactly "this file is plausibly what its extension announces",
and it is worth making because the case it catches is real — see `_XCI` below.

── A required BIOS is named, never a refusal ──────────────────────────────
§5.3 rule 4.  Seven systems declare a `required: true` file and the box refuses
the launch without it, naming the file (`backend/services/bios.py:222-250`).
That is a *launch* blocker.  Refusing the import as well would delete the one
thing the player could still act on — the game would not be there to play once
they copied the BIOS in — so the missing file is reported on the job and the
validation is unaffected by it.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from ..bios import missing_required
from ..catalog import load_catalog
from ..gamemedia.identity import read_sfo
from ..rom_scanner import _DISC_DESCRIPTORS, matches_ext, shadowed_by_a_descriptor
from .inspector import (MAX_LISTING_ENTRIES, MISSING_7Z, InspectionError,
                        _archive_members, _missing_descriptor_files)
from .transformer import SHAPE_DIR, Shape

log = logging.getLogger(__name__)

#: The three verdicts, persisted on the job row as `validation`.
VERIFIED = "verified"
UNVERIFIED = "unverified"
REFUSED = "refused"

#: How many files one shape may hold before this refuses to walk it. The same
#: bound inspection and transformation use, and for the same reason.
MAX_SHAPE_ENTRIES = MAX_LISTING_ENTRIES

#: How many missing BIOS files one sentence names before it stops listing.
MAX_NAMED_BIOS_FILES = 4


class ValidationError(RuntimeError):
    """Validation could not run — not that the download is bad.

    The mirror of `InspectionError`: "this box has no 7z" and "this archive is
    truncated" are different facts, and a player who reads the first goes and
    updates GameCore where the second sends them back to the download.
    """


@dataclass(frozen=True)
class Validation:
    """What was proven about a shape, and what could not be."""

    verdict: str
    #: Why it was refused, in words a player can act on. Empty otherwise.
    reason: str = ""
    #: Names whose format was actually established, with what established it.
    proven: tuple[str, ...] = ()
    #: Names whose format carries nothing this box can check. Reported, never
    #: a refusal — see the module docstring.
    unproven: tuple[str, ...] = ()
    #: §5.3 rule 4: the launch blocker this game will hit, if any. Never
    #: affects `verdict`.
    bios_warning: str = ""

    @property
    def ok(self) -> bool:
        return self.verdict != REFUSED


@dataclass(frozen=True)
class _Signature:
    """One format's fixed field, where it sits, and what a miss is worth.

    `probes` are alternatives: any one matching establishes the format, which
    is how one extension covers several families (`.iso`) or several revisions
    of one (`.fds`). A negative offset is measured from the end of the file.
    `source` is not decoration — it is the reason this box is allowed to refuse
    a download on four bytes, and it is checked in review, not at runtime.
    """

    what: str
    probes: tuple[tuple[int, bytes], ...]
    proof: bool
    source: str
    #: A length below which the format cannot exist at all. `0` means the
    #: probes are the only floor.
    minimum: int = 0


# The Nintendo cartridge logo, verified by the hardware before it will run a
# cartridge: the DMG/CGB boot ROM compares it byte for byte and halts on a
# mismatch (Pan Docs, "The Cartridge Header" — 0x0104-0x0133), and the GBA BIOS
# and the DS firmware do the same with their own copy (GBATEK, "GBA Cartridge
# Header" at 0x04 and "DS Cartridge Header" at 0xC0, whose CRC16 sits at
# 0x15C). Eight bytes are compared and not the whole field (48 on the Game
# Boy, 156 on the DS): the prefix is already decisive at one chance in 2^64,
# and a shorter comparison cannot refuse a dump over a byte some trimmer
# touched.
_GB_LOGO = bytes.fromhex("ceed6666cc0d000b")
_NINTENDO_LOGO = bytes.fromhex("24ffae51699aa221")

#: `.xci` is a **hint** and not a proof, against the documentation, on
#: evidence. Switchbrew's gamecard format puts `HEAD` at 0x100, after the
#: 0x100-byte RSA-2048 signature — but the one real `.xci` this project has
#: (an 8 GB download in the development sandbox) carries no `HEAD` there, no
#: `HFS0` and no `PFS0` anywhere in its first 256 MiB — while measuring
#: exactly 0x1DC000000 bytes, the size an untrimmed 8 GB gamecard image is
#: documented to have, with its last 2.7 GiB zeroed. Either that file is not a
#: gamecard image or the documented layout has a variant nobody wrote down. A
#: refusal must not rest on an open question, so a match counts as proof of
#: format and a miss counts as nothing. Nothing in the test suite reads that
#: file (it is versioned nowhere), and this note is the whole of its
#: contribution.
_XCI = _Signature(
    "a Switch gamecard image", ((0x100, b"HEAD"),), False,
    "switchbrew, Gamecard Format — contradicted by the one real sample, see above")

#: Keyed on the suffix, never on the system: half of a pair predicate (§0).
_SIGNATURES: dict[str, _Signature] = {
    # ── containers, whose own specification opens with a fixed field ──────
    ".zip": _Signature(
        "a zip archive",
        ((0, b"PK\x03\x04"), (0, b"PK\x05\x06"), (0, b"PK\x07\x08")), True,
        "PKWARE APPNOTE.TXT 4.3.7 (0x04034b50); Python's own "
        "zipfile.stringFileHeader, and measured on a zip written here"),
    ".7z": _Signature(
        "a 7z archive", ((0, b"7z\xbc\xaf\x27\x1c"),), True,
        "7-Zip 7zHeader.cpp kSignature; measured on an archive written by the "
        "7z on this box"),
    ".gz": _Signature(
        "a gzip stream", ((0, b"\x1f\x8b"),), True,
        "RFC 1952 §2.3.1 ID1/ID2; measured on gzip.compress output"),
    ".chd": _Signature(
        "a MAME CHD image", ((0, b"MComprHD"),), True,
        "MAME's CHD header tag (src/lib/util/chd.*), which every version of "
        "the format has carried; file(1) agrees"),
    ".rvz": _Signature(
        "an RVZ disc image", ((0, b"RVZ\x01"),), True,
        "Dolphin Source/Core/DiscIO/WIABlob (RVZ/WIA magic); file(1) agrees"),
    ".wbfs": _Signature(
        "a WBFS disc image", ((0, b"WBFS"),), True,
        "the WBFS header's magic word, read by every WBFS reader"),
    ".cso": _Signature(
        "a compressed ISO", ((0, b"CISO"), (0, b"ZISO")), True,
        "the ciso/maxcso header magic, and PPSSPP's CSO block device which "
        "accepts both spellings"),
    ".pbp": _Signature(
        "a PSP PBP package", ((0, b"\x00PBP"),), True,
        "the PBP header magic 00 50 42 50"),
    ".wux": _Signature(
        "a Wii U compressed disc image", ((0, b"WUX0"),), True,
        "the wux container's own header, defined by the format"),
    ".gcm": _Signature(
        "a GameCube disc image",
        ((0x1C, b"\xc2\x33\x9f\x3d"), (0x18, b"\x5d\x1c\x9e\xa3")), True,
        "YAGCD/WiiBrew disc header magic words; file(1) agrees on both"),
    ".rpx": _Signature(
        "a Wii U executable", ((0, b"\x7fELF"),), True,
        "RPX is an ELF variant; ELF magic per its specification, and the same "
        "check installer/fetch.py:MAGIC already makes"),
    ".xex": _Signature(
        "an Xbox 360 executable", ((0, b"XEX2"), (0, b"XEX1")), True,
        "the XEX header magic; file(1) agrees"),
    ".nsp": _Signature(
        "a Switch PFS0 package", ((0, b"PFS0"),), True,
        "switchbrew, PFS0 — the NSP container format; file(1) agrees"),
    ".3ds": _Signature(
        "a 3DS game card image", ((0x100, b"NCSD"),), True,
        "3dbrew, NCSD — magic at 0x100 after the signature; file(1) agrees"),
    ".cia": _Signature(
        "a 3DS CIA package", ((0, b"\x20\x20\x00\x00\x00\x00\x00\x00"),), True,
        "3dbrew, CIA — the archive header size is always 0x2020, type and "
        "version zero"),
    ".wad": _Signature(
        "a Wii WAD package",
        ((0, b"\x00\x00\x00\x20Is"), (0, b"\x00\x00\x00\x20ib")), False,
        "WiiBrew, WAD files — header size 0x20 then the type; a hint because "
        "the same extension names Doom's unrelated IWAD/PWAD"),
    ".mds": _Signature(
        "an Alcohol media descriptor", ((0, b"MEDIA DESCRIPTOR"),), False,
        "the MDS format's 16-byte signature; a hint because file(1) reads the "
        "same prefix as an Amiga MED song, so the string is not unique"),
    ".ccd": _Signature(
        "a CloneCD descriptor", ((0, b"[CloneCD]"),), False,
        "CloneCD writes this INI section first; a hint because it is text and "
        "a byte-order mark or a comment may legitimately precede it"),

    # ── cartridges, where the console itself enforces the field ───────────
    ".nes": _Signature(
        "an iNES image", ((0, b"NES\x1a"),), True,
        "nesdev, iNES/NES 2.0 header; file(1) agrees"),
    ".unf": _Signature(
        "a UNIF image", ((0, b"UNIF"),), True,
        "the UNIF specification; file(1) agrees"),
    ".unif": _Signature(
        "a UNIF image", ((0, b"UNIF"),), True,
        "the UNIF specification; file(1) agrees"),
    ".fds": _Signature(
        "a Famicom Disk System image",
        ((0, b"FDS\x1a"), (0, b"\x01*NINTENDO-HVC*")), True,
        "nesdev, FDS file format — the fwNES header, or the raw disk's own "
        "block 1; file(1) agrees on the first"),
    ".gb": _Signature(
        "a Game Boy cartridge", ((0x104, _GB_LOGO),), True,
        "Pan Docs, The Cartridge Header — the boot ROM halts on a mismatch; "
        "file(1) agrees"),
    ".gbc": _Signature(
        "a Game Boy Color cartridge", ((0x104, _GB_LOGO),), True,
        "Pan Docs, The Cartridge Header; file(1) agrees"),
    ".gba": _Signature(
        "a Game Boy Advance cartridge", ((0x04, _NINTENDO_LOGO),), True,
        "GBATEK, GBA Cartridge Header — the BIOS verifies it; file(1) agrees"),
    ".nds": _Signature(
        "a Nintendo DS cartridge", ((0xC0, _NINTENDO_LOGO),), True,
        "GBATEK, DS Cartridge Header — the firmware checks its CRC16 at "
        "0x15C; file(1) agrees"),
    ".z64": _Signature(
        "a big-endian Nintendo 64 image", ((0, b"\x80\x37\x12\x40"),), True,
        "the N64 PI BSD DOM1 configuration word, the first word of every "
        "cartridge; §3.4 asks gopher64 for exactly this byte order"),
    ".n64": _Signature(
        "a little-endian Nintendo 64 image", ((0, b"\x40\x12\x37\x80"),), True,
        "the same word, little-endian — §3.4, gopher64"),
    ".v64": _Signature(
        "a byte-swapped Nintendo 64 image", ((0, b"\x37\x80\x40\x12"),), True,
        "the same word, byte-swapped — §3.4, gopher64"),

    # ── hints: the extension names more than one thing ────────────────────
    ".iso": _Signature(
        "a disc image",
        ((0x8001, b"CD001"),                  # ISO 9660, 2048-byte sectors
         (0x9319, b"CD001"),                  # ISO 9660, raw 2352-byte sectors
         (0x18, b"\x5d\x1c\x9e\xa3"),         # Wii
         (0x1C, b"\xc2\x33\x9f\x3d"),         # GameCube
         (0x10000, b"MICROSOFT*XBOX*MEDIA"),  # XDVDFS, sector 32
         (0, b"SEGA SEGASATURN"),
         (0, b"SEGA SEGAKATANA"),
         (0, b"SEGADISCSYSTEM")), False,
        "the two ISO 9660 offsets file(1) recognises, measured on this box; "
        "the GameCube and Wii disc magics, which file(1) also recognises; the "
        "Sega IP.BIN headers; XDVDFS. A hint because the set is open — a Wii U "
        "WUD is none of them and is still a disc",
        minimum=0x8000),
    ".cdi": _Signature(
        "a DiscJuggler image", ((-8, b"\x04\x00\x00\x80"),
                                (-8, b"\x05\x00\x00\x80"),
                                (-8, b"\x06\x00\x00\x80")), False,
        "cdirip reads the version word from the last eight bytes (2.0, 3.0, "
        "3.5); a hint because older writers exist and the word is at the end, "
        "where a trim would remove it"),
    ".gen": _Signature(
        "a Mega Drive image", ((0x100, b"SEGA"),), False,
        "the TMSS check on Mega Drive hardware reads 'SEGA' at 0x100; file(1) "
        "agrees. A hint, and deliberately not extended to `.md`, `.mdx` or "
        "`.smd`, which also name interleaved copier dumps with no header there"),
    ".32x": _Signature(
        "a 32X image", ((0x100, b"SEGA"),), False,
        "same header, same hardware check, same caveat as `.gen`"),
    ".xci": _XCI,
}


# ── reading a few bytes, and only a few ────────────────────────────────────


def _matches(path: Path, signature: _Signature) -> bool:
    """Did one of this format's probes find its field where it belongs?

    One open, one seek and one read per probe — no head buffer, so the cost is
    the length of the magic and not the size of the file.  A negative offset is
    measured from the end, which is where DiscJuggler puts its version word.
    A probe that reaches past the end simply does not match: a truncated
    download is not a special case to detect, it is a file whose header is not
    there.
    """
    try:
        with path.open("rb") as stream:
            for offset, magic in signature.probes:
                try:
                    stream.seek(offset,
                                os.SEEK_END if offset < 0 else os.SEEK_SET)
                    if stream.read(len(magic)) == magic:
                        return True
                except OSError:
                    # A seek before the start of a file shorter than the probe.
                    # Not an unreadable file — just not this format.
                    continue
    except OSError as exc:
        raise ValidationError(
            f"the produced file {path.name} cannot be read") from exc
    return False


# ── what the library would actually list ───────────────────────────────────


def _entries(root: Path) -> tuple[Path, ...]:
    try:
        with os.scandir(root) as scan:
            names = sorted((entry.name for entry in scan), key=str.lower)
    except OSError as exc:
        raise ValidationError("the produced shape cannot be listed") from exc
    if len(names) > MAX_SHAPE_ENTRIES:
        raise ValidationError("the produced shape holds too many files to check")
    return tuple(root / name for name in names)


def _listed(files: tuple[Path, ...], extensions: tuple[str, ...]) -> tuple[Path, ...]:
    """The produced files the scan would show as games.

    `shadowed_by_a_descriptor` is subtracted for the same reason the
    transformation subtracts it: a track opened through its `.cue` is not a
    library entry and is not judged as one.  An empty `extensions` list means
    "list everything" (§1.5), and is honoured rather than read as "list
    nothing" — which would turn `rpcs3`'s empty list into a refusal.
    """
    hidden = shadowed_by_a_descriptor(list(files), list(extensions))
    return tuple(f for f in files
                 if f.name.lower() not in hidden
                 and (not extensions or matches_ext(f.name, list(extensions))))


@dataclass
class _Findings:
    """What one class's checks established, accumulated as they run."""

    reason: str = ""
    proven: list[str] = field(default_factory=list)
    unproven: list[str] = field(default_factory=list)


def _check_file(path: Path, found: _Findings, *, floor_only: bool = False) -> bool:
    """The floor plus the signature, for one file the library would list.

    Returns False as soon as something refuses, so the caller stops at the
    first fault instead of collecting a list nobody reads.

    `floor_only` is for a file the scan will never list on its own — a track
    opened through its `.cue`.  It is still held to the floor, because an empty
    track stops the game at its first read, but it is not reported as
    unproven: `.bin` is raw track data and *has* no header, so listing it
    beside a `.sfc` would drown the one fact that verdict exists to carry.
    """
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ValidationError(
            f"the produced file {path.name} cannot be read") from exc
    if size == 0:
        # The floor, and the one refusal every format has. A download can
        # arrive complete by every earlier measure and still be empty: the
        # acquisition size is `0` whenever the service does not say
        # (`jobs.AcquiredTarget`), so nothing before this point compared it.
        found.reason = (f"the download is empty: {path.name} has no content, "
                        "so there is nothing to play")
        return False

    if floor_only:
        return True

    signature = _SIGNATURES.get(path.suffix.lower())
    if signature is None:
        found.unproven.append(path.name)
        return True

    if _matches(path, signature):
        found.proven.append(f"{path.name} is {signature.what}")
        return True
    if size < signature.minimum:
        found.reason = (f"{path.name} is too short to be {signature.what} "
                        f"({size} bytes)")
        return False
    if signature.proof:
        found.reason = (f"{path.name} is not {signature.what}: the bytes its "
                        "format requires are not there, so this is not the "
                        "file its name claims")
        return False
    found.unproven.append(path.name)
    return True


# ── one check per class ────────────────────────────────────────────────────


def _validate_plain(files: tuple[Path, ...], extensions: tuple[str, ...],
                    ingestion_class: str) -> _Findings:
    """Classes A, B and D: the file itself, and whether it would be listed.

    One function for three classes, and that is the matrix's own logic rather
    than a shortcut.  §5.2 says A, B and D are separated by *what the ingest
    must physically do* — unpack, do nothing, unpack only an undeclared
    container — and that work is finished by the time this runs.  What is left
    is one question, and it does not change with the predicate that routed the
    job here: **is this file plausibly what its name announces?**  §5.1 words
    it three ways (a declared extension, magic bytes, a readable header) and
    §3.4 then asks `nes` for an iNES header, `gamegear` for "magic" and
    `gopher64` for a byte order — the same check, named after whichever half of
    it that row cared about.
    """
    found = _Findings()
    listed = _listed(files, extensions)
    if not listed:
        arrived = ", ".join(f.name for f in files[:3]) or "nothing"
        found.reason = (
            f"this class {ingestion_class} shape holds no file the library "
            f"would list ({arrived}); it would import and show no game")
        return found
    for path in listed:
        if not _check_file(path, found):
            return found
    return found


def _validate_archive(files: tuple[Path, ...], root: Path) -> _Findings:
    """Class C: the archive opens, and it is still called what it was called.

    Both halves matter and neither implies the other.  §5.1 requires the name
    *preserved* because the emulator looks the romset up by it — a `sf2.zip`
    that arrived and left as `sf2 (World).zip` is a file MAME will not find —
    and the source is right there beside the shape to compare against.  Opening
    is a real read of the produced copy and not a repeat of inspection's: what
    inspection listed was the download, and this lists what was written from it.
    """
    found = _Findings()
    if len(files) != 1:
        names = ", ".join(f.name for f in files[:4]) or "nothing"
        found.reason = ("this class C shape is not a single archive "
                        f"({names}); §5.1 requires the archive itself, whole")
        return found
    archive = files[0]
    if not _check_file(archive, found):
        return found

    try:
        source = {entry.name for entry in _entries(root.parent)} - {SHAPE_DIR}
    except ValidationError:
        source = set()
    if source and archive.name not in source:
        # Named by the whole download and not by a guess at which of its files
        # was the archive: if there is more than one, saying which one was
        # meant is exactly what this step cannot know.
        arrived = ", ".join(sorted(source))
        found.reason = (
            f"the archive was renamed on the way through: the download holds "
            f"{arrived} and the shape holds {archive.name!r}. The emulator "
            "looks a romset up by its name, so a renamed archive is a game it "
            "cannot find")
        return found

    try:
        members = _archive_members(archive)
    except InspectionError as exc:
        if str(exc) == MISSING_7Z:
            raise ValidationError(MISSING_7Z) from exc
        found.reason = (f"the archive {archive.name} cannot be opened, so "
                        "nothing can read the romset inside it")
        return found
    if not members:
        found.reason = f"the archive {archive.name} is empty"
        return found
    found.proven.append(f"{archive.name} opens and holds {len(members)} file(s)")
    return found


def _validate_set(files: tuple[Path, ...],
                  extensions: tuple[str, ...]) -> _Findings:
    """Class E: the descriptor, and every file it names, in the shape.

    The completeness arithmetic is `inspector._missing_descriptor_files` and is
    deliberately not written twice — it already knows that a `.ccd` needs its
    `.img` and `.sub`, that a `.mds` needs its `.mdf`, and that everything else
    is read out of the descriptor's own text.  What is new is *where* it is
    asked: inspection asked it of the download, and this asks it of the shape,
    which is the only thing import will carry.  A track dropped between the two
    is invisible to the first question and fatal to the game.
    """
    found = _Findings()
    descriptors = tuple(f for f in files
                        if f.suffix.lower() in _DISC_DESCRIPTORS
                        and (not extensions or matches_ext(f.name, list(extensions))))
    if not descriptors:
        found.reason = ("this class E shape holds no descriptor the library "
                        "would list, so its tracks are an unplayable pile")
        return found
    for descriptor in descriptors:
        if not _check_file(descriptor, found):
            return found
        try:
            missing = _missing_descriptor_files(descriptor, files)
        except InspectionError as exc:
            raise ValidationError(str(exc)) from exc
        if missing:
            found.reason = (
                f"{descriptor.name} names {', '.join(dict.fromkeys(missing))}, "
                "which the shape does not hold; the game would start and stop "
                "at the missing track")
            return found
        named = _named_companions(descriptor, files)
        for companion in named:
            if not _check_file(companion, found, floor_only=True):
                return found
        found.proven.append(
            f"{descriptor.name} and the {len(named)} file(s) it names are present")
    return found


def _named_companions(descriptor: Path,
                      files: tuple[Path, ...]) -> tuple[Path, ...]:
    """The files this descriptor turned out to name, as produced paths.

    `shadowed_by_a_descriptor` is the scanner's own map from a hidden file to
    the entry that hides it, so asking it which files this descriptor owns is
    asking the same question the library answers when it decides what to list.
    Extensions are deliberately not passed: the question here is what this
    descriptor *names*, not what the pack would show, and a companion is a
    companion whether or not its own extension is declared.
    """
    hidden = shadowed_by_a_descriptor(list(files), None)
    return tuple(f for f in files if hidden.get(f.name.lower()) == descriptor.name)


def _validate_directory(entries: tuple[Path, ...]) -> _Findings:
    """Class F: the game says who it is.

    `identity.read_sfo` is the reader the scraper already uses on these trees
    (`PS3_GAME/PARAM.SFO`, `sce_sys/param.sfo` and the three other spellings it
    knows), and reusing it is what keeps validation and identification agreeing
    about the same directory: a tree this passes but the scraper cannot read
    would be an import that produces a tile with no name.

    The check is the parse and not the presence.  A zero-byte `PARAM.SFO`
    exists; `read_sfo` answers `{}` for it, because the `\\x00PSF` magic is the
    first thing it compares.
    """
    found = _Findings()
    directories = tuple(e for e in entries
                        if e.is_dir() and not e.is_symlink())
    if not directories:
        found.reason = ("this class F shape holds no game directory; a folder "
                        "system lists directories and nothing else (§1.2)")
        return found
    for directory in directories:
        identity = read_sfo(directory)
        if not identity:
            found.reason = (
                f"{directory.name} carries no readable identity file "
                "(PS3_GAME/PARAM.SFO or sce_sys/param.sfo), so nothing can "
                "tell what game it is")
            return found
        title = identity.get("TITLE") or identity.get("TITLE_ID") or "a game"
        found.proven.append(f"{directory.name} identifies itself as {title!r}")
    return found


# ── the required BIOS, named and never blocking ────────────────────────────


def bios_warning(system_id: str) -> str:
    """The launch blocker this console will hit, or "".

    §5.3 rule 4, and the whole of it: this sentence is the *report*, and it is
    read by nothing that decides.  `bios.missing_required` is the same function
    the launch gate calls (`bios.py:222-250`), asked one step earlier so the
    player learns at download time rather than in front of a refused launch.

    Never raises, for the same reason that function does not: a check that
    cannot run must never be the thing that costs an import.
    """
    try:
        missing = missing_required(system_id)
    except Exception:                                          # noqa: BLE001
        log.exception("store: the BIOS check for %r failed", system_id)
        return ""
    if not missing:
        return ""
    # The same two spellings `bios.launch_blocker` uses, because they are two
    # different instructions: a named file is copied to a name, and an
    # `anyFile` pack (duckstation) takes whatever image it recognises out of a
    # directory, so naming one would be inventing a filename.
    names = [f"an image in {entry.get('path') or 'its BIOS directory'}"
             if entry.get("any_file")
             else (entry.get("file") or "a BIOS file")
             for entry in missing]
    shown = ", ".join(names[:MAX_NAMED_BIOS_FILES])
    if len(names) > MAX_NAMED_BIOS_FILES:
        shown += f" and {len(names) - MAX_NAMED_BIOS_FILES} more"
    return (f"once imported this game will not start until {shown} "
            f"{'is' if len(names) == 1 else 'are'} in place — that is a launch "
            "blocker, not a reason to refuse the download")


# ── the whole judgement ────────────────────────────────────────────────────


def validate(shape: Shape, system_id: str) -> Validation:
    """Judge one produced shape. Reads; never writes; always answers.

    A refusal comes back as a `Validation` rather than an exception, exactly as
    `inspector.inspect` answers an incomplete download: the worker persists the
    verdict *and then* fails the job, so a job refused here is a job whose row
    says what was found.  `ValidationError` is kept for the other thing — a
    check this box could not run at all.
    """
    pack = load_catalog().get(system_id)
    if pack is None or pack.data.get("kind") != "emulator":
        raise ValidationError("the downloaded job's emulator pack is unavailable")
    roms = pack.data.get("roms") or {}
    extensions = tuple(x for x in (roms.get("extensions") or [])
                       if isinstance(x, str))

    root = shape.root
    if not root.is_dir() or root.is_symlink():
        raise ValidationError("the produced shape is not there to be checked")
    entries = _entries(root)
    if not entries:
        raise ValidationError("the produced shape is empty")
    files = tuple(e for e in entries if e.is_file() and not e.is_symlink())

    ingestion_class = shape.ingestion_class
    if ingestion_class == "F":
        found = _validate_directory(entries)
    elif ingestion_class == "C":
        found = _validate_archive(files, root)
    elif ingestion_class == "E":
        found = _validate_set(files, extensions)
    elif ingestion_class in ("A", "B", "D"):
        found = _validate_plain(files, extensions, ingestion_class)
    else:
        raise ValidationError("this download has no ingestion class to check")

    warning = bios_warning(system_id)
    if found.reason:
        verdict = REFUSED
    elif found.proven:
        verdict = VERIFIED
    else:
        # Nothing here carries a field this box can check. Said out loud, and
        # not dressed up as a pass: it is the honest answer for a `.sfc`, and
        # a reader who sees it knows the import rests on the shape alone.
        verdict = UNVERIFIED
    return Validation(verdict=verdict, reason=found.reason,
                      proven=tuple(found.proven), unproven=tuple(found.unproven),
                      bios_warning=warning)
