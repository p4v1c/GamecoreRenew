"""The controllers router: the mapping wizard's wiring, and what is gone.

These tests assert the WIRING, not the services: that each route exists and
reaches its function. What the wizard does with a capture is covered in
test_controller_capture.py and test_mapping_db.py.

"Scan mapping" and "Forget mapping" (`POST`/`DELETE /controllers/scan-mapping`)
were removed. The route must not come back half-alive — a stale theme or an old
page still calling it has to get a plain 404, and must not reach the snapshot
files the autoconfig pipeline still restores from.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.main import app                              # noqa: E402
from backend.services import controller_capture           # noqa: E402
from backend.services import controller_profiles          # noqa: E402
from backend.services.configgen import mapping_db         # noqa: E402


@pytest.fixture
def client():
    return TestClient(app)


@pytest.mark.parametrize("verb", ["post", "delete"])
def test_the_removed_scan_and_forget_routes_do_nothing(client, verb, tmp_path,
                                                       monkeypatch):
    """Both verbs of the old path answer 404 and leave the snapshots alone.

    The snapshots are the one thing on disk the removed actions ever touched,
    and autoconfig still restores them on every connect: a route that survived
    the removal as a catch-all and deleted one would cost somebody a mapping
    they can no longer re-create from the couch.
    """
    snaps = tmp_path / "controller-snapshots"
    (snaps / "cemu").mkdir(parents=True)
    kept = snaps / "cemu" / "054c_09cc.snap"
    kept.write_text("<emulated_controller/>")
    monkeypatch.setattr(controller_profiles, "SNAP_DIR", snaps)
    monkeypatch.setattr("backend.services.configgen.SNAP_DIR", snaps)

    r = getattr(client, verb)("/api/controllers/scan-mapping")

    assert r.status_code == 404, r.text
    assert kept.read_text() == "<emulated_controller/>"
    assert not hasattr(controller_profiles, "scan_mapping")
    assert not hasattr(controller_profiles, "forget_mapping")


# ── the wizard ───────────────────────────────────────────────────────────────

GUID = "03000325adde0000efbe000011010000"
LINE = f"{GUID},Generic Pad,a:b0,b:b1,platform:Linux,"


def test_the_wizard_reaches_the_capture_service(client, monkeypatch):
    calls = {}

    def fake_start():
        calls["start"] = True
        return {"ok": True}

    monkeypatch.setattr(controller_capture, "start", fake_start)
    monkeypatch.setattr(controller_capture, "commit",
                        lambda b, n: {"ok": True, "bindings": len(b), "name": n})

    assert client.post("/api/controllers/mapping/start").json()["ok"] is True
    assert calls.get("start")

    body = client.post("/api/controllers/mapping/commit",
                       json={"bindings": {"a": "b0", "b": "b1"},
                             "name": "My Pad"}).json()
    assert body["bindings"] == 2 and body["name"] == "My Pad"


def test_commit_takes_a_body_so_the_cross_origin_guard_covers_it(client):
    """main.py's guard only stops what a browser cannot send from a page it did
    not get from us — and a plain HTML form CAN post urlencoded. A Pydantic
    body makes FastAPI answer 422 to anything else, which is the second half of
    the protection. Losing it would let an ad on an unrelated site rewrite the
    controller database."""
    r = client.post("/api/controllers/mapping/commit",
                    data="bindings=a:b0",
                    headers={"content-type": "application/x-www-form-urlencoded"})

    assert r.status_code == 422


def test_the_saved_mappings_are_listed_and_can_be_dropped(client, monkeypatch):
    """A capture that turns out wrong must be undoable from the couch. This is
    the WIZARD's forget, and it stays: it drops one SDL mapping line the owner
    made, not an emulator snapshot."""
    store = [LINE]
    monkeypatch.setattr(mapping_db, "read_user", lambda: list(store))
    monkeypatch.setattr(mapping_db, "remove",
                        lambda g: bool(store.clear()) or True)

    listed = client.get("/api/controllers/mapping/saved").json()
    assert listed["saved"] == [{"guid": GUID, "name": "Generic Pad",
                                "line": LINE, "served": True}]

    assert client.post("/api/controllers/mapping/forget",
                       json={"guid": GUID}).json()["forgotten"] is True
    assert store == []


def test_the_event_socket_refuses_a_page_we_do_not_serve(client):
    """A socket streaming every press on the owner's pad to any page that can
    reach the box is a keylogger with extra steps. `/ws` in main.py checks the
    origin; a WebSocket does not pass through the HTTP middleware, so this one
    has to check it too — and did not, until this test."""
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect) as refused:
        with client.websocket_connect(
                "/api/ws/controllers/mapping",
                headers={"origin": "http://evil.example", "host": "127.0.0.1:8765"}):
            pass

    # The code, not just "it raised": a bare `Exception` here would be
    # satisfied by any breakage at all, which is how a guard test stops
    # guarding without anyone noticing.
    assert refused.value.code == 1008, "policy violation is the refusal we mean"


def test_the_socket_says_so_when_no_session_is_open(client, monkeypatch):
    """Not a silent close: the UI has to be able to tell "the wizard was never
    started" from "the pad went away"."""
    monkeypatch.setattr(controller_capture, "current", lambda: None)

    with client.websocket_connect("/api/ws/controllers/mapping") as socket:
        message = socket.receive_json()

    assert message["event"] == "error"


def test_a_stored_mapping_that_is_not_in_force_says_so(client, monkeypatch):
    """Stored and served are different states, and the screen must not show
    them as one.

    A capture is measured through /dev/input; for a pad SDL reads through a
    HIDAPI driver it is another driver's numbering, so `mapping_db.servable`
    keeps it out of the file SDL is given. It stays in the owner's file — but a
    list that could not say which lines are live would show a mapping that is
    doing nothing exactly like one that is working, which is how the reference
    box came to be re-run through the wizard four times.
    """
    hidapi = "05008fe54c050000cc09000000006800"
    line = f"{hidapi},PS4 Controller,a:b0,b:b1,platform:Linux,"
    monkeypatch.setattr(mapping_db, "read_user", lambda: [LINE, line])

    saved = client.get("/api/controllers/mapping/saved").json()["saved"]

    assert [e["served"] for e in saved] == [True, False]

