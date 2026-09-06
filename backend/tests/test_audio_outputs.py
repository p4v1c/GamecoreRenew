"""/api/settings/audio/sinks — the outputs, and only the outputs.

`wpctl status` is a tree, and this used to be read as a flat list with one
escape hatch: the section was left on `Sink endpoints:` and on nothing else.
That heading is optional. **This box does not print it** — measured on
PipeWire/WirePlumber 1.6.7, where `Sinks:` is followed straight by `Sources:` —
so the parser stayed inside the sinks for the rest of the output and offered
the microphone as somewhere to send sound to. Video's own `Sinks:` was on the
far side of the same gate.

The 2026-09-04 audit filed this as conditional, on the grounds that the machine
it examined did print the heading. The condition holds here, which is why it is
fixed rather than noted.

Nothing below runs wpctl.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.routers.settings import audio                        # noqa: E402

# What this box answers, trimmed. No `Sink endpoints:` anywhere in it.
THIS_BOX = """PipeWire 'pipewire-0' [1.6.7, pavic@GameCore, cookie:4190901850]
 └─ Clients:
        32. kwin_wayland                        [1.6.7, pid:934]

Audio
 ├─ Devices:
 │      43. Radeon High Definition Audio Controller [alsa]
 │  
 ├─ Sinks:
 │  *   52. Ryzen HD Audio Controller Analog Stereo [vol: 1.18]
 │      54. Radeon HDMI Audio             [vol: 1.00]
 │  
 ├─ Sources:
 │  *   53. Ryzen HD Audio Controller Analog Stereo [vol: 1.00]
 │  
 ├─ Filters:
 └─ Streams:

Video
 ├─ Devices:
 ├─ Sinks:
 │      70. Screen capture                [vol: 1.00]
 ├─ Sources:
"""

# The older shape, which the previous parser was written against.
WITH_ENDPOINTS = """Audio
 ├─ Sinks:
 │  *   41. HDMI Output                   [vol: 0.70]
 │  
 ├─ Sink endpoints:
 │      99. Something else                [vol: 0.10]
 │  
 ├─ Sources:
 │  *   42. Microphone                    [vol: 1.00]
"""


def _sinks(monkeypatch, status: str):
    monkeypatch.setattr(audio, "_run", AsyncMock(return_value=(0, status)))
    return asyncio.run(audio.list_sinks())


def test_a_microphone_is_not_an_audio_output(monkeypatch):
    rows = _sinks(monkeypatch, THIS_BOX)
    assert [r["id"] for r in rows] == ["52", "54"]
    assert rows[0]["default"] is True and rows[1]["default"] is False
    assert rows[0]["name"] == "Ryzen HD Audio Controller Analog Stereo"


def test_video_has_sinks_too_and_they_are_not_speakers(monkeypatch):
    assert "70" not in [r["id"] for r in _sinks(monkeypatch, THIS_BOX)]


def test_the_older_layout_still_reads_the_same_way(monkeypatch):
    """A heading this parser no longer depends on must not break it either."""
    rows = _sinks(monkeypatch, WITH_ENDPOINTS)
    assert [r["id"] for r in rows] == ["41"]


def test_a_box_with_no_audio_at_all_answers_an_empty_list(monkeypatch):
    assert _sinks(monkeypatch, "PipeWire 'pipewire-0' [1.6.7]\n") == []
