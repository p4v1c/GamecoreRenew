"""A theme may restyle the settings screen; it may not lose a column of it.

`frontend/src/settings/settings.css` lays the screen out as three grid tracks —
rail | main | aside — and the pages that have a detail column (Wi-Fi, Bluetooth,
Controllers) put three children into that grid. A theme that overrides
`grid-template-columns` with two tracks does not thereby *remove* the third
child: CSS grid auto-places it on a second row, in the first column, at its own
420px width.

That is what Orbit's Wi-Fi page looked like. The network list was squeezed into
a short first row and clipped mid-entry, and the "Active network" panel sat
underneath the rail, cut off by the bottom of the frame. Nothing in the theme
said "put the details under the rail" — it said "there are two columns", and the
browser did the rest.

Read off the stylesheets rather than rendered: jsdom computes no grid, so the
frontend suite cannot see this at all. The invariant is narrow on purpose — a
theme is free to stack the aside, it just has to SAY so.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
THEMES = ROOT / "config" / "themes"
HOST_CSS = ROOT / "frontend" / "src" / "settings" / "settings.css"

# `.gcs-set-body { … grid-template-columns: <tracks>; … }`
BODY_RULE = re.compile(
    r"\.gcs-set-body[^{}]*\{[^{}]*?grid-template-columns:\s*([^;}]+)", re.S)


def _tracks(value: str) -> int:
    """How many columns this declaration defines.

    `minmax(0, 1fr)` is one track with a comma in it, so the split has to be on
    top-level whitespace and not on commas.
    """
    depth, count, in_track = 0, 0, False
    for ch in value.strip():
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if depth == 0 and ch.isspace():
            in_track = False
            continue
        if not in_track:
            count += 1
            in_track = True
    return count


def _shipped_themes():
    for d in sorted(THEMES.iterdir()):
        if not d.is_dir() or d.name[0] in "._":
            continue
        manifest, css = d / "theme.json", d / "theme.css"
        if not manifest.is_file() or not css.is_file():
            continue
        try:
            provides = json.loads(manifest.read_text()).get("provides") or []
        except json.JSONDecodeError:
            continue
        if "shell" in provides:
            yield pytest.param(d, id=d.name)


CASES = list(_shipped_themes())


def test_there_is_something_to_check():
    """A parametrised test with an empty parameter set is skipped in a line
    nobody reads."""
    assert len(CASES) >= 3, f"expected the shipped themes, found {CASES}"


def test_the_host_still_lays_the_screen_out_in_three():
    """Everything below is measured against this. If the host's own layout
    changes, these tests are comparing against a number that no longer means
    anything — so it is asserted rather than assumed."""
    found = BODY_RULE.findall(HOST_CSS.read_text())
    assert found, "no .gcs-set-body grid-template-columns in the host stylesheet"
    assert _tracks(found[0]) == 3, (
        f"the host now lays the settings screen out in {_tracks(found[0])} "
        "columns; this file's premise needs rewriting")


@pytest.mark.parametrize("theme_dir", CASES)
def test_a_theme_that_narrows_the_grid_keeps_the_detail_column(theme_dir: Path):
    """Either three tracks, or an explicit home for the third child.

    `grid-column` on `.gcs-set-aside` is what makes stacking a decision. Without
    it a two-track override reads as "the details go somewhere, I have not said
    where", and where they go is under the rail, clipped.
    """
    sheet = (theme_dir / "theme.css").read_text()
    narrow = [decl for decl in BODY_RULE.findall(sheet) if _tracks(decl) < 3]
    if not narrow:
        return
    assert re.search(r"\.gcs-set-aside[^{}]*\{[^{}]*grid-column", sheet), (
        f"{theme_dir.name}: .gcs-set-body is overridden to "
        f"{[d.strip() for d in narrow]} — fewer than the host's three tracks — "
        "and .gcs-set-aside is never placed. The detail column does not "
        "disappear: it auto-places on a second row under the rail, at its own "
        "420px, and is clipped by the bottom of the frame. Either keep a third "
        "track or give the aside a grid-column."
    )
