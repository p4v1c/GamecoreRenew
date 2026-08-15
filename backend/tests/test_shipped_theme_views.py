"""What a shipped theme is not allowed to drop.

A theme owns its markup, and that includes leaving things out. But a theme is
also the only thing most owners ever see: `config/theme.json` on the reference
box says `active: "shelf"`, and the fallback view is reached by nobody.

So a prop that is the ONLY route to something the box cannot work without is
not a style choice, and the validation session measured what happens when it is
treated as one. Neither shelf nor summer destructured `onRemap`, so the mapping
wizard — the one way to make a controller SDL cannot name usable at all — was
invisible on both. It was verified in both directions: setting `theme.json` to
`active: null` made the button appear.

`scripts/check-theme.mjs` cannot catch this. A view that silently ignores a
prop is perfectly valid JavaScript; it imports, it renders, and the only symptom
is a button nobody can find.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

THEMES = ROOT / "config" / "themes"

# Themes that ship with the box. `_skeleton` is a template and is deliberately
# not held to this: it exists to be copied, and a starting point that already
# had every escape hatch wired would teach nothing about which are load-bearing.
SHIPPED = ("shelf", "summer")


def _gamepad_view(theme: str) -> str:
    path = THEMES / theme / "views" / "gamepad.js"
    assert path.is_file(), f"{theme} ships no gamepad view"
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("theme", SHIPPED)
def test_the_controller_screen_can_reach_the_mapping_wizard(theme):
    """The measured fault: 274 calls to /api/controllers/devices from this
    screen and not one to /mapping/start, because the button was not there."""
    source = _gamepad_view(theme)

    assert "onRemap" in source, (
        f"{theme}/views/gamepad.js never mentions onRemap, so the mapping "
        f"wizard is unreachable from this theme. For a pad SDL cannot name it "
        f"is the only way to make the box usable.")
    assert re.search(r"onClick=\$\{onRemap\}", source), (
        f"{theme} destructures onRemap but nothing invokes it")


@pytest.mark.parametrize("theme", SHIPPED)
def test_the_hold_gesture_is_written_where_it_is_used(theme):
    """The button alone was not enough even when it existed: it was selectable
    with a mouse and nothing else, on a screen reached from a sofa. The host
    owns the gesture (GamepadModal, REMAP_HOLD_MS) so a theme cannot lose it —
    but a gesture nobody is told about is a gesture nobody makes."""
    source = _gamepad_view(theme)

    assert re.search(r"Hold \$\{glyphs\.top\}", source), (
        f"{theme} does not say which button opens the wizard. `glyphs.top` "
        f"rather than a literal △: the same screen serves an Xbox pad, where "
        f"it is Y.")
