"""A service's refusal reaches the client as {"detail": ...}, not a bare 500."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient   # noqa: E402

from backend import main                    # noqa: E402
from backend.services import systems        # noqa: E402


def test_a_broken_systems_json_names_itself(tmp_path, monkeypatch):
    broken = tmp_path / "systems.json"
    broken.write_text('[{"id": "nes",')                # truncated hand edit
    monkeypatch.setattr(systems, "SYSTEMS_FILE", broken)
    monkeypatch.setattr(systems, "_file_cache", {})
    r = TestClient(main.app).get("/api/systems")      # no lifespan: no box side effects
    assert r.status_code == 500
    assert "systems.json" in r.json()["detail"]
