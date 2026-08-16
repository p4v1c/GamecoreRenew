"""Re-encode cover art as lossless WebP — same pixels, fewer bytes, faster decode.

85 of the 89 covers on the reference box are PNG, which is the wrong container
for a photographic image. Lossless WebP is **identical pixel for pixel** — this
is not a quality trade, it is the same picture in a better wrapper — and the
renderer, which is where the boot time actually goes, decodes it measurably
faster.

Measured here, on those 89 real files (Pillow 12.3, libwebp, method=4):

    85 PNG   42.6 MB → 29.6 MB   (-30.5 %)   decode 605 ms → 421 ms  (-30 %)
     4 JPEG   3.4 MB →  9.9 MB   (+197 %)    decode  64 ms → 149 ms  (+134 %)

Which decides the three questions this raises:

**JPEG is left alone.** Not a hedge — a measurement. Lossless WebP has to
reproduce the JPEG's compression artefacts exactly, so it spends bytes encoding
noise the original threw away: the four files grow by 128 % to 382 % and take
two to four times longer to decode. Converting them would make the boot worse.
`_SOURCE_SUFFIXES` is therefore PNG only.

**Every result is checked before it is kept.** `_is_worth_it` drops any encode
that came out larger, so a PNG that is really a re-wrapped photograph keeps its
original container instead of inheriting the JPEG failure above. On today's
library that guard never fires — all 85 shrink — which is exactly when it is
worth writing, because nothing will tell you the day a new cover trips it.

**Nothing is replaced until it is proved identical.** `_same_pixels` decodes
the WebP back and compares it to the source in RGBA. Lossless is lossless by
definition; this is about a library bug or a mode conversion going wrong, on a
box where a corrupted cover would be a visible defect with no explanation. It
costs one extra decode on a path that has just finished a network fetch.

`method=4`, not 6. Measured on 20 of the real covers: method=6 costs 4.3 s per
image against 268 ms — sixteen times the CPU — to save a further 2 % of bytes.
On a box that is also drawing a UI, that trade is not worth making.

Pillow is imported optionally. It is the only new dependency this feature
needs, and a box that somehow lacks it must degrade to "covers stay PNG"
rather than fail to serve a library.
"""
import logging
from pathlib import Path

log = logging.getLogger(__name__)

try:                                    # optional — see the module docstring
    from PIL import Image
except ImportError:                     # pragma: no cover - depends on the box
    Image = None

# PNG only. The JPEG measurement above is the reason, and it is not close.
_SOURCE_SUFFIXES = (".png",)

_TARGET_SUFFIX = ".webp"

# Encoder settings. `lossless` is the whole point; `exact` keeps the RGB values
# under fully transparent pixels, which is what makes the round-trip check below
# an equality rather than an approximation.
_SAVE = {"lossless": True, "quality": 100, "method": 4, "exact": True}


def available() -> bool:
    """False when Pillow is not installed — every caller then keeps the PNG."""
    return Image is not None


def _same_pixels(a, b) -> bool:
    """True when two decoded images carry the same pixels.

    Compared in RGBA so a palette source and its RGBA round-trip are judged on
    what they draw rather than on how they store it. Three of the covers here
    are palette-mode PNGs.
    """
    if a.size != b.size:
        return False
    return a.convert("RGBA").tobytes() == b.convert("RGBA").tobytes()


def _is_worth_it(src: Path, dest: Path) -> bool:
    try:
        return dest.stat().st_size < src.stat().st_size
    except OSError:
        return False


def to_webp(path: Path) -> Path:
    """Re-encode one cover in place, returning the path to use.

    Returns `path` unchanged whenever anything at all is not right: Pillow
    missing, wrong source format, larger result, pixels that did not survive,
    an unreadable file. The caller's cover is never worse off for having asked
    — the worst case is that it stays a PNG.

    The source is unlinked only after the replacement is on disk and verified,
    so an interruption leaves both files rather than neither.
    """
    if Image is None or path.suffix.lower() not in _SOURCE_SUFFIXES:
        return path

    dest = path.with_suffix(_TARGET_SUFFIX)
    try:
        with Image.open(path) as im:
            im.load()
            # A PNG may carry a colour profile — 12 of the 85 here do. Dropping
            # it would shift the colours in the browser, which is precisely the
            # "nothing degraded" promise this conversion is making.
            icc = im.info.get("icc_profile")
            im.save(dest, "WEBP", icc_profile=icc, **_SAVE)

        if not _is_worth_it(path, dest):
            dest.unlink(missing_ok=True)
            log.debug("cover_encode: %s is smaller as it is — kept", path.name)
            return path

        with Image.open(path) as before, Image.open(dest) as after:
            before.load()
            after.load()
            if not _same_pixels(before, after):
                dest.unlink(missing_ok=True)
                log.warning("cover_encode: %s did not survive the round trip — "
                            "kept as it is", path.name)
                return path
    except Exception:
        dest.unlink(missing_ok=True)
        log.debug("cover_encode: could not re-encode %s", path.name, exc_info=True)
        return path

    path.unlink(missing_ok=True)
    return dest


def migrate(covers_root: Path, *, should_continue=None) -> tuple[int, int]:
    """Re-encode the covers already on disk. Returns (converted, bytes saved).

    This exists because `emu/` is excluded from the OTA rsync, so conversion at
    write time — which is where every *new* cover goes through — will never
    reach a single one of the 89 files an installed box already has. Without
    this pass the owner of the reference box would get none of the measured
    gain, since their library is already scraped.

    Idempotent and cheap to repeat: a system directory whose covers are already
    WebP costs one `iterdir` and nothing else. Runs in the background, and
    `should_continue` lets the caller stop between files — a player starting a
    game must not be sharing the CPU with a re-encode.
    """
    if Image is None or not covers_root.is_dir():
        return 0, 0

    converted = 0
    saved = 0
    for path in sorted(covers_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in _SOURCE_SUFFIXES:
            continue
        if should_continue is not None and not should_continue():
            log.info("cover_encode: migration paused after %d file(s)", converted)
            break
        try:
            before = path.stat().st_size
        except OSError:
            continue
        result = to_webp(path)
        if result != path:
            converted += 1
            try:
                saved += before - result.stat().st_size
            except OSError:
                pass

    if converted:
        log.info("cover_encode: %d cover(s) re-encoded as lossless WebP, %.1f MB saved",
                 converted, saved / (1024 * 1024))
    return converted, saved
