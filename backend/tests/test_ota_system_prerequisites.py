"""System packages carried to already-installed boxes, entirely on fixtures."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
STEP = REPO / "install" / "steps" / "install-ota-prerequisites.sh"
SESSION_STEP = REPO / "install" / "steps" / "setup-gamecore-session.sh"


@pytest.fixture
def package_box(tmp_path):
    state = tmp_path / "installed"
    calls = tmp_path / "calls"
    pacman = tmp_path / "pacman"
    pacman.write_text(f"""#!/usr/bin/env bash
printf '%s\\n' "$*" >> {calls}
if [[ "$1" == "-Qq" ]]; then
  grep -qxF "$2" {state} 2>/dev/null
  exit $?
fi
if [[ "${{GAMECORE_PACMAN_FAIL:-0}}" == 1 ]]; then exit 23; fi
printf '%s\\n' p7zip > {state}
""")
    pacman.chmod(0o755)
    manifest = tmp_path / "stage" / "var/lib/gamecore/pacman-installed"

    def run(*, fail: bool = False):
        env = dict(os.environ)
        env.update(DESTDIR=str(tmp_path / "stage"), GAMECORE_PACMAN=str(pacman),
                   GAMECORE_PKG_MANIFEST=str(manifest),
                   GAMECORE_PACMAN_FAIL="1" if fail else "0")
        return subprocess.run(["bash", str(STEP)], env=env, text=True,
                              capture_output=True, timeout=60)

    return run, calls, manifest


def test_an_ota_installs_only_the_declared_missing_package_and_records_it(package_box):
    run, calls, manifest = package_box
    first = run()
    second = run()
    assert first.returncode == second.returncode == 0
    asked = calls.read_text().splitlines()
    assert asked.count("-S --noconfirm --needed p7zip") == 1
    assert asked.count("-Qq p7zip") == 2
    assert manifest.read_text().splitlines() == ["p7zip"]


def test_a_failed_package_install_claims_no_ownership(package_box):
    run, _calls, manifest = package_box
    result = run(fail=True)
    assert result.returncode == 23
    assert not manifest.exists()


def test_the_existing_bounded_migration_is_the_only_ota_entry_point():
    text = SESSION_STEP.read_text()
    assert 'bash "$HERE/install-ota-prerequisites.sh"' in text
    updater = (REPO / "update" / "linux.sh").read_text()
    assert "pacman" not in updater
