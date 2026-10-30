"""`flatpak kill` must run with the user's runtime dir.

The backend is a system unit with no XDG_RUNTIME_DIR; without it flatpak
finds no instance under $XDG_RUNTIME_DIR/.flatpak and kills nothing.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.services import process_manager as pm


def test_flatpak_kill_runs_with_the_runtime_dir(monkeypatch):
    seen = {}

    async def fake_exec(*argv, **kw):
        seen["argv"], seen["env"] = argv, kw.get("env")

        class Done:
            async def wait(self):
                return 0
        return Done()

    async def fake_display_env():
        return {"XDG_RUNTIME_DIR": "/run/user/1000"}

    monkeypatch.setattr(pm.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(pm, "display_env", fake_display_env)
    target = pm.Session(launch_args=["--app-id", "net.lutris.Lutris", "x.lutris"])

    asyncio.run(pm.ProcessManager()._flatpak_kill(target))

    assert seen["argv"] == ("flatpak", "kill", "net.lutris.Lutris")
    assert seen["env"]["XDG_RUNTIME_DIR"] == "/run/user/1000"
