#!/usr/bin/env python3
"""Draw a plain bezel with a transparent hole at an exact console ratio.

    scripts/make-console-bezel.py assets/overlays/mgba.gba.png --ratio 3:2

Why this script exists rather than three committed PNGs with no provenance
--------------------------------------------------------------------------
A bezel's hole is the part that has to be *right*, to the pixel: `bezels.py`
derives it from the alpha channel, `bezel_capture.py` keys its corrections on
its ratio, and a hole one pixel off its console's aspect is a frame that bites
into the picture. A binary blob in git cannot be reviewed for that. This can:
the ratio is an argument, the arithmetic is eight lines, and regenerating is
one command when a console is added or a frame size changes.

It also keeps the artwork honest about what it is. Community bezel packs are
other people's box art and logos — GameCore does not host them, ship them in
the ISO, or fetch them unasked, the same posture it takes with BIOS files and
keys. What this draws is a gradient and a bevel: nothing borrowed, and
deliberately plain enough that replacing it is obviously an improvement.

Why stdlib and not Pillow
-------------------------
Same reason `bezels._alpha_bbox` decodes PNG by hand instead of shelling out to
ImageMagick: no install script puts an imaging library on a box or on a
contributor's machine, and a tool that works here and not there is worse than
one that is a little longer. zlib and struct ship with Python.
"""
from __future__ import annotations

import argparse
import struct
import sys
import zlib
from pathlib import Path

# Wide enough to read as a frame edge at three metres, narrow enough not to eat
# into the picture. The hole itself is never touched by it — the bevel is drawn
# OUTSIDE the rectangle, so the transparent region stays exactly the ratio that
# was asked for.
_BEVEL = 28


def _chunk(kind: bytes, body: bytes) -> bytes:
    return (struct.pack(">I", len(body)) + kind + body
            + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF))


def _hex(s: str) -> tuple[int, int, int]:
    s = s.lstrip("#")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def hole_for(frame_w: int, frame_h: int, ratio_w: int, ratio_h: int,
             margin: int) -> tuple[int, int, int, int]:
    """The largest rectangle of this exact ratio that fits, centred.

    Height first, then width from the ratio — and the width is checked, not
    assumed: a console wider than the frame (a 3:2 hole in a 4:3 frame) has to
    be fitted by width instead, or the rectangle runs off the sides and the
    "hole" becomes two vertical stripes.
    """
    h = frame_h - 2 * margin
    w = h * ratio_w // ratio_h
    if w > frame_w - 2 * margin:
        w = frame_w - 2 * margin
        h = w * ratio_h // ratio_w
    # Centred to the pixel. An odd remainder goes to the left/top, which is the
    # same rounding `in_window` uses, so a measured hole and a drawn one agree.
    return (frame_w - w) // 2, (frame_h - h) // 2, w, h


def render(frame_w: int, frame_h: int, hole: tuple[int, int, int, int],
           top: tuple[int, int, int], bottom: tuple[int, int, int],
           accent: tuple[int, int, int]) -> bytes:
    hx, hy, hw, hh = hole
    rows = bytearray()

    for y in range(frame_h):
        t = y / max(1, frame_h - 1)
        base = tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3))

        # Every row starts as the flat gradient colour, then only the pixels
        # that need to differ are written. Touching 2 million pixels one at a
        # time in Python is seconds; this is milliseconds.
        row = bytearray(bytes(base + (255,)) * frame_w)

        inside_y = hy <= y < hy + hh
        if inside_y:
            # Punch the hole: alpha 0, colour irrelevant but kept black so a
            # viewer that ignores alpha shows black bars rather than a colour.
            row[hx * 4:(hx + hw) * 4] = b"\x00\x00\x00\x00" * hw

        # The bevel: a band hugging the hole on all four sides, brightening
        # toward it. Distance is to the RECTANGLE, so the corners round off on
        # their own instead of forming a square notch.
        for x in range(max(0, hx - _BEVEL), min(frame_w, hx + hw + _BEVEL)):
            if inside_y and hx <= x < hx + hw:
                continue                                   # the hole itself
            dx = max(hx - x, x - (hx + hw - 1), 0)
            dy = max(hy - y, y - (hy + hh - 1), 0)
            d = max(dx, dy)
            if d > _BEVEL:
                continue
            k = (1 - d / _BEVEL) ** 2                      # sharp at the edge
            p = x * 4
            row[p:p + 3] = bytes(
                round(base[i] + (accent[i] - base[i]) * k * 0.85) for i in range(3))

        rows += b"\x00" + row                              # filter 0: None

    ihdr = struct.pack(">IIBBBBB", frame_w, frame_h, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", zlib.compress(bytes(rows), 9))
            + _chunk(b"IEND", b""))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", type=Path)
    ap.add_argument("--ratio", required=True,
                    help="the console's aspect, e.g. 10:9 for Game Boy, 3:2 for GBA")
    ap.add_argument("--frame", default="1920x1080",
                    help="the frame the hole is measured in (default 1920x1080, "
                         "the window_rect config/overlays.json forces)")
    ap.add_argument("--margin", type=int, default=0,
                    help="pixels of frame kept above and below the hole")
    ap.add_argument("--top", default="#161a24", help="gradient colour at the top")
    ap.add_argument("--bottom", default="#05070b", help="gradient colour at the bottom")
    ap.add_argument("--accent", default="#8bac0f", help="the bevel's colour")
    a = ap.parse_args()

    try:
        rw, rh = (int(v) for v in a.ratio.split(":"))
        fw, fh = (int(v) for v in a.frame.lower().split("x"))
    except ValueError:
        print("--ratio takes W:H and --frame takes WxH", file=sys.stderr)
        return 2
    if rw <= 0 or rh <= 0 or fw <= 0 or fh <= 0:
        print("ratio and frame must be positive", file=sys.stderr)
        return 2

    hole = hole_for(fw, fh, rw, rh, a.margin)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_bytes(render(fw, fh, hole, _hex(a.top), _hex(a.bottom), _hex(a.accent)))

    x, y, w, h = hole
    from math import gcd
    d = gcd(w, h)
    print(f"{a.out}: {fw}x{fh} frame, hole {w}x{h}+{x}+{y} "
          f"= {w // d}:{h // d} (asked {rw}:{rh})")
    # The ratio is the whole point, so a rounding that broke it is an error and
    # not a warning: a hole that is 1199x1080 instead of 1200x1080 resolves,
    # draws, and bites one pixel into the picture forever.
    if w * rh != h * rw:
        print(f"  ERROR: {w}x{h} is not {rw}:{rh}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
