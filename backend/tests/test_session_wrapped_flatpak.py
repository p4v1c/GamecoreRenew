"""A launcher that wraps `flatpak run`: the sandbox leaves the launcher's group.

Measured on the box: `flatpak run` started by a non-leader puts bwrap and the
game in a new process group. Suspend and Quit aimed at the launcher's group
only; the game kept its sound while "suspended" and survived Quit.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.services import process_identity  # noqa: E402

# The child mimics flatpak: it leaves its parent's group, then waits.
_WRAPPER = (
    "import subprocess, sys, time\n"
    "subprocess.Popen([sys.executable, '-c',"
    " 'import os, time; os.setpgid(0, 0); time.sleep(60)'])\n"
    "time.sleep(60)\n"
)


def _wait_for(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_a_child_that_left_the_group_is_found():
    wrapper = subprocess.Popen([sys.executable, "-c", _WRAPPER],
                               start_new_session=True)
    try:
        assert _wait_for(lambda: process_identity.descendant_groups(wrapper.pid))
        (group,) = process_identity.descendant_groups(wrapper.pid)
        assert group != wrapper.pid
    finally:
        for group in process_identity.descendant_groups(wrapper.pid) | {wrapper.pid}:
            os.killpg(group, signal.SIGKILL)
        wrapper.wait()


def test_no_descendants_is_an_empty_set():
    assert process_identity.descendant_groups(2 ** 22 + 1) == set()
