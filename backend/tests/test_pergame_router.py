"""What the options panel is told, and what it is refused.

The panel is driven by a pad from four metres away. Every branch below exists
because the alternative is a screen the player cannot act on: a blank list that
might mean "nothing to set" or might mean "the backend fell over", a button
that starts a game when it promised a settings window, a "remove" that reports
success on a profile that was never there.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.main import app  # noqa: E402
from backend.services import pergame  # noqa: E402
from backend.services.catalog import load_catalog  # noqa: E402


def _pick(supported: bool):
    for pack in sorted(load_catalog().values(), key=lambda p: p.id):
        block = pack.data.get("perGame")
        if block and block["supported"] is supported:
            return pack
    return None


SUPPORTING = _pick(True)
UNSUPPORTED = _pick(False)
assert SUPPORTING and UNSUPPORTED, (
    "the catalogue has no pack on one side of the per-game contract — half the "
    "cases below would assert nothing")

PROFILED = next((p for p in sorted(load_catalog().values(), key=lambda x: x.id)
                 if (p.data.get("perGame") or {}).get("profiles")), None)
assert PROFILED, "no pack ships a profile — the remove/restore cases are vacuous"


@pytest.fixture(autouse=True)
def isolated_records(tmp_path, monkeypatch):
    monkeypatch.setattr(pergame, "pergame_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(pergame, "_version_memo", {})
    # Pinned rather than probed: `flatpak info` would make the answers depend
    # on which emulators the developer happens to have installed.
    monkeypatch.setattr(pergame, "emulator_version", lambda _s: "99.0.0")


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_a_system_that_cannot_do_this_says_so_instead_of_returning_an_error(client):
    """Ten of the thirteen systems land here, every time the panel opens. A
    404 would fill the log of a box that is behaving perfectly, and would look
    to the frontend exactly like the backend having a problem."""
    r = client.get(f"/api/pergame/{UNSUPPORTED.id}", params={"rom": "Game.iso"})
    assert r.status_code == 200
    body = r.json()
    assert body["supported"] is False
    assert body["why"], "the panel has nothing to put on screen in place of the list"
    assert body["canOpenSettings"] is False


def test_an_unidentifiable_dump_is_a_normal_answer_and_not_a_failure(client):
    """A `.wux` is encrypted; a ROM with no header carries nothing. The panel
    has to distinguish "this game cannot be named" from "the request failed",
    because only one of them is worth telling the player about."""
    r = client.get(f"/api/pergame/{SUPPORTING.id}",
                   params={"rom": "/nonexistent/Nothing.bin"})
    assert r.status_code == 200
    body = r.json()
    assert body["supported"] is True
    assert body["gameId"] is None
    assert body["profile"] == {"available": False}


def test_a_bad_system_id_is_refused_before_it_names_a_directory(client):
    """The id becomes a path component under the records root."""
    r = client.get("/api/pergame/..%2F..%2Fetc", params={"rom": "x"})
    assert r.status_code in (400, 404)


def test_the_panel_reports_a_profile_it_can_then_remove(client, monkeypatch, tmp_path):
    profile = PROFILED.data["perGame"]["profiles"][0]
    gid = profile["gameId"]
    monkeypatch.setattr(pergame, "identify", lambda _s, _r: gid)

    pergame.adopt_profile(PROFILED.id, gid)

    r = client.get(f"/api/pergame/{PROFILED.id}", params={"rom": "Game.iso"})
    state = r.json()["profile"]
    assert state["available"] and state["applied"] and state["inRange"]
    assert state["why"], "the player is asked to keep or drop a setting unexplained"

    r = client.post(f"/api/pergame/{PROFILED.id}/profile",
                    json={"rom": "Game.iso", "action": "remove"})
    assert r.status_code == 200
    assert r.json()["profile"]["dismissed"] is True

    r = client.post(f"/api/pergame/{PROFILED.id}/profile",
                    json={"rom": "Game.iso", "action": "restore"})
    assert r.status_code == 200
    assert r.json()["profile"]["dismissed"] is False


def test_removing_a_profile_that_does_not_exist_is_refused_rather_than_reported_ok(
        client, monkeypatch):
    """A success on a profile that was never there teaches the player that the
    button works, which is the worst possible thing to teach them about a
    button whose whole job is to undo something."""
    monkeypatch.setattr(pergame, "identify", lambda _s, _r: "NOSUCHGAME")
    r = client.post(f"/api/pergame/{PROFILED.id}/profile",
                    json={"rom": "Game.iso", "action": "remove"})
    assert r.status_code == 404


def test_an_action_nobody_implements_is_refused(client, monkeypatch):
    monkeypatch.setattr(pergame, "identify", lambda _s, _r: "ANYTHING")
    r = client.post(f"/api/pergame/{PROFILED.id}/profile",
                    json={"rom": "Game.iso", "action": "delete-everything"})
    assert r.status_code == 400


def test_the_settings_button_is_only_offered_where_a_window_exists(client):
    """An emulator with no settings window must not be offered one. The player
    presses it, nothing happens, and from a sofa that is indistinguishable from
    the box having frozen."""
    assert client.get(f"/api/pergame/{UNSUPPORTED.id}").json()["canOpenSettings"] \
        is False
    r = client.post(f"/api/pergame/{UNSUPPORTED.id}/open", json={"rom": ""})
    assert r.status_code == 404


def test_the_settings_button_opens_a_window_and_never_starts_the_game(
        client, monkeypatch):
    """Handing the emulator a ROM path starts the game — the one thing the
    player did NOT ask for from a button marked "settings", and they would get
    a fullscreen game with their menu underneath it."""
    launched = {}

    async def fake_launch(**kwargs):
        launched.update(kwargs)

    monkeypatch.setattr(pergame, "settings_launcher",
                        lambda _s: ("flatpak", "run org.example.Emu"))
    from backend.services.process_manager import process_manager
    monkeypatch.setattr(process_manager, "launch", fake_launch)
    monkeypatch.setattr(type(process_manager), "is_running",
                        property(lambda _self: False))

    r = client.post(f"/api/pergame/{SUPPORTING.id}/open",
                    json={"rom": "/roms/Game.iso"})
    assert r.status_code == 200
    assert not launched.get("rom_path"), (
        f"the settings button passed a ROM and started the game: {launched}")
    assert "--fullscreen" not in launched["exec_args"]


def test_the_settings_window_does_not_start_over_a_running_game(client, monkeypatch):
    monkeypatch.setattr(pergame, "settings_launcher",
                        lambda _s: ("flatpak", "run org.example.Emu"))
    from backend.services.process_manager import process_manager
    monkeypatch.setattr(type(process_manager), "is_running",
                        property(lambda _self: True))
    r = client.post(f"/api/pergame/{SUPPORTING.id}/open", json={"rom": ""})
    assert r.status_code == 409
