"""The overlay monitor's contract with Electron.

It runs as a subprocess of `electron/main.js` and speaks JSON-lines over stdio:
one object per line, flushed. Nothing else enforces that — a stray `print()`, a
missing flush, or an object spread over two lines and the bezel silently stops
following the emulator's window, on a box, with no error anywhere.

X11 is not exercised here. What is exercised is the protocol, and the two
degraded paths a box actually hits: a Wayland session, and python-xlib absent.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.services import overlay_monitor as om


# ── the wire format ────────────────────────────────────────────────────────

def test_every_event_is_one_line_of_json(capsys):
    """`electron/main.js` splits stdout on newlines and parses each piece."""
    om.emit({"event": "window:opened", "system_id": "pcsx2"})
    om.emit({"event": "window:closed", "system_id": "pcsx2"})
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 2
    assert [json.loads(x)["event"] for x in lines] == ["window:opened", "window:closed"]


def test_an_event_carrying_a_newline_still_occupies_one_line(capsys):
    """Window titles come from the emulator and are not ours to trust —
    json.dumps escapes the newline rather than emitting it."""
    om.emit({"event": "error", "message": "two\nlines"})
    out = capsys.readouterr().out
    assert out.count("\n") == 1
    assert json.loads(out)["message"] == "two\nlines"


def test_emit_error_is_a_normal_event_not_a_stderr_write(capsys):
    """It travels the same channel as everything else, or Electron never sees
    it: only stdout is parsed."""
    om.emit_error("no display")
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out) == {"event": "error", "message": "no display"}


# ── the degraded paths ─────────────────────────────────────────────────────

def test_a_wayland_session_leaves_the_monitor_without_a_manager(monkeypatch):
    """Overlays are X11-only. On a Wayland session the monitor must construct
    and do nothing, not raise — the kiosk still has to start."""
    monkeypatch.setattr(om, "_WAYLAND_SESSION", True)
    assert om.OverlayMonitor()._mgr is None


def test_without_python_xlib_it_also_constructs(monkeypatch):
    monkeypatch.setattr(om, "_WAYLAND_SESSION", False)
    monkeypatch.setattr(om, "_XLIB_OK", False)
    assert om.OverlayMonitor()._mgr is None


def test_stopping_a_monitor_that_never_started_is_not_an_error(monkeypatch):
    """`main.js` sends `quit` on shutdown regardless of whether a game ran."""
    monkeypatch.setattr(om, "_WAYLAND_SESSION", True)
    mon = om.OverlayMonitor()
    mon.stop()
    mon.stop()
    assert mon._thread is None
