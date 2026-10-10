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
from backend.services import paths, profiles, themes
from backend.services.errors import ServiceError


@pytest.fixture(autouse=True)
def wardrobe(monkeypatch):
    """The themes as profiles see them: what is on, and which ids exist. The
    real module reads the box's theme.json, wherever these tests run."""
    worn = types.SimpleNamespace(on="shelf", installed={"shelf", "orbit", "jelly"})

    def check(theme_id):
        if theme_id is not None and theme_id not in worn.installed:
            raise LookupError("no such theme")

    def set_active(theme_id):
        check(theme_id)
        worn.on = theme_id
        return theme_id

    monkeypatch.setattr(themes, "get_active", lambda: worn.on)
    monkeypatch.setattr(themes, "shipped", lambda: "shelf")
    monkeypatch.setattr(themes, "check", check)
    monkeypatch.setattr(themes, "set_active", set_active)
    return worn


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
    assert e.value.detail.startswith("Sam "), "named as the profile that has it"


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
    assert body["shared_saves"] == ["PC", "Xbox 360"], "the emulators that say why they cannot"


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


def test_the_pictures_are_the_ones_the_interface_draws():
    from pathlib import Path
    import re
    js = (Path(__file__).resolve().parents[2] / "frontend/src/settings/avatars.js").read_text()
    drawn = set(re.findall(r"^\s*\['([a-z]+)', '", js, re.M))
    assert drawn == set(profiles.AVATARS)


def test_a_picture_is_set_and_cleared(named):
    me = profiles.active()["id"]
    assert profiles.update(me, {"avatar": "fox"})["avatar"] == "fox"
    assert profiles.update(me, {"avatar": None})["avatar"] is None
    with pytest.raises(ServiceError):
        profiles.update(me, {"avatar": "dragon"})


def test_a_picture_from_an_older_version_reads_as_none(named):
    state = json.loads(profiles._file().read_text())
    state["profiles"][0]["avatar"] = "rocket"
    profiles._file().write_text(json.dumps(state))
    assert profiles.active()["avatar"] is None


def test_log_in_automatically_is_off_until_turned_on(client):
    assert client.get("/api/profiles").json()["auto_login"] is False
    assert client.put("/api/profiles/auto-login", json={"enabled": True}).json() == {"auto_login": True}
    assert client.get("/api/profiles").json()["auto_login"] is True


# ── the theme follows the profile ────────────────────────────────────────────

def test_switching_puts_on_the_theme_the_profile_wore(client, wardrobe):
    max_id = profiles.active()["id"]
    sam = profiles.create("Sam")
    client.put("/api/profiles/active", json={"id": sam["id"]})
    profiles.remember_theme("orbit")          # Sam picks Orbit in Settings
    wardrobe.on = "orbit"
    assert client.put("/api/profiles/active", json={"id": max_id}).status_code == 200
    assert wardrobe.on == "shelf"             # Max had Shelf on when Sam took over
    client.put("/api/profiles/active", json={"id": sam["id"]})
    assert wardrobe.on == "orbit"


def test_a_theme_picked_by_one_profile_never_lands_on_another(client, wardrobe):
    """Max picks Jelly in Settings → Themes; Sam, who never picked one, used
    to be handed Jelly for good at the first switch."""
    max_id = profiles.active()["id"]
    sam = profiles.create("Sam")
    profiles.remember_theme("jelly")
    wardrobe.on = "jelly"
    client.put("/api/profiles/active", json={"id": sam["id"]})
    assert wardrobe.on == "shelf" and profiles.active()["theme"] == "shelf"
    client.put("/api/profiles/active", json={"id": max_id})
    assert wardrobe.on == "jelly"


def test_a_profile_saved_without_a_theme_gets_the_out_of_box_look(client, store, wardrobe):
    """Profiles made before this fix have no `theme`: the one leaving keeps
    what it wore, the one arriving gets the look a new box shows."""
    sam = profiles.create("Sam")
    state = json.loads(store.read_text())
    for p in state["profiles"]:
        p.pop("theme", None)
    store.write_text(json.dumps(state))
    wardrobe.on = "jelly"
    client.put("/api/profiles/active", json={"id": sam["id"]})
    assert wardrobe.on == "shelf"
    by_name = {p["name"]: p for p in profiles.list_profiles()["profiles"]}
    assert by_name["Max"]["theme"] == "jelly" and by_name["Sam"]["theme"] == "shelf"


def test_a_theme_is_remembered_only_once_profiles_exist(store):
    profiles.remember_theme("orbit")
    assert "theme" not in profiles.active()
    profiles.update(profiles.active()["id"], {"name": "Max"})
    profiles.remember_theme(None)             # the built-in look is a choice too
    assert profiles.active()["theme"] is None


def test_editing_the_active_profiles_theme_puts_it_on(client, wardrobe):
    me = profiles.active()["id"]
    r = client.patch(f"/api/profiles/{me}", json={"theme": "jelly"})
    assert r.status_code == 200 and wardrobe.on == "jelly"
    sam = profiles.create("Sam")
    client.patch(f"/api/profiles/{sam['id']}", json={"theme": "orbit"})
    assert wardrobe.on == "jelly"             # Sam is not playing: nothing changes yet
    r = client.patch(f"/api/profiles/{me}", json={"theme": "gone"})
    assert r.status_code == 400


def test_a_theme_uninstalled_since_leaves_the_screen_as_it_is(client, wardrobe):
    max_id = profiles.active()["id"]
    sam = profiles.create("Sam")
    profiles.update(sam["id"], {"theme": "orbit"})
    wardrobe.installed.discard("orbit")
    assert client.put("/api/profiles/active", json={"id": sam["id"]}).status_code == 200
    assert wardrobe.on == "shelf" and profiles.active()["id"] != max_id


# ── controllers shown on a profile (display only) ────────────────────────────

DS4 = {"id": "84:30:95:07:c8:1c", "name": "PS4 Controller", "connection": "Bluetooth"}
XBOX = {"id": "045e:0b13", "name": "Xbox Wireless Controller", "connection": "USB"}


@pytest.fixture
def pads(monkeypatch):
    connected = [DS4, XBOX]
    monkeypatch.setattr(profiles_router.controller_roster, "connected_pads", lambda: list(connected))
    return connected


def test_a_controller_is_shown_on_one_profile_only(client, pads):
    max_id = profiles.active()["id"]
    sam = profiles.create("Sam")
    r = client.post(f"/api/profiles/{max_id}/controllers", json={"id": DS4["id"]})
    assert r.status_code == 200
    assert r.json()["controllers"] == [{"id": DS4["id"], "name": "PS4 Controller"}]
    client.post(f"/api/profiles/{sam['id']}/controllers", json={"id": DS4["id"]})
    by_name = {p["name"]: p for p in client.get("/api/profiles").json()["profiles"]}
    assert by_name["Max"]["controllers"] == []
    assert [c["id"] for c in by_name["Sam"]["controllers"]] == [DS4["id"]]


def test_only_a_connected_controller_can_be_added(client, pads):
    me = profiles.active()["id"]
    r = client.post(f"/api/profiles/{me}/controllers", json={"id": "aa:bb:cc:dd:ee:ff"})
    assert r.status_code == 404 and "not connected" in r.json()["detail"]
    assert client.post(f"/api/profiles/{me}/controllers", json={"id": "x" * 65}).status_code == 422
    assert client.post("/api/profiles/nobody/controllers", json={"id": XBOX["id"]}).status_code == 404


def test_a_removed_controller_stays_known_to_nobody(client, pads):
    me = profiles.active()["id"]
    client.post(f"/api/profiles/{me}/controllers", json={"id": XBOX["id"]})
    pads.clear()                              # off: it can still be removed
    r = client.delete(f"/api/profiles/{me}/controllers/{XBOX['id']}")
    assert r.status_code == 200 and r.json()["controllers"] == []
    assert client.delete(f"/api/profiles/{me}/controllers/{XBOX['id']}").status_code == 404


def test_a_controllers_mac_is_masked_in_the_log(named, caplog):
    caplog.set_level("INFO", logger=profiles.log.name)
    profiles.add_controller(profiles.active()["id"], DS4)
    assert "84:30:95:xx:xx:1c" in caplog.text and DS4["id"] not in caplog.text
