"""External disks: what is plugged in, where it lands, and when it goes away.

"I plug my ROM disk in" is one of the first three things anyone expects from a
console in a living room, and before this there was no trace of it anywhere in
the repository — no udisks, no mount, nothing. A disk plugged into the box did
exactly nothing.

Two roots, and the difference between them is the whole design:

  the MOUNT POINT      where udisks decided to put the filesystem. Not ours,
                       not stable, and not something to record anywhere.
  the STABLE LINK      `<DATA>/volumes/<slug>` — a symlink WE own, named after
                       the disk's label, pointing at wherever it landed today.

That split exists because udisks mounts at `/run/media/<user>/<label>` and the
name it picks is not reproducible: plug the same disk in twice without a clean
unmount in between and the second mount is `LABEL 1`. A `romsPath` recorded
against a real mount point is therefore a library that works until the day
someone pulls the cable, and then silently scans nothing. Recorded against the
stable link it survives, because the link is re-pointed on every arrival.

`<DATA>/volumes/my-disk/roms` is a relative path like any other in
systems.json, so `paths.resolve_data_path` already resolves it and no consumer
needed changing — that is the P3 split paying for itself.

**Nothing here mounts anything by itself.** Every operation that touches a real
device goes through `runner`, a callable that runs an argv and is replaced
wholesale in the tests. No test in this repository has ever run `mount`,
`udisksctl` or `mkfs`, and the injectable runner is what keeps that true while
still exercising the argv that would have been run.

**Removal is expected, not exceptional.** A living-room box has its disk pulled
mid-game sooner or later. Every reader here treats a vanished path as a normal
state — `iter_rom_files` already returns nothing for a directory that is not
there — so the failure mode is an empty system, never a traceback that takes
the grid down.
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import paths

log = logging.getLogger(__name__)

LSBLK_TIMEOUT = 10
UDISKS_TIMEOUT = 30

# What lsblk is asked for. Named once: the parser below indexes these keys, and
# a column added to one and not the other is a KeyError on a box with a disk in
# it and nowhere else.
LSBLK_COLUMNS = "NAME,PATH,LABEL,UUID,FSTYPE,MOUNTPOINT,RM,HOTPLUG,SIZE,TYPE"

# Filesystems that carry no POSIX ownership or permission bits.
#
# This is not a detail. An emulator's saves on exFAT get whatever uid/gid and
# mode the mount options impose on EVERY file, so a Flatpak sandbox writing
# there does not behave as it does on ext4: permissions cannot be preserved, a
# lock file cannot be trusted, and an interrupted write has no atomic rename to
# fall back on. ROMs are read-only data and are perfectly happy there. Saves are
# not, and `refuses_saves()` below is what says so out loud rather than letting
# someone discover it when a save is gone.
NO_POSIX_PERMISSIONS = frozenset({"exfat", "ntfs", "ntfs3", "vfat", "msdos", "fuseblk"})

# Filesystems worth offering at all. A disk full of swap or LVM metadata is not
# a ROM disk, and listing it invites someone to try to mount it.
MOUNTABLE = frozenset({
    "ext2", "ext3", "ext4", "btrfs", "xfs", "f2fs",
    "exfat", "ntfs", "ntfs3", "vfat", "msdos", "fuseblk", "iso9660", "udf",
})

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class Volume:
    """One filesystem that could hold a library."""
    name: str                 # sdb1
    path: str                 # /dev/sdb1
    label: str
    uuid: str
    fstype: str
    mountpoint: str           # "" when not mounted
    removable: bool
    size: str

    @property
    def is_mounted(self) -> bool:
        return bool(self.mountpoint)

    @property
    def slug(self) -> str:
        return slug_for(self.label, self.uuid)

    @property
    def keeps_permissions(self) -> bool:
        return self.fstype not in NO_POSIX_PERMISSIONS


def slug_for(label: str, uuid: str = "") -> str:
    """The stable directory name for a disk, from its label.

    Derived from the LABEL because that is the only name the owner chose and
    the only one they will recognise in a settings screen — `roms-disk`, not
    `A4E2-19F7`. The uuid is the fallback, not the primary: a disk with no
    label still has to be reachable, but naming every disk by uuid would make
    the one path a person has to type unreadable.

    Lowercased and stripped to `[a-z0-9-]` because this becomes a path
    component that ends up inside `systems.json`, and a label may legitimately
    contain a space, a slash or a quote. `My ROMs/2` naming a directory two
    levels deep is a library that scans the wrong place, silently.

    A label that survives none of that (`"///"`, or Cyrillic) falls back to the
    uuid too — an empty slug would collide with every other empty slug and
    point every unlabelled disk at one directory.
    """
    slug = _SLUG_STRIP.sub("-", label.strip().lower()).strip("-")
    if slug:
        return slug
    tail = _SLUG_STRIP.sub("-", uuid.strip().lower()).strip("-")
    return f"disk-{tail}" if tail else ""


# ── reading what is plugged in ───────────────────────────────────────────────

def _default_runner(argv: list[str], timeout: int) -> tuple[int, str, str]:
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except (OSError, subprocess.SubprocessError) as e:
        log.debug("storage: %s — %s", " ".join(argv), e)
        return 1, "", str(e)


Runner = "callable(argv, timeout) -> (rc, stdout, stderr)"


def parse_lsblk(payload: str) -> list[Volume]:
    """Flatten `lsblk -J` into the filesystems that could hold a library.

    Pure, and separated from the call on purpose: this is where every real
    quirk lives — a partition nested under a disk, a whole-disk filesystem with
    no partition table at all (common on pre-formatted USB sticks), a `null`
    where a string was expected. Testing it needs a JSON string, not a disk.

    Only removable/hotplug devices are returned. The internal NVMe holding the
    system also has a `label` and a `mountpoint`, and offering it in a screen
    that has an Unmount button would be handing someone a way to unmount their
    own root filesystem from a sofa.
    """
    try:
        blob = json.loads(payload)
    except (ValueError, TypeError):
        log.warning("storage: lsblk output was not JSON")
        return []

    out: list[Volume] = []

    def walk(node: dict, inherited_removable: bool) -> None:
        # Removability is a property of the DISK; a partition on a USB stick
        # reports rm=false itself. Reading it off the partition is why an
        # external disk's partitions used to look internal.
        removable = (bool(node.get("rm")) or bool(node.get("hotplug"))
                     or inherited_removable)
        fstype = node.get("fstype") or ""
        if fstype in MOUNTABLE:
            out.append(Volume(
                name=node.get("name") or "",
                path=node.get("path") or f"/dev/{node.get('name') or ''}",
                label=node.get("label") or "",
                uuid=node.get("uuid") or "",
                fstype=fstype,
                mountpoint=node.get("mountpoint") or "",
                removable=removable,
                size=node.get("size") or "",
            ))
        for child in node.get("children") or []:
            walk(child, removable)

    for node in blob.get("blockdevices") or []:
        walk(node, False)
    return [v for v in out if v.removable]


def list_volumes(runner=None) -> list[Volume]:
    """Every external filesystem the box can see. Never raises.

    `lsblk` and not /proc/mounts, because the question includes disks that are
    plugged in and NOT mounted — which is the entire state this module exists
    to move out of.
    """
    run = runner or _default_runner
    try:
        rc, stdout, _stderr = run(["lsblk", "-J", "-o", LSBLK_COLUMNS], LSBLK_TIMEOUT)
        if rc != 0:
            return []
        return parse_lsblk(stdout)
    except Exception:
        log.exception("storage: could not list volumes")
        return []


# ── the stable link ──────────────────────────────────────────────────────────

def link_path(volume: Volume) -> Path | None:
    """`<DATA>/volumes/<slug>`, or None for a disk with no usable name."""
    slug = volume.slug
    return (paths.volumes_dir() / slug) if slug else None


def link_volume(volume: Volume) -> Path | None:
    """Point `<DATA>/volumes/<slug>` at wherever this disk landed today.

    A symlink, and re-pointed on every arrival, because the mount point is not
    stable and a `romsPath` is. Plug the same disk in twice without a clean
    unmount and udisks calls the second mount `LABEL 1`; a library recorded
    against the real path scans nothing from then on, without a word.

    Writable-side only: `<DATA>` belongs to the player and this needs no root,
    which is what lets it happen on a hotplug event rather than at install.
    """
    if not volume.is_mounted:
        return None
    target = link_path(volume)
    if target is None:
        log.warning("storage: %s has neither a usable label nor a uuid — "
                    "no stable path can be derived for it", volume.path)
        return None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        # Replaced, never merged into. `symlink_to` on an existing name raises,
        # and an is_dir() check would follow the old link and answer about the
        # PREVIOUS disk — which is how the link would end up pointing at a
        # mount point that has been reused by something else.
        if target.is_symlink() or target.exists():
            target.unlink()
        target.symlink_to(volume.mountpoint)
    except OSError:
        log.exception("storage: could not link %s → %s", target, volume.mountpoint)
        return None
    log.info("storage: %s → %s", target, volume.mountpoint)
    return target


def unlink_volume(volume: Volume) -> bool:
    """Drop the stable link for a disk that has gone.

    Deliberately leaves a link that is not ours alone: `missing_ok` and a
    symlink check, never a recursive delete. `<DATA>/volumes/<slug>` is a path
    an owner may legitimately have replaced with a real directory, and this
    module removing a directory tree it did not create is the one bug in here
    that would cost someone their ROMs.
    """
    target = link_path(volume)
    if target is None or not target.is_symlink():
        return False
    try:
        target.unlink()
    except OSError:
        log.exception("storage: could not remove %s", target)
        return False
    return True


def stale_links(live: list[Volume]) -> list[Path]:
    """Links under `<DATA>/volumes` that point nowhere reachable.

    A box is powered off with a disk attached and comes up without it: nothing
    generated an arrival or a departure, so the link from the last session is
    still there pointing at an empty `/run/media/...`. It resolves, it is a
    directory, and it scans zero games — which reads exactly like a library
    that lost its contents.
    """
    keep = {link_path(v) for v in live if v.is_mounted}
    try:
        entries = list(paths.volumes_dir().iterdir())
    except OSError:
        return []
    return [p for p in entries
            if p.is_symlink() and p not in keep and not p.resolve().is_dir()]


# ── acting on a device ───────────────────────────────────────────────────────
#
# Both of these shell out to udisksctl, which does the privileged part over
# D-Bus as the logged-in user — no sudoers rule, no root in the backend. They
# are the only two functions in this module that change anything on a device,
# and neither is ever called by a test: `runner` is replaced, and what is
# asserted is the argv.

def mount(volume: Volume, runner=None) -> tuple[bool, str]:
    """Mount a disk that is plugged in but not mounted. (ok, message)."""
    if volume.is_mounted:
        return True, volume.mountpoint
    run = runner or _default_runner
    rc, stdout, stderr = run(
        ["udisksctl", "mount", "--no-user-interaction", "-b", volume.path],
        UDISKS_TIMEOUT)
    if rc != 0:
        detail = (stderr or stdout or "").strip().splitlines()
        return False, (detail[-1][:200] if detail else f"udisksctl mount failed ({rc})")
    return True, stdout.strip()


def unmount(volume: Volume, runner=None) -> tuple[bool, str]:
    """Flush and detach, so the cable can be pulled. (ok, message).

    The whole point is the flush. Pulling a disk that has unwritten data is how
    a save is lost, and "it looked finished" is not something a player can
    check — which is why there is a button for this at all rather than a line
    of documentation asking them to be careful.
    """
    if not volume.is_mounted:
        return True, "not mounted"
    run = runner or _default_runner
    rc, stdout, stderr = run(
        ["udisksctl", "unmount", "--no-user-interaction", "-b", volume.path],
        UDISKS_TIMEOUT)
    if rc != 0:
        detail = (stderr or stdout or "").strip().splitlines()
        # "target is busy" is the common one and it is actionable: something is
        # reading the disk, usually a game that is still running.
        return False, (detail[-1][:200] if detail else f"udisksctl unmount failed ({rc})")
    unlink_volume(volume)
    return True, stdout.strip()


# ── what the UI is told ──────────────────────────────────────────────────────

def describe(volume: Volume) -> dict:
    """One row for the storage screen."""
    link = link_path(volume)
    return {
        "name": volume.name,
        "device": volume.path,
        "label": volume.label,
        "uuid": volume.uuid,
        "fstype": volume.fstype,
        "size": volume.size,
        "mountpoint": volume.mountpoint,
        "mounted": volume.is_mounted,
        "slug": volume.slug,
        # What a romsPath should be written against — never the mountpoint.
        "stable_path": str(link) if link else "",
        "keeps_permissions": volume.keeps_permissions,
        "saves_warning": "" if volume.keeps_permissions else SAVES_WARNING,
    }


SAVES_WARNING = (
    "This disk has no POSIX permissions (exFAT/NTFS). ROMs are fine here — "
    "they are only ever read. Emulator saves are not: every file takes the "
    "mount's own uid and mode, so a Flatpak emulator cannot preserve "
    "permissions, cannot rely on a lock file, and has no atomic rename to fall "
    "back on if a write is interrupted. Keep saves on the internal disk."
)


def report(runner=None) -> list[dict]:
    """Every external disk, mounted or not. Never raises."""
    try:
        return [describe(v) for v in list_volumes(runner)]
    except Exception:
        log.exception("storage: report failed")
        return []


def find(device: str, runner=None) -> Volume | None:
    """The volume for a `/dev/...` path, or None.

    By device path and not by index: a list position is not a handle, and an
    Unmount button that acted on "the third row" would unmount the wrong disk
    the moment one arrived while the screen was open.
    """
    for volume in list_volumes(runner):
        if volume.path == device:
            return volume
    return None


# ── who is affected when a disk goes ─────────────────────────────────────────

def path_is_under(path: str | Path, mountpoint: str) -> bool:
    """Is `path` inside `mountpoint` — without touching the disk.

    Purely lexical, deliberately. The question is asked precisely when the
    mount has just vanished, so anything that stats the path answers about a
    directory that is no longer there. `Path.is_relative_to` on the strings is
    the only form that still works after the cable is out.
    """
    if not path or not mountpoint:
        return False
    try:
        return Path(path).is_relative_to(Path(mountpoint))
    except (TypeError, ValueError):
        return False
