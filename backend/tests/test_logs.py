"""The logs directory: launch output kept, files capped, purge never breaks logging.

Emulator output used to go to /dev/null, so a game that crashed left nothing
to read. Every path is under a throwaway data root (`paths.use_roots`).
"""
import asyncio
import logging
import sys
from pathlib import Path
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routers import logs as logs_router
from backend.services import logs, paths
from backend.services import process_manager as pm


@pytest.fixture
def data(tmp_path, monkeypatch):
    before = (paths.GAMECORE_ROOT, paths.GAMECORE_DATA)
    paths.use_roots(tmp_path / "code", tmp_path / "data")
    yield tmp_path / "data" / "logs"
    paths.use_roots(*before)


def test_a_launch_keeps_what_the_emulator_printed(data, monkeypatch):
    manager = pm.ProcessManager()
    monkeypatch.setattr(pm, "display_env", AsyncMock(return_value={}))
    monkeypatch.setattr(pm.ws, "broadcast", AsyncMock())
    monkeypatch.setattr(pm.ws, "set_current_game", lambda data: None)
    monkeypatch.setattr(manager, "_save_state", lambda: None)
    monkeypatch.setattr(manager, "_clear_session", lambda: None)
    monkeypatch.setattr(manager, "_watch", AsyncMock())

    async def scenario():
        await manager.launch("/bin/sh", "-c 'echo out; echo err >&2'",
                             game_key="Some Game (Europe).nds", system_id="melonds")
        await manager._fg.proc.wait()

    asyncio.run(scenario())
    (log,) = (data / "launch" / "melonds").glob("*.log")
    assert "Some_Game_Europe_.nds" in log.name
    text = log.read_text()
    assert text.startswith("$ /bin/sh -c")
    assert "out\n" in text and "err\n" in text


def test_only_the_newest_launches_are_kept_and_old_ones_are_cut(data):
    folder = data / "launch" / "pcsx2"
    folder.mkdir(parents=True)
    for i in range(logs.LAUNCHES_KEPT + 3):
        (folder / f"old{i:02d}.log").write_text("x")
    big = folder / "old99.log"          # newest by name, written last
    big.write_bytes(b"a" * (logs.LAUNCH_MAX_BYTES + 10) + b"END")

    with logs.launch_output("pcsx2", "game.iso", ["pcsx2"]):
        pass

    kept = list(folder.glob("*.log"))
    assert len(kept) == logs.LAUNCHES_KEPT
    assert big.read_bytes().endswith(b"END")
    assert big.stat().st_size < logs.LAUNCH_MAX_BYTES + 100


def test_a_log_that_cannot_be_written_never_costs_the_launch(data, monkeypatch):
    data.parent.mkdir(parents=True)
    data.write_text("a file where the directory should be")
    with logs.launch_output("gb", "game.gb", ["mgba"]) as out:
        assert out is pm.asyncio.subprocess.DEVNULL


def test_logging_keeps_working_after_a_purge(data):
    logger = logging.getLogger("gamecore.test.logs")
    logger.setLevel(logging.INFO)
    handler = logs.SectionFile(data / "backend" / "backend.log")
    logging.getLogger().addHandler(handler)
    try:
        logger.info("before")
        assert logs.usage()["files"] == 1

        freed = logs.purge()
        assert freed["files"] == 1 and freed["bytes"] > 0
        assert not (data / "backend").exists()

        logger.info("after")
        assert "after" in (data / "backend" / "backend.log").read_text()
    finally:
        logging.getLogger().removeHandler(handler)
        handler.close()


def test_the_api_reports_and_purges(data):
    (data / "launch" / "gb").mkdir(parents=True)
    (data / "launch" / "gb" / "a.log").write_text("12345")
    app = FastAPI()
    app.include_router(logs_router.router, prefix="/api")
    client = TestClient(app)

    assert client.get("/api/logs").json() == {"files": 1, "bytes": 5}
    assert client.delete("/api/logs").json() == {"ok": True, "freed": {"files": 1, "bytes": 5}}
    assert client.get("/api/logs").json() == {"files": 0, "bytes": 0}
