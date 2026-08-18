"""What the emulator actually drew, when it disagrees with what it announced.

A bezel's hole is cut for the ratio a system is supposed to render at. The
emulator does not always oblige: an aspect-ratio setting left on "stretch", a
core that letterboxes a 4:3 game inside a 16:9 surface, a widescreen hack. The
overlay is then perfectly correct about a picture that is not there — a frame
sitting over part of the game, with black showing through part of the hole, and
nothing on screen to suggest which of the two is wrong.

The only witness is the screen. So a frame is captured a second into the game,
the drawn region is measured out of it, and if that disagrees with the hole the
hole is corrected and the answer remembered.

What this module is careful about
---------------------------------
A capture is a guess about a moving picture, and a wrong correction is worse
than no correction: it moves a hole that was right. Three things stop that.

**Two samples, not one.** A second into a game is very often a black loading
screen, which measures as no content at all — or worse, as a small logo in the
middle of the frame, which measures as a plausible-looking rectangle. Two
samples a second and a half apart have to agree before anything is believed.

**Plausibility, not just arithmetic.** What is being looked for is
letterboxing: a picture centred in the window with even bars on opposite sides.
A measurement that is not centred, or that fills the window, or that covers a
quarter of it, is not a ratio mismatch — it is a dark scene, a menu, or a
capture that caught a transition.

**The correction is cached against the hole it corrects**, keyed by system and
by the ratio that was announced. A box therefore captures once per system per
ratio and then stops looking; and if the artwork is later replaced by one with
a different hole, the key changes and the stale answer is not reused.

X11 only, like the rest of the overlay stack. There is no capture path on a
Wayland session and this module is never reached there.
"""
from __future__ import annotations

import json
import logging
from math import gcd
from pathlib import Path

from .paths import config_dir

log = logging.getLogger(__name__)

# Below this, a pixel is a black bar rather than a dark picture. Emulators
# letterbox with true black; a game's own dark scene rarely sits this low
# across a whole row, and the plausibility checks below catch it when it does.
_BLACK = 18

# A drawn region smaller than this fraction of the window is a logo on a
# loading screen, not a game.
_MIN_COVERAGE = 0.25
# Above this, nothing is corrected — and this one costs a real case.
#
# An emulator stretching a 4:3 game across the whole window genuinely draws
# edge to edge, and correcting to that would be right. But a bright splash
# screen measures identically, and believing one would cache "no bars here" and
# retire a perfectly good bezel permanently. A missed correction leaves the box
# exactly as it is today; a false one throws artwork away. The tie goes to
# doing nothing.
_MAX_COVERAGE = 0.995
# How far off-centre a letterboxed picture may sit before the measurement is
# read as something other than letterboxing.
_CENTRE_TOLERANCE = 8
# Two samples agree within this many pixels on every edge.
_AGREE_TOLERANCE = 4
# Below this, the announced hole was right and moving it would be churn.
_MIN_DRIFT = 6

_CORRECTIONS_FILE = "bezel-corrections.json"


# ── Measuring one frame ──────────────────────────────────────────────────────

def content_bbox(pixels: bytes, width: int, height: int,
                 stride: int, bpp: int = 4) -> tuple[int, int, int, int] | None:
    """The non-black rectangle of a captured frame, or None if it is all black.

    `pixels` is raw image data as X hands it over: `stride` bytes per row,
    `bpp` bytes per pixel, the first three of which are the colour channels in
    some order. Which order does not matter here — the question asked of each
    pixel is only whether it is dark, and that is the same question whether the
    bytes are BGRX or RGBX.
    """
    if width <= 0 or height <= 0 or stride < width * bpp:
        return None
    if len(pixels) < (height - 1) * stride + width * bpp:
        return None

    min_x, min_y, max_x, max_y = width, height, -1, -1
    for y in range(height):
        row = pixels[y * stride:y * stride + width * bpp]
        lo = hi = -1
        for x in range(width):
            p = x * bpp
            # Any channel above the floor makes the pixel lit. Cheaper than a
            # luminance and more forgiving of a single-channel dark blue.
            if row[p] > _BLACK or row[p + 1] > _BLACK or row[p + 2] > _BLACK:
                if lo < 0:
                    lo = x
                hi = x
        if lo >= 0:
            if y < min_y:
                min_y = y
            max_y = y
            if lo < min_x:
                min_x = lo
            if hi > max_x:
                max_x = hi

    if max_x < 0:
        return None
    return (min_x, min_y, max_x - min_x + 1, max_y - min_y + 1)


def is_plausible(box: tuple[int, int, int, int], width: int, height: int) -> bool:
    """Does this measurement look like a letterboxed picture?

    The check exists because `content_bbox` will always return *something* for
    any frame that is not entirely black, and most of those somethings are not
    a game's drawing surface. A menu, a logo, a fade — each measures as a
    rectangle, and each would move a hole that was already right.
    """
    x, y, w, h = box
    coverage = (w * h) / (width * height)
    if not (_MIN_COVERAGE <= coverage <= _MAX_COVERAGE):
        return False
    # Letterboxing is symmetric: whatever is trimmed off the left is trimmed
    # off the right. A picture hard against one edge is something else.
    return (abs(x - (width - x - w)) <= _CENTRE_TOLERANCE
            and abs(y - (height - y - h)) <= _CENTRE_TOLERANCE)


def agree(a: tuple[int, int, int, int] | None,
          b: tuple[int, int, int, int] | None) -> tuple[int, int, int, int] | None:
    """The measurement two samples both support, or None.

    A second into a game is very often a loading screen. Requiring two samples
    to land in the same place is what separates "the emulator renders here"
    from "something was on screen at that moment".
    """
    if a is None or b is None:
        return None
    if all(abs(p - q) <= _AGREE_TOLERANCE for p, q in zip(a, b)):
        return b                     # the later sample: more of the game drawn
    return None


def worth_applying(measured: tuple[int, int, int, int], hole: dict) -> bool:
    """Is the difference big enough to be a mismatch rather than rounding?

    Without this every launch would rewrite the hole by a pixel or two and the
    cache would never settle.
    """
    x, y, w, h = measured
    return (abs(x - hole["x"]) >= _MIN_DRIFT or abs(y - hole["y"]) >= _MIN_DRIFT
            or abs(w - hole["w"]) >= _MIN_DRIFT or abs(h - hole["h"]) >= _MIN_DRIFT)


# ── Remembering the answer ───────────────────────────────────────────────────

def ratio_of(hole: dict) -> str:
    """The announced ratio, reduced — "4:3", "16:9", "1440:968".

    Part of the cache key rather than the raw size, because the same ratio cut
    at two resolutions is the same mismatch and should be learned once.
    """
    w, h = int(hole["w"]), int(hole["h"])
    if w <= 0 or h <= 0:
        return "0:0"
    d = gcd(w, h)
    return f"{w // d}:{h // d}"


def key_for(system_id: str, hole: dict, console: str | None = None) -> str:
    """The cache key: system, console when the pack has any, announced ratio.

    Why the console is in the key at all
    ------------------------------------
    The elegant answer is that it need not be: give each console its own PNG
    and the holes measured out of their alphas differ, so the ratios differ, so
    the keys already differ. That is true and it is not enough — it holds only
    once the player has supplied a PNG per console. Until then the three share
    one image, one hole and one ratio, which is exactly the state the reference
    box was found in: a single `mgba@1:1` correction of 1234x1080, learned from
    a Game Boy, cutting 193 pixels off each side of every Game Boy Advance
    game. And `for_launch` sets `"measure": False` as soon as an answer exists,
    so the box never looks again. The key has to separate them on its own.

    Why a pack with no consoles keeps the bare `<system>@<ratio>`
    -------------------------------------------------------------
    Because that string is on every box that exists. Eleven of the thirteen
    packs declare one console, their corrections were learned under this exact
    key, and changing it would silently discard all of them and make every box
    re-measure — an operation with a real failure mode, run to fix nothing.

    A pack that DOES declare consoles always carries a console segment, `"-"`
    when the extension did not say which. That is deliberate rather than
    falling back to the bare key: the bare key is where the old, console-blind
    corrections are, and a `.zip` Game Boy Advance game must not inherit the
    Game Boy rectangle that made this change necessary. Those entries are left
    on disk — reverting this commit has to bring a box back exactly as it was —
    but nothing can find them any more.
    """
    if console:
        return f"{system_id}/{console}@{ratio_of(hole)}"
    if _has_consoles(system_id):
        return f"{system_id}/-@{ratio_of(hole)}"
    return f"{system_id}@{ratio_of(hole)}"


def _has_consoles(system_id: str) -> bool:
    """Does this pack declare consoles at all?

    Imported here rather than at module scope: `bezels` imports this module,
    and `consoles` is only ever needed inside this one function.
    """
    from . import consoles
    return bool(consoles.declared(system_id))


def _path() -> Path:
    return config_dir() / _CORRECTIONS_FILE


def corrections() -> dict[str, dict]:
    try:
        loaded = json.loads(_path().read_text())
        return loaded if isinstance(loaded, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def correction_for(system_id: str, hole: dict,
                   console: str | None = None) -> dict | None:
    """A hole already learned to be wrong at this ratio, corrected.

    Returns the replacement rectangle, or None to use the hole as announced.
    """
    return corrections().get(key_for(system_id, hole, console))


def record(system_id: str, hole: dict, measured: tuple[int, int, int, int],
           console: str | None = None) -> bool:
    """Learn a correction. False when the measurement was not worth keeping.

    Deliberately silent about *why* not, at this level: the caller has already
    decided the measurement was plausible, and this is only the last guard
    against writing down a difference too small to matter.
    """
    if not worth_applying(measured, hole):
        return False
    x, y, w, h = measured
    data = corrections()
    data[key_for(system_id, hole, console)] = {"x": x, "y": y, "w": w, "h": h}
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
    tmp.replace(p)
    log.info("bezels: %s%s renders at %dx%d+%d+%d, not %dx%d+%d+%d — corrected",
             system_id, f"/{console}" if console else "",
             w, h, x, y, hole["w"], hole["h"], hole["x"], hole["y"])
    return True


def forget() -> None:
    """For tests. The cache is read from disk on every call, so there is no
    in-memory copy to invalidate — this only removes the file."""
    _path().unlink(missing_ok=True)
