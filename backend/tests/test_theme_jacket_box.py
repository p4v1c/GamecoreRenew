"""A wrapper that a percentage height is measured against must have a box.

Orbit's `Jacket` puts its `<img>` inside a `<span class="orbit-jacket">`. Both
places that draw one size the picture the same way — `.game-tile .tile-art img`
and `.library-cover img` are `width: 100%; height: 100%; object-fit: cover` —
and a percentage height resolves against the parent's *definite* height. An
unstyled `<span>` is inline and has neither a box nor a height, so the height
came out `auto` and the image kept its own proportions inside a container it
was written to fill.

On the home rail that is glaring: `.tile-art` is a square and box art is
portrait, so the jacket sat small in the middle of the tile with the tile's own
gradient showing round it. The library hid the same defect, because
`.library-cover` is `aspect-ratio: 2/3` — near enough a jacket's shape that
nobody noticed the picture was sizing itself.

Read off the stylesheet, and it has to be: jsdom applies no external CSS and
computes no layout, so the frontend suite cannot see any of this. What is
asserted is narrow — that the wrapper is given a box — because that is the
whole of the defect. How the picture is cropped is `object-fit`'s business and
is deliberately not checked here.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ORBIT = ROOT / "config" / "themes" / "orbit"

# Any rule whose selector ends at `.orbit-jacket` — the wrapper itself, not
# something inside it.
WRAPPER_RULE = re.compile(r"\.orbit-jacket\s*\{([^}]*)\}")


@pytest.fixture(scope="module")
def sheet() -> str:
    return (ORBIT / "theme.css").read_text()


def test_the_picture_is_still_sized_against_its_wrapper(sheet: str):
    """The premise. If nobody asks the image to fill its parent any more, the
    test below is guarding nothing and should be deleted rather than left to
    pass forever."""
    depends = [rule for rule in re.findall(r"[^{}]*img\s*\{[^}]*\}", sheet)
               if "height:100%" in rule.replace(" ", "")]
    assert depends, (
        "no rule sizes a jacket image to its parent's height any more — this "
        "file's premise is gone")


def test_the_jacket_wrapper_is_laid_out(sheet: str):
    """The wrapper must be given a box. HOW is the theme's business.

    The defect this guards is the wrapper having no rule at all: an unstyled
    span is inline, and the image inside it sizes itself instead of filling
    the card. That is what shipped once, and what "too small in a square tile"
    looked like.

    It deliberately does not say `position: absolute`. 3.6.5 fixed it that way
    and 3.6.14 replaced it on purpose — "Jackets have their own in-flow boxes.
    A generic absolute wrapper made the library cards collapse and overrode the
    carefully sized home stage." A test that pinned the technique would have
    been a test fighting the designer, and briefly was: the absolute rule was
    re-appended over that one and collapsed the cards again.
    """
    bodies = [b.replace(" ", "") for b in WRAPPER_RULE.findall(sheet)]
    assert bodies, (
        ".orbit-jacket has no rule of its own. It wraps the image the cards "
        "size, and an unstyled span is inline: the picture sizes itself "
        "inside a container meant to hold it.")
    box = "".join(bodies)
    assert "display:" in box or "position:" in box, (
        f".orbit-jacket is mentioned but never laid out: {box!r}")


def test_the_fallback_fills_the_same_box(sheet: str):
    """The two-letter stand-in is what a game with no art gets, and it is on
    screen as often as the pictures are. It fills the card or it sits in a
    corner of it."""
    fallback = re.findall(r"\.orbit-jacket\s*>\s*\.art-fallback\s*\{([^}]*)\}", sheet)
    assert fallback, ".orbit-jacket > .art-fallback has no rule"
    body = "".join(fallback).replace(" ", "")
    assert "width:100%" in body and "height:100%" in body, body
