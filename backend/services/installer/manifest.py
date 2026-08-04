"""The install manifest under /var/lib/gamecore/.

install/uninstall.sh reads these to know what THIS install actually changed, so
it can put the machine back without guessing. Without them an uninstaller
cannot tell "we installed caddy" from "caddy was already here", and the only
safe answer is then to remove nothing.

The rule every writer here follows, and the reason the files exist: record only
what was NOT already present. An emulator the owner had before GameCore must
never end up on the removal list — but an override GameCore applied to it must,
which is why `flatpak-overrides` is a superset of `flatpak-installed`.

Mirrors the bash helpers in install/arch.sh (`record_new_pkgs`,
`record_new_flatpak`, `record_flatpak_override`) so a provider called from the
backend feeds exactly the same files as one called from the installer.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

MANIFEST_DIR = Path("/var/lib/gamecore")
PKG_MANIFEST = MANIFEST_DIR / "pacman-installed"
FLATPAK_MANIFEST = MANIFEST_DIR / "flatpak-installed"
OVERRIDE_MANIFEST = MANIFEST_DIR / "flatpak-overrides"
# Not written by the shell installer: things a provider dropped into
# GAMECORE_PATH itself (an AppImage, an extracted archive). uninstall.sh
# removes the install directory wholesale, so this is a record for `verify`
# and for the hot-install path, not a removal list.
ASSET_MANIFEST = MANIFEST_DIR / "assets-installed"


def _append_unique(path: Path, value: str) -> None:
    """Add a line if it is not already there. Never raises: a manifest that
    cannot be written must not abort an install that is otherwise fine — it
    degrades the uninstaller, and that is worth a warning, not a failure."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
        if value in existing:
            return
        with path.open("a", encoding="utf-8") as f:
            f.write(value + "\n")
    except OSError as e:
        log.warning("manifest: could not record %r in %s — %s "
                    "(the uninstaller will not know about it)", value, path, e)


def pacman_has(package: str) -> bool:
    try:
        r = subprocess.run(["pacman", "-Qq", package],
                           capture_output=True, timeout=30)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def flatpak_installed(app_id: str) -> bool:
    """`flatpak list | grep -q <id>` matches substrings — org.DolphinEmu
    .dolphin-emu also matches a hypothetical …-beta. Compare the application
    column exactly instead."""
    try:
        r = subprocess.run(["flatpak", "list", "--app", "--columns=application"],
                           capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            return False
        return app_id in {line.strip() for line in r.stdout.splitlines()}
    except (OSError, subprocess.SubprocessError):
        return False


def record_new_package(package: str) -> None:
    """Only if pacman does not already have it — see the module docstring."""
    if not pacman_has(package):
        _append_unique(PKG_MANIFEST, package)


def record_new_flatpak(app_id: str) -> None:
    _append_unique(FLATPAK_MANIFEST, app_id)


def record_flatpak_override(app_id: str) -> None:
    """A superset of what we installed: an emulator the user already had still
    gets a GameCore override, and the uninstaller has to reset it."""
    _append_unique(OVERRIDE_MANIFEST, app_id)


def record_asset(path: str) -> None:
    _append_unique(ASSET_MANIFEST, path)
