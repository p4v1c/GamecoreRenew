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
                    "asset": None, "hole": None, "frame": None,
                    "measure": False}


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


# ── Learning that the emulator draws somewhere else ─────────────────────────

def test_a_reported_mismatch_moves_the_hole_on_the_next_launch(client, library):
    """The loop this endpoint exists to close.

    The bezel announces 4:3 and the emulator letterboxes instead. The first
    launch draws the announced hole and reports what it saw; the second starts
    out right and is told not to bother looking again.
    """
    write_png(library / "assets" / "overlays" / "duckstation.png",
              1920, 1080, (240, 0, 1440, 1080))

    first = client.get("/api/overlays/resolve/duckstation").json()
    assert first["hole"] == {"x": 240, "y": 0, "w": 1440, "h": 1080}
    assert first["measure"] is True

    r = client.post("/api/overlays/measured/duckstation", json={
        "announced": first["hole"],
        "measured": {"x": 0, "y": 120, "w": 1920, "h": 840},
        "window": {"w": 1920, "h": 1080},
    })
    assert r.json() == {"ok": True, "applied": True, "reason": None}

    second = client.get("/api/overlays/resolve/duckstation").json()
    assert second["hole"] == {"x": 0, "y": 120, "w": 1920, "h": 840}
    # The announced rectangle is still reported, because it is the key the
    # correction was filed under — relearning against the corrected value
    # would move the hole a little further every single launch.
    assert second["announced"] == {"x": 240, "y": 0, "w": 1440, "h": 1080}
    assert second["measure"] is False


def test_a_logo_on_a_loading_screen_is_reported_and_refused(client, library):
    """The monitor can only decide the two samples agreed. Whether what they
    agreed on is a game is decided here, where it can be tested."""
    write_png(library / "assets" / "overlays" / "duckstation.png",
              1920, 1080, (240, 0, 1440, 1080))
    r = client.post("/api/overlays/measured/duckstation", json={
        "announced": {"x": 240, "y": 0, "w": 1440, "h": 1080},
        "measured": {"x": 860, "y": 470, "w": 200, "h": 140},
        "window": {"w": 1920, "h": 1080},
    })
    assert r.json()["applied"] is False

    body = client.get("/api/overlays/resolve/duckstation").json()
    assert body["hole"] == {"x": 240, "y": 0, "w": 1440, "h": 1080}
    # Nothing was written, so the next launch looks again rather than giving up.
    assert body["measure"] is True


def test_a_measurement_within_tolerance_changes_nothing(client, library):
    """Otherwise every launch rewrites the hole by a pixel and the box never
    stops capturing."""
    write_png(library / "assets" / "overlays" / "duckstation.png",
              1920, 1080, (240, 0, 1440, 1080))
    r = client.post("/api/overlays/measured/duckstation", json={
        "announced": {"x": 240, "y": 0, "w": 1440, "h": 1080},
        "measured": {"x": 242, "y": 1, "w": 1438, "h": 1079},
        "window": {"w": 1920, "h": 1080},
    })
    assert r.json() == {"ok": True, "applied": False, "reason": "within tolerance"}


def test_a_malformed_measurement_is_refused_not_crashed(client, library):
    r = client.post("/api/overlays/measured/duckstation", json={
        "announced": {"x": 0}, "measured": {}, "window": {},
    })
    assert r.status_code == 400


# ── The player's own choice ─────────────────────────────────────────────────

def _pack(library: Path) -> None:
    overlays = library / "assets" / "overlays"
    write_png(overlays / "duckstation.png", 1920, 1080, (240, 52, 1440, 968))
    write_png(overlays / "duckstation" / "Crash Bandicoot (USA).png",
              1920, 1080, (240, 0, 1440, 1080))


def test_turning_an_overlay_off_draws_nothing_at_all(client, library):
    """Not the declared frame. Switching a bezel off used to have nowhere to
    land except "no PNG", and "no PNG" means "draw the JSON frame" — so the
    artwork would be replaced by black bars, which is the opposite of the
    request."""
    _pack(library)
    r = client.put("/api/overlays/choices/duckstation",
                   json={"rom": "Crash Bandicoot (USA).cue", "choice": "off"})
    assert r.status_code == 200, r.text

    body = client.get("/api/overlays/resolve/duckstation",
                      params={"rom": "Crash Bandicoot (USA).cue"}).json()
    assert body["source"] == "off"
    assert body["asset"] is None
    assert body["hole"] is None


def test_a_choice_applies_to_the_game_and_not_to_the_system(client, library):
    _pack(library)
    client.put("/api/overlays/choices/duckstation",
               json={"rom": "Crash Bandicoot (USA).cue", "choice": "off"})

    other = client.get("/api/overlays/resolve/duckstation",
                       params={"rom": "Silent Hill (USA).cue"}).json()
    assert other["source"] == "system"


def test_a_choice_survives_the_dump_being_replaced(client, library):
    """Stored under the normalised key, so the European re-dump of a game
    keeps the setting made on the American one. A preference filed under a
    filename would silently reset the day someone swapped a ROM."""
    _pack(library)
    client.put("/api/overlays/choices/duckstation",
               json={"rom": "Crash Bandicoot (USA).cue", "choice": "off"})

    body = client.get("/api/overlays/resolve/duckstation",
                      params={"rom": "Crash Bandicoot (Europe) (Rev 1).chd"}).json()
    assert body["source"] == "off"


def test_going_back_to_automatic_forgets_the_choice(client, library):
    """Removed, not stored as "auto". The automatic answer changes when a pack
    is installed, and a written-down answer would never notice."""
    _pack(library)
    client.put("/api/overlays/choices/duckstation",
               json={"rom": "Crash Bandicoot (USA).cue", "choice": "off"})
    r = client.put("/api/overlays/choices/duckstation",
                   json={"rom": "Crash Bandicoot (USA).cue", "choice": None})
    assert r.json()["current"] is None
    assert r.json()["resolved"]["source"] == "game"


def test_the_system_bezel_can_be_chosen_over_the_game_one(client, library):
    """It does not live in the pack directory, so the index that answers every
    other lookup cannot find it — the one case that needs its own branch."""
    _pack(library)
    r = client.put("/api/overlays/choices/duckstation",
                   json={"rom": "Crash Bandicoot (USA).cue", "choice": "duckstation.png"})
    assert r.status_code == 200, r.text
    assert r.json()["resolved"]["asset"] == "/assets/overlays/duckstation.png"


def test_a_bezel_that_does_not_exist_cannot_be_chosen(client, library):
    """A preference is only ever allowed to name something on this box.
    Otherwise the setting saves happily and does nothing at launch."""
    _pack(library)
    r = client.put("/api/overlays/choices/duckstation",
                   json={"rom": "Crash Bandicoot (USA).cue", "choice": "Nonesuch.png"})
    assert r.status_code == 404


def test_a_chosen_bezel_that_later_disappears_falls_back(client, library):
    """A pack uninstalled under a preference that names it. Falling back to
    the cascade beats an overlay pointing at a missing file."""
    _pack(library)
    client.put("/api/overlays/choices/duckstation",
               json={"rom": "Crash Bandicoot (USA).cue",
                     "choice": "Crash Bandicoot (USA).png"})
    (library / "assets" / "overlays" / "duckstation" / "Crash Bandicoot (USA).png").unlink()

    body = client.get("/api/overlays/resolve/duckstation",
                      params={"rom": "Crash Bandicoot (USA).cue"}).json()
    assert body["source"] == "system"


def test_the_options_screen_is_offered_only_what_exists(client, library):
    _pack(library)
    body = client.get("/api/overlays/choices/duckstation",
                      params={"rom": "Crash Bandicoot (USA).cue"}).json()
    assert body["current"] is None
    assert [o["level"] for o in body["options"]] == ["game", "system"]

    bare = client.get("/api/overlays/choices/duckstation",
                      params={"rom": "Silent Hill (USA).cue"}).json()
    assert [o["level"] for o in bare["options"]] == ["system"]


def test_a_choice_needs_a_game(client, library):
    r = client.put("/api/overlays/choices/duckstation", json={"rom": "", "choice": "off"})
    assert r.status_code == 400


def test_the_declared_hole_answers_when_the_png_is_missing(client, library):
    """A box whose bezel was never uploaded still gets the frame overlays.json
    describes — that is what the JSON is for, and all it is for."""
    body = client.get("/api/overlays/resolve/duckstation").json()
    assert body["source"] == "declared"
    assert body["asset"] is None
    assert body["hole"] == {"x": 240, "y": 52, "w": 1440, "h": 968}
