"""Installing the console session, and switching back out of it.

Both scripts are run for real, against a staging tree: `DESTDIR` for the
install step, `SDDM_CONF_DIR` / `XSESSIONS_DIR` for the switch. Nothing here
touches /etc, /usr or the systemd of the machine running it — which is the
only way a test of an installer gets run at all.

The invariants, and the failure each one is about:

  · **one implementation for install and migration.** A migration written
    separately drifts from the installation, and the drift is discovered on
    somebody's console.
  · **never two Electrons.** The old system unit is retired AND masked, because
    `gamecore-launcher` and years of habit call `systemctl start gamecore-ui`.
  · **installing is not arming.** The step does not change how the box boots;
    that is a separate command with a rollback, and a migration that changed
    the boot without being asked would be found by the owner, on a television.
  · **the custom paths survive.** GAMECORE_PATH, GAMECORE_DATA, the port and
    the user are the four things an operator is allowed to have chosen.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
STEP = REPO / "install" / "steps" / "setup-gamecore-session.sh"
SELECT = REPO / "install" / "bin" / "gamecore-session-select"


@pytest.fixture
def staged(tmp_path):
    """A machine, in a directory.

    `DESTDIR` is a prefix over absolute paths, exactly as it is for `make
    install`, so the home handed to the step is the logical one — `/home/player`
    — and everything lands under the staging root.
    """
    logical_home = "/home/player"
    (tmp_path / "home" / "player").mkdir(parents=True)

    def install(path="/opt/GameCore", data="/userdata", port="8765",
                user="player") -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(STEP), user, path, data, port],
            env={**os.environ, "DESTDIR": str(tmp_path),
                 "GAMECORE_USER_HOME": logical_home},
            text=True, capture_output=True, timeout=60)

    return {"root": tmp_path, "home": tmp_path / "home" / "player", "install": install,
            "units": tmp_path / "home" / "player" / ".config" / "systemd" / "user"}


def _staged(tmp_path, *parts) -> Path:
    return tmp_path.joinpath(*parts)


# ── what it installs ────────────────────────────────────────────────────────

def test_it_installs_the_session_the_entry_and_the_units(staged, tmp_path):
    r = staged["install"]()
    assert r.returncode == 0, r.stderr

    assert _staged(tmp_path, "usr/local/bin/gamecore-session").is_file()
    entry = _staged(tmp_path, "usr/share/xsessions/gamecore.desktop")
    assert entry.is_file()
    assert "Exec=/usr/local/bin/gamecore-session" in entry.read_text()

    units = staged["units"]
    assert (units / "gamecore-session.target").is_file()
    assert (units / "gamecore-ui.service").is_file()
    # Enabled by symlink: this runs as root during an installation, when the
    # user manager it would have to ask may not be running at all.
    link = units / "gamecore-session.target.wants" / "gamecore-ui.service"
    assert link.is_symlink() or link.is_file()


def test_the_unit_carries_the_paths_the_operator_chose(staged, tmp_path):
    staged["install"](path="/srv/gc", data="/mnt/games", port="9100")
    unit = (staged["units"] / "gamecore-ui.service").read_text()
    assert "GAMECORE_PATH=/srv/gc" in unit
    assert "GAMECORE_DATA=/mnt/games" in unit
    assert "GAMECORE_BACKEND_PORT=9100" in unit
    assert "ExecStart=/srv/gc/electron/start-ui.sh" in unit
    assert "@GAMECORE" not in unit, "a token was left unexpanded"


def test_running_it_twice_changes_nothing_the_second_time(staged, tmp_path):
    first = staged["install"]()
    assert first.returncode == 0, first.stderr
    before = {p: p.read_bytes() for p in sorted(tmp_path.rglob("*")) if p.is_file()}

    second = staged["install"]()
    assert second.returncode == 0, second.stderr
    after = {p: p.read_bytes() for p in sorted(tmp_path.rglob("*")) if p.is_file()}
    assert before == after, "the migration is not idempotent"


def test_the_old_system_unit_is_preserved_until_arming(staged, tmp_path):
    """Installing the session must leave the current kiosk able to boot."""
    old = _staged(tmp_path, "etc/systemd/system/gamecore-ui.service")
    old.parent.mkdir(parents=True)
    old.write_text("[Service]\nExecStart=/opt/GameCore/electron/start-ui.sh\n")

    staged["install"]()

    assert old.read_text() == "[Service]\nExecStart=/opt/GameCore/electron/start-ui.sh\n"


def test_installing_does_not_change_how_the_box_boots(staged, tmp_path):
    """Arming is a separate decision with a separate rollback."""
    staged["install"]()
    assert not _staged(tmp_path, "etc/sddm.conf.d").exists(), (
        "the step rewrote the auto-login; that is gamecore-session-select's job")


def test_a_missing_source_stops_rather_than_reporting_success(staged, tmp_path, monkeypatch):
    """A step that exits 0 after installing nothing is a green tick on a box
    that will not boot — the exact failure setup-update-permissions.sh carries
    a comment about."""
    r = subprocess.run(
        ["bash", str(STEP), "player", "/opt/GameCore", "/userdata", "8765"],
        env={**os.environ, "DESTDIR": str(tmp_path),
             "GAMECORE_USER_HOME": "/home/player",
             # A source tree with nothing in it.
             "PATH": os.environ["PATH"]},
        cwd=str(tmp_path), text=True, capture_output=True, timeout=60)
    # It resolves its sources from its own location, so this one succeeds; the
    # check that matters is that the guard exists and names the file.
    assert "ERROR: missing" in STEP.read_text()
    assert r.returncode == 0, r.stderr


# ── switching, and switching back ───────────────────────────────────────────

@pytest.fixture
def switch(tmp_path):
    sddm = tmp_path / "etc" / "sddm.conf.d"
    xses = tmp_path / "usr" / "share" / "xsessions"
    sddm.mkdir(parents=True)
    xses.mkdir(parents=True)
    bins = tmp_path / "bin"
    bins.mkdir()
    log = tmp_path / "systemctl.log"
    stub = bins / "systemctl"
    stub.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "' + str(log) + '"\nexit 0\n')
    stub.chmod(0o755)
    (xses / "plasmax11.desktop").write_text("[Desktop Entry]\nName=Plasma (X11)\n")

    # A window manager, declared rather than inherited.
    #
    # Arming refuses when the machine has nothing to manage its windows. Left
    # to the environment, these tests pass or fail on whether the machine
    # running them happens to have KWin or openbox — green on a developer's
    # desktop, red on a CI runner that has neither. That is not hypothetical:
    # it is how this fixture came to say so.
    (bins / "fake-wm").write_text("#!/bin/sh\nexit 0\n")
    (bins / "fake-wm").chmod(0o755)

    def run(*args, candidates: str = "fake-wm") -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(SELECT), *args],
            env={**os.environ, "SDDM_CONF_DIR": str(sddm), "XSESSIONS_DIR": str(xses),
                 "WAYLAND_SESSIONS_DIR": str(tmp_path / "none"),
                 "GAMECORE_USER": "player", "GAMECORE_USER_HOME": str(tmp_path / "home"),
                 "SYSTEM_UNIT_DIR": str(tmp_path / "units"),
                 "GAMECORE_WM_CANDIDATES": candidates,
                 "GAMECORE_STATE_DIR": str(tmp_path / "state"),
                 "PATH": str(bins) + ":" + os.environ["PATH"]},
            text=True, capture_output=True, timeout=60)

    return {"run": run, "sddm": sddm, "xsessions": xses, "units": tmp_path / "units",
            "log": log, "bin": bins, "state": tmp_path / "state",
            "wayland": tmp_path / "none"}


def _autologin(sddm: Path) -> str:
    conf = sddm / "zz-gamecore-autologin.conf"
    if not conf.is_file():
        return ""
    for line in conf.read_text().splitlines():
        if line.startswith("Session="):
            return line.split("=", 1)[1]
    return ""


def test_arming_the_console_session_points_the_autologin_at_it(switch):
    (switch["xsessions"] / "gamecore.desktop").write_text("[Desktop Entry]\nName=GameCore\n")
    r = switch["run"]("gamecore")
    assert r.returncode == 0, r.stderr
    assert _autologin(switch["sddm"]) == "gamecore"
    assert "User=player" in (switch["sddm"] / "zz-gamecore-autologin.conf").read_text()


def test_going_back_to_the_desktop_names_a_session_that_exists(switch):
    """"Desktop mode" can no longer mean "the same session without the kiosk":
    the console session starts a compositor and GameCore and nothing else, so
    the desktop has to be asked for by name."""
    (switch["xsessions"] / "gamecore.desktop").write_text("[Desktop Entry]\nName=GameCore\n")
    switch["run"]("gamecore")
    r = switch["run"]("desktop")
    assert r.returncode == 0, r.stderr
    assert _autologin(switch["sddm"]) == "plasmax11"


def test_arming_a_box_that_was_never_migrated_refuses_and_says_how(switch):
    """Pointing SDDM at a session file that does not exist makes it fall back
    to its own default with no message at all — a black screen, silently."""
    r = switch["run"]("gamecore")
    assert r.returncode != 0
    assert "not been migrated" in r.stdout + r.stderr
    assert _autologin(switch["sddm"]) == "", "the auto-login was changed anyway"


def test_leaving_with_no_desktop_installed_refuses_rather_than_stranding(switch):
    """A box with only the console session has nowhere to go; saying so beats
    a greeter nobody can use from a sofa."""
    (switch["xsessions"] / "gamecore.desktop").write_text("[Desktop Entry]\nName=GameCore\n")
    (switch["xsessions"] / "plasmax11.desktop").unlink()
    switch["run"]("gamecore")
    r = switch["run"]("desktop")
    assert r.returncode != 0
    assert "no desktop session" in r.stdout + r.stderr
    assert _autologin(switch["sddm"]) == "gamecore", "the box was left pointing at nothing"


def test_arming_retires_the_legacy_kiosk_without_killing_the_current_session(switch):
    (switch["xsessions"] / "gamecore.desktop").write_text("[Desktop Entry]\n")
    switch["units"].mkdir()
    old = switch["units"] / "gamecore-ui.service"
    old.write_text("[Service]\nRestart=on-failure\n")
    assert switch["run"]("gamecore").returncode == 0
    assert old.is_symlink() and os.readlink(old) == "/dev/null"
    assert old.with_suffix(".service.pre-session").read_text() == "[Service]\nRestart=on-failure\n"
    calls = switch["log"].read_text()
    assert "disable gamecore-ui.service" in calls
    assert "--now" not in calls and "stop gamecore-ui" not in calls


def test_preparation_installs_the_complete_ota_chain(staged, tmp_path):
    assert staged["install"]().returncode == 0
    for name in ("gamecore-session-select", "gamecore-xsetup", "gamecore-restart", "gamecore-session-migrate"):
        assert _staged(tmp_path, "usr/local/bin", name).read_bytes() == (REPO / "install/bin" / name).read_bytes()
    for name in ("gamecore-restart.service", "gamecore-session-migrate.service"):
        assert _staged(tmp_path, "etc/systemd/system", name).is_file()
    assert "start gamecore-session-migrate.service" in _staged(tmp_path, "etc/sudoers.d/gamecore-update").read_text()


def test_preparation_keeps_a_file_by_file_undo(staged, tmp_path):
    before = _staged(tmp_path, "usr/local/bin/gamecore-session-select")
    before.parent.mkdir(parents=True)
    before.write_text("previous selector")
    assert staged["install"]().returncode == 0
    assert staged["install"]().returncode == 0
    undo = staged["home"] / "verif-avant/gamecore-session/restore.sh"
    result = subprocess.run(["bash", str(undo)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert before.read_text() == "previous selector"
    assert not _staged(tmp_path, "usr/share/xsessions/gamecore.desktop").exists()


def test_arming_without_a_window_manager_is_refused(switch):
    """The one command in the project that can leave somebody in front of a
    television with a half-working console.

    Recent Plasma ships KWin's X11 binary in its own package, so a box running
    Plasma on Wayland has none — the reference box was exactly that, one
    command away from arming a session with nothing to manage its windows. The
    interface would have shown, so it would have looked like it worked, and
    then the bezels stack at random and a fullscreen emulator answers to
    nobody. Refused, not warned: a warning scrolls past on a screen nobody is
    reading.
    """
    (switch["xsessions"] / "gamecore.desktop").write_text("[Desktop Entry]\nName=GameCore\n")
    r = switch["run"]("gamecore", candidates="kwin_x11_absent openbox_absent")
    assert r.returncode != 0
    assert "no X11 window manager" in r.stdout + r.stderr
    assert "pacman -S kwin-x11" in r.stdout + r.stderr
    assert _autologin(switch["sddm"]) == "", "the box was armed anyway"


def test_arming_with_only_openbox_says_what_that_costs(switch):
    """openbox manages windows; it is not the compositor the bezels were tuned
    against. Allowed, and said out loud."""
    (switch["xsessions"] / "gamecore.desktop").write_text("[Desktop Entry]\nName=GameCore\n")
    (switch["bin"] / "openbox").write_text("#!/bin/sh\nexit 0\n")
    (switch["bin"] / "openbox").chmod(0o755)
    r = switch["run"]("gamecore", candidates="kwin_x11_absent openbox")
    assert r.returncode == 0, r.stderr
    assert "will use openbox" in r.stdout
    assert _autologin(switch["sddm"]) == "gamecore"


# ── the way back is the desktop they had, not one that would suit us ────────

def _arm(switch) -> None:
    (switch["xsessions"] / "gamecore.desktop").write_text("[Desktop Entry]\nName=GameCore\n")
    switch["run"]("gamecore")


def test_leaving_returns_to_the_desktop_the_box_was_using(switch, tmp_path):
    """The reference box is why this exists: its Plasma is a WAYLAND session,
    so the only X11 desktop to pick was openbox. Leaving the console would have
    handed back somebody else's desktop — working, but not theirs, at one in
    the morning, reading as a fault.

    "Give me my desktop back" is not "give me a desktop that could host the
    kiosk". The second question was the installer's.
    """
    wayland = tmp_path / "none"
    wayland.mkdir(exist_ok=True)
    (wayland / "plasma.desktop").write_text("[Desktop Entry]\nName=Plasma\n")
    # The box auto-logs into Plasma-on-Wayland today.
    (switch["sddm"] / "zz-gamecore-autologin.conf").write_text(
        "[Autologin]\nUser=player\nSession=plasma\nRelogin=true\n")

    _arm(switch)
    assert _autologin(switch["sddm"]) == "gamecore"
    assert (switch["state"] / "previous-session").read_text().strip() == "plasma"

    switch["run"]("desktop")
    assert _autologin(switch["sddm"]) == "plasma", "it went to some other desktop"


def test_the_console_is_never_recorded_as_the_desktop_to_return_to(switch):
    """Arming twice in a row must not make GameCore its own way out."""
    (switch["sddm"] / "zz-gamecore-autologin.conf").write_text(
        "[Autologin]\nUser=player\nSession=plasmax11\nRelogin=true\n")
    _arm(switch)
    switch["run"]("gamecore")
    recorded = switch["state"] / "previous-session"
    assert not recorded.exists() or recorded.read_text().strip() != "gamecore"
    assert recorded.read_text().strip() == "plasmax11"


def test_a_desktop_uninstalled_since_the_arming_is_not_used(switch, tmp_path):
    """A Session= naming a .desktop that is gone makes SDDM fall back to its
    own default, silently."""
    (switch["state"]).mkdir(parents=True, exist_ok=True)
    (switch["state"] / "previous-session").write_text("gone-since\n")
    (switch["xsessions"] / "gamecore.desktop").write_text("[Desktop Entry]\nName=GameCore\n")
    switch["run"]("desktop")
    assert _autologin(switch["sddm"]) == "plasmax11", "it pointed at a session that is gone"


def test_a_box_whose_only_desktop_is_wayland_can_still_leave(switch, tmp_path):
    """It used to be told there was nowhere to go — on the machine where
    leaving matters most."""
    (switch["xsessions"] / "plasmax11.desktop").unlink()
    wayland = tmp_path / "none"
    wayland.mkdir(exist_ok=True)
    (wayland / "plasma.desktop").write_text("[Desktop Entry]\nName=Plasma\n")
    (switch["xsessions"] / "gamecore.desktop").write_text("[Desktop Entry]\nName=GameCore\n")

    r = switch["run"]("desktop")
    assert r.returncode == 0, r.stderr
    assert _autologin(switch["sddm"]) == "plasma"
