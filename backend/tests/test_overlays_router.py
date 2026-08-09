"""`GET /api/overlays/resolve/{system_id}` — the one call a launch makes.

Electron asks this before it starts the window monitor, and whatever comes
back decides what is drawn over the game. Two properties matter more than the
happy path.

It must never fail a launch. A system with no bezel is the normal answer for
five of the thirteen — the 16:9 consoles have no black bars to hide — and a
404 or a 500 here would put a failed request in front of every one of those
launches on a box that is behaving perfectly.

And it must not be a way to read the disk. `system_id` names a directory under
the overlays root and `rom` names a file inside it; both arrive from the
renderer, which got the system id from a tile the operator can edit by hand.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.services import bezels, paths                        # noqa: E402
from backend.tests.test_bezels import write_png                   # noqa: E402


@pytest.fixture
def client():
    from backend import main
    with TestClient(main.app) as c:
        yield c


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "GAMECORE_ROOT", tmp_path)
    monkeypatch.setattr(paths, "GAMECORE_DATA", tmp_path)
    bezels.forget()
    (tmp_path / "assets" / "overlays").mkdir(parents=True)
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "config" / "overlays.json").write_text(json.dumps(
        {"duckstation": {"window_rect": {"x": 0, "y": 0, "w": 1920, "h": 1080},
                         "hole": {"x": 240, "y": 52, "w": 1440, "h": 968}}}))
    yield tmp_path
    bezels.forget()


def test_two_games_resolve_to_two_bezels_over_the_wire(client, library):
    """The phase's acceptance criterion, seen from where Electron stands."""
    overlays = library / "assets" / "overlays"
    write_png(overlays / "duckstation.png", 1920, 1080, (240, 52, 1440, 968))
    write_png(overlays / "duckstation" / "Crash Bandicoot (USA).png",
              1920, 1080, (240, 0, 1440, 1080))
    write_png(overlays / "duckstation" / "Silent Hill (USA).png",
              1920, 1080, (300, 60, 1320, 960))

    crash = client.get("/api/overlays/resolve/duckstation",
                       params={"rom": "Crash Bandicoot (Europe) (v1.1).bin"}).json()
    hill = client.get("/api/overlays/resolve/duckstation",
                      params={"rom": "Silent Hill (USA) (Disc 1).chd"}).json()

    assert crash["source"] == hill["source"] == "game"
    assert crash["asset"] != hill["asset"]
    assert crash["hole"] == {"x": 240, "y": 0, "w": 1440, "h": 1080}
    assert hill["hole"] == {"x": 300, "y": 60, "w": 1320, "h": 960}


def test_a_game_with_no_bezel_of_its_own_gets_the_system_one(client, library):
    write_png(library / "assets" / "overlays" / "duckstation.png",
              1920, 1080, (240, 52, 1440, 968))
    body = client.get("/api/overlays/resolve/duckstation",
                      params={"rom": "Some Import (Japan).chd"}).json()
    assert body["source"] == "system"
    assert body["asset"] == "/assets/overlays/duckstation.png"


def test_a_system_with_no_bezel_at_all_is_a_200_and_not_a_404(client, library):
    """Five of the thirteen systems are 16:9 and want no overlay. This is the
    common answer, not an error, and it has to be cheap and quiet."""
    body = client.get("/api/overlays/resolve/rpcs3",
                      params={"rom": "Whatever.pkg"}).json()
    assert body == {"system_id": "rpcs3", "source": "none",
                    "asset": None, "hole": None, "frame": None}


def test_no_rom_at_all_still_answers(client, library):
    """An app tile launches with no ROM path — `game_key` is then the system
    id itself and there is nothing to look a game up by."""
    write_png(library / "assets" / "overlays" / "duckstation.png",
              1920, 1080, (240, 52, 1440, 968))
    body = client.get("/api/overlays/resolve/duckstation").json()
    assert body["source"] == "system"


@pytest.mark.parametrize("bad", ["..", "../../etc", "a/b", "", " ", "x" * 65])
def test_a_system_id_that_is_not_one_is_refused(client, library, bad):
    """`system_id` is joined onto the overlays root. Without the guard, `..`
    walks out of it and the endpoint reports whether arbitrary PNGs exist."""
    r = client.get(f"/api/overlays/resolve/{bad}")
    assert r.status_code in (400, 404), r.text


def test_a_rom_name_cannot_point_the_lookup_at_another_directory(client, library):
    """Only the filename is used. A `rom` carrying directories would otherwise
    let the pack index be built somewhere nobody chose."""
    overlays = library / "assets" / "overlays"
    write_png(overlays / "duckstation.png", 1920, 1080, (240, 52, 1440, 968))
    write_png(overlays / "duckstation" / "Crash Bandicoot (USA).png",
              1920, 1080, (240, 0, 1440, 1080))

    body = client.get("/api/overlays/resolve/duckstation",
                      params={"rom": "../../../Crash Bandicoot (USA).cue"}).json()
    # The traversal is stripped, so this still resolves the game — by name,
    # from inside the pack directory, which is the only place it may come from.
    assert body["source"] == "game"
    assert body["asset"] == ("/assets/overlays/duckstation/"
                             "Crash%20Bandicoot%20%28USA%29.png")


def test_the_declared_hole_answers_when_the_png_is_missing(client, library):
    """A box whose bezel was never uploaded still gets the frame overlays.json
    describes — that is what the JSON is for, and all it is for."""
    body = client.get("/api/overlays/resolve/duckstation").json()
    assert body["source"] == "declared"
    assert body["asset"] is None
    assert body["hole"] == {"x": 240, "y": 52, "w": 1440, "h": 968}
