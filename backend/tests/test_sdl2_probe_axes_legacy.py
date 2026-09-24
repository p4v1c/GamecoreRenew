"""The Legacy Batch extends GameCore's official SDL2 seam with AXES."""
from backend.services.configgen import controllers as cc


def test_sdl2_probe_parses_axis_count_without_changing_existing_fields(monkeypatch):
    cc._sdl2_cache.clear()
    class R:
        stdout = "GUID " + "0" * 32 + "\nAXES 6\nMAP 0000,Pad,a:b0,\n"
    monkeypatch.setattr(cc.subprocess, "run", lambda *a, **k: R())
    out = cc.sdl2_probe("054c", "09cc")
    assert out["guid"] == "0" * 32
    assert out["axes"] == "6"
    assert out["map"].endswith("a:b0,")
