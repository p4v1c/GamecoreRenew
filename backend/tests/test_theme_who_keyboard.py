"""The new-profile keyboard on "Who's using this controller?" has a panel of its own.

`.gcs-who-kb-panel` is filled with `--set-card-2`; a theme whose palette has no
such token (Shelf keeps its settings palette on :root without it) drew a
transparent panel, and the profile tiles showed through the keys.
"""
from pathlib import Path

import pytest

from backend.tests.css_bundle import read_css

THEMES = Path(__file__).resolve().parents[2] / "config" / "themes"
SKINNED = sorted(p.parent.parent.name for p in THEMES.glob("*/css/who.css"))


@pytest.mark.parametrize("theme", SKINNED)
def test_the_who_keyboard_panel_is_filled_on_every_theme(theme):
    css = read_css(THEMES / theme / "theme.css")
    assert "--set-card-2" in css or "gcs-who-kb-panel { background" in css, theme
