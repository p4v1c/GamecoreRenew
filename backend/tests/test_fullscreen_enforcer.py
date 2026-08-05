"""The enforcer that fullscreens an app with no fullscreen flag.

It existed, it was correct, and for months nothing called it: the tile's
`fullscreen` block was dropped when Stremio moved to a wrapper script, and
`enforce()` returns silently when the block is missing or empty. Silence is the
right behaviour — every other tile has no block — but it meant the regression
looked exactly like normal operation.

So the tests below are about the two halves of that: the config is read the way
`games.py` passes it, and window matching is forgiving in the ways X11 requires.
No X server is involved; the display is a fake.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.services import fullscreen_enforcer as fe


# ── fakes: just enough Xlib to answer _find_window ─────────────────────────

class FakeWindow:
    def __init__(self, wm_class=None, raises=False):
        self._cls, self._raises = wm_class, raises

    def get_wm_class(self):
        if self._raises:
            raise RuntimeError("window vanished between the list and the query")
        return self._cls


class FakeDisplay:
    """A display whose _NET_CLIENT_LIST is whatever you pass in."""

    def __init__(self, windows, has_client_list=True):
        self._windows = windows
        self._has = has_client_list

    def intern_atom(self, name):
        return 1

    def screen(self):
        display = self

        class Root:
            def get_full_property(self, atom, kind):
                if not display._has:
                    return None
                return type("Prop", (), {"value": list(range(len(display._windows)))})()

        return type("Screen", (), {"root": Root()})()

    def create_resource_object(self, kind, wid):
        return self._windows[wid]


# ── window matching ────────────────────────────────────────────────────────

def test_wm_class_matching_ignores_case():
    """Stremio's pack lists three spellings because X11 applications are not
    consistent about which one they report."""
    win = FakeWindow(("stremio", "Stremio"))
    found = fe._find_window(FakeDisplay([win]), ["com.stremio.Stremio", "STREMIO"])
    assert found is win


def test_no_match_returns_none_rather_than_the_first_window():
    """Fullscreening the wrong window is worse than fullscreening none — it
    would take over whatever else is on the screen."""
    assert fe._find_window(FakeDisplay([FakeWindow(("firefox",))]), ["stremio"]) is None


def test_a_window_that_dies_mid_enumeration_is_skipped():
    """_NET_CLIENT_LIST is a snapshot. By the time each entry is queried the
    window may be gone, and one corpse must not hide the window we want."""
    wanted = FakeWindow(("stremio",))
    disp = FakeDisplay([FakeWindow(raises=True), wanted])
    assert fe._find_window(disp, ["stremio"]) is wanted


def test_a_display_with_no_client_list_yields_nothing():
    """A bare X server with no EWMH-aware window manager. Not an error."""
    assert list(fe._iter_client_windows(FakeDisplay([], has_client_list=False))) == []


# ── the config games.py hands over ─────────────────────────────────────────

def _run(cfg, monkeypatch):
    """Call enforce() with the blocking half stubbed, and report its arguments."""
    seen = {}
    monkeypatch.setattr(fe, "_XLIB_OK", True)

    def fake_sync(system_id, wm_classes, timeout_s):
        seen.update(system_id=system_id, wm_classes=wm_classes, timeout_s=timeout_s)

    monkeypatch.setattr(fe, "_enforce_sync", fake_sync)
    asyncio.run(fe.enforce("stremio", cfg))
    return seen


def test_the_block_the_stremio_pack_ships_reaches_the_enforcer(monkeypatch):
    seen = _run({"wm_class": ["stremio", "Stremio"], "timeout_s": 60}, monkeypatch)
    assert seen == {"system_id": "stremio",
                    "wm_classes": ["stremio", "Stremio"],
                    "timeout_s": 60.0}


def test_a_missing_timeout_falls_back_rather_than_raising(monkeypatch):
    assert _run({"wm_class": ["stremio"]}, monkeypatch)["timeout_s"] == 45.0


def test_an_empty_block_does_nothing_at_all(monkeypatch):
    """This is the silence that hid the regression for months. It is correct —
    but it is why test_catalog_tiles.py asserts the block exists at the source."""
    assert _run({}, monkeypatch) == {}
    assert _run({"wm_class": []}, monkeypatch) == {}


def test_without_python_xlib_it_declines_instead_of_crashing(monkeypatch):
    """The backend must start on a box where python-xlib failed to install."""
    monkeypatch.setattr(fe, "_XLIB_OK", False)
    called = []
    monkeypatch.setattr(fe, "_enforce_sync", lambda *a: called.append(a))
    asyncio.run(fe.enforce("stremio", {"wm_class": ["stremio"]}))
    assert called == []
