"""Eden's Switch saves, copied into Ryujinx before it starts. Eden is never written.

The Switch ran Eden (dev.eden_emu.eden) from v1.2.84; on a box that used it,
Eden holds the only copy of the saves. Ryujinx finds a save through its index
(imkvdb.arc), not by folder name, so each save gets a container and an index
entry shaped like the ones Ryujinx 1.3.3 writes itself:

  Eden     nand/user/save/0000000000000000/<U1:016X><U0:016X>/<title:016X>/
           U0, U1 = the user's 16 bytes as two u64 LE; all zeros = device save.
           Users: nand/system/save/8000000000000010/su/avators/profiles.dat
  Ryujinx  bis/user/save/<id:016x>/{0/, ExtraData0, ExtraData1}
           bis/system/save/8000000000000000/{0,1}/{imkvdb.arc, lastPublishedId}

Rules: a save Ryujinx already has (same title, user, type) is never touched;
each Eden save is copied at most once per target (`MARKER`, beside the index,
so it follows a profile's folder); a save is committed whole or not at all.
"""
from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from backend.utils import atomic_write_bytes, atomic_write_json

EDEN_APP_ID = "dev.eden_emu.eden"
RYUJINX_APP_ID = "io.github.ryubing.Ryujinx"
USER_SAVES = Path("bis/user/save")
INDEX_DIR = Path("bis/system/save/8000000000000000")
MARKER = "gamecore-eden-import.json"
EDEN_SAVES = Path("nand/user/save")
EDEN_PROFILES = Path("nand/system/save/8000000000000010/su/avators/profiles.dat")
# Eden's size record, skipped: Ryujinx keeps the sizes in ExtraData.
EDEN_SIZE_FILE = ".yuzu_save_size"
# Where the Eden-era switch pack put a profile's saves: <profile>/switch/save.
EDEN_PROFILE_FOLDER = "save"
# Ryujinx's own default user (Profiles.json `last_opened` on a fresh install).
RYUJINX_DEFAULT_USER = "00000000000000010000000000000000"

TYPE_SYSTEM, TYPE_ACCOUNT, TYPE_DEVICE = 0, 1, 3
SPACE_USER = 1
INDEX_SAVE_ID = 0x8000000000000000
# What Ryujinx 1.3.3 writes for a new index save, and DataSize 0 for the
# imported saves: Ryujinx extends a save smaller than the game's declared size.
INDEX_SAVE_SIZE = 0xC0000
EXTRA_DATA_SIZE = 0x200
ENTRY_SIZE = 0x40
PROFILE_RECORD, PROFILE_HEADER, PROFILE_SLOTS = 0xC8, 0x10, 8
ZERO_USER = bytes(16)


class ImportRefused(Exception):
    """Something cannot be told apart safely; nothing was written."""


@dataclass(frozen=True)
class EdenSave:
    title: int
    user: bytes          # 16 raw bytes, Ryujinx's user for account saves
    kind: int            # TYPE_ACCOUNT or TYPE_DEVICE
    path: Path

    @property
    def key(self) -> str:
        return f"{self.title:016X}:{self.kind}"


# ── reading both layouts ─────────────────────────────────────────────────────

def eden_users(profiles_dat: Path) -> list[bytes]:
    """The users Eden knows, as 16 raw bytes. [] when the file is missing."""
    try:
        raw = profiles_dat.read_bytes()
    except OSError:
        return []
    users = []
    for slot in range(PROFILE_SLOTS):
        at = PROFILE_HEADER + slot * PROFILE_RECORD
        uuid = raw[at:at + 16]
        if len(uuid) == 16 and uuid != ZERO_USER:
            users.append(uuid)
    return users


def eden_dir_user(name: str) -> bytes:
    """Eden's folder name (U1 then U0, hex) back to the 16 raw bytes."""
    return struct.pack("<QQ", int(name[16:], 16), int(name[:16], 16))


def ryujinx_user(ryujinx: Path) -> bytes:
    """The Ryujinx user that plays: Profiles.json `last_opened`, as raw bytes."""
    try:
        data = json.loads((ryujinx / "system/Profiles.json").read_text(encoding="utf-8"))
        user = str(data.get("last_opened") or RYUJINX_DEFAULT_USER)
        return struct.pack("<QQ", int(user[:16], 16), int(user[16:32], 16))
    except FileNotFoundError:
        return struct.pack("<QQ", 1, 0)
    except (OSError, ValueError, AttributeError) as e:
        raise ImportRefused(f"Ryujinx's Profiles.json is unreadable ({e.__class__.__name__})") from e


def _has_data(folder: Path) -> bool:
    return any(p.is_file() and p.name != EDEN_SIZE_FILE for p in folder.rglob("*"))


def eden_saves(save_root: Path, users: list[bytes], target_user: bytes) -> tuple[list[EdenSave], list[str]]:
    """Every Eden save worth copying, and a note for each folder left out.

    Account saves come from Eden's single user, re-keyed to `target_user`;
    with several users the right one cannot be told, so none is copied.
    """
    base = save_root / "0000000000000000"
    saves: list[EdenSave] = []
    notes: list[str] = []
    if not base.is_dir():
        return saves, notes
    for user_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        try:
            user = eden_dir_user(user_dir.name)
        except ValueError:
            notes.append(f"{user_dir.name}: not a user folder, skipped")
            continue
        if user == ZERO_USER:
            kind, owner = TYPE_DEVICE, ZERO_USER
        elif user in users and len(users) == 1:
            kind, owner = TYPE_ACCOUNT, target_user
        else:
            why = "several Eden users" if user in users else "not an Eden user"
            notes.append(f"{user_dir.name}: {why}, skipped")
            continue
        for title_dir in sorted(p for p in user_dir.iterdir() if p.is_dir()):
            try:
                title = int(title_dir.name, 16)
            except ValueError:
                continue
            if _has_data(title_dir):
                saves.append(EdenSave(title, owner, kind, title_dir))
    return saves, notes


# ── the index (LibHac KeyValueArchive) ───────────────────────────────────────

def attribute(title: int, user: bytes, kind: int, static_id: int = 0) -> bytes:
    """SaveDataAttribute: program id, user, static save id, type (0x40 bytes)."""
    return struct.pack("<Q16sQB", title, user, static_id, kind).ljust(ENTRY_SIZE, b"\0")


def read_index(index_dir: Path) -> list[tuple[bytes, bytes]]:
    """(key, value) pairs from the committed imkvdb.arc; [] when there is none."""
    try:
        raw = (index_dir / "0/imkvdb.arc").read_bytes()
    except FileNotFoundError:
        return []
    if raw[:4] != b"IMKV" or len(raw) < 12:
        raise ImportRefused("Ryujinx's save index is not an IMKV archive")
    count, at, out = struct.unpack_from("<I", raw, 8)[0], 12, []
    for _ in range(count):
        if raw[at:at + 4] != b"IMEN":
            raise ImportRefused("Ryujinx's save index is truncated")
        ksz, vsz = struct.unpack_from("<II", raw, at + 4)
        out.append((raw[at + 12:at + 12 + ksz], raw[at + 12 + ksz:at + 12 + ksz + vsz]))
        at += 12 + ksz + vsz
    return out


def _order(entry: tuple[bytes, bytes]) -> tuple:
    """LibHac's SaveDataAttribute order: program, type, user, static id, rank,
    index. Its flat map refuses an archive out of order (Ryujinx aborts)."""
    program, high, low, static, kind, rank, idx = struct.unpack_from("<QQQQBBH", entry[0])
    return program, kind, high, low, static, rank, idx


def pack_index(entries: list[tuple[bytes, bytes]]) -> bytes:
    entries = sorted(entries, key=_order)
    body = b"".join(b"IMEN" + struct.pack("<II", len(k), len(v)) + k + v for k, v in entries)
    return b"IMKV" + struct.pack("<II", 0, len(entries)) + body


def extra_data(attr: bytes, owner: int, size: int, commit_id: bytes) -> bytes:
    """SaveDataExtraData: attribute, owner id, sizes, commit id (0x200 bytes)."""
    tail = struct.pack("<QQI4xQQ", owner, 0, 0, size, size) + commit_id
    return (attr + tail).ljust(EXTRA_DATA_SIZE, b"\0")


def _write_extra(folder: Path, data: bytes) -> None:
    for name in ("ExtraData0", "ExtraData1"):
        atomic_write_bytes(folder / name, data)


class Index:
    """Ryujinx's save index for one target, written back after every save."""

    def __init__(self, ryujinx: Path):
        self.dir = ryujinx / INDEX_DIR
        self.saves = ryujinx / USER_SAVES
        self.entries = read_index(self.dir)
        last = self.dir / "0/lastPublishedId"
        self.last_id = struct.unpack("<Q", last.read_bytes()[:8])[0] if last.is_file() else 0
        self.keys = {k[:0x21] for k, _v in self.entries}

    def has(self, attr: bytes) -> bool:
        return attr[:0x21] in self.keys

    def next_id(self) -> int:
        """Past every id Ryujinx published, and past every folder on disk."""
        used = [self.last_id] + [struct.unpack_from("<Q", v)[0] for _k, v in self.entries
                                 if struct.unpack_from("<Q", v)[0] < INDEX_SAVE_ID]
        if self.saves.is_dir():
            for p in self.saves.iterdir():
                try:
                    used.append(int(p.name.split(".")[0], 16))
                except ValueError:
                    pass
        return max(used) + 1

    def add(self, attr: bytes, save_id: int) -> None:
        value = struct.pack("<QQQBB", save_id, 0, 0, SPACE_USER, 0).ljust(ENTRY_SIZE, b"\0")
        self.entries.append((attr, value))
        self.keys.add(attr[:0x21])
        self.last_id = max(self.last_id, save_id)
        if not (self.dir / "ExtraData0").exists():
            # A Ryujinx that never started: its index save, as it would create it.
            sys_attr = attribute(0, ZERO_USER, TYPE_SYSTEM, INDEX_SAVE_ID)
            _write_extra(self.dir, extra_data(sys_attr, 0, INDEX_SAVE_SIZE, os.urandom(8)))
        # 0/ is what Ryujinx mounts; 1/ is resynced from it, but kept equal.
        for commit in ("0", "1"):
            if commit == "0" or (self.dir / commit).is_dir():
                atomic_write_bytes(self.dir / commit / "imkvdb.arc", pack_index(self.entries))
                atomic_write_bytes(self.dir / commit / "lastPublishedId",
                                   struct.pack("<Q", self.last_id))


# ── the copy ─────────────────────────────────────────────────────────────────

def running(app_ids: tuple[str, ...] = (EDEN_APP_ID, RYUJINX_APP_ID)) -> list[str]:
    """The emulators among `app_ids` that run now: their files are in use."""
    try:
        out = subprocess.run(["flatpak", "ps", "--columns=application"], capture_output=True,
                             text=True, timeout=10).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return []        # no flatpak: neither emulator can be running
    return sorted(set(app_ids) & set(out))


def eden_source(ryujinx: Path, eden_data: Path, profile_root: Path | None) -> Path:
    """The Eden saves that belong to whoever Ryujinx's saves point at now.

    A profile placed by GameCore makes bis/user/save a link into
    `profile_root`; its Eden saves sit beside it, in the Eden pack's folder.
    """
    saves = ryujinx / USER_SAVES
    if profile_root is not None and saves.is_symlink():
        target = Path(os.readlink(saves))
        if target.is_relative_to(profile_root):
            return target.parent / EDEN_PROFILE_FOLDER
    eden = eden_data / EDEN_SAVES
    parked = eden.with_name(eden.name + ".gamecore-primary")
    if parked.is_dir():
        return parked        # Eden stopped with a profile's saves placed
    if eden.is_symlink():
        raise ImportRefused(f"{eden} is a link: whose saves those are cannot be told")
    return eden


def _load_marker(index_dir: Path) -> set[str]:
    try:
        return set(json.loads((index_dir / MARKER).read_text(encoding="utf-8")).get("imported", []))
    except (OSError, ValueError, AttributeError):
        return set()


def import_saves(ryujinx: Path, eden_root: Path, eden_data: Path,
                 deadline: float | None = None) -> list[str]:
    """Copy what Ryujinx lacks from `eden_root`. Returns one line per decision."""
    busy = running()
    if busy:
        raise ImportRefused(f"{', '.join(busy)} is running")
    target = ryujinx_user(ryujinx)
    found, notes = eden_saves(eden_root, eden_users(eden_data / EDEN_PROFILES), target)
    if not found:
        return notes
    index = Index(ryujinx)
    done = _load_marker(index.dir)
    for save in found:
        attr = attribute(save.title, save.user, save.kind)
        if save.key in done:
            continue
        if index.has(attr):
            notes.append(f"{save.key}: Ryujinx has its own save, Eden's left alone")
            done.add(save.key)
            continue
        if deadline is not None and time.monotonic() > deadline:
            notes.append("out of time: the rest at the next launch")
            break
        save_id = index.next_id()
        staging = index.saves / f"{save_id:016x}.gamecore-tmp"
        shutil.rmtree(staging, ignore_errors=True)
        shutil.copytree(save.path, staging / "0",
                        ignore=shutil.ignore_patterns(EDEN_SIZE_FILE))
        _write_extra(staging, extra_data(attr, save.title, 0, os.urandom(8)))
        if deadline is not None and time.monotonic() > deadline:
            # Ryujinx may start any moment: an index written now could race it.
            shutil.rmtree(staging, ignore_errors=True)
            notes.append("out of time: the rest at the next launch")
            break
        staging.rename(index.saves / f"{save_id:016x}")
        index.add(attr, save_id)
        done.add(save.key)
        atomic_write_json(index.dir / MARKER, {"imported": sorted(done)}, indent=2)
        notes.append(f"{save.key}: copied from {save.path} as {save_id:016x}")
    return notes


def log_notes(notes: list[str], log_dir: Path) -> None:
    """Append to the pack's own log (<data>/logs/packs/switch/eden-import.log)."""
    if not notes:
        return
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(log_dir / "eden-import.log", "a", encoding="utf-8") as f:
        f.writelines(f"{stamp} {line}\n" for line in notes)
