"""What a media type is called, whichever source answered.

Split out of gamescrape.py. Pure data and the two lookups over it: every media
type ScreenScraper can return, mapped to a stable slug shared with LaunchBox,
plus the category and kind a frontend needs to group them.

One vocabulary for two sources is the whole point — the UI groups media the
same way whether the LaunchBox tier or the ScreenScraper tier answered, and
neither source's naming leaks into the interface.

Imported by gamescrape.py, which re-exports every public name below — no caller
outside this package changes an import.
"""
from __future__ import annotations

import re

# ── ScreenScraper media types ────────────────────────────────────────────────
#
# Every media type ScreenScraper can return, mapped to a stable slug shared with
# LaunchBox (see TYPE_ALIASES), plus the category and kind a frontend needs to
# group them without hardcoding a list of its own.
#
# The reference is `mediasJeuListe.php`, which declares 50 types with their short
# name, category, kind and file format. It is NOT exhaustive: real `jeuInfos`
# responses also carry `pictoliste`, `pictomonochrome`, `pictocouleur` and
# `background`, absent from that endpoint. Hence a baked table (works offline, no
# extra request) AND a slug derived automatically for anything unknown — a 55th
# type added tomorrow still gets a sane, stable name with no code change.
#
# Regenerate the reference with:  gamescrape.py --ss-media-types
#
# (slug, category, kind)
SS_MEDIA: dict[str, tuple[str, str, str]] = {
    # Box art
    "box-2D":            ("box-front",             "box",        "image"),
    "box-2D-back":       ("box-back",              "box",        "image"),
    "box-2D-side":       ("box-spine",             "box",        "image"),
    "box-3D":            ("box-3d",                "box",        "image"),
    "box-texture":       ("box-texture",           "box",        "image"),
    "box-scan":          ("box-scan",              "box",        "image"),
    # Cartridge / disc. ScreenScraper has NO 3D support art: the table used to
    # map a `support-3D` that exists neither in the reference nor in any
    # response — a dead entry promising a media that never arrives.
    "support-2D":        ("cart-front",            "cart",       "image"),
    "support-texture":   ("cart-texture",          "cart",       "image"),
    "support-scan":      ("cart-scan",             "cart",       "image"),
    # Logos, cut out on transparent background
    "wheel":             ("clear-logo",            "logo",       "image"),
    "wheel-hd":          ("clear-logo-hd",         "logo",       "image"),
    "wheel-carbon":      ("clear-logo-carbon",     "logo",       "image"),
    "wheel-steel":       ("clear-logo-steel",      "logo",       "image"),
    "wheel-tarcisios":   ("clear-logo-tarcisio",   "logo",       "image"),
    # Screenshots
    "ss":                ("screenshot-gameplay",   "screenshot", "image"),
    "sstitle":           ("screenshot-game-title", "screenshot", "image"),
    # Ready-made compositions (box + screenshot + logo), built for grid views
    "mixrbv1":           ("mix-rbv1",              "mix",        "image"),
    "mixrbv2":           ("mix-rbv2",              "mix",        "image"),
    # Marquees and headers
    "marquee":           ("arcade-marquee",        "marquee",    "image"),
    "screenmarquee":     ("screen-marquee",        "marquee",    "image"),
    "screenmarqueesmall": ("screen-marquee-small", "marquee",    "image"),
    # Other artwork
    "fanart":            ("fanart-background",     "artwork",    "image"),
    "background":        ("background",            "artwork",    "image"),
    "steamgrid":         ("square",                "artwork",    "image"),
    "figurine":          ("figurine",              "artwork",    "image"),
    "flyer":             ("flyer",                 "artwork",    "image"),
    "maps":              ("maps",                  "artwork",    "image"),
    # Bezels and overlays, for filling the sides of a 4:3 game on a 16:9 screen
    "bezel-16-9":        ("bezel",                 "bezel",      "image"),
    "bezel-16-9-v":      ("bezel-16-9-vertical",   "bezel",      "image"),
    "bezel-16-9-cocktail": ("bezel-16-9-cocktail", "bezel",      "image"),
    "bezel-4-3":         ("bezel-4-3",             "bezel",      "image"),
    "bezel-4-3-v":       ("bezel-4-3-vertical",    "bezel",      "image"),
    "bezel-4-3-cocktail": ("bezel-4-3-cocktail",   "bezel",      "image"),
    "overlay":           ("overlay",               "bezel",      "image"),
    # Small pictograms, for dense list views
    "pictoliste":        ("icon-list",             "icon",       "image"),
    "pictocouleur":      ("icon-color",            "icon",       "image"),
    "pictomonochrome":   ("icon-mono",             "icon",       "image"),
    # Video. `video-normalized` used to collapse onto `video`, so whichever
    # arrived last silently won — they are distinct now, and the normalized one
    # is the better default (consistent format and loudness).
    "video":             ("video",                 "video",      "video"),
    "video-normalized":  ("video-normalized",      "video",      "video"),
    # Documents and themes
    "manuel":            ("manual",                "document",   "document"),
    "themehs":           ("theme",                 "theme",      "archive"),
    "themehb":           ("theme-hyperbat",        "theme",      "archive"),
    # Virtual pinball cabinets. Useless on a console frontend, but they arrive
    # anyway and deserve stable names rather than raw ScreenScraper ones.
    # "fronton" is the backglass in English pinball terms.
    "ssdmd":             ("pinball-dmd",                  "pinball", "image"),
    "sstable":           ("pinball-table",                "pinball", "image"),
    "sstopper":          ("pinball-topper",               "pinball", "image"),
    "ssfronton1-1":      ("pinball-backglass-1-1",        "pinball", "image"),
    "ssfronton4-3":      ("pinball-backglass-4-3",        "pinball", "image"),
    "ssfronton16-9":     ("pinball-backglass-16-9",       "pinball", "image"),
    "videodmd":          ("pinball-dmd-video",            "pinball", "video"),
    "videotable":        ("pinball-table-video",          "pinball", "video"),
    "videotable4k":      ("pinball-table-video-4k",       "pinball", "video"),
    "videotopper":       ("pinball-topper-video",         "pinball", "video"),
    "videofronton4-3":   ("pinball-backglass-video-4-3",  "pinball", "video"),
    "videofronton16-9":  ("pinball-backglass-video-16-9", "pinball", "video"),
}

# Kept for the existing call sites: slug lookup alone.
SS_TO_SLUG: dict[str, str] = {ss: v[0] for ss, v in SS_MEDIA.items()}


def ss_media_slug(ss_type: str) -> str:
    """Stable slug for a ScreenScraper media type, known or not.

    An unknown type is not dropped — it is lowercased and stripped of anything
    that is not a letter, a digit or a dash, so it stays usable as a filename
    and as a JSON key. Returning the raw name instead let `Screenshot Titre` or
    a type with a slash through into a path.
    """
    known = SS_MEDIA.get(ss_type)
    if known:
        return known[0]
    slug = re.sub(r"[^a-z0-9]+", "-", (ss_type or "").lower()).strip("-")
    return slug or "unknown"


def ss_media_info(ss_type: str) -> tuple[str, str, str]:
    """(slug, category, kind) — `unknown` category for a type we do not know."""
    return SS_MEDIA.get(ss_type) or (ss_media_slug(ss_type), "unknown", "image")


# LaunchBox categories are derived by rule rather than listed one by one: its 33
# type names are already descriptive and prefixed consistently, so a rule also
# covers the ones it adds later. Same vocabulary as SS_MEDIA, so the frontend
# groups media the same way whichever tier answered.
_LB_CATEGORY_RULES: tuple[tuple[str, str], ...] = (
    ("arcade-marquee", "marquee"),
    ("arcade-", "arcade"),
    ("clear-logo", "logo"),
    ("screenshot", "screenshot"),
    ("icon", "icon"),
)


def lb_media_info(slug: str) -> tuple[str, str]:
    """(category, kind) for a LaunchBox image type. Its dump is images only.

    Note that LaunchBox DOES have `cart-3d` — the disc or cartridge in
    perspective, 2 947 images. ScreenScraper has no equivalent, which is why the
    SS table pointed at a `support-3D` that never existed.
    """
    for prefix, category in _LB_CATEGORY_RULES:
        if prefix in slug:
            return category, "image"
    if "box" in slug:
        return "box", "image"
    if "cart" in slug or "disc" in slug:
        return "cart", "image"
    return "artwork", "image"
