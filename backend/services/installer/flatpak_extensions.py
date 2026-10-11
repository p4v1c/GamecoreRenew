"""Flatpak extensions a pack's app needs, on the branch its runtime expects.

`install.extensions` names an extension (gamescope's Vulkan layer for Lutris)
and the extension point it plugs into. The branch is never written in the
pack: it is the `version` the app's metadata, else its runtime's metadata,
declares for that point. On the Flathub Lutris of 2026 (runtime
org.gnome.Platform//49) that reads `[Extension org.freedesktop.Platform.VulkanLayer]
version = 25.08`. When Lutris moves to a newer runtime, the next run installs
the matching branch; an older one is left installed (Flatpak never uses it).

Installed in the installation that holds the app (`--system` or `--user`),
from the app's own remote, never asking: `flatpak install` alone prompts for
both when a remote exists in two installations. Already present = nothing done,
so a layer the owner installed by hand is left as it is.
"""
from __future__ import annotations

import configparser
import logging
import subprocess
from typing import Callable

from . import manifest
from .providers import Result

log = logging.getLogger(__name__)

FLATPAK_TIMEOUT_S = 60
INSTALL_TIMEOUT_S = 1800
INSTALLATIONS = ("system", "user")

Run = Callable[..., subprocess.CompletedProcess]


def declared_version(metadata: str, point: str) -> str | None:
    """The branch a Flatpak metadata file declares for an extension point."""
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        parser.read_string(metadata)
    except configparser.Error:
        return None
    section = f"Extension {point}"
    if not parser.has_section(section):
        return None
    version = parser.get(section, "version", fallback="").strip()
    if version:
        return version
    versions = [v.strip() for v in parser.get(section, "versions", fallback="").split(";")]
    return next((v for v in versions if v), None)


def _flatpak(run: Run, *args: str, timeout: int = FLATPAK_TIMEOUT_S) -> tuple[int, str]:
    try:
        r = run(["flatpak", *args], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:
        log.warning("flatpak_extensions: flatpak %s failed — %s", " ".join(args), e)
        return 1, ""
    return r.returncode, r.stdout or ""


def installation_of(app_id: str, run: Run) -> str | None:
    """'system' or 'user': where the app is installed, system first."""
    for where in INSTALLATIONS:
        if _flatpak(run, "info", f"--{where}", app_id)[0] == 0:
            return where
    return None


def branch_for(app_id: str, where: str, point: str, run: Run) -> str | None:
    """The extension point's branch, from the app's metadata, then its runtime's."""
    code, meta = _flatpak(run, "info", f"--{where}", "--show-metadata", app_id)
    if code == 0 and (version := declared_version(meta, point)):
        return version
    code, runtime = _flatpak(run, "info", f"--{where}", "--show-runtime", app_id)
    runtime = runtime.strip()
    if code != 0 or not runtime:
        return None
    # The runtime may sit in the other installation; flatpak finds it in either.
    code, meta = _flatpak(run, "info", "--show-metadata", runtime)
    return declared_version(meta, point) if code == 0 else None


def ensure(pack, ctx, run: Run = subprocess.run) -> list[Result]:
    """Install each declared extension on its branch. Never raises."""
    spec = pack.data.get("install") or {}
    wanted = spec.get("extensions") or []
    if spec.get("provider") != "flatpak" or not wanted:
        return []
    if ctx.dry_run:
        return [Result(True, f"{pack.id}: would install {e['id']} on the branch "
                             f"its runtime declares") for e in wanted]
    app_id = next((a for a in pack.app_ids if installation_of(a, run)), None)
    if app_id is None:
        return [Result(False, f"{pack.id}: {', '.join(pack.app_ids)} is not installed — "
                              f"extensions not installed")]
    where = installation_of(app_id, run)
    out = []
    for ext in wanted:
        out.append(_ensure_one(pack.id, app_id, where, ext, run))
    return out


def _ensure_one(pack_id: str, app_id: str, where: str, ext: dict, run: Run) -> Result:
    branch = branch_for(app_id, where, ext["extensionPoint"], run)
    if branch is None:
        return Result(False, f"{pack_id}: no branch declared for {ext['extensionPoint']} "
                             f"by {app_id} or its runtime — {ext['id']} not installed")
    ref = f"{ext['id']}//{branch}"
    if _flatpak(run, "info", f"--{where}", ref)[0] == 0:
        return Result(True, f"{ref} already present ({where})", already=True)
    code, origin = _flatpak(run, "info", f"--{where}", "--show-origin", app_id)
    remote = origin.strip() if code == 0 and origin.strip() else "flathub"
    code, _ = _flatpak(run, "install", "-y", "--noninteractive", f"--{where}", remote, ref,
                       timeout=INSTALL_TIMEOUT_S)
    if code != 0:
        return Result(False, f"{ref}: flatpak install exited {code}")
    if where == "system":
        manifest.record_new_flatpak(ref)
    return Result(True, f"{ref} installed ({where}, for {app_id})")
