"""Fixed host prerequisites for pack daemons; no pack-supplied root commands.

Both installation entry points run this through the pack applier. The receipt
keeps the original files, group membership and ptrace value for uninstall.
"""
from __future__ import annotations

import grp
import json
import os
from pathlib import Path
import subprocess

from .providers import Result

ETC = Path("/etc")
PTRACE = Path("/proc/sys/kernel/yama/ptrace_scope")
RECEIPT = Path("/var/lib/gamecore/layout-access.json")
UINPUT_FILES = {
    "modules-load.d/gamecore-layout-toggle.conf": "uinput\n",
    # uaccess must be tagged BEFORE 73-seat-late.rules applies the session ACL.
    "udev/rules.d/70-gamecore-layout-uinput.rules":
        'KERNEL=="uinput", SUBSYSTEM=="misc", GROUP="input", MODE="0660", TAG+="uaccess"\n',
}
PTRACE_FILE = "sysctl.d/90-gamecore-layout-ptrace.conf"
PTRACE_CONFIG = "# melonDS layout daemon: access to another process of the gaming user.\nkernel.yama.ptrace_scope = 0\n"


def _run(*argv: str) -> None:
    subprocess.run(list(argv), check=True, capture_output=True, text=True, timeout=30)


def _load() -> dict:
    return json.loads(RECEIPT.read_text()) if RECEIPT.exists() else {"files": {}}


def _save(state: dict) -> None:
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    tmp = RECEIPT.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2) + "\n")
    tmp.chmod(0o600)
    tmp.replace(RECEIPT)


def _write(state: dict, rel: str, content: str) -> None:
    path = ETC / rel
    if rel not in state["files"]:
        state["files"][rel] = {
            "before": path.read_text() if path.exists() else None,
            "mode": path.stat().st_mode & 0o777 if path.exists() else 0o644,
            "installed": content,
        }
        _save(state)  # recoverable even if installation stops after the write
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    path.chmod(0o644)


def apply_host_access(pack, ctx) -> list[Result]:
    access = pack.data.get("hostAccess") or {}
    if not any(access.values()):
        return []
    if ctx.dry_run:
        return [Result(True, f"{pack.id}: would prepare host access {access}")]
    if os.geteuid() != 0:
        return [Result(False, f"{pack.id}: hostAccess needs root; install with sudo gamecore-emu install {pack.id}")]
    try:
        state = _load()
        if access.get("uinput"):
            if ctx.user:
                input_group = grp.getgrnam("input")
                if ctx.user not in input_group.gr_mem:
                    # getgrouplist also includes a user's primary group.
                    import pwd
                    account = pwd.getpwnam(ctx.user)
                    if input_group.gr_gid not in os.getgrouplist(ctx.user, account.pw_gid):
                        if ctx.user not in state.setdefault("input_users_added", []):
                            state["input_users_added"].append(ctx.user)
                            _save(state)
                        _run("usermod", "-aG", "input", ctx.user)
            for rel, content in UINPUT_FILES.items():
                _write(state, rel, content)
            _run("modprobe", "uinput")
            _run("udevadm", "control", "--reload-rules")
            _run("udevadm", "trigger", "--action=add", "--subsystem-match=misc", "--sysname-match=uinput")
            _run("udevadm", "settle", "--timeout=10")
        if access.get("ptrace"):
            if "ptrace_before" not in state:
                state["ptrace_before"] = PTRACE.read_text().strip()
                _save(state)
            _write(state, PTRACE_FILE, PTRACE_CONFIG)
            _run("sysctl", "-w", "kernel.yama.ptrace_scope=0")
        return [Result(True, f"{pack.id}: host access ready {access}")]
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as e:
        return [Result(False, f"{pack.id}: host access failed — {e}")]


def restore() -> None:
    """Called only by the full uninstaller, after stopping the layout services.

Leave a file edited since install alone. Never unload uinput; other software
can use it. Keep the receipt if a command fails, so uninstall can be retried.
"""
    if not RECEIPT.exists():
        return
    state = _load()
    for rel, saved in state["files"].items():
        # Only our fixed destinations, even if the receipt is malformed.
        if rel not in {*UINPUT_FILES, PTRACE_FILE}:
            continue
        path = ETC / rel
        if not path.exists() or path.read_text() != saved["installed"]:
            continue
        if rel == PTRACE_FILE:
            state["restore_ptrace_pending"] = True
            _save(state)
        if saved["before"] is None:
            path.unlink()
        else:
            path.write_text(saved["before"])
            path.chmod(saved["mode"])
    if state.get("restore_ptrace_pending") and PTRACE.read_text().strip() == "0":
        previous = state.get("ptrace_before", "0")
        if previous in {"0", "1", "2", "3"}:
            _run("sysctl", "-w", f"kernel.yama.ptrace_scope={previous}")
    state.pop("restore_ptrace_pending", None)
    _save(state)
    for user in state.get("input_users_added", []):
        if user in grp.getgrnam("input").gr_mem:
            _run("gpasswd", "-d", user, "input")
    _run("udevadm", "control", "--reload-rules")
    RECEIPT.unlink()
