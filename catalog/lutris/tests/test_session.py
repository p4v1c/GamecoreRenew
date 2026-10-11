"""The launch wrapper: the session lasts exactly as long as the game."""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PACK = Path(__file__).resolve().parents[1]
SCRIPT = PACK / "files" / "lutris_session.py"
spec = importlib.util.spec_from_file_location("test_lutris_session", SCRIPT)
session = importlib.util.module_from_spec(spec)
spec.loader.exec_module(session)


class FakeChild:
    """A Lutris process that exits after `exits_after` polls (None = never)."""

    def __init__(self, exits_after=None, code=0):
        self.polls, self.exits_after, self.code = 0, exits_after, code
        self.killed = False

    def poll(self):
        self.polls += 1
        if self.killed or (self.exits_after is not None and self.polls > self.exits_after):
            return self.code
        return None

    def wait(self, timeout=None):
        self.killed = True
        return self.code

    def kill(self):
        self.killed = True


class Clock:
    def __init__(self):
        self.now = 0.0

    def sleep(self, seconds):
        self.now += seconds

    def __call__(self):
        return self.now


def run_follow(child, timeline, linger=10.0):
    """`timeline` answers game_running() call by call; then False for ever."""
    answers = iter(timeline)
    closed = []
    clock = Clock()
    code = session.follow(child, running=lambda: next(answers, False),
                          close=lambda: closed.append(True), sleep=clock.sleep,
                          clock=clock, linger=linger)
    return code, closed, clock.now


def test_the_session_waits_for_the_game_to_start_then_ends_with_it():
    child = FakeChild(exits_after=None)
    # Lutris boots (3 polls), the game runs (4 polls), the game exits.
    code, closed, _ = run_follow(child, [False] * 3 + [True] * 4)
    assert code == 0
    assert closed == [True]          # Lutris never quit on its own: closed


def test_lutris_that_quits_after_its_game_is_not_closed():
    child = FakeChild(exits_after=6)
    code, closed, elapsed = run_follow(child, [False, True, True, True])
    assert code == 0 and closed == []
    assert elapsed < 10


def test_a_lutris_that_dies_without_a_game_ends_the_session_with_an_error():
    child = FakeChild(exits_after=2, code=0)
    code, closed, _ = run_follow(child, [False] * 10)
    assert code == 1 and closed == []


def test_a_game_outliving_lutris_still_holds_the_session():
    child = FakeChild(exits_after=1)
    calls = [True] * 20
    code, closed, elapsed = run_follow(child, calls)
    assert code == 0
    assert elapsed >= 20 * session.POLL_S


def test_a_game_under_gamescope_is_still_followed():
    # Lutris starts `gamescope … -- gamemoderun umu-run …` as lutris-wrapper's
    # child: the wrapper, which is what is followed, is unchanged.
    cmd = (b"python3\0/app/share/lutris/bin/lutris-wrapper\0FIFA 22\0" b"0\0" b"0\0"
           b"gamescope\0-W\0" b"3840\0-H\0" b"2160\0-f\0--\0gamemoderun\0umu-run\0")
    assert session.is_game_cmdline(cmd) is True
    assert session.is_game_cmdline(b"gamescope\0-f\0--\0game.exe\0") is False


@pytest.mark.parametrize("cmdline, expected", [
    (b"lutris-wrapper: Celeste\0\0\0", True),
    (b"/usr/bin/python3\0/app/share/lutris/bin/lutris-wrapper\0Celeste\0", True),
    (b"/usr/bin/python3\0/app/bin/lutris\0lutris:rungameid/3\0", False),
    (b"vim\0notes-about-lutris-wrapper\0", False),
])
def test_a_game_is_recognised_by_its_lutris_wrapper(cmdline, expected):
    assert session.is_game_cmdline(cmdline) is expected


def test_game_running_reads_only_this_users_processes(tmp_path):
    proc = tmp_path / "proc"
    (proc / "42").mkdir(parents=True)
    (proc / "42" / "cmdline").write_bytes(b"lutris-wrapper: Hades\0")
    (proc / "self").mkdir()
    assert session.game_running(proc, uid=os.getuid()) is True
    assert session.game_running(proc, uid=os.getuid() + 1) is False
    assert session.game_running(tmp_path / "nowhere") is False


def test_a_file_that_is_not_a_stub_is_refused(tmp_path):
    stub = tmp_path / "Game.lutris"
    stub.write_text("hello")
    assert session.main(["--app-id", "net.lutris.Lutris", str(stub)]) == 2


def test_a_stub_launches_lutris_by_game_id(tmp_path, monkeypatch):
    stub = tmp_path / "Celeste.lutris"
    stub.write_text(json.dumps({"lutrisId": 12, "name": "Celeste"}))
    started = []
    order = []
    monkeypatch.setattr(session, "_gamescope_defaults", lambda app: order.append("gamescope"))
    monkeypatch.setattr(session, "game_running", lambda *a: False)
    monkeypatch.setattr(session, "instance_running", lambda app: False)
    monkeypatch.setattr(session.subprocess, "Popen",
                        lambda cmd: started.append(cmd) or order.append("lutris") or "child")
    monkeypatch.setattr(session, "follow", lambda child, **kw: 0)
    assert session.main(["--app-id", "net.lutris.Lutris", str(stub)]) == 0
    assert started == [["flatpak", "run", "net.lutris.Lutris", "lutris:rungameid/12"]]
    # The settings are in place before Lutris reads them.
    assert order == ["gamescope", "lutris"]


def test_a_gamescope_failure_never_stops_the_launch(monkeypatch):
    def boom(*a):
        raise RuntimeError("disk full")
    monkeypatch.setattr(session.lutris_gamescope, "apply", boom)
    session._gamescope_defaults("net.lutris.Lutris")


def test_an_idle_lutris_is_closed_before_the_launch(tmp_path, monkeypatch):
    stub = tmp_path / "Celeste.lutris"
    stub.write_text(json.dumps({"lutrisId": 3}))
    up = [True]
    killed = []
    monkeypatch.setattr(session, "game_running", lambda *a: False)
    monkeypatch.setattr(session, "instance_running", lambda app: up[0])
    monkeypatch.setattr(session, "close_instance",
                        lambda app: killed.append(app) or up.__setitem__(0, False))
    monkeypatch.setattr(session.subprocess, "Popen", lambda cmd: "child")
    monkeypatch.setattr(session, "follow", lambda child, **kw: 0)
    monkeypatch.setattr(session, "_gamescope_defaults", lambda app: None)
    session.main(["--app-id", "net.lutris.Lutris", str(stub)])
    assert killed == ["net.lutris.Lutris"]


def test_a_running_game_is_never_taken_over(tmp_path, monkeypatch):
    stub = tmp_path / "Celeste.lutris"
    stub.write_text(json.dumps({"lutrisId": 3}))
    monkeypatch.setattr(session, "game_running", lambda *a: True)
    monkeypatch.setattr(session.subprocess, "Popen",
                        lambda cmd: pytest.fail("must not start Lutris"))
    assert session.main(["--app-id", "net.lutris.Lutris", str(stub)]) == 1


def test_the_installed_script_starts_on_its_own():
    run = subprocess.run([sys.executable, str(SCRIPT), "--help"],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
