"""Which bezel belongs to a game, and where its window is.

Batocera resolves a decoration in a cascade — the game, then the system, then
nothing — and GameCore's data model already carried the hard half: the `hole`
of `config/overlays.json` is exactly what a Bezel Project `.info` file
describes. What was missing is the per-game level, and one thing worth more
than either: a hole nobody has to keep in sync by hand.

Why the hole is measured and not read
-------------------------------------
`config/` and `assets/overlays/` are both excluded from the OTA rsync
(`update/linux.sh`, the `--exclude` block) — deliberately, they are the
player's. The consequence is that a wrong `hole` in the shipped overlays.json
can never be corrected on a box that already exists: the release carries the
fix and the rsync drops it on the floor.

There was one. `gopher64` declared `1407x888+258+90` while its own PNG is
transparent over `1440x1080+240+0` — a frame 33 px too narrow and 192 px too
short, painted over the game. Nothing caught it because the two values had no
way to disagree in public.

So the hole is derived from the PNG's own alpha channel, which is the only
copy that is actually on the box. The declared value survives as the fallback
for a system whose PNG is missing, and `test_bezels.py` now fails the build
when a shipped PNG and its declared hole drift apart again.

Why a PNG decoder rather than ImageMagick
-----------------------------------------
The README's recipe is
`magick overlay.png -alpha extract -threshold 50% -negate -format "%@" info:`
and it is the right thing to type at a shell. It is the wrong thing to depend
on at launch time: no install script puts ImageMagick on a box, so the feature
would work on the developer's machine and silently do nothing in the living
room — the failure mode that is hardest to notice from a sofa.

The decoder below reads only what it needs. All five PNG row filters reference
bytes at a distance of exactly one pixel (`x[i-bpp]`, `prev[i]`, `prev[i-bpp]`),
so each channel unfilters independently of the others: taking a stride slice of
the alpha byte alone is not an approximation, it is the same arithmetic on a
quarter of the data. 1.6 s of unfiltering for a 1920x1080 RGBA bezel becomes
0.4 s, which is what makes this affordable in front of a game starting.
`test_bezels.py` pins the result against ImageMagick's on the shipped assets
wherever `magick` happens to exist.
"""
from __future__ import annotations

import json
import logging
import struct
import zlib
from pathlib import Path

from .gamemedia.parser import normalize, parse_rom
from .paths import config_dir, overlays_dir

log = logging.getLogger(__name__)

# Below this, a pixel counts as part of the hole. The same 50 % cut the
# README's `-threshold 50%` makes, so the two recipes cannot disagree.
_ALPHA_CUT = 128

# A bezel whose hole is this much of the frame is not decorating anything. It
# is also what a fully transparent PNG measures as, which is the shape an
# interrupted download leaves behind — and a hole covering the whole screen
# would read as "the bezel works" while doing nothing at all.
_HOLE_MAX_COVERAGE = 0.995

# The cache is keyed by identity, not by name: a bezel replaced through the
# upload endpoint keeps its path and would otherwise keep a stale hole.
_CACHE_FILE = "bezel-holes.json"
_memo: dict[str, dict] = {}
_disk: dict[str, dict] | None = None

# opaque → 0, transparent → 1, so a row scan is `bytes.find` and not a loop
_MASK = bytes(1 if a < _ALPHA_CUT else 0 for a in range(256))


# ── Identity ─────────────────────────────────────────────────────────────────

def rom_key(name: str) -> str:
    """The comparable identity of a ROM or bezel filename.

    Both sides of the match go through this: `Crash Bandicoot (USA).cue` on the
    library side and `Crash Bandicoot (USA).png` on the pack side have to land
    on the same string, or a Bezel Project pack matches nothing and the cascade
    silently falls through to the system bezel for every game.

    It is `parse_rom` + `normalize` from the scraper's parser and deliberately
    not a second regex. That vocabulary — the region table, the language table,
    `TAG_RE`, the articles — is the same problem already solved once, and a
    ROM's identity has to be one answer: a name that scrapes as one game and
    resolves a bezel as another is worse than either being wrong alone.
    """
    return normalize(parse_rom(name)["title"])


# ── The cascade ──────────────────────────────────────────────────────────────

def _pack_dir(system_id: str) -> Path:
    return overlays_dir() / system_id


def _pack_index(system_id: str) -> dict[str, Path]:
    """`rom_key` → PNG, for one system's per-game pack.

    Not cached. A pack directory holds a few thousand files at most and the
    call happens once per launch; a cache here would need invalidating on every
    path the addon writes through, and a stale index is a bezel that stops
    appearing after the pack it belongs to was installed.
    """
    d = _pack_dir(system_id)
    if not d.is_dir():
        return {}
    index: dict[str, Path] = {}
    try:
        entries = sorted(d.iterdir())
    except OSError as e:
        log.warning("bezels: cannot list %s — %s", d, e)
        return {}
    for p in entries:
        if p.suffix.lower() != ".png" or not p.is_file():
            continue
        # sorted() above makes the winner of a collision deterministic rather
        # than dependent on the order the filesystem happens to return.
        index.setdefault(rom_key(p.name), p)
    return index


def resolve(system_id: str, rom_name: str | None = None) -> tuple[Path | None, str]:
    """The bezel for this game, and which level of the cascade produced it.

    `(path, "game")` → a bezel named after this ROM;
    `(path, "system")` → the system's own bezel;
    `(None, "none")` → there is no bezel, and the caller must draw nothing.

    That last one is not a detail. The fallback frame drawn from a declared
    hole is only ever correct for a system whose geometry someone measured;
    inventing one for a system with no bezel at all puts black bars over a game
    that was filling the screen correctly.
    """
    if rom_name:
        hit = _pack_index(system_id).get(rom_key(rom_name))
        if hit:
            return hit, "game"
    system_png = overlays_dir() / f"{system_id}.png"
    if system_png.is_file():
        return system_png, "system"
    return None, "none"


# ── Measuring the hole ───────────────────────────────────────────────────────

def _alpha_bbox(png: Path) -> tuple[int, int, int, int, int, int] | None:
    """(x, y, w, h, image_w, image_h) of the transparent region, or None.

    None means "this file did not answer", never "the hole is empty" — the
    caller falls back to the declared geometry rather than to a guess. An
    interlaced, 16-bit or palette PNG lands here, and so does a truncated one.
    """
    try:
        raw = png.read_bytes()
    except OSError as e:
        log.warning("bezels: cannot read %s — %s", png, e)
        return None
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        return None

    idat = bytearray()
    width = height = depth = colour = interlace = 0
    i = 8
    try:
        while i + 8 <= len(raw):
            (length,) = struct.unpack(">I", raw[i:i + 4])
            kind = raw[i + 4:i + 8]
            body = raw[i + 8:i + 8 + length]
            if len(body) != length:
                return None                      # truncated
            if kind == b"IHDR":
                width, height, depth, colour, _, _, interlace = \
                    struct.unpack(">IIBBBBB", body)
            elif kind == b"IDAT":
                idat += body
            elif kind == b"IEND":
                break
            i += 12 + length
    except struct.error:
        return None

    # Colour types 4 and 6 are the two that carry an alpha channel of their
    # own. A palette PNG's transparency lives in tRNS and needs the palette
    # walked per pixel; no bezel is stored that way and guessing is worse than
    # deferring to the declared hole.
    if interlace or depth != 8 or colour not in (4, 6) or not width or not height:
        return None

    channels = 4 if colour == 6 else 2
    stride = width * channels
    try:
        data = zlib.decompress(bytes(idat))
    except zlib.error as e:
        log.warning("bezels: %s has an unreadable image stream — %s", png, e)
        return None
    if len(data) < height * (stride + 1):
        return None

    prev = bytearray(width)
    min_x, min_y, max_x, max_y = width, height, -1, -1
    pos = 0
    rest = range(1, width)
    for y in range(height):
        filt = data[pos]
        # Stride slice: the alpha byte of every pixel, still filtered. See the
        # module docstring — the filters are per-channel, so this is exact.
        cur = bytearray(data[pos + channels:pos + 1 + stride:channels])
        pos += 1 + stride
        if filt == 1:                                        # Sub
            for x in rest:
                cur[x] = (cur[x] + cur[x - 1]) & 255
        elif filt == 2:                                      # Up
            for x in range(width):
                cur[x] = (cur[x] + prev[x]) & 255
        elif filt == 3:                                      # Average
            cur[0] = (cur[0] + (prev[0] >> 1)) & 255
            for x in rest:
                cur[x] = (cur[x] + ((cur[x - 1] + prev[x]) >> 1)) & 255
        elif filt == 4:                                      # Paeth
            cur[0] = (cur[0] + prev[0]) & 255
            for x in rest:
                a, b, c = cur[x - 1], prev[x], prev[x - 1]
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                cur[x] = (cur[x] + (a if pa <= pb and pa <= pc
                                    else b if pb <= pc else c)) & 255
        elif filt != 0:
            return None                                      # not a PNG filter

        mask = bytes(cur).translate(_MASK)
        lo = mask.find(1)
        if lo >= 0:
            hi = mask.rfind(1)
            if y < min_y:
                min_y = y
            max_y = y
            if lo < min_x:
                min_x = lo
            if hi > max_x:
                max_x = hi
        prev = cur

    if max_x < 0:
        return None                                          # fully opaque
    return (min_x, min_y, max_x - min_x + 1, max_y - min_y + 1, width, height)


def measure_hole(png: Path) -> dict | None:
    """The transparent rectangle of a bezel, in its own pixel space.

    Returns `{"x","y","w","h","frame_w","frame_h"}` or None. The frame size
    travels with the hole because a pack made for 1280x960 is not wrong, it is
    just not 1920x1080 — the consumer scales, and cannot without knowing what
    the numbers were measured against.
    """
    try:
        st = png.stat()
    except OSError:
        return None
    # size as well as mtime: an rsync or an unpack can land a different file on
    # the same second, and a bezel measured as its predecessor is a frame over
    # the wrong part of the screen with nothing on screen to explain it.
    sig = f"{st.st_mtime_ns}:{st.st_size}"
    key = str(png)

    hit = _memo.get(key) or _cache().get(key)
    if hit and hit.get("sig") == sig:
        return hit["hole"]

    box = _alpha_bbox(png)
    hole = None
    if box:
        x, y, w, h, fw, fh = box
        # A hole this large is a bezel that decorates nothing — see the
        # constant. Reported as "no hole" so the caller keeps the declared one.
        if (w * h) / (fw * fh) <= _HOLE_MAX_COVERAGE:
            hole = {"x": x, "y": y, "w": w, "h": h, "frame_w": fw, "frame_h": fh}

    entry = {"sig": sig, "hole": hole}
    _memo[key] = entry
    _cache()[key] = entry
    _save_cache()
    return hole


# ── Cache ────────────────────────────────────────────────────────────────────
#
# On disk as well as in memory: a bezel costs 0.4 s to measure and the box
# restarts its backend on every update, so an in-memory cache alone would spend
# that again on the first launch of every game after each reboot.

def _cache_path() -> Path:
    return config_dir() / _CACHE_FILE


def _cache() -> dict[str, dict]:
    global _disk
    if _disk is None:
        try:
            loaded = json.loads(_cache_path().read_text())
            _disk = loaded if isinstance(loaded, dict) else {}
        except (OSError, json.JSONDecodeError):
            _disk = {}
    return _disk


def _save_cache() -> None:
    """Best effort. A cache that cannot be written must not stop a game."""
    try:
        p = _cache_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(_cache()))
        tmp.replace(p)
    except OSError as e:
        log.debug("bezels: hole cache not written — %s", e)


def forget() -> None:
    """Drop both caches. For tests, and for the roots moving under us."""
    global _disk
    _memo.clear()
    _disk = None


# ── What the UI and Electron ask for ─────────────────────────────────────────

def describe(system_id: str, rom_name: str | None = None,
             declared: dict | None = None) -> dict:
    """Everything one launch needs to decide what to draw.

        {"source": "game"|"system"|"declared"|"none",
         "asset": "/assets/overlays/…" | None,
         "hole": {"x","y","w","h","frame_w","frame_h"} | None}

    `source` is not decoration. "none" means draw nothing at all, and the
    difference between it and "declared" is the difference between a game shown
    whole and a game with black bars nobody asked for.
    """
    png, level = resolve(system_id, rom_name)

    if png is not None:
        hole = measure_hole(png)
        if hole is not None:
            return {"source": level, "asset": _asset_url(png), "hole": hole}
        # A PNG that will not measure is still a PNG the overlay can draw. It
        # is the hole that falls back, not the image — dropping the asset here
        # would hide a bezel that renders perfectly well over a game.
        if declared:
            return {"source": level, "asset": _asset_url(png),
                    "hole": _with_frame(declared)}
        return {"source": level, "asset": _asset_url(png), "hole": None}

    if declared:
        return {"source": "declared", "asset": None, "hole": _with_frame(declared)}
    return {"source": "none", "asset": None, "hole": None}


def _with_frame(declared: dict) -> dict:
    """A declared hole, given the frame it was always implicitly measured in.

    `config/overlays.json` holes are written against the 1920x1080 the
    `window_rect` of the same entry forces, and never said so. Saying it here
    means the consumer has one shape to handle instead of two.
    """
    out = {k: int(declared[k]) for k in ("x", "y", "w", "h") if k in declared}
    out.setdefault("frame_w", 1920)
    out.setdefault("frame_h", 1080)
    return out


def _asset_url(png: Path) -> str:
    """The URL `main.py` already serves this file at.

    `overlays_dir()` is mounted at /assets/overlays (main.py), so the URL is
    the path relative to that mount and not a second notion of where bezels
    live.
    """
    try:
        rel = png.relative_to(overlays_dir())
    except ValueError:
        return f"/assets/overlays/{png.name}"
    return "/assets/overlays/" + "/".join(rel.parts)
