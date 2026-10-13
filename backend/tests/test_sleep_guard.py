"""Every sleep closes the games: the logind delay lock and the sweep under it.

The lock holder is a real `cat` (what `systemd-inhibit ... cat` keeps alive);
the sweep is recorded. No real lock is taken and nothing sleeps.
"""
from __future__ import annotations

import asyncio

import pytest

from backend.services import launch, rest_mode, sleep_guard


@pytest.fixture
def guard(monkeypatch):
    calls: list[tuple] = []

    async def close_everything(exit_wait=None, force_wait=None):
        calls.append(("close", exit_wait, force_wait))
        return []

    monkeypatch.setattr(sleep_guard, "INHIBIT_CMD", ("cat",))
    monkeypatch.setattr(sleep_guard.rest_mode, "close_everything", close_everything)
    monkeypatch.setattr(sleep_guard, "_holder", None)
    monkeypatch.setattr(sleep_guard, "_swept_for_sleep", False)
    yield calls
    launch.open_gate()


def test_the_lock_is_held_while_awake_and_released_by_closing_a_pipe(guard):
    async def scenario():
        assert await sleep_guard.take()
        holder = sleep_guard._holder
        assert sleep_guard.holding()
        assert await sleep_guard.take(), "taking twice must not start a second holder"
        assert sleep_guard._holder is holder
        await sleep_guard.release()
        assert holder.returncode == 0, "cat ended on EOF, the lock with it"
        assert not sleep_guard.holding()
    asyncio.run(scenario())


def test_a_sleep_closes_everything_then_lets_go(guard):
    async def scenario():
        await sleep_guard.take()
        holder = sleep_guard._holder
        await sleep_guard.before_sleep()
        assert guard == [("close", sleep_guard.SLEEP_EXIT_WAIT_SECS,
                          sleep_guard.SLEEP_FORCE_WAIT_SECS)]
        assert holder.returncode is not None, "the sleep would wait for the lock"
        assert launch._gate_reason, "a launch could start a game after the sweep"
    asyncio.run(scenario())


def test_the_sweep_fits_under_loginds_delay():
    """The drop-in raises InhibitDelayMaxSec to 15 s; the sweep must end first."""
    worst = sleep_guard.SLEEP_EXIT_WAIT_SECS + sleep_guard.SLEEP_FORCE_WAIT_SECS
    assert worst < sleep_guard.SLEEP_BUDGET_SECS < 15


def test_a_slow_sweep_still_releases_and_is_finished_after_the_wake(guard, monkeypatch):
    async def slow(exit_wait=None, force_wait=None):
        guard.append(("close",))
        await asyncio.sleep(10)

    monkeypatch.setattr(sleep_guard.rest_mode, "close_everything", slow)
    monkeypatch.setattr(sleep_guard, "SLEEP_BUDGET_SECS", 0.05)

    async def scenario():
        await sleep_guard.take()
        await sleep_guard.before_sleep()
        assert not sleep_guard.holding()
        monkeypatch.setattr(sleep_guard.rest_mode, "close_everything",
                            lambda *a: asyncio.sleep(0, result=[]))
        await sleep_guard.after_wake()
        assert sleep_guard.holding(), "the lock was not taken back after the wake"
        await sleep_guard.release()
    asyncio.run(scenario())


def test_a_failing_sweep_never_keeps_the_lock(guard, monkeypatch):
    async def broken(*a):
        raise RuntimeError("boom")
    monkeypatch.setattr(sleep_guard.rest_mode, "close_everything", broken)

    async def scenario():
        await sleep_guard.take()
        await sleep_guard.before_sleep()
        assert not sleep_guard.holding()
    asyncio.run(scenario())


def test_the_wake_sweeps_again_only_after_a_sleep(guard):
    async def scenario():
        await sleep_guard.after_wake()            # a start-up, not a wake
        assert guard == []
        await sleep_guard.before_sleep()
        await sleep_guard.after_wake()
        assert len(guard) == 2
        await sleep_guard.release()
    asyncio.run(scenario())


def test_no_systemd_inhibit_is_a_warning(monkeypatch, caplog):
    monkeypatch.setattr(sleep_guard, "INHIBIT_CMD", ("gamecore-no-such-tool",))
    monkeypatch.setattr(sleep_guard, "_holder", None)
    assert asyncio.run(sleep_guard.take()) is False
    assert "games survive" in caplog.text


def test_the_rest_button_and_the_lock_do_not_double_kill(monkeypatch):
    """Rest mode sweeps, then suspends; logind's PrepareForSleep finds nothing left."""
    killed: list[int] = []

    class S:
        def __init__(self, n):
            self.session_id, self.pgid, self.game_key, self.system_id = n, n, "g", "s"

    resident = [S(7)]

    class PM:
        foreground_session = None

        @property
        def background_sessions(self):
            return list(resident)

        async def kill(self, sid):
            killed.append(sid)
            resident.clear()

    monkeypatch.setattr(rest_mode, "process_manager", PM())
    monkeypatch.setattr(rest_mode.pm, "_pgid_alive", lambda pgid: False)
    monkeypatch.setattr(sleep_guard, "INHIBIT_CMD", ("cat",))
    monkeypatch.setattr(sleep_guard, "_holder", None)

    async def suspend():
        await sleep_guard.before_sleep()     # what logind triggers meanwhile
        return True, ""
    monkeypatch.setattr(rest_mode, "_suspend", suspend)

    async def scenario():
        await sleep_guard.take()
        await rest_mode.enter()
        assert killed == [7]
        assert not sleep_guard.holding()
        rest_mode.woke()
    asyncio.run(scenario())
