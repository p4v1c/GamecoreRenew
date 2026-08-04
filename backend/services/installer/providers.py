"""One strategy per way of obtaining a binary.

    flatpak          appId                                    the EMU_FLATPAK loop
    github-asset     repo, asset, dest, magic, version?, sha256?   the DuckStation block
    github-archive   repo, asset, dest, entrypoint, requires  the Xenia block
    pacman           packages                                 pacman_optional

Callable from the bash installer (scripts/gamecore-provider.py) and, later,
from the backend at runtime — the same code either way, so a hot install cannot
behave differently from a fresh one.

Every provider feeds /var/lib/gamecore/, so `uninstall.sh` keeps removing only
what GameCore actually installed.

Nothing here is fatal by itself. A provider that fails costs one tile and says
so; the install carries on. That is not politeness — the Xenia block once
aborted the whole installer at 52 %, before a single systemd unit, sudoers rule
or autologin drop-in existed, and left a machine that was neither a working
install nor a clean one.
"""
from __future__ import annotations

import logging
import os
import pwd
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import manifest
from .fetch import extract, fetch_release_asset

log = logging.getLogger(__name__)


@dataclass
class Context:
    gamecore_path: Path
    user: str = ""
    dry_run: bool = False


@dataclass
class Result:
    ok: bool
    message: str
    already: bool = False       # was already there; nothing was changed


def _chown(path: Path, user: str, recursive: bool = False) -> None:
    """Hand the artefact to the gaming user. Silent when not running as root:
    the backend path runs as that user already and has nothing to do."""
    if not user or os.geteuid() != 0:
        return
    try:
        info = pwd.getpwnam(user)
    except KeyError:
        log.warning("providers: no such user %r — ownership left as root", user)
        return
    targets = [path] if not recursive else [path, *path.rglob("*")]
    for p in targets:
        try:
            os.chown(p, info.pw_uid, info.pw_gid)
        except OSError:
            pass


def _pacman_install(packages: list[str], optional: bool = False) -> bool:
    """`--needed` so a re-run is a no-op. Records what was NOT already there
    BEFORE installing, so "already present" never lands on the removal list."""
    if not packages:
        return True
    for pkg in packages:
        manifest.record_new_package(pkg)
    try:
        r = subprocess.run(["pacman", "-S", "--noconfirm", "--needed", *packages],
                           capture_output=True, text=True, timeout=1800)
    except (OSError, subprocess.SubprocessError) as e:
        log.warning("providers: pacman failed — %s", e)
        return False
    if r.returncode != 0 and not optional:
        log.warning("providers: pacman -S %s exited %s", " ".join(packages), r.returncode)
    return r.returncode == 0


# ── flatpak ────────────────────────────────────────────────────────────────

def install_flatpak(pack, ctx: Context) -> Result:
    app_id = pack.data["install"]["appId"]
    if ctx.dry_run:
        return Result(True, f"would install flatpak {app_id}")

    already = manifest.flatpak_installed(app_id)
    if already:
        # Left out of the uninstall manifest on purpose: an emulator the owner
        # had before GameCore must never end up on the removal list.
        log.info("providers: %s already installed", app_id)
    else:
        try:
            r = subprocess.run(["flatpak", "install", "-y", "flathub", app_id],
                               capture_output=True, text=True, timeout=3600)
        except (OSError, subprocess.SubprocessError) as e:
            return Result(False, f"{app_id}: flatpak install failed — {e}")
        if r.returncode != 0:
            return Result(False, f"{app_id}: flatpak install exited {r.returncode}")
        manifest.record_new_flatpak(app_id)

    # The sandbox override applies either way — hence a manifest of its own.
    flags = sandbox_flags(pack, ctx)
    try:
        subprocess.run(["flatpak", "override", *flags, app_id],
                       capture_output=True, text=True, timeout=120)
        manifest.record_flatpak_override(app_id)
    except (OSError, subprocess.SubprocessError):
        log.warning("providers: could not set the sandbox override for %s", app_id)

    return Result(True, f"{app_id} " + ("already present" if already else "installed"),
                  already=already)


def sandbox_flags(pack, ctx: Context) -> list[str]:
    """The pack's sandbox policy, or the emulator default.

    Two genuinely different policies exist — emulators get the ROM directory,
    a gamepad and X11; Stremio gets the whole filesystem and no X11 socket —
    so it is declared per pack rather than hardcoded in two unrelated places.
    """
    sb = pack.data.get("sandbox")
    if sb is None:
        return [f"--filesystem={ctx.gamecore_path}", "--device=all", "--socket=x11"]
    return ([f"--filesystem={v}" for v in sb.get("filesystem", [])]
            + [f"--device={v}" for v in sb.get("device", [])]
            + [f"--socket={v}" for v in sb.get("socket", [])])


# ── github-asset (DuckStation) ─────────────────────────────────────────────

def install_github_asset(pack, ctx: Context) -> Result:
    spec = pack.data["install"]
    dest = ctx.gamecore_path / spec["dest"]
    magic = spec.get("magic")

    if ctx.dry_run:
        return Result(True, f"would fetch {spec['repo']}:{spec['asset']} → {dest}")

    # `-f dest` alone treats a truncated download or a saved HTML error page as
    # "installed" forever. Check the magic instead.
    from .fetch import _magic_ok
    if dest.is_file() and _magic_ok(dest, magic):
        return Result(True, f"{pack.id} already present", already=True)
    dest.unlink(missing_ok=True)

    ok = fetch_release_asset(spec["repo"], spec["asset"], dest, magic=magic,
                             version=spec.get("version", "latest"),
                             sha256=spec.get("sha256"))
    if not ok:
        return Result(False,
                      f"{pack.id} could not be downloaded — its tile will be missing. "
                      f"Re-run the installer once the network is back; "
                      f"nothing else is affected.")

    if mode := spec.get("mode"):
        dest.chmod(int(mode, 8))
    _chown(dest, ctx.user)
    return Result(True, f"{pack.id} installed → {spec['dest']}")


# ── github-archive (Xenia) ─────────────────────────────────────────────────

def install_github_archive(pack, ctx: Context) -> Result:
    spec = pack.data["install"]
    into = ctx.gamecore_path / spec["dest"]
    entry = into / spec["entrypoint"]

    if ctx.dry_run:
        return Result(True, f"would fetch {spec['repo']}:{spec['asset']} → {into}")

    if entry.is_file():
        return Result(True, f"{pack.id} already present", already=True)

    # Tools needed to extract and to run it. Installed before the download so a
    # successful fetch is never wasted on a missing unzip.
    if requires := spec.get("requires"):
        _pacman_install(list(requires))

    # mktemp, not a fixed /tmp name: this runs as root and a predictable path
    # is a symlink target waiting to happen.
    fd, tmp_name = tempfile.mkstemp(prefix="gamecore-pack-")
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        ok = fetch_release_asset(spec["repo"], spec["asset"], tmp,
                                 magic=spec.get("magic"),
                                 pattern=spec.get("assetPattern"),
                                 version=spec.get("version", "latest"),
                                 sha256=spec.get("sha256"))
        if not ok:
            return Result(False,
                          f"{pack.id} could not be downloaded — its tile will be "
                          f"missing. Re-run the installer once the network is back; "
                          f"nothing else is affected.")
        if not extract(tmp, into):
            return Result(False, f"{pack.id}: extraction failed — its tile will be missing")
    finally:
        tmp.unlink(missing_ok=True)

    _chown(into, ctx.user, recursive=True)
    if not entry.is_file():
        return Result(False,
                      f"{pack.id}: {spec['entrypoint']} not found after extraction "
                      f"— it will not launch")
    return Result(True, f"{pack.id} installed → {spec['dest']}/")


# ── pacman ─────────────────────────────────────────────────────────────────

def install_pacman(pack, ctx: Context) -> Result:
    packages = list(pack.data["install"]["packages"])
    if ctx.dry_run:
        return Result(True, f"would install {' '.join(packages)}")
    ok = _pacman_install(packages)
    return Result(ok, f"{pack.id}: " + ("installed " if ok else "could not install ")
                  + " ".join(packages))


PROVIDERS = {
    "flatpak": install_flatpak,
    "github-asset": install_github_asset,
    "github-archive": install_github_archive,
    "pacman": install_pacman,
}


def install(pack, ctx: Context) -> Result:
    """Run the pack's provider. A pack with no `install` block installs nothing
    — youtube is a Firefox profile, there is no artefact to obtain."""
    spec = pack.data.get("install")
    if not spec:
        return Result(True, f"{pack.id}: nothing to install", already=True)
    provider = PROVIDERS.get(spec["provider"])
    if provider is None:
        return Result(False, f"{pack.id}: unknown provider {spec['provider']!r}")
    try:
        return provider(pack, ctx)
    except Exception as e:                       # never take the install down
        log.exception("providers: %s failed", pack.id)
        return Result(False, f"{pack.id}: {e.__class__.__name__} — {e}")
