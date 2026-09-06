"""What the backend has finished starting, and what a client may conclude.

The shell has to know when GameCore is *usable*, not when its process exists.
Those are different moments, and the only thing that used to tell them apart
was `/api/sysinfo` — an endpoint that opens a UDP socket towards 8.8.8.8 to
find the box's own address, walks the disk, reads the controller batteries and
summarises the BIOS directory. Asked in a loop, on the boot path, on a box that
may have no network at all, to answer a question it was never written for.

So the startup is recorded here instead, step by step, and `/api/ready` reads
it. Two rules decide what belongs in `REQUIRED`:

  · a step is required when answering without it would make the front end tell
    the player something false;
  · a step is NOT required when it only refines what is already true.

That is why the running-game adoption is required and the playtime repair is
not. Serving before the adoption means answering "nothing is running" while an
emulator is on screen — a home the player can navigate over a live game, with
the pad driving both. Serving before the repair means a few playtime figures
are the ones from before it ran; the repair broadcasts when it has moved any,
and nothing on screen is untrue in the meantime.

Nothing here measures a duration or waits for one. The steps are facts.
"""
from __future__ import annotations

import logging
import time

log = logging.getLogger(__name__)

#: Steps a client must not be told "ready" without.
REQUIRED = ("database", "session")

#: Steps that refine the box without gating it. Reported, never waited on.
BACKGROUND = ("playtime_repair", "screen", "power")

PENDING, DONE, FAILED = "pending", "done", "failed"

_steps: dict[str, str] = {}
_started: float = time.monotonic()


def begin() -> None:
    """Called once, at the top of the lifespan."""
    global _started
    _started = time.monotonic()
    _steps.clear()
    for name in REQUIRED + BACKGROUND:
        _steps[name] = PENDING


def done(step: str) -> None:
    _steps[step] = DONE


def failed(step: str) -> None:
    """A step that raised. Recorded rather than hidden — a required one failing
    is the difference between a box that is slow and a box that is broken, and
    the shell has no other way to tell."""
    _steps[step] = FAILED


def is_ready() -> bool:
    return all(_steps.get(name) == DONE for name in REQUIRED)


def snapshot() -> dict:
    """Cheap by construction: a dict lookup and a subtraction.

    No I/O, no subprocess, no socket. This is polled while the box is at its
    busiest — during its own start — and an expensive health check is a health
    check that changes what it measures.
    """
    return {
        "ready": is_ready(),
        "state": "ready" if is_ready() else "starting",
        "steps": dict(_steps),
        "since_start_s": round(time.monotonic() - _started, 3),
    }
