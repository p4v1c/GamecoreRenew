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
    monkeypatch.setattr(resume.standby, "exit_standby", note("screen"))
    monkeypatch.setattr(resume.display, "restore_preferred", note("display"))
    monkeypatch.setattr(resume.gamepad_monitor, "request_reprofile",
                        lambda: seen.append("pads"))
    monkeypatch.setattr(resume.bt_wake, "allow_paired_pads", note("bluetooth"))
    broadcast = AsyncMock(side_effect=lambda ev, data: seen.append(ev))
    monkeypatch.setattr(resume.ws, "broadcast", broadcast)
    monkeypatch.setattr(resume, "_resumes", 0)
    return seen


def test_a_wake_reopens_lights_announces_and_redetects(steps):
    asyncio.run(resume.on_resume())
    assert steps == ["gate", "screen", "power:resumed", "display", "pads", "bluetooth"]
    assert resume.resume_count() == 1


def test_one_failed_step_does_not_cost_the_others(steps, monkeypatch):
    async def broken():
        raise RuntimeError("xrandr is gone")
    monkeypatch.setattr(resume.display, "restore_preferred", broken)
    asyncio.run(resume.on_resume())
    assert "power:resumed" in steps and "bluetooth" in steps and "pads" in steps


def test_the_monitor_acts_on_the_wake_and_not_on_the_sleep(steps, monkeypatch):
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


def test_no_gdbus_is_a_warning_not_a_crash(monkeypatch, caplog):
    monkeypatch.setattr(resume, "LOGIND_MONITOR", ("gamecore-no-such-tool",))
    asyncio.run(resume.run())
    assert "will not be noticed" in caplog.text
