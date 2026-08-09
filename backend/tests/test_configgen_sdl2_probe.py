"""`sdl2_probe` — telling "SDL said no" apart from "SDL was never asked".

The reference box logged `SDL2 probe failed for 045e:02fd` three times over
several days, each at the instant a Bluetooth Xbox pad connected, and the
player was told *SDL2 would not report a GUID for 045e:02fd*. Those are not
the same sentence: the probe subprocess had raised, so SDL never answered at
all. Measured minutes afterwards, the same host SDL2 and the same libSDL2.so
bundled with Ryujinx both returned `050018dc5e040000fd02000003090000` — ten
runs out of ten, 0.85 s each, against an 8 s timeout.

Both facts used to leave `sdl2_probe` as an empty dict, which is why the
give-up could only name the commoner one, and why the errno behind those three
lines is now unrecoverable: the handler discarded the exception too.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.services.configgen import controllers as cc        # noqa: E402


def test_a_probe_that_could_not_run_is_not_an_answer_about_the_pad(monkeypatch):
    """An unrunnable probe must be distinguishable from an SDL that answered.

    `SDL_NumJoysticks` returning no match is a finding about the pad. A
    subprocess that never ran is a finding about this box, and the two call for
    different things — the mapping wizard against a retry.
    """
    cc._sdl2_cache.clear()
    # EAGAIN, which is what a fork that cannot get a process slot raises — and
    # Python specialises it to BlockingIOError, so the reported class is read
    # off the exception rather than spelled out here.
    failure = OSError(11, "Try again")
    monkeypatch.setattr(cc.subprocess, "run", _raising(failure))

    out = cc.sdl2_probe("045e", "02fd")

    assert out.get("guid", "") == "", "no GUID either way — that part is unchanged"
    assert out.get("error") == type(failure).__name__, (
        "the caller cannot say what happened if both failures look identical")


def test_a_timeout_is_reported_as_a_failure_to_run_not_as_a_missing_pad():
    """`TimeoutExpired` is a SubprocessError, not an OSError.

    Named separately because the two arrive through the same `except` clause
    and only one of them was ever suspected: the reference box's failures came
    1.8 s after the trigger, against an 8 s timeout, so they were NOT timeouts
    — and nothing in the log could have established that at the time.
    """
    cc._sdl2_cache.clear()
    real_run = cc.subprocess.run
    try:
        cc.subprocess.run = _raising(subprocess.TimeoutExpired("python", 8))
        out = cc.sdl2_probe("045e", "02fd")
    finally:
        cc.subprocess.run = real_run

    assert out.get("error") == "TimeoutExpired"


def test_a_failed_probe_is_not_remembered(monkeypatch):
    """A failure must not be cached, or the retry budget is spent on a memory.

    `sdl2_probe` caches for 5 s and gamepad_monitor re-profiles every ~3 s, so
    caching a failure would hand the next attempts the same non-answer without
    ever asking SDL again — and the whole PROFILE_RETRIES budget could burn
    inside one cache window.
    """
    cc._sdl2_cache.clear()
    calls = []

    def boom(*a, **k):
        calls.append(1)
        raise OSError(11, "Try again")

    monkeypatch.setattr(cc.subprocess, "run", boom)

    cc.sdl2_probe("045e", "02fd")
    cc.sdl2_probe("045e", "02fd")

    assert len(calls) == 2, "the second call read a cached failure"


def _raising(exc):
    def run(*a, **k):
        raise exc
    return run
