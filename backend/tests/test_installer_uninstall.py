"""Installer/uninstaller package decisions, exercised only on fake commands."""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from backend.services.catalog import load_catalog
from backend.services.installer import manifest
from backend.services.installer import providers

ROOT = Path(__file__).resolve().parents[2]
ARCH = ROOT / "install/arch.sh"
UNINSTALL = ROOT / "install/uninstall.sh"

RETRO_PACKAGES = (
    "retroarch",
    "libretro-beetle-pce",
    "libretro-flycast",
    "libretro-genesis-plus-gx",
    "libretro-kronos",
    "libretro-mame",
    "libretro-mesen",
    "libretro-picodrive",
)


def _fake_pacman(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                 preexisting: tuple[str, ...] = ()) -> Path:
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    log = tmp_path / "pacman.log"
    pacman = fakebin / "pacman"
    pacman.write_text("""#!/usr/bin/env bash
case "$1" in
  -Qq) grep -qxF "$2" <<<"${PREEXISTING_PACKAGES:-}" ;;
  -Qi) printf 'Name            : %s\nRequired By     : None\n' "$2" ;;
  -S|-Rns) printf '%s\n' "$*" >>"$PACMAN_LOG" ;;
  *) exit 2 ;;
esac
""")
    pacman.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fakebin}:{os.environ['PATH']}")
    monkeypatch.setenv("PACMAN_LOG", str(log))
    monkeypatch.setenv("PREEXISTING_PACKAGES", "\n".join(preexisting))
    return log


def test_the_pacman_packs_are_the_eight_reviewed_packages():
    packs = load_catalog(ROOT / "catalog", ROOT / "config/catalog.d",
                         ROOT / ".test-no-ota")
    declared = {
        package
        for pack in packs.values()
        if (pack.data.get("install") or {}).get("provider") == "pacman"
        for package in pack.data["install"]["packages"]
    }
    assert declared == set(RETRO_PACKAGES)


def test_pacman_provider_records_every_new_retro_package(tmp_path, monkeypatch):
    log = _fake_pacman(tmp_path, monkeypatch)
    pkg_manifest = tmp_path / "manifest/pacman-installed"
    monkeypatch.setattr(manifest, "PKG_MANIFEST", pkg_manifest)

    assert providers._pacman_install(list(RETRO_PACKAGES))
    assert pkg_manifest.read_text().splitlines() == list(RETRO_PACKAGES)
    assert log.read_text().splitlines() == [
        "-S --noconfirm --needed " + " ".join(RETRO_PACKAGES)]


def test_pacman_provider_does_not_record_preexisting_retro_packages(
        tmp_path, monkeypatch):
    _fake_pacman(tmp_path, monkeypatch, RETRO_PACKAGES)
    pkg_manifest = tmp_path / "manifest/pacman-installed"
    monkeypatch.setattr(manifest, "PKG_MANIFEST", pkg_manifest)

    assert providers._pacman_install(list(RETRO_PACKAGES))
    assert not pkg_manifest.exists()


def test_arch_manifest_helper_records_p7zip_only_when_new(tmp_path, monkeypatch):
    """p7zip is a base installer dependency, not a catalogue provider one."""
    _fake_pacman(tmp_path, monkeypatch)
    source = ARCH.read_text()
    helper = re.search(r"^record_new_pkgs\(\) \{.*?^\}", source, re.S | re.M)
    assert helper
    pkg_manifest = tmp_path / "fresh/pacman-installed"
    harness = tmp_path / "record.sh"
    harness.write_text("\n".join([
        "set -uo pipefail", f'MANIFEST_DIR="{pkg_manifest.parent}"',
        f'PKG_MANIFEST="{pkg_manifest}"',
        helper.group(0), "record_new_pkgs p7zip",
    ]))
    subprocess.run(["bash", str(harness)], check=True, timeout=30)
    assert pkg_manifest.read_text().splitlines() == ["p7zip"]

    monkeypatch.setenv("PREEXISTING_PACKAGES", "p7zip")
    existing_manifest = tmp_path / "existing/pacman-installed"
    harness.write_text("\n".join([
        "set -uo pipefail", f'MANIFEST_DIR="{existing_manifest.parent}"',
        f'PKG_MANIFEST="{existing_manifest}"',
        helper.group(0), "record_new_pkgs p7zip",
    ]))
    subprocess.run(["bash", str(harness)], check=True, timeout=30)
    assert existing_manifest.exists()
    assert existing_manifest.read_text() == ""


def test_remove_packages_accepts_retroarch_cores_and_p7zip(
        tmp_path, monkeypatch):
    """Run only section 12 against a fake manifest and fake pacman."""
    packages = (*RETRO_PACKAGES, "p7zip")
    log = _fake_pacman(tmp_path, monkeypatch, packages)
    pkg_manifest = tmp_path / "pacman-installed"
    pkg_manifest.write_text("\n".join(packages) + "\n")
    source = UNINSTALL.read_text()
    block = source.split(
        "#  12. pacman packages", 1)[1].split(
        "#  13. Application files", 1)[0]
    harness = tmp_path / "remove.sh"
    harness.write_text("\n".join([
        "set -uo pipefail", "msg() { :; }; info() { :; }; warn() { :; };",
        "ok() { :; }; confirm() { return 0; };", "run() { \"$@\"; }",
        "REMOVE_PACKAGES=true", f'PKG_LIST="{pkg_manifest}"', block,
    ]))
    result = subprocess.run(["bash", str(harness)], capture_output=True,
                            text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert log.read_text().splitlines() == [
        "-Rns --noconfirm " + " ".join(packages)]


def test_assets_installed_is_not_a_promised_but_dead_manifest():
    source = (ROOT / "backend/services/installer/manifest.py").read_text()
    assert "assets-installed" not in source
    assert "record_asset" not in source
