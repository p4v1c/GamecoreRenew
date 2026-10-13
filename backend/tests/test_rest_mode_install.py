"""The root pieces of Rest mode, installed into a staging tree (DESTDIR).

They reach an installed box only through the OTA's migration, which runs
setup-gamecore-session.sh; so that path is the one tested, not only the step.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STEP = REPO / "install" / "steps" / "setup-rest-mode.sh"
SESSION_STEP = REPO / "install" / "steps" / "setup-gamecore-session.sh"
PIECES = ("etc/sudoers.d/gamecore-rest", "usr/local/bin/gamecore-wake-setup",
          "etc/systemd/system/gamecore-wake.service",
          "etc/udev/rules.d/90-gamecore-wake.rules")


def _run(cmd, root: Path):
    return subprocess.run(cmd, env={**os.environ, "DESTDIR": str(root),
                                    "GAMECORE_USER_HOME": "/home/player"},
                          text=True, capture_output=True, timeout=60)


def _tree(root: Path) -> dict:
    return {p: p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def test_the_step_installs_every_piece_and_enables_the_unit(tmp_path):
    r = _run(["bash", str(STEP), "player"], tmp_path)
    assert r.returncode == 0, r.stderr
    for piece in PIECES:
        assert (tmp_path / piece).is_file(), piece
    link = tmp_path / "etc/systemd/system/multi-user.target.wants/gamecore-wake.service"
    assert os.readlink(link) == "../gamecore-wake.service"
    assert os.access(tmp_path / "usr/local/bin/gamecore-wake-setup", os.X_OK)


def test_the_sudoers_rule_grants_suspend_and_nothing_else(tmp_path):
    _run(["bash", str(STEP), "player"], tmp_path)
    rules = [line for line in (tmp_path / PIECES[0]).read_text().splitlines()
             if not line.startswith("#")]
    assert rules == ["player ALL=(root) NOPASSWD: /usr/bin/systemctl suspend"]
    assert oct((tmp_path / PIECES[0]).stat().st_mode & 0o777) == "0o440"


def test_a_second_run_changes_nothing(tmp_path):
    _run(["bash", str(STEP), "player"], tmp_path)
    before = _tree(tmp_path)
    r = _run(["bash", str(STEP), "player"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert "(unchanged)" in r.stdout
    assert _tree(tmp_path) == before


def test_the_ota_migration_path_installs_them_too(tmp_path):
    """update/linux.sh → gamecore-session-migrate → setup-gamecore-session.sh."""
    (tmp_path / "home" / "player").mkdir(parents=True)
    r = _run(["bash", str(SESSION_STEP), "player", "/opt/GameCore", "/userdata", "8765"],
             tmp_path)
    assert r.returncode == 0, r.stderr
    for piece in PIECES:
        assert (tmp_path / piece).is_file(), piece
    restore = (tmp_path / "home/player/verif-avant/gamecore-session/restore.sh").read_text()
    assert "gamecore-wake.service" in restore, "the rollback forgets the new files"


def test_the_unit_runs_the_installed_helper():
    unit = (REPO / "install/system/gamecore-wake.service").read_text()
    assert "ExecStart=/usr/local/bin/gamecore-wake-setup\n" in unit
    rule = (REPO / "install/system/90-gamecore-wake.rules").read_text()
    assert rule.count("/usr/local/bin/gamecore-wake-setup --device %S%p") == 2
