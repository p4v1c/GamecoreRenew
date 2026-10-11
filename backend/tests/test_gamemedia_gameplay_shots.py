"""LaunchBox gameplay screenshots beyond the first, for the Shelf PC back's shot row."""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from backend.services.gamemedia import gamemedia as gm


def test_launchbox_keeps_three_gameplay_shots(monkeypatch):
    shots = [f"https://cdn/{n}.jpg" for n in range(4)]

    class Db:
        def close(self):
            pass
    monkeypatch.setattr(gm.gs, "lb_index_ready", lambda: True)
    monkeypatch.setattr(gm.gs, "open_db", lambda auto=False: Db())
    monkeypatch.setattr(gm.gs, "find_game",
                        lambda *a: ({"id": 1, "name": "FIFA 22", "platform": "Windows"}, 1.0))
    monkeypatch.setattr(gm.gs, "game_images",
                        lambda *a: {"screenshot-gameplay": shots, "box-front": ["https://cdn/b.jpg"]})
    media = gm.lb_everything({"title": "FIFA 22", "systems": ["Windows"]}, 0.72)["media"]
    assert media["screenshot-gameplay"]["url"] == shots[0]
    assert media["screenshot-gameplay-2"]["url"] == shots[1]
    assert media["screenshot-gameplay-3"]["url"] == shots[2]
    assert media["screenshot-gameplay-3"]["category"] == "screenshot"
    assert "screenshot-gameplay-4" not in media and "box-front-2" not in media
