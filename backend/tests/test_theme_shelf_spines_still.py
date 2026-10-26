"""Shelf's spines move only when the shelf does.

The box's X pointer never leaves the screen: unclutter hides it, but Chromium
still hovers whatever is under it. A `.cz-spine:hover` lift therefore raised
the spine that slid under the parked pointer on every d-pad step, then the next
one on the next step: a box "pulled out" that nobody chose.

Read off the stylesheet: jsdom applies no external CSS.
"""
from __future__ import annotations

import re
from pathlib import Path

from backend.tests.css_bundle import read_css

SHELF = Path(__file__).resolve().parents[2] / "config" / "themes" / "shelf"
RULE = re.compile(r"([^{}]+)\{([^}]*)\}")


def test_no_hover_rule_moves_a_spine():
    sheet = re.sub(r"/\*.*?\*/", "", read_css(SHELF / "theme.css"), flags=re.S)
    moving = [sel.strip() for sel, body in RULE.findall(sheet)
              if ":hover" in sel and "cz-spine" in sel and "transform" in body]
    assert not moving, f"a parked pointer would lift spines: {moving}"
