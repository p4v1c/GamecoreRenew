"""One layout in one stylesheet, and the two ways that can silently come undone.

`frontend/src/settings/settings.css` carries the geometry of the settings
screen and the power menu. The two shipped themes carry only their palette:
their copies of the layout were deleted once it was proven, screen by screen,
that removing them changed not one pixel.

That is a good arrangement and a fragile one, because both failure modes are
invisible until someone opens the settings screen on a television:

  1. **The host stylesheet stops being loaded.** It reaches the bundle by being
     imported from a module that is always in it. Drop that import and both
     themes render a palette with no layout — a column of unstyled text.
  2. **A theme restates the layout again.** Harmless the day it is written,
     and the beginning of the drift that having one copy was meant to end.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
HOST_CSS = REPO / "frontend" / "src" / "settings" / "settings.css"
THEMES = REPO / "config" / "themes"

# Properties that are the palette. Everything else is layout, and layout is the
# host's. `--*` counts as palette whatever it looks like: the custom properties
# on this screen exist to be the colours.
PALETTE = re.compile(r"color|background|border|box-shadow|fill|stroke|opacity|filter|outline")


def _rules(src: str) -> dict[str, dict[str, str]]:
    """Every top-level rule, as {selector: {property: value}}.

    Written out rather than pulled from a CSS parser: the repository has no
    Python CSS dependency, and adding one to assert on two files is a worse
    trade than forty lines that only have to handle the files in this repo.
    """
    out: dict[str, dict[str, str]] = {}
    i, n = 0, len(src)
    while i < n:
        if src.startswith("/*", i):
            i = src.index("*/", i) + 2
            continue
        if src[i].isspace():
            i += 1
            continue
        brace = src.index("{", i)
        sel = " ".join(src[i:brace].split())
        depth, k = 0, brace
        while k < n:
            if src[k] == "{":
                depth += 1
            elif src[k] == "}":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        if not sel.startswith("@"):
            props = out.setdefault(sel, {})
            for decl in src[brace + 1:k].split(";"):
                if ":" in decl:
                    key, _, val = decl.partition(":")
                    props[key.strip()] = " ".join(val.split())
        i = k + 1
    return out


def _shipped_themes() -> list[Path]:
    return [d for d in sorted(THEMES.iterdir())
            if d.is_dir() and d.name[0] not in "._" and (d / "theme.css").is_file()]


def test_the_host_stylesheet_carries_the_layout():
    """The frame the whole screen hangs off. If these lose their geometry there
    is no second copy to fall back on any more."""
    rules = _rules(HOST_CSS.read_text())
    assert rules.get(".gcs-set", {}).get("position") == "fixed"
    assert "grid-template-columns" in rules.get(".gcs-set-body", {}), (
        "the three-column rail/main/aside grid is gone from the only file that has it"
    )
    for sel in (".gcs-set-rail", ".gcs-set-row", ".gcs-pack", ".gcs-pwr", ".gcs-pwr-row"):
        assert sel in rules, f"{sel} has no layout anywhere"


@pytest.mark.parametrize("theme_dir", _shipped_themes(), ids=lambda d: d.name)
def test_a_theme_does_not_restate_what_the_host_already_gives_it(theme_dir):
    """CSS cascades per property, so a theme only needs to write what differs.

    Both themes shipped a full copy of the layout — 1054 declarations between
    them, identical to the host's and winning only by source order. They were
    removed after every settings page and the power menu were rendered before
    and after and compared: zero differing pixels, in both themes.

    A duplicate reappearing here is not a bug on the day it lands. It is the
    start of the drift that one copy was supposed to end — the two files agree
    now and stop agreeing the first time only one of them is corrected.
    """
    host = _rules(HOST_CSS.read_text())
    theme = _rules((theme_dir / "theme.css").read_text())

    repeated = []
    for sel, props in theme.items():
        if "gcs-" not in sel or sel not in host:
            continue
        for key, val in props.items():
            if key.startswith("--") or "!important" in val:
                continue        # palette, or a deliberate override
            if PALETTE.search(key):
                continue        # the theme's own business
            if host[sel].get(key) == val:
                repeated.append(f"{sel} {{ {key}: {val} }}")

    assert not repeated, (
        f"{theme_dir.name} restates {len(repeated)} declaration(s) the host "
        f"stylesheet already makes — delete them, they change nothing:\n  "
        + "\n  ".join(repeated[:10])
    )


def test_the_host_stylesheet_is_actually_loaded():
    """It reaches the browser by being imported, and by nothing else.

    No import, no layout — and not for the built-in UI alone: both themes now
    depend on this file being in the bundle, because neither carries the layout
    any more. This is the single line whose deletion breaks all three surfaces
    at once.
    """
    importers = [p for p in (REPO / "frontend" / "src").rglob("*.ts*")
                 if "settings/settings.css'" in p.read_text()
                 or 'settings/settings.css"' in p.read_text()]
    assert importers, (
        "nothing imports settings/settings.css — the settings screen has no "
        "layout in any theme"
    )
