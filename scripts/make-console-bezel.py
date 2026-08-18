#!/usr/bin/env python3
"""Draw a plain bezel with a transparent hole at an exact console ratio.

    scripts/make-console-bezel.py assets/overlays/mgba.gba.png --ratio 3:2

The three mGBA bezels this repository ships were drawn with:

    scripts/make-console-bezel.py assets/overlays/mgba.gb.png  --ratio 10:9 \
        --top '#1b2418' --bottom '#080b06' --accent '#9bbc0f'
    scripts/make-console-bezel.py assets/overlays/mgba.gbc.png --ratio 10:9 \
        --top '#22162a' --bottom '#0a0710' --accent '#b76ff5'
    scripts/make-console-bezel.py assets/overlays/mgba.gba.png --ratio 3:2 \
        --top '#151b30' --bottom '#070912' --accent '#7c86ff'

10:9 for the Game Boy is the machine's own 160x144. Note that mGBA with
`sgb.borders=1` (the shipped seed) runs a Game Boy game through Super Game Boy
mode and draws a 256x224 frame — 8:7 — around it; the reference box measured
exactly that (1234x1080). A 10:9 hole then covers 17 px of that SGB border on
each side and none of the game. That is the deliberate choice: the frame hugs
the game, not the border. `--ratio 8:7` is one flag away for a box that wants
the other reading.

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

# The frame around the hole, from the hole outward. Distances in pixels of the
# frame, all OUTSIDE the transparent rectangle — the hole itself is never
# touched, so it stays exactly the ratio that was asked for.
#
#   0 .. _RECESS      a dark band, the "depth" of the cut-out
#   _RECESS .. +_LINE a crisp bright line in the console's colour
#   .. _GLOW          a soft halo fading back into the panel
#   .. +_MAT         a flat matte band, the "mount" the picture sits in
#   1 px              a thin dark seam closing the mount
#   .. _GLOW          a soft halo of the console's colour fading into the panel
_RECESS = 7
_LINE = 3
_MAT = 34
_GLOW = 150

# How much darker the far edges of the panels get. Draws the eye inward.
_VIGNETTE = 0.55
# Brushed texture: one row in three a hair lighter. Invisible from the sofa,
# a material rather than a flat fill from up close.
_BRUSH = 0.045


def _chunk(kind: bytes, body: bytes) -> bytes:
    return (struct.pack(">I", len(body)) + kind + body
            + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF))


def _hex(s: str) -> tuple[int, int, int]:
    s = s.lstrip("#")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def _mix(a: tuple[int, int, int], b: tuple[int, int, int], k: float) -> tuple[int, int, int]:
    return tuple(round(a[i] + (b[i] - a[i]) * k) for i in range(3))  # type: ignore[return-value]


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
    """Two panels, a vertical gradient, and a lit frame around the hole.

    Everything is a function of two distances — how far a pixel is from the
    hole, and how far it is from the frame's outer edge — so the picture is
    the same shape whatever the ratio: a wide GBA hole gets narrow panels, a
    square-ish Game Boy hole gets wide ones, and the frame around each looks
    like the same object.
    """
    hx, hy, hw, hh = hole
    # A pale version of the accent for the crisp line: pure accent reads as a
    # coloured stripe, a lifted one reads as light catching an edge.
    line = _mix(accent, (255, 255, 255), 0.35)

    # Per column, once: distance to the hole in x, and the vignette factor.
    dxs = [max(hx - x, x - (hx + hw - 1), 0) for x in range(frame_w)]
    # Distance to the nearest outer edge, as a fraction of the panel's width
    # on that side, so both panels darken the same way whatever their width.
    left_w = max(1, hx)
    right_w = max(1, frame_w - (hx + hw))
    vig = []
    for x in range(frame_w):
        if x < hx:
            t = x / left_w
        elif x >= hx + hw:
            t = (frame_w - 1 - x) / right_w
        else:
            t = 1.0
        # 1.0 at the hole, (1 - _VIGNETTE) at the outer edge, eased.
        vig.append(1.0 - _VIGNETTE * (1.0 - t) ** 1.6)

    mat_end = _RECESS + _LINE + _MAT
    rows = bytearray()
    for y in range(frame_h):
        t = y / max(1, frame_h - 1)
        base = _mix(top, bottom, t)
        # Lit from a point at mid-height: the panels are a touch brighter
        # level with the middle of the picture and fall off toward the top
        # and bottom edges, which is what stops them reading as flat strips.
        spot = 1.0 - 0.28 * abs(2 * t - 1) ** 1.5
        brush = 1.0 + _BRUSH if y % 3 == 0 else 1.0
        dy = max(hy - y, y - (hy + hh - 1), 0)
        inside_y = dy == 0

        row = bytearray(frame_w * 4)
        for x in range(frame_w):
            dx = dxs[x]
            if inside_y and dx == 0:
                # The hole. Alpha 0; colour kept black so a viewer that
                # ignores alpha shows black bars rather than a colour.
                continue
            d = max(dx, dy)
            v = vig[x] * spot
            r, g, b = round(base[0] * v), round(base[1] * v), round(base[2] * v)

            if d <= _RECESS:
                # Into the shadow of the cut. Darkest right at the hole.
                k = 0.5 + 0.5 * (d / _RECESS)
                r, g, b = round(r * k), round(g * k), round(b * k)
            elif d <= _RECESS + _LINE:
                r, g, b = line
            elif d <= mat_end:
                # The mount: flat, a little lighter than the panel, untextured.
                r, g, b = _mix((r, g, b), accent, 0.22)
                r, g, b = _mix((r, g, b), (255, 255, 255), 0.06)
            elif d == mat_end + 1:
                r, g, b = round(r * 0.45), round(g * 0.45), round(b * 0.45)
            else:
                if d <= _GLOW:
                    k = (1 - (d - mat_end) / (_GLOW - mat_end)) ** 2.0
                    r, g, b = _mix((r, g, b), accent, k * 0.4)
                r, g, b = round(r * brush), round(g * brush), round(b * brush)

            p = x * 4
            row[p] = min(255, r)
            row[p + 1] = min(255, g)
            row[p + 2] = min(255, b)
            row[p + 3] = 255

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
