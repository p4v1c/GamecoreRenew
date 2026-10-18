"""Waking up: the logind signal, and what a wake owes the player.

The monitor is a fake `gdbus` (a shell printing the lines gdbus prints); the
steps are recorded. Nothing here sleeps or wakes a machine.
"""
from __future__ import annotations

import asyncio
import shlex
from unittest.mock import AsyncMock

import pytest

from backend.services import resume

SLEEP = "/org/freedesktop/login1: org.freedesktop.login1.Manager.PrepareForSleep (true,)"
WAKE = "/org/freedesktop/login1: org.freedesktop.login1.Manager.PrepareForSleep (false,)"


@pytest.mark.parametrize("line, expected", [
    (SLEEP, True),
    (WAKE, False),
    ("/org/freedesktop/login1: org.freedesktop.login1.Manager.SessionNew ('3', objectpath '/x')", None),
    ("", None),
])
def test_the_sleep_signal_is_read_from_gdbus_lines(line, expected):
    assert resume.parse_sleep_signal(line) is expected


@pytest.fixture
def steps(monkeypatch):
    """Every step of a wake, recorded in order."""
    seen: list[str] = []

    def note(name, result=None):
        async def step(*a, **kw):
            seen.append(name)
            return result
        return step

    monkeypatch.setattr(resume.rest_mode, "woke", lambda: seen.append("gate"))
    monkeypatch.setattr(resume.sleep_guard, "after_wake", note("sweep"))
    monkeypatch.setattr(resume.sleep_guard, "before_sleep", note("close"))
    monkeypatch.setattr(resume.sleep_guard, "take", note("lock"))
    monkeypatch.setattr(resume.sleep_guard, "release", note("unlock"))
    monkeypatch.setattr(resume.standby, "exit_standby", note("screen"))
    monkeypatch.setattr(resume.display, "restore_preferred", note("display"))
    monkeypatch.setattr(resume.display_ready, "wait_for_display", note("link"))
    monkeypatch.setattr(resume.standby, "load_config", lambda: {"wake_settle_secs": 0})
    monkeypatch.setattr(resume.gamepad_monitor, "request_reprofile",
                        lambda: seen.append("pads"))
    monkeypatch.setattr(resume.bt_wake, "set_wake_permissions", note("bluetooth"))
    monkeypatch.setattr(resume.wake_source, "remember", lambda: seen.append("counts"))
    monkeypatch.setattr(resume.wake_source, "report", lambda: seen.append("source"))
    broadcast = AsyncMock(side_effect=lambda ev, data: seen.append(ev))
    monkeypatch.setattr(resume.ws, "broadcast", broadcast)
    monkeypatch.setattr(resume, "_resumes", 0)
    monkeypatch.setattr(resume, "_sleeping", False)
    return seen


def test_a_wake_reopens_lights_announces_and_redetects(steps):
    asyncio.run(resume.on_resume())
    # The UI hears of the wake only once the link is up and the mode is back.
    assert steps == ["source", "sweep", "gate", "screen", "link", "display", "power:resumed",
                     "pads", "bluetooth"]
    assert resume.resume_count() == 1


def test_one_failed_step_does_not_cost_the_others(steps, monkeypatch):
    async def broken():
        raise RuntimeError("xrandr is gone")
    monkeypatch.setattr(resume.display, "restore_preferred", broken)
    asyncio.run(resume.on_resume())
    assert "power:resumed" in steps and "bluetooth" in steps and "pads" in steps


def test_the_sleep_closes_games_and_the_wake_puts_the_box_back(steps, monkeypatch):
    script = f"printf '%s\\n' {shlex.quote(SLEEP)} {shlex.quote(WAKE)}"
    monkeypatch.setattr(resume, "LOGIND_MONITOR", ("sh", "-c", script))
    monkeypatch.setattr(resume, "RESTART_SECS", 30.0)

    async def scenario():
        task = asyncio.create_task(resume.run())
        for _ in range(100):
            if resume.resume_count():
                break
            await asyncio.sleep(0.02)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())
    assert resume.resume_count() == 1
    assert steps.count("power:resumed") == 1
    # Lock while listening, the counts and the sweep on the sleep, then the
    # wake source before anything else of the wake's.
    assert steps[:6] == ["lock", "counts", "power:sleeping", "close", "source", "sweep"]


def test_no_gdbus_is_a_warning_not_a_crash(monkeypatch, caplog):
    monkeypatch.setattr(resume, "LOGIND_MONITOR", ("gamecore-no-such-tool",))
    asyncio.run(resume.run())
    assert "will not be noticed" in caplog.text


def test_the_wake_count_and_sleeping_flag_move_only_when_the_screen_is_back(steps, monkeypatch):
    seen = {}

    async def link(*a, **kw):
        seen["count_during_wait"] = resume.resume_count()
        seen["sleeping_during_wait"] = resume.is_sleeping()

    monkeypatch.setattr(resume.display_ready, "wait_for_display", link)

    async def scenario():
        await resume.announce_sleep()
        assert resume.is_sleeping()
        await resume.on_resume()

    asyncio.run(scenario())
    assert seen == {"count_during_wait": 0, "sleeping_during_wait": True}
    assert resume.resume_count() == 1 and not resume.is_sleeping()


def test_the_settle_delay_is_waited_before_the_announcement(steps, monkeypatch):
    import time
    monkeypatch.setattr(resume.standby, "load_config", lambda: {"wake_settle_secs": 0.2})
    stamps = {}
    real = resume.ws.broadcast

    async def stamp(ev, data):
        stamps[ev] = time.monotonic()
        await real(ev, data)

    monkeypatch.setattr(resume.ws, "broadcast", stamp)

    async def link(*a, **kw):
        stamps["link"] = time.monotonic()
    monkeypatch.setattr(resume.display_ready, "wait_for_display", link)
    asyncio.run(resume.on_resume())
    assert stamps["power:resumed"] - stamps["link"] >= 0.19


def test_a_cancel_swallowed_while_releasing_the_lock_still_stops_the_monitor(monkeypatch):
    """Python 3.11's wait_for can eat a cancel that lands as it finishes; the
    loop then slept 30 s and the backend's shutdown hung behind it."""
    monkeypatch.setattr(resume, "LOGIND_MONITOR", ("true",))
    monkeypatch.setattr(resume, "RESTART_SECS", 30.0)
    releasing = asyncio.Event()

    async def take():
        return True

    async def release():
        releasing.set()
        try:
            await asyncio.sleep(0.2)
        except asyncio.CancelledError:
            pass                                 # what wait_for did

    monkeypatch.setattr(resume.sleep_guard, "take", take)
    monkeypatch.setattr(resume.sleep_guard, "release", release)

    async def scenario():
        task = asyncio.create_task(resume.run())
        await releasing.wait()
        task.cancel()
        done, _ = await asyncio.wait({task}, timeout=2)
        assert done, "the monitor loop outlived its cancellation"

    asyncio.run(scenario())
