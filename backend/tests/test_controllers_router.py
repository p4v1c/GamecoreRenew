"""The two halves of the "Scan mapping" gesture.

`restore()` refuses a snapshot whose GUID names another controller — the box
already holds one, cemu/045e_02fd.snap containing a DualShock 4's config. A
refusal is only an improvement if the owner can act on it, and for a long time
they could not: this router exposed POST and nothing else, so a poisoned
snapshot was permanent and re-applied on every connect.

These tests assert the WIRING, not the service: that both verbs exist on the
path and reach their function. What each function does is covered in
test_configgen_snapshots.py, on the mechanism itself.
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


def test_a_saved_mapping_can_be_deleted(client, monkeypatch):
    """The missing inverse. Without it a detected disagreement has no way out
    and the owner trades a silent overwrite for a silent deadlock."""
    seen = {}

    def fake_forget():
        seen["called"] = True
        return {"ok": True, "controller": "Xbox pad", "forgotten": ["cemu"]}

    monkeypatch.setattr(controller_profiles, "forget_mapping", fake_forget)

    r = client.delete("/api/controllers/scan-mapping")

    assert r.status_code == 200
    assert seen.get("called"), "DELETE did not reach forget_mapping()"
    assert r.json()["forgotten"] == ["cemu"]


def test_scanning_is_still_reachable(client, monkeypatch):
    """Guard-rail: the new verb must not have displaced the existing one."""
    monkeypatch.setattr(controller_profiles, "scan_mapping",
                        lambda: {"ok": True, "controller": "pad",
                                 "saved": [], "refused": []})

    assert client.post("/api/controllers/scan-mapping").status_code == 200


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
    """A capture that turns out wrong must be undoable from the couch — the
    same reason DELETE exists for the snapshots above it."""
    store = [LINE]
    monkeypatch.setattr(mapping_db, "read_user", lambda: list(store))
    monkeypatch.setattr(mapping_db, "remove",
                        lambda g: bool(store.clear()) or True)

    listed = client.get("/api/controllers/mapping/saved").json()
    assert listed["saved"] == [{"guid": GUID, "name": "Generic Pad", "line": LINE}]

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
