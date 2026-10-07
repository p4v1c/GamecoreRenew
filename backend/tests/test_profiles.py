"""Profiles: the primary one appears by itself, names are checked, ids never move.

Every path is under a throwaway data root (`paths.use_roots`).
"""
import json

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from backend.routers import profiles as profiles_router
from backend.services import paths, profiles
from backend.services.errors import ServiceError


@pytest.fixture
def store(tmp_path):
    before = (paths.GAMECORE_ROOT, paths.GAMECORE_DATA)
    paths.use_roots(tmp_path / "code", tmp_path / "data")
    yield paths.profiles_dir() / "profiles.json"
    paths.use_roots(*before)


@pytest.fixture
def client(store):
    app = FastAPI()
    app.include_router(profiles_router.router, prefix="/api")

    @app.exception_handler(ServiceError)
    async def _refused(_request, exc):
        return JSONResponse(status_code=exc.status, content={"detail": exc.detail})

    return TestClient(app)


def test_first_read_creates_one_primary_profile(store):
    state = profiles.list_profiles()
    (only,) = state["profiles"]
    assert only["name"] == "Player 1" and only["primary"] is True
    assert state["active"] == only["id"]
    assert json.loads(store.read_text())["active"] == only["id"], "persisted, so the id stays"
    assert profiles.list_profiles()["profiles"][0]["id"] == only["id"]


def test_names_are_trimmed_and_checked(store):
    assert profiles.create("  Ana   Lou ")["name"] == "Ana Lou"
    for bad in ("", "   ", "x" * (profiles.NAME_MAX + 1), "tab\u0007"):
        with pytest.raises(ServiceError) as e:
            profiles.create(bad)
        assert e.value.status == 400


def test_names_are_unique_ignoring_case(store):
    profiles.create("Sam")
    with pytest.raises(ServiceError) as e:
        profiles.create("sAM")
    assert e.value.status == 409


def test_colour_and_avatar_are_checked(store):
    with pytest.raises(ServiceError):
        profiles.create("Sam", color="#123456")
    with pytest.raises(ServiceError):
        profiles.create("Sam", avatar="mario")
    assert profiles.create("Sam")["color"] == list(profiles.PALETTE)[1], "first unused colour"


def test_rename_keeps_the_id(store):
    p = profiles.create("Sam")
    renamed = profiles.update(p["id"], {"name": "Samuel", "color": list(profiles.PALETTE)[3]})
    assert renamed["id"] == p["id"] and renamed["name"] == "Samuel"
    # Renaming to its own name in another case is not a clash with itself.
    assert profiles.update(p["id"], {"name": "SAMUEL"})["name"] == "SAMUEL"


def test_the_last_profile_cannot_be_deleted(store):
    (only,) = profiles.list_profiles()["profiles"]
    with pytest.raises(ServiceError) as e:
        profiles.delete(only["id"])
    assert e.value.status == 409


def test_deleting_primary_and_active_hands_both_on(store):
    first = profiles.active()
    other = profiles.create("Sam")
    assert profiles.delete(first["id"])["active"] == other["id"]
    (left,) = profiles.list_profiles()["profiles"]
    assert left["primary"] is True


def test_a_failed_write_leaves_the_old_file(store, monkeypatch):
    profiles.create("Sam")
    before = store.read_text()

    def torn(self, *a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(type(store), "write_text", torn)
    with pytest.raises(OSError):
        profiles.create("Lou")
    assert store.read_text() == before
    assert not list(store.parent.glob("*.gamecore-tmp"))


def test_a_broken_file_is_set_aside_not_lost(store):
    store.parent.mkdir(parents=True)
    store.write_text("{not json")
    assert profiles.list_profiles()["profiles"][0]["name"] == "Player 1"
    (aside,) = store.parent.glob("profiles.json.broken-*")
    assert aside.read_text() == "{not json"


def test_a_hand_edit_with_no_active_profile_falls_back_to_the_first(store):
    store.parent.mkdir(parents=True)
    store.write_text('{"profiles": [{"id": "ab", "name": "Sam", "color": "#127a6d",'
                     ' "avatar": null, "created": "", "primary": true}]}')
    assert profiles.active()["id"] == "ab"


def test_a_file_of_the_wrong_shape_is_set_aside(store):
    store.parent.mkdir(parents=True)
    store.write_text('{"profiles": [{"name": "no id"}]}')
    assert profiles.list_profiles()["profiles"][0]["name"] == "Player 1"
    assert list(store.parent.glob("profiles.json.broken-*"))


def test_api_round_trip(client):
    listed = client.get("/api/profiles").json()
    assert [p["color"] for p in listed["palette"]] == list(profiles.PALETTE)
    sam = client.post("/api/profiles", json={"name": "Sam"}).json()
    assert client.post("/api/profiles", json={"name": "sam"}).status_code == 409
    r = client.patch(f"/api/profiles/{sam['id']}", json={"name": "Lou", "avatar": None})
    assert r.json()["name"] == "Lou" and r.json()["id"] == sam["id"]
    assert client.put("/api/profiles/active", json={"id": sam["id"]}).json()["id"] == sam["id"]
    assert client.get("/api/profiles/active").json()["name"] == "Lou"
    assert client.put("/api/profiles/active", json={"id": "nope"}).status_code == 404
    assert client.delete(f"/api/profiles/{sam['id']}").json()["active"] == listed["active"]
    assert client.delete(f"/api/profiles/{listed['active']}").status_code == 409


def test_api_patch_without_name_keeps_it(client):
    sam = client.post("/api/profiles", json={"name": "Sam"}).json()
    r = client.patch(f"/api/profiles/{sam['id']}", json={"name": None, "color": list(profiles.PALETTE)[4]})
    assert r.json()["name"] == "Sam" and r.json()["color"] == list(profiles.PALETTE)[4]


def test_the_list_says_which_systems_keep_saves_per_profile(client):
    body = client.get("/api/profiles").json()
    assert "Nintendo DS" in body["separate_saves"]
