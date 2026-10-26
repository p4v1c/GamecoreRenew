"""The launch cover's signal: what the emulator's log or window says after
the spawn, never before it, and a cover that always comes down.

Logs are files under tmp_path; the catalogue, the websocket and the process
manager are doubles. No emulator runs, no X display is opened.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.services import configgen, launch_ready, native_ports
from backend.services import launch as launch_service

CATALOG = Path(__file__).resolve().parents[2] / "catalog"
RPCS3 = r"Thread \(main_thread\) \["


def _cursor(pattern: Path, rx: str = "READY") -> launch_ready._LogCursor:
    return launch_ready._LogCursor(str(pattern), re.compile(rx), launch_ready._snapshot(str(pattern)))


# ── the log ──────────────────────────────────────────────────────────────────

def test_a_line_from_the_previous_run_does_not_count(tmp_path):
    log = tmp_path / "emu.log"
    log.write_text("boot\nREADY\n")
    cur = _cursor(log)
    assert not cur.found()
    with log.open("a") as f:
        f.write("still loading\n")
    assert not cur.found()
    with log.open("a") as f:
        f.write("READY\n")
    assert cur.found()


def test_a_recreated_log_is_read_from_its_start(tmp_path):
    """RPCS3 moves the old log aside and writes a new RPCS3.log."""
    log = tmp_path / "RPCS3.log"
    log.write_text("old\n" * 50 + "READY\n")
    cur = _cursor(log)
    log.rename(tmp_path / "RPCS3.log.gz")
    log.write_text("READY\n")
    assert cur.found()


def test_a_log_truncated_in_place_is_read_again(tmp_path):
    log = tmp_path / "emu.log"
    log.write_text("x" * 500 + "\n")
    cur = _cursor(log)
    assert not cur.found()
    log.write_text("READY\n")
    assert cur.found()


def test_a_new_file_per_run_is_found_by_its_pattern(tmp_path):
    """Ryujinx starts Ryujinx_<version>_<date>.log on every launch."""
    old = tmp_path / "Ryujinx_1_a.log"
    old.write_text("SurfaceFlinger CreateLayerFromId: Creating layer 1\n")
    cur = _cursor(tmp_path / "Ryujinx_*.log", "SurfaceFlinger CreateLayerFromId")
    assert not cur.found()
    new = tmp_path / "Ryujinx_1_b.log"
    new.write_text("Gpu LoadShaders: Shader cache loaded.\n")
    assert not cur.found()
    with new.open("a") as f:
        f.write("SurfaceFlinger CreateLayerFromId: Creating layer 1\n")
    assert cur.found()


def test_a_line_written_in_two_halves_is_matched_once_whole(tmp_path):
    log = tmp_path / "emu.log"
    log.write_text("")
    cur = _cursor(log)
    with log.open("a") as f:
        f.write("REA")
    assert not cur.found()
    with log.open("a") as f:
        f.write("DY\n")
    assert cur.found()


def test_a_missing_log_is_not_an_error(tmp_path):
    assert not _cursor(tmp_path / "nothing.log").found()


def test_the_rpcs3_signal_is_the_games_first_line_not_the_emulators():
    """Measured on a FIFA 19 boot: the emulator's main thread logs as
    `{PPU[..] main_thread}` while it builds its caches; the game's own code, once
    it runs, as `{PPU[..] Thread (main_thread) [liblv2: ..]}`."""
    rx = re.compile(RPCS3)
    assert not rx.search("·! 0:00:12.447478 {PPU[0x1000000] main_thread} SPU: SPU Runtime: Built the interpreter.")
    assert rx.search("·W 0:00:29.000123 {PPU[0x1000000] Thread (main_thread) [liblv2: 0x02693ddc]} "
                     "sys_memory: sys_memory_allocate(size=0x10000, flags=0x200, alloc_addr=*0xd0040cb4)")


# ── what a launch declares ───────────────────────────────────────────────────

def _pack(ready: dict | None, app_id: str = "net.rpcs3.RPCS3"):
    data = {"launch": {"path": "flatpak", **({"ready": ready} if ready else {})}}
    expand = lambda value, home: Path(value.replace("@FLATPAK_CACHE@", f"{home}/.var/app/{app_id}/cache"))
    return SimpleNamespace(data=data, expand=expand)


def test_a_pack_log_path_takes_the_flatpak_cache_token(tmp_path, monkeypatch):
    monkeypatch.setattr(configgen, "HOME", tmp_path)
    pack = _pack({"log": "@FLATPAK_CACHE@/rpcs3/RPCS3.log", "match": RPCS3})
    monkeypatch.setattr(launch_ready, "load_catalog", lambda: {"rpcs3": pack})
    spec = launch_ready.spec_for("rpcs3", "/emu/rpcs3/God of War 3", port=False)
    assert spec["log"] == f"{tmp_path}/.var/app/net.rpcs3.RPCS3/cache/rpcs3/RPCS3.log"


def test_a_pack_without_ready_is_covered_until_fullscreen(monkeypatch):
    monkeypatch.setattr(launch_ready, "load_catalog", lambda: {"snes9x": _pack(None)})
    assert launch_ready.spec_for("snes9x", "/emu/snes9x/Mario.sfc", port=False) == {
        "timeoutSec": launch_ready.FULLSCREEN_CAP_S}


def test_a_pack_that_forces_fullscreen_lends_its_ceiling(monkeypatch):
    pack = _pack(None)
    pack.data["launch"]["fullscreen"] = {"wmClass": ["gamescope"], "timeoutSec": 120}
    monkeypatch.setattr(launch_ready, "load_catalog", lambda: {"lutris": pack})
    assert launch_ready.spec_for("lutris", "/emu/lutris/FIFA.lutris", port=False) == {
        "timeoutSec": 120, "fullscreenClass": ["gamescope"]}


def test_an_unknown_system_gets_no_cover(monkeypatch):
    monkeypatch.setattr(launch_ready, "load_catalog", lambda: {})
    assert launch_ready.spec_for("nope", "/x", port=False) is None


def test_a_port_declares_its_signal_in_its_header(tmp_path):
    script = tmp_path / "Uncharted 2.sh"
    script.write_text("#!/bin/sh\n"
                      "# gamecore-ready-log: Saves/last_run.log\n"
                      "# gamecore-ready-match: Entering original x86-64 code\n"
                      "exec ./Uncharted.AppImage --play\n")
    assert native_ports.declared_ready(script, tmp_path) == {
        "log": str(tmp_path / "Saves" / "last_run.log"), "match": "Entering original x86-64 code"}
    script.write_text("# gamecore-ready-window: bbport, Bloodborne\n")
    assert native_ports.declared_ready(script, tmp_path) == {"wmClass": ["bbport", "Bloodborne"]}
    script.write_text("# gamecore-saves: Saves\n")
    assert native_ports.declared_ready(script, tmp_path) is None


def test_every_shipped_signal_is_a_valid_pattern():
    for pack in CATALOG.glob("*/pack.json"):
        ready = json.loads(pack.read_text()).get("launch", {}).get("ready")
        if ready and "match" in ready:
            re.compile(ready["match"])


def test_packs_that_share_an_emulator_wait_for_the_same_signal():
    def ready(pid):
        return json.loads((CATALOG / pid / "pack.json").read_text())["launch"].get("ready")
    assert ready("switch") == ready("ryujinx")
    assert ready("gamecube") == ready("wii") == ready("dolphin")


# ── the cover always comes down ──────────────────────────────────────────────

@pytest.fixture(autouse=True)
def full_screen(monkeypatch):
    """The game's window fills the screen unless a test says otherwise."""
    state = {"frames": [True]}

    def covers(pgid, wm_classes=()):
        f = state["frames"]
        return f.pop(0) if len(f) > 1 else f[0]
    monkeypatch.setattr(launch_ready.window_black, "covers_screen", covers)
    return state

@pytest.fixture
def events(monkeypatch):
    sent: list[tuple[str, dict]] = []

    async def broadcast(event, data):
        sent.append((event, data))
    monkeypatch.setattr(launch_ready.ws, "broadcast", broadcast)
    monkeypatch.setattr(launch_ready, "POLL_S", 0.01)
    return sent


def _game(monkeypatch, key="U.sh", system="rpcs3"):
    state = {"current": {"game_key": key, "system_id": system}}
    monkeypatch.setattr(launch_ready, "_still_ours",
                        lambda w: state["current"] == {"game_key": w.game_key, "system_id": w.system_id})
    return state


def _log_spec(monkeypatch, log: Path, cap: int = 5):
    monkeypatch.setattr(launch_ready, "spec_for",
                        lambda *a, **k: {"log": str(log), "match": "READY", "timeoutSec": cap})


def test_the_signal_takes_the_cover_down(tmp_path, monkeypatch, events):
    log = tmp_path / "emu.log"
    log.write_text("READY\n")        # the previous run's line
    _log_spec(monkeypatch, log)
    _game(monkeypatch)

    async def run():
        w = await launch_ready.announce("U.sh", "rpcs3", "/r/U.sh")
        assert events == [("game:loading", {"game_key": "U.sh", "system_id": "rpcs3", "timeout_s": 5.0})]
        task = asyncio.create_task(launch_ready._run(w))
        await asyncio.sleep(0.05)
        assert len(events) == 1, "an old line raised the cover's fall"
        with log.open("a") as f:
            f.write("READY\n")
        await asyncio.wait_for(task, 2)
    asyncio.run(run())
    assert events[-1] == ("game:ready", {"game_key": "U.sh", "system_id": "rpcs3", "reason": "signal"})


def test_no_signal_drops_the_cover_at_the_ceiling(tmp_path, monkeypatch, events):
    _log_spec(monkeypatch, tmp_path / "silent.log", cap=5)
    _game(monkeypatch)

    async def run():
        w = await launch_ready.announce("U.sh", "rpcs3", "/r/U.sh")
        w.cap_s = 0.05
        await asyncio.wait_for(launch_ready._run(w), 2)
    asyncio.run(run())
    assert events[-1][1]["reason"] == "timeout"


def test_a_game_that_ends_while_loading_drops_the_cover(tmp_path, monkeypatch, events):
    _log_spec(monkeypatch, tmp_path / "silent.log")
    state = _game(monkeypatch)

    async def run():
        w = await launch_ready.announce("U.sh", "rpcs3", "/r/U.sh")
        task = asyncio.create_task(launch_ready._run(w))
        await asyncio.sleep(0.03)
        state["current"] = None
        await asyncio.wait_for(task, 2)
    asyncio.run(run())
    assert events[-1][1]["reason"] == "ended"


def test_a_failed_spawn_drops_the_cover(tmp_path, monkeypatch, events):
    _log_spec(monkeypatch, tmp_path / "emu.log")

    async def refuse(*_a, **_k):
        raise launch_service.LaunchRefused(503, "not installed")
    monkeypatch.setattr(launch_service, "_start", refuse)
    with pytest.raises(launch_service.LaunchRefused):
        asyncio.run(launch_service._spawn({"id": "rpcs3"}, "rpcs3", "/r/G", "flatpak", "", "G"))
    assert [e for e, _ in events] == ["game:loading", "game:ready"]
    assert events[-1][1]["reason"] == "failed"


def test_a_bad_pattern_launches_without_a_cover(monkeypatch, events):
    monkeypatch.setattr(launch_ready, "spec_for", lambda *a, **k: {"log": "/x", "match": "("})
    assert asyncio.run(launch_ready.announce("G", "rpcs3", "/r/G")) is None
    assert events == []


def test_a_system_without_a_signal_launches_as_before(monkeypatch, events):
    monkeypatch.setattr(launch_ready, "spec_for", lambda *a, **k: None)

    async def start(*_a, **_k):
        return False
    monkeypatch.setattr(launch_service, "_start", start)
    assert asyncio.run(launch_service._spawn({"id": "snes9x"}, "snes9x", "/r/M.sfc", "x", "", "M.sfc")) is False
    assert events == []


# ── the hand-over: the emulator's loading screen, then black, then the game ─

def _hand_over_spec(monkeypatch, log: Path, **extra):
    monkeypatch.setattr(launch_ready, "spec_for", lambda *a, **k: {
        "log": str(log), "match": "READY", "timeoutSec": 5, "handOver": "black", **extra})
    monkeypatch.setattr(launch_ready, "HAND_OVER_POLL_S", 0.01)
    monkeypatch.setattr(launch_ready.process_manager.__class__, "foreground_session",
                        property(lambda self: SimpleNamespace(pgid=4242)))


def _screens(monkeypatch, *frames):
    """What the game's window shows at each look: True black, False not, None unreadable."""
    seen = list(frames)
    looked: list[int] = []

    def is_black(pgid):
        looked.append(pgid)
        return seen.pop(0) if len(seen) > 1 else seen[0]
    monkeypatch.setattr(launch_ready.window_black, "is_black", is_black)
    return looked


def _signalled_run(tmp_path, monkeypatch):
    log = tmp_path / "emu.log"
    log.write_text("")

    async def run():
        w = await launch_ready.announce("G", "rpcs3", "/r/G")
        with log.open("a") as f:
            f.write("READY\n")
        await asyncio.wait_for(launch_ready._run(w), 2)
    return log, run


def test_after_the_signal_the_cover_waits_for_the_window_to_go_black(tmp_path, monkeypatch, events):
    log, run = _signalled_run(tmp_path, monkeypatch)
    _hand_over_spec(monkeypatch, log)
    _game(monkeypatch, key="G")
    # Measured: RPCS3's loading screen for a few looks after its log line, then black.
    looked = _screens(monkeypatch, False, False, False, True)
    asyncio.run(run())
    assert events[-1][1]["reason"] == "black"
    assert len(looked) == 4 and set(looked) == {4242}


def test_a_window_that_cannot_be_read_leaves_the_logs_word(tmp_path, monkeypatch, events):
    log, run = _signalled_run(tmp_path, monkeypatch)
    _hand_over_spec(monkeypatch, log)
    _game(monkeypatch, key="G")
    _screens(monkeypatch, None)
    asyncio.run(run())
    assert events[-1][1]["reason"] == "signal"


def test_a_game_that_never_shows_black_still_drops_the_cover(tmp_path, monkeypatch, events):
    log, run = _signalled_run(tmp_path, monkeypatch)
    _hand_over_spec(monkeypatch, log, handOverSec=0.05)
    _game(monkeypatch, key="G")
    _screens(monkeypatch, False)
    asyncio.run(run())
    assert events[-1][1]["reason"] == "signal"


def test_rpcs3_and_ryujinx_hand_over_through_black():
    for pack in ("rpcs3", "switch", "ryujinx"):
        ready = json.loads((Path(__file__).parents[2] / "catalog" / pack / "pack.json").read_text())["launch"]["ready"]
        assert ready.get("handOver") == "black", pack


# ── no small window before fullscreen ────────────────────────────────────────

def test_a_pack_with_no_signal_drops_the_cover_once_its_window_fills_the_screen(monkeypatch, events, full_screen):
    monkeypatch.setattr(launch_ready, "spec_for", lambda *a, **k: {"timeoutSec": 5})
    monkeypatch.setattr(launch_ready.process_manager.__class__, "foreground_session",
                        property(lambda self: SimpleNamespace(pgid=4242)))
    monkeypatch.setattr(launch_ready, "HAND_OVER_POLL_S", 0.01)
    _game(monkeypatch, key="G", system="gamecube")
    # Dolphin: a small window first, then fullscreen.
    full_screen["frames"] = [False, False, True]

    async def run():
        w = await launch_ready.announce("G", "gamecube", "/r/G")
        await asyncio.wait_for(launch_ready._run(w), 2)
    asyncio.run(run())
    assert events[-1][1]["reason"] == "fullscreen"
    assert full_screen["frames"] == [True], "dropped before the window filled the screen"


def test_a_declared_signal_still_waits_for_fullscreen(tmp_path, monkeypatch, events, full_screen):
    log, run = _signalled_run(tmp_path, monkeypatch)
    _hand_over_spec(monkeypatch, log)
    _game(monkeypatch, key="G")
    _screens(monkeypatch, True)
    full_screen["frames"] = [False, True]
    asyncio.run(run())
    assert events[-1][1]["reason"] == "black"
    assert full_screen["frames"] == [True]
