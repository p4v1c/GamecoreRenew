"""Tell the process group we started from one that merely reuses its number.

A pgid alone survives a power cut in session.json but not in the kernel: after
a reboot it can name any process. Boot id + the leader's start time cannot.
"""
from pathlib import Path

BOOT_ID_FILE = Path("/proc/sys/kernel/random/boot_id")
PROC_DIR = Path("/proc")
# Field 22 of /proc/<pid>/stat: start time in clock ticks since boot.
_STARTTIME_FIELD = 22
# Fields after `comm` (field 2) start at field 3.
_FIRST_FIELD_AFTER_COMM = 3


def boot_id() -> str:
    """This boot's id, or "" when /proc cannot say."""
    try:
        return BOOT_ID_FILE.read_text().strip()
    except OSError:
        return ""


def start_time(pid: int) -> str:
    """The start time of `pid`, or "" when it does not exist or is unreadable."""
    try:
        stat = (PROC_DIR / str(pid) / "stat").read_text()
    except OSError:
        return ""
    # comm may hold spaces and ')'; the numeric fields follow the last ')'.
    rest = stat.rsplit(")", 1)[-1].split()
    index = _STARTTIME_FIELD - _FIRST_FIELD_AFTER_COMM
    return rest[index] if len(rest) > index else ""


def matches(entry: dict, pgid: int) -> bool:
    """Whether a saved session still names the group it was saved for.

    An entry without both fields (an older build) never matches: adopting a
    stranger's group is worse than losing track of our own.
    """
    saved_boot = str(entry.get("boot_id") or "")
    saved_start = str(entry.get("leader_start") or "")
    if not saved_boot or not saved_start:
        return False
    return saved_boot == boot_id() and saved_start == start_time(pgid)
