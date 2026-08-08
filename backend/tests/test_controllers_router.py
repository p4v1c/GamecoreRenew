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
from backend.services import controller_profiles          # noqa: E402


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
