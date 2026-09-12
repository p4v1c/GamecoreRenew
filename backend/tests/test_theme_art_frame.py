"""The frame belongs to the game, and a selection draws one ring, not two.

Two faults reported from the sofa on the same evening, both of them about a
box drawn in the wrong place.

**The empty space.** A library card reserves a 2:3 portrait cell — deliberately,
and it must stay that way: "A stable jacket wall. Artwork keeps its full shape
inside the frame; changing every card's grid geometry as hundreds of cached
images decode stalls pad navigation on larger libraries." But the border, the
rounded corners and the selection ring were drawn on that CELL rather than on
the picture in it, so anything that is not 2:3 was framed together with its own
empty space. A Game Boy box is nearly square, a Nintendo 64 carton is
landscape: both showed wide bands of card gradient above and below the art,
with the ring around the bands. Switch covers looked right only because they
happen to be the shape of the cell.

**The extra square.** A pad-focused tile drew a second ring round the whole
button — logo, title and category — on top of the one the theme draws on the
artwork. The rule written to prevent it keys on `.using-gamepad`, which nothing
in GameCore sets, so it never applied; and neither did the ring-on-the-artwork
paired with it.

Read off the stylesheet, as `test_theme_jacket_box.py` has to be and says why:
jsdom applies no external CSS and computes no layout, so the frontend suite is
structurally blind to all of this. What is asserted is the shape of the answer
— which box carries the frame, which selector carries the ring — and not the
pixel values, which are the designer's business.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ORBIT = ROOT / "config" / "themes" / "orbit"


@pytest.fixture(scope="module")
def sheet() -> str:
    """The stylesheet with its comments taken out.

    Not tidiness: the crude `selector { body }` split below has no idea what a
    comment is, so a `/* … */` block ends up glued to the front of the selector
    that follows it. Every prose word in it then reads as part of that
    selector — and the prose here says `using-gamepad` and names three tile
    classes, which is exactly what these tests match on. Left in, a rule was
    rejected for what the paragraph above it said about it.
    """
    return re.sub(r"/\*.*?\*/", "", (ORBIT / "theme.css").read_text(), flags=re.S)


def parsed(sheet: str) -> list[tuple[str, str]]:
    """(selector, body) for every rule, bodies with their spaces taken out."""
    return [(sel.strip(), body.replace(" ", "").replace("\n", ""))
            for sel, body in re.findall(r"([^{}]+)\{([^}]*)\}", sheet)]


def rules(sheet: str, pattern: str) -> list[str]:
    """Every rule body whose selector matches."""
    return [body for sel, body in parsed(sheet) if re.search(pattern, sel)]


# ── the premise: `.using-gamepad` is a class nobody sets ─────────────────────

def test_nothing_sets_the_using_gamepad_class():
    """The whole reason the ring rules had to be rewritten.

    If some host or theme starts setting it, the old rules come back to life,
    this file's reasoning stops holding, and the duplicate ring may well
    return — so this is the first thing to check when it does.
    """
    # The trees that can put a class on an element. Not this file, which names
    # it in order to say it is dead, and not the stylesheet, where the dead
    # rules still sit.
    culprits = []
    for tree in ("config/themes", "frontend/src", "electron"):
        for path in (ROOT / tree).rglob("*"):
            if not path.is_file() or path.suffix not in {".js", ".jsx", ".ts", ".tsx", ".html"}:
                continue
            if "node_modules" in path.parts:
                continue
            if "using-gamepad" in path.read_text(errors="replace"):
                culprits.append(str(path.relative_to(ROOT)))
    assert not culprits, (
        "something sets `using-gamepad` now: " + ", ".join(culprits) +
        " — the rules keyed on it are live again, re-read this file")


# ── one ring per selection ───────────────────────────────────────────────────

def test_the_pad_ring_is_not_drawn_round_the_whole_tile(sheet: str):
    """The square the player sees round Steam. The tile's own ring has to be
    suppressed for pad focus, not only for `:focus-visible` — a `.focus()` that
    follows a gamepad button is not keyboard interaction and `:focus-visible`
    never matches for a player on the sofa."""
    # `using-gamepad` is excluded and that exclusion is the test. A rule behind
    # a class nobody sets suppresses nothing, and one such rule — written for
    # this exact purpose — is still in the sheet saying `outline: none
    # !important`. Counting it is how this defect stayed invisible.
    suppress = [sel for sel, body in parsed(sheet)
                if ".pad-focus" in sel and "using-gamepad" not in sel
                and re.search(r"application-tile|game-tile|library-card", sel)
                and ("outline:none" in body or "outline:0" in body)]
    assert suppress, (
        "no LIVE rule stops the generic ring being drawn round a pad-focused "
        "tile — the only one that does is behind `.using-gamepad`, which "
        "nothing sets")


@pytest.mark.parametrize("tile,art", [
    ("application-tile", "application-tile-image"),
    ("game-tile", "tile-art"),
    ("library-card", "img"),
])
def test_a_pad_focused_tile_rings_its_artwork(sheet: str, tile: str, art: str):
    """Suppressing the button's ring is only half of it: something still has to
    show the player where they are."""
    ringed = [sel for sel, body in parsed(sheet)
              if "using-gamepad" not in sel and ".pad-focus" in sel
              and tile in sel and art in sel and "outline:" in body]
    assert ringed, f"a pad-focused .{tile} draws no ring on its .{art}"


# ── the frame follows the artwork ────────────────────────────────────────────

def test_the_reserved_cell_still_has_a_fixed_shape(sheet: str):
    """Two things at once, and the second is easy to lose.

    The stable wall: if the cell starts sizing itself from the picture, the grid
    moves as images decode, which is what the comment above the grid rule says
    stalls pad navigation on a large library.

    And the cap: the picture is bounded by `max-height: 100%`, and a percentage
    resolves against a parent with a DEFINITE height. The cell has one only
    because it declares its own ratio. Take that away — or wrap the picture in
    an auto-height box on the way to it — and the cap silently becomes `none`:
    `plausible()` accepts ratios down to 0.5, and a jacket that tall then
    overflows the cell and lands on the title.
    """
    cell = rules(sheet, r"\.library-jacket")
    ratios = [body for body in cell if "aspect-ratio:" in body]
    assert ratios, (
        "the jacket cell no longer declares a ratio at all, so nothing gives it "
        "a definite height and `max-height: 100%` on the picture is inert: "
        + repr(cell))
    # 3.6.20 lets one measured ratio describe a whole shelf — see
    # `views/library.js` — but a cell with nothing measured yet still needs a
    # shape, and it is the old portrait. A `var()` with no fallback computes to
    # `auto` and the cap goes with it.
    assert any("2/3" in body for body in ratios), (
        "the cell's ratio has no 2:3 fallback left, so a shelf that has not "
        "been measured — the All view, or the moment before the first picture "
        "decodes — reserves nothing: " + repr(ratios))


def test_the_artwork_keeps_its_own_shape(sheet: str):
    """`width: 100%; height: 100%` is what put a Game Boy box in a portrait
    frame. Bounded auto sizing makes the element's box the picture's box."""
    art = rules(sheet, r"\.library-jacket\s*>\s*img")
    assert art, ".library-jacket > img has no rule of its own"
    body = "".join(art)
    assert "max-width:100%" in body and "max-height:100%" in body, body
    assert "width:auto" in body and "height:auto" in body, body


def test_the_frame_is_drawn_on_the_artwork(sheet: str):
    """The whole point: the border and the corners belong to the picture, so
    that they hug it whatever its shape."""
    body = "".join(rules(sheet, r"\.library-jacket\s*>\s*img"))
    assert "border-radius:" in body, body
    assert "border:1px" in body, body


def test_the_selection_ring_hugs_the_artwork_too(sheet: str):
    """A ring round the reserved cell is a ring round the empty space beside a
    Game Boy box, which is what the photograph showed."""
    ringed = [sel for sel, b in parsed(sheet)
              if "library-card.selected" in sel.replace(" ", "")
              and "library-jacket" in sel and "img" in sel
              and "outline:" in b and "outline:0" not in b]
    assert ringed, (
        "a selected library card draws no ring on the picture itself — a ring "
        "on the cell is a ring round the empty space beside a Game Boy box")


def test_the_stand_in_still_fills_the_cell(sheet: str):
    """The one case with no artwork to hug: the two-letter stand-in for a game
    whose art will never arrive. It has no shape of its own to follow, so the
    fixed cell is the right answer for it and it keeps the frame."""
    fallback = "".join(rules(sheet, r"\.library-jacket\s*>\s*\.art-fallback"))
    assert fallback, ".library-jacket > .art-fallback has no rule"
    assert "width:100%" in fallback and "height:100%" in fallback, fallback
    assert "border-radius:" in fallback, (
        "the stand-in lost its corners when the frame moved to the picture: "
        + fallback)
