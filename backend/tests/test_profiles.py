"""Profiles: the primary one appears by itself, names are checked, ids never move.

Every path is under a throwaway data root (`paths.use_roots`).
"""
import json
import types

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
def named(store):
    """A box where profiles have started: the primary has a name."""
    first = profiles.active()
    profiles.update(first["id"], {"name": "Max"})
    return store


@pytest.fixture
def client(named):
    app = FastAPI()
    app.include_router(profiles_router.router, prefix="/api")

    @app.exception_handler(ServiceError)
    async def _refused(_request, exc):
        return JSONResponse(status_code=exc.status, content={"detail": exc.detail})

    return TestClient(app)


def test_first_read_creates_one_unnamed_primary_profile(store):
    """Unnamed is "no profiles": players stay P1-P4 until someone names it."""
    state = profiles.list_profiles()
    (only,) = state["profiles"]
    assert only["name"] == "" and only["primary"] is True
    assert state["active"] == only["id"]
    assert json.loads(store.read_text())["active"] == only["id"], "persisted, so the id stays"
    assert profiles.list_profiles()["profiles"][0]["id"] == only["id"]


def test_names_are_trimmed_and_checked(named):
    assert profiles.create("  Ana   Lou ")["name"] == "Ana Lou"
    for bad in ("", "   ", "x" * (profiles.NAME_MAX + 1), "tab\u0007"):
        with pytest.raises(ServiceError) as e:
            profiles.create(bad)
        assert e.value.status == 400


def test_names_are_unique_ignoring_case(named):
    profiles.create("Sam")
    with pytest.raises(ServiceError) as e:
        profiles.create("sAM")
    assert e.value.status == 409


def test_colour_and_avatar_are_checked(named):
    with pytest.raises(ServiceError):
        profiles.create("Sam", color="#123456")
    with pytest.raises(ServiceError):
        profiles.create("Sam", avatar="mario")
    assert profiles.create("Sam")["color"] == list(profiles.PALETTE)[1], "first unused colour"


def test_rename_keeps_the_id(named):
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


def test_the_primary_profile_cannot_be_deleted(named):
    """It owns the saves beside the ROMs: handing that on would swap saves."""
    first = profiles.active()
    profiles.create("Sam")
    with pytest.raises(ServiceError) as e:
        profiles.delete(first["id"])
    assert e.value.status == 409
    assert len(profiles.list_profiles()["profiles"]) == 2


def test_deleting_the_active_profile_hands_active_to_the_primary(named):
    sam = profiles.create("Sam")
    profiles.set_active(sam["id"])
    assert profiles.delete(sam["id"])["active"] == profiles.list_profiles()["profiles"][0]["id"]
    assert profiles.active()["primary"] is True


def test_a_failed_write_leaves_the_old_file(named, monkeypatch):
    store = named
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
    assert profiles.list_profiles()["profiles"][0]["name"] == ""
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
    assert profiles.list_profiles()["profiles"][0]["name"] == ""
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


def test_an_empty_list_is_set_aside_too(store):
    store.parent.mkdir(parents=True)
    store.write_text('{"active": "x", "profiles": []}')
    assert profiles.list_profiles()["profiles"][0]["primary"] is True
    assert list(store.parent.glob("profiles.json.broken-*"))


def test_the_old_default_name_reads_as_unnamed_while_alone(store):
    store.parent.mkdir(parents=True)
    store.write_text('{"active": "ab", "profiles": [{"id": "ab", "name": "Player 1",'
                     ' "color": "#127a6d", "avatar": null, "created": "", "primary": true}]}')
    assert profiles.active()["name"] == ""


def test_another_profile_needs_the_first_one_named(store):
    with pytest.raises(ServiceError) as e:
        profiles.create("Sam")
    assert e.value.status == 409
    profiles.update(profiles.active()["id"], {"name": "Max"})
    assert profiles.create("Sam")["name"] == "Sam"


def test_no_switch_while_a_game_is_on_or_suspended(named, monkeypatch):
    """A suspended game resumes without being placed again: switching would
    have the new profile play in the old one's save."""
    sam = profiles.create("Sam")
    monkeypatch.setattr(profiles, "_game_in_progress", lambda: "mario.nds")
    with pytest.raises(ServiceError) as e:
        profiles.set_active(sam["id"])
    assert e.value.status == 409 and "mario.nds" in e.value.detail
    assert profiles.active()["name"] == "Max"
    # Picking the profile already active is not a switch.
    assert profiles.set_active(profiles.active()["id"])["name"] == "Max"


def test_deleting_the_active_profile_mid_game_is_refused(named, monkeypatch):
    sam = profiles.create("Sam")
    profiles.set_active(sam["id"])
    monkeypatch.setattr(profiles, "_game_in_progress", lambda: "mario.nds")
    with pytest.raises(ServiceError):
        profiles.delete(sam["id"])
    assert profiles.active()["id"] == sam["id"]


def test_an_app_does_not_hold_the_profile(named, monkeypatch):
    from backend.services.process_manager import process_manager
    app = types.SimpleNamespace(is_app=True, game_key="stremio")
    monkeypatch.setattr(type(process_manager), "foreground_session", property(lambda s: app))
    monkeypatch.setattr(type(process_manager), "background_sessions", property(lambda s: []))
    assert profiles._game_in_progress() is None
    game = types.SimpleNamespace(is_app=False, game_key="zelda.nds")
    monkeypatch.setattr(type(process_manager), "background_sessions", property(lambda s: [game]))
    assert profiles._game_in_progress() == "zelda.nds"
