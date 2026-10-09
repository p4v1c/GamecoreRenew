"""A metadata cache write cut short leaves the previous entry readable.

`write_text` truncates then writes: a power cut in between left a torn JSON,
which `resolve` then treated as no cache at all.
"""
import asyncio
import json
from pathlib import Path

from backend.services import metadata


def test_a_cache_write_cut_short_keeps_the_old_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(metadata, "METADATA_DIR", tmp_path)
    monkeypatch.setattr(metadata, "rom_in_root", lambda system, filename: None)
    monkeypatch.setattr(metadata.gamemedia, "available", lambda: True)

    async def found(sid, rom):
        return {"found": True}

    monkeypatch.setattr(metadata.gamemedia, "resolve", found)
    monkeypatch.setattr(metadata.gamemedia, "to_game_meta",
                        lambda manifest: {"found": True, "title": "Melee",
                                          "source": "gamemedia"})
    cache = tmp_path / "gc" / "Melee.json"
    cache.parent.mkdir()
    old = {"found": False, "tiers_tried": ["thegamesdb"]}
    cache.write_text(json.dumps(old))

    real_write_text = Path.write_text

    def power_cut(self, text, *args, **kwargs):
        real_write_text(self, text[: len(text) // 2], *args, **kwargs)
        raise OSError("power cut")

    monkeypatch.setattr(Path, "write_text", power_cut)
    try:
        asyncio.run(metadata.resolve({"id": "gc"}, "Melee.iso"))
    except OSError:
        pass
    monkeypatch.undo()

    assert json.loads(cache.read_text()) == old
