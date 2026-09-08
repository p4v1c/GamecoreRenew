"""Suspending a session, and the two locks that decided whether it works.

The feature is "put my game down without losing it". Everything here is about
the two places that made that impossible rather than about SIGSTOP itself,
which is the easy part:

  · `/games/launch` refused every launch while `is_running` was true, and a
    process frozen by SIGSTOP still has `returncode is None` — so it is
    running by that definition for as long as it is suspended. Backgrounding a
    game therefore locked the box out of starting anything else, which is the
    one thing the player backgrounded it in order to do.
  · playtime was wall-clock between launch and exit, so a game left suspended
    overnight billed the player for the night.

Nothing here starts a process or signals anything real: the children are fakes
and `os.killpg` is recorded rather than sent. The one thing that WAS measured
on real processes is written down in the report — a Flatpak sandbox is five
processes in one group, and SIGSTOP to the group moves all five.
"""
from __future__ import annotations

import asyncio
import signal
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.services import process_manager as pm  # noqa: E402


class FakeProcess:
    """A child that exits when the test says so."""

    def __init__(self, pid: int = 4242):
        self.pid = pid
        self.returncode = None
        self.done = asyncio.Event()

    async def wait(self):
        await self.done.wait()
        return self.returncode


@pytest.fixture
def manager(monkeypatch):
    """A manager whose signals are recorded and whose disk is not touched."""
    m = pm.ProcessManager()
    monkeypatch.setattr(pm, "display_env", AsyncMock(return_value={}))
    monkeypatch.setattr(pm.ws, "broadcast", AsyncMock())
    monkeypatch.setattr(pm.ws, "set_current_game", lambda data: None)
    monkeypatch.setattr(m, "_save_state", lambda: None)
    monkeypatch.setattr(m, "_clear_session", lambda: None)
    # The screen handover is X11 and has nothing to say in a unit test.
    monkeypatch.setattr(m, "_give_back_the_screen", AsyncMock())
    monkeypatch.setattr(m, "_raise_interface", AsyncMock())
    return m


@pytest.fixture
def signals(monkeypatch):
    """Every (pgid, signal) the manager sends, in order."""
    sent: list[tuple[int, int]] = []
    monkeypatch.setattr(pm.os, "killpg", lambda pgid, sig: sent.append((pgid, sig)))
    # The pgid of a fake child is its pid; getpgid would raise on a pid that
    # does not exist.
    monkeypatch.setattr(pm.os, "getpgid", lambda pid: pid)
    return sent


async def _launch(manager, procs, *, game_key: str, system_id: str,
                  rom_path: str = "rom.iso", monkeypatch=None):
    proc = procs.pop(0)
    monkeypatch.setattr(pm.asyncio, "create_subprocess_exec",
                        AsyncMock(return_value=proc))
    await manager.launch("fake", "", rom_path=rom_path, game_key=game_key,
                         system_id=system_id)
    return proc


# ── the signal, and where it is aimed ────────────────────────────────────────

def test_suspending_signals_the_group_and_not_the_process(manager, signals,
                                                          monkeypatch):
    """An emulator is a tree, and a Flatpak one is five processes deep.

    Measured on the reference box: `flatpak run` is the outer bwrap, a second
    bwrap wrapping xdg-dbus-proxy, the proxy itself, the inner bwrap and the
    application — one process group, because `start_new_session=True` made it
    and nothing inside bwrap calls setsid. SIGSTOP to the group put all five
    in `T`; to the pid it would have frozen the wrapper and left the game
    running with the interface drawn over it.
    """
    async def scenario():
        proc = FakeProcess(pid=1234)
        monkeypatch.setattr(pm.asyncio, "create_subprocess_exec",
                            AsyncMock(return_value=proc))
        await manager.launch("flatpak", "run org.example.Emu", game_key="g",
                             system_id="pcsx2")
        await manager.background()
        assert signals == [(1234, signal.SIGSTOP)]
        await manager.foreground()
        assert signals[-1] == (1234, signal.SIGCONT)

    asyncio.run(scenario())


# ── lock 1: the 409 ──────────────────────────────────────────────────────────

def test_a_suspended_session_does_not_refuse_the_next_launch(manager, signals,
                                                             monkeypatch):
    """The lock the whole feature turned on.

    `is_running` was true for a frozen process, so the launch gate refused
    everything while a game sat in the background — and the player had
    backgrounded it precisely in order to open something else.
    """
    async def scenario():
        procs = [FakeProcess(pid=11), FakeProcess(pid=22)]
        await _launch(manager, procs, game_key="zelda.iso", system_id="dolphin",
                      monkeypatch=monkeypatch)
        await manager.background()

        assert manager.is_running, "the suspended game is still resident"
        assert not manager.is_foreground, "but nothing is on the screen"

        # This is the line that used to raise.
        await _launch(manager, procs, game_key="stremio", system_id="stremio",
                      rom_path="", monkeypatch=monkeypatch)
        assert manager.foreground_session.game_key == "stremio"
        assert [s.game_key for s in manager.background_sessions] == ["zelda.iso"]

    asyncio.run(scenario())


def test_a_second_thing_on_the_screen_is_still_refused(manager, signals,
                                                       monkeypatch):
    """The half of the old rule that was right: one screen, one session."""
    async def scenario():
        procs = [FakeProcess(pid=11), FakeProcess(pid=22)]
        await _launch(manager, procs, game_key="a", system_id="s1",
                      monkeypatch=monkeypatch)
        with pytest.raises(pm.SessionConflict):
            await _launch(manager, procs, game_key="b", system_id="s2",
                          monkeypatch=monkeypatch)

    asyncio.run(scenario())


def test_the_third_resident_session_is_refused_by_name(manager, signals,
                                                       monkeypatch):
    """The cap is memory, and the refusal says what is holding it.

    Two suspended emulators are already several gigabytes; a third is the OOM
    killer, and the OOM killer would take the player's suspended game. So the
    launch is refused — and refused in words that name what to close, because
    "a game is already running" about two games that are frozen is the box
    arguing with itself.
    """
    async def scenario():
        procs = [FakeProcess(pid=11), FakeProcess(pid=22), FakeProcess(pid=33)]
        await _launch(manager, procs, game_key="a.iso", system_id="s1",
                      monkeypatch=monkeypatch)
        await manager.background()
        await _launch(manager, procs, game_key="b.iso", system_id="s2",
                      monkeypatch=monkeypatch)
        await manager.background()

        with pytest.raises(pm.SessionConflict) as e:
            await _launch(manager, procs, game_key="c.iso", system_id="s3",
                          monkeypatch=monkeypatch)
        assert "a.iso" in str(e.value) and "b.iso" in str(e.value)

    asyncio.run(scenario())


def test_suspending_is_never_refused_while_something_is_on_the_screen(
        manager, signals, monkeypatch):
    """The dead end an earlier draft of this shipped with.

    With a single background slot, a player inside game B with game A already
    suspended pressed Home twice to get out, the suspend was refused, and the
    only way off that screen was to quit the game they were playing. Moving a
    session from the screen to the background creates no session — the
    resident count is the same either side of it — so there was never a memory
    argument for that refusal.
    """
    async def scenario():
        procs = [FakeProcess(pid=11), FakeProcess(pid=22)]
        await _launch(manager, procs, game_key="a.iso", system_id="s1",
                      monkeypatch=monkeypatch)
        await manager.background()
        await _launch(manager, procs, game_key="b.iso", system_id="s2",
                      monkeypatch=monkeypatch)

        await manager.background()          # must not raise
        assert manager.foreground_session is None
        assert len(manager.background_sessions) == 2

    asyncio.run(scenario())


# ── lock 2's backend half: what the state says ───────────────────────────────

def test_the_state_reports_both_slots_and_stays_readable_by_an_old_client(
        manager, signals, monkeypatch):
    """`/games/session` has always been "the game in front of me", flat.

    Keeping that shape is what makes a front end which predates this feature
    read a box whose only session is suspended as "nothing in front of me" —
    which is true, and is the answer that leaves its pad unblocked rather than
    frozen over a game nobody can see.
    """
    async def scenario():
        procs = [FakeProcess(pid=11)]
        await _launch(manager, procs, game_key="zelda.iso", system_id="dolphin",
                      monkeypatch=monkeypatch)

        state = manager.session_state()
        assert state["game_key"] == "zelda.iso"
        assert state["state"] == "foreground"
        assert "background" not in state

        await manager.background()
        state = manager.session_state()
        assert "game_key" not in state, (
            "a suspended session must not fill the flat fields — an old client "
            "reads those as 'a game is on my screen' and blocks the pad")
        assert [s["game_key"] for s in state["background"]] == ["zelda.iso"]
        assert state["background"][0]["state"] == "background"

    asyncio.run(scenario())


def test_an_application_session_is_named_as_one(manager, signals, monkeypatch):
    """A tile with no ROM launches with `game_key == system_id`.

    That identity is the only thing separating an application from a game once
    the session exists, and a theme has to know: the button says "Close app" or
    "Close game", and getting it wrong is the interface talking about a game
    the player never started.
    """
    async def scenario():
        procs = [FakeProcess(pid=11)]
        await _launch(manager, procs, game_key="stremio", system_id="stremio",
                      rom_path="", monkeypatch=monkeypatch)
        assert manager.session_state()["kind"] == "app"

        procs = [FakeProcess(pid=22)]
        m2 = pm.ProcessManager()
        monkeypatch.setattr(m2, "_save_state", lambda: None)
        await _launch(m2, procs, game_key="zelda.iso", system_id="dolphin",
                      monkeypatch=monkeypatch)
        assert m2.session_state()["kind"] == "game"

    asyncio.run(scenario())


# ── the events ───────────────────────────────────────────────────────────────

def test_both_events_are_numbered_and_carry_the_whole_state(manager, signals,
                                                            monkeypatch):
    """The run number exists because two sessions can overlap for a moment.

    And the snapshot exists because a resume moves BOTH slots at once: a client
    rebuilding its picture from "run 3 came forward" alone cannot know what
    happened to run 2, and would drop a session that is still frozen — leaving
    the player with a game the interface no longer shows and no way to reach it.
    """
    async def scenario():
        broadcast = AsyncMock()
        monkeypatch.setattr(pm.ws, "broadcast", broadcast)
        procs = [FakeProcess(pid=11), FakeProcess(pid=22)]
        await _launch(manager, procs, game_key="a.iso", system_id="s1",
                      monkeypatch=monkeypatch)
        await manager.background()
        await _launch(manager, procs, game_key="b.iso", system_id="s2",
                      monkeypatch=monkeypatch)
        await manager.foreground()          # swaps b out, a in

        sent = [(c.args[0], c.args[1]) for c in broadcast.await_args_list]
        names = [e for e, _ in sent]
        assert names.count("game:backgrounded") == 2
        assert names.count("game:foregrounded") == 1

        bg_second = [d for e, d in sent if e == "game:backgrounded"][1]
        fg = [d for e, d in sent if e == "game:foregrounded"][0]
        assert bg_second["game_key"] == "b.iso"
        assert fg["game_key"] == "a.iso"
        assert isinstance(fg["session"], int)
        assert fg["session"] != bg_second["session"], (
            "two runs, two numbers — a late event about one must not be "
            "mistaken for the other")

        # The snapshot describes the box AFTER the transition, both slots.
        snap = fg["state_snapshot"]
        assert snap["game_key"] == "a.iso"
        assert [s["game_key"] for s in snap["background"]] == ["b.iso"]

    asyncio.run(scenario())


# ── playtime ─────────────────────────────────────────────────────────────────

def test_suspended_seconds_are_not_billed_as_playtime(monkeypatch):
    """A SIGSTOP is not a game being played.

    Without this, a game left in the background overnight bills the player for
    the night: the box's own statistics would reward suspending a game and
    walking away, and "hours played" would stop meaning anything.
    """
    clock = {"now": 1000.0}
    monkeypatch.setattr(pm.time, "time", lambda: clock["now"])

    s = pm.Session(game_key="g", system_id="s", start_time=1000.0, session_id=1)
    clock["now"] = 1060.0                     # one minute of actual play
    s.state, s.bg_since = "background", clock["now"]
    clock["now"] = 1060.0 + 8 * 3600          # suspended overnight
    assert s.played_secs(clock["now"]) == 60

    # Resumed and played for another minute.
    s.bg_total += clock["now"] - s.bg_since
    s.bg_since, s.state = 0.0, "foreground"
    clock["now"] += 60
    assert s.played_secs(clock["now"]) == 120


def test_playtime_never_goes_backwards(monkeypatch):
    """A clock that jumped must not subtract from a player's hours."""
    s = pm.Session(game_key="g", system_id="s", start_time=5000.0, session_id=1)
    assert s.played_secs(4000.0) == 0


# ── killing ──────────────────────────────────────────────────────────────────

def test_closing_a_suspended_session_thaws_it_first(manager, signals,
                                                    monkeypatch):
    """A stopped process cannot run its own exit path.

    `flatpak kill` sends SIGTERM inside the sandbox, and a frozen process never
    handles it — the sandbox would go down by SIGKILL alone with its files
    still open. SIGCONT first, so the teardown it was given can actually run.
    """
    async def scenario():
        procs = [FakeProcess(pid=77)]
        await _launch(manager, procs, game_key="a.iso", system_id="s1",
                      monkeypatch=monkeypatch)
        await manager.background()
        signals.clear()
        await manager.kill()
        assert signals[0] == (77, signal.SIGCONT), (
            f"the frozen session was killed without being thawed: {signals}")

    asyncio.run(scenario())


def test_a_bare_kill_closes_the_suspended_one_when_the_screen_is_empty(
        manager, signals, monkeypatch):
    """What "close it" means from a session bar with nothing else running."""
    async def scenario():
        procs = [FakeProcess(pid=77)]
        await _launch(manager, procs, game_key="a.iso", system_id="s1",
                      monkeypatch=monkeypatch)
        await manager.background()
        await manager.kill()
        assert signals[-1] == (77, signal.SIGKILL)

    asyncio.run(scenario())


# ── the reap, which the slot cap made load-bearing ───────────────────────────

def test_a_game_that_has_exited_does_not_hold_a_slot(manager, signals,
                                                     monkeypatch):
    """`is_running` frees a child the instant it has a return code, which is
    before its watcher gets the event loop back. A slot still holding an exited
    game would refuse the next launch by naming games that are already gone."""
    async def scenario():
        procs = [FakeProcess(pid=11), FakeProcess(pid=22), FakeProcess(pid=33)]
        first = await _launch(manager, procs, game_key="a.iso", system_id="s1",
                              monkeypatch=monkeypatch)
        await manager.background()
        second = await _launch(manager, procs, game_key="b.iso", system_id="s2",
                               monkeypatch=monkeypatch)
        # Both children are gone, but neither watcher has been given a turn.
        first.returncode = 0
        second.returncode = 0

        await _launch(manager, procs, game_key="c.iso", system_id="s3",
                      monkeypatch=monkeypatch)
        assert manager.foreground_session.game_key == "c.iso"
        assert manager.background_sessions == []

    asyncio.run(scenario())


# ── across a backend restart ─────────────────────────────────────────────────

def test_a_suspended_session_survives_a_backend_restart(tmp_path, monkeypatch):
    """SIGSTOP outlives the process that sent it.

    A backend restarted by an OTA while a game was suspended must find it
    again — it is the session that most needs finding, because a frozen process
    cannot exit on its own to clear itself. Losing it would leave a frozen
    emulator holding its RAM with nothing left that knows its pgid.
    """
    session_file = tmp_path / "session.json"
    monkeypatch.setattr(pm, "SESSION_FILE", session_file)
    monkeypatch.setattr(pm.ws, "set_current_game", lambda data: None)
    monkeypatch.setattr(pm, "_pgid_alive", lambda pgid: True)

    session_file.write_text(
        '{"sessions": [{"pgid": 4242, "game_key": "zelda.iso", '
        '"system_id": "dolphin", "exec_path": "flatpak", "launch_args": [], '
        '"rom_path": "", "started_at": 1000.0, "state": "background", '
        '"bg_since": 1060.0, "bg_total": 0.0}]}')

    fresh = pm.ProcessManager()
    asyncio.run(fresh.adopt_orphan())

    assert fresh.foreground_session is None, "it must not come back on screen"
    held = fresh.background_sessions
    assert [s.game_key for s in held] == ["zelda.iso"]
    assert held[0].state == "background"
    assert fresh.is_running and not fresh.is_foreground


def test_a_session_file_from_an_older_build_is_still_adopted(tmp_path,
                                                             monkeypatch):
    """The flat shape, written by every build before the second slot.

    A downgrade — an OTA rolled back with a game running — must not leave an
    unkillable emulator on the screen because the file grew a key.
    """
    session_file = tmp_path / "session.json"
    monkeypatch.setattr(pm, "SESSION_FILE", session_file)
    monkeypatch.setattr(pm.ws, "set_current_game", lambda data: None)
    monkeypatch.setattr(pm, "_pgid_alive", lambda pgid: True)
    session_file.write_text(
        '{"pgid": 99, "game_key": "old.iso", "system_id": "pcsx2", '
        '"exec_path": "/usr/bin/pcsx2", "launch_args": [], "rom_path": "", '
        '"started_at": 1000.0}')

    fresh = pm.ProcessManager()
    asyncio.run(fresh.adopt_orphan())
    assert fresh.foreground_session is not None
    assert fresh.foreground_session.game_key == "old.iso"


def test_what_is_written_can_be_read_back(tmp_path, monkeypatch):
    """Both slots round-trip, so a restart finds the box as it was left."""
    session_file = tmp_path / "session.json"
    monkeypatch.setattr(pm, "SESSION_FILE", session_file)
    monkeypatch.setattr(pm.ws, "set_current_game", lambda data: None)
    monkeypatch.setattr(pm, "_pgid_alive", lambda pgid: True)
    monkeypatch.setattr(pm.os, "getpgid", lambda pid: pid)
    monkeypatch.setattr(pm.os, "killpg", lambda pgid, sig: None)
    monkeypatch.setattr(pm, "display_env", AsyncMock(return_value={}))
    monkeypatch.setattr(pm.ws, "broadcast", AsyncMock())

    async def scenario():
        m = pm.ProcessManager()
        monkeypatch.setattr(m, "_raise_interface", AsyncMock())
        for pid, key, sysid in ((11, "a.iso", "s1"), (22, "b.iso", "s2")):
            monkeypatch.setattr(pm.asyncio, "create_subprocess_exec",
                                AsyncMock(return_value=FakeProcess(pid=pid)))
            await m.launch("fake", "", rom_path="r", game_key=key, system_id=sysid)
            await m.background()

        fresh = pm.ProcessManager()
        await fresh.adopt_orphan()
        assert sorted(s.game_key for s in fresh.background_sessions) == \
            ["a.iso", "b.iso"]

    asyncio.run(scenario())
