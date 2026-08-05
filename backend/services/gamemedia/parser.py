"""The ROM-name vocabulary, and the parser that reads it.

Split out of gamescrape.py, which had grown to 1 308 lines. This half is the
one with no dependencies at all: it turns a filename into a structured
description and normalises a title for comparison, and it touches no database,
no network and no credentials. Everything else in the package depends on it and
it depends on nothing.

The tables travel with the parser because they ARE the parser: `parse_rom`
reads EXT_MAP, REGIONS, LANGS and TAG_RE, `normalize` reads TAG_RE and
ARTICLES, and PLATFORMS/REGION_PREF/TYPE_ALIASES are the same vocabulary seen
from the LaunchBox side. Splitting a table from the function that reads it is
how a list ends up maintained in two places.

Imported by gamescrape.py, which re-exports every name below — no caller
outside this package changes an import.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

# ── Consoles: short key → LaunchBox platform name ───────────────────────────
PLATFORMS: dict[str, str] = {
    "nds": "Nintendo DS", "3ds": "Nintendo 3DS", "gba": "Nintendo Game Boy Advance",
    "gbc": "Nintendo Game Boy Color", "gb": "Nintendo Game Boy",
    "nes": "Nintendo Entertainment System",
    "snes": "Super Nintendo Entertainment System", "n64": "Nintendo 64",
    "gamecube": "Nintendo GameCube", "wii": "Nintendo Wii", "wiiu": "Nintendo Wii U",
    "switch": "Nintendo Switch", "virtualboy": "Nintendo Virtual Boy",
    "psx": "Sony Playstation", "ps2": "Sony Playstation 2",
    "ps3": "Sony Playstation 3", "ps4": "Sony Playstation 4",
    "psp": "Sony PSP", "vita": "Sony Playstation Vita",
    "megadrive": "Sega Genesis", "mastersys": "Sega Master System",
    "gamegear": "Sega Game Gear", "saturn": "Sega Saturn",
    "dreamcast": "Sega Dreamcast", "segacd": "Sega CD",
    "xbox": "Microsoft Xbox", "x360": "Microsoft Xbox 360",
    "xone": "Microsoft Xbox One", "arcade": "Arcade",
}

# Extension → candidate consoles, tried in order.
EXT_MAP: dict[str, list[str]] = {
    "nds": ["nds"], "ds": ["nds"], "dsi": ["nds"],
    "3ds": ["3ds"], "cia": ["3ds"], "cci": ["3ds"],
    "gba": ["gba"], "agb": ["gba"], "gbc": ["gbc"], "gb": ["gb"],
    "nes": ["nes"], "fds": ["nes"], "unf": ["nes"],
    "sfc": ["snes"], "smc": ["snes"], "snes": ["snes"],
    "n64": ["n64"], "z64": ["n64"], "v64": ["n64"],
    "gcm": ["gamecube"], "gcz": ["gamecube"],
    "rvz": ["wii", "gamecube"], "wbfs": ["wii"], "wia": ["wii", "gamecube"],
    "wud": ["wiiu"], "wux": ["wiiu"], "rpx": ["wiiu"],
    "xci": ["switch"], "nsp": ["switch"],
    "cue": ["psx"], "pbp": ["psx"], "ecm": ["psx"],
    "chd": ["psx", "ps2", "saturn", "dreamcast"],
    "iso": ["ps2", "psp", "gamecube", "wii", "psx"],
    "bin": ["psx", "megadrive"],
    "cso": ["psp"], "pkg": ["ps3"], "vpk": ["vita"],
    "md": ["megadrive"], "gen": ["megadrive"], "smd": ["megadrive"],
    "sms": ["mastersys"], "gg": ["gamegear"],
    "gdi": ["dreamcast"], "cdi": ["dreamcast"],
    "zip": ["arcade"], "7z": ["arcade"],
}

# --types shortcuts → slug shared by both sources (see slug()).
TYPE_ALIASES: dict[str, str] = {
    "3d": "box-3d", "box3d": "box-3d",
    "box": "box-front", "boxart": "box-front", "cover": "box-front",
    "front": "box-front", "back": "box-back", "spine": "box-spine",
    "cart": "cart-front", "cart3d": "cart-3d", "disc": "disc",
    "logo": "clear-logo", "clearlogo": "clear-logo",
    "snap": "screenshot-gameplay", "screenshot": "screenshot-gameplay",
    "gameplay": "screenshot-gameplay", "title": "screenshot-game-title",
    "gameover": "screenshot-game-over", "select": "screenshot-game-select",
    "fanart": "fanart-background", "background": "fanart-background",
    "banner": "banner", "poster": "poster", "square": "square",
    "marquee": "arcade-marquee", "cabinet": "arcade-cabinet",
    "flyer": "advertisement-flyer-front", "video": "video",
}

# ROM region tag → LaunchBox region preference order.
REGION_PREF: dict[str | None, list[str]] = {
    "eu": ["Europe", "United Kingdom", "France", "Germany", "Spain", "Italy",
           "World", "North America", "United States", "Japan"],
    "us": ["North America", "United States", "World", "Europe",
           "United Kingdom", "Japan"],
    "jp": ["Japan", "World", "North America", "United States", "Europe"],
    "wor": ["World", "Europe", "North America", "United States", "Japan"],
    None: ["World", "Europe", "North America", "United States", "Japan"],
}

REGIONS = {
    "europe": "eu", "eur": "eu", "e": "eu", "pal": "eu", "france": "eu",
    "fr": "eu", "germany": "eu", "spain": "eu", "italy": "eu", "uk": "eu",
    "usa": "us", "us": "us", "ntsc": "us", "canada": "us",
    "japan": "jp", "jpn": "jp", "j": "jp",
    "world": "wor", "w": "wor",
    "korea": "kr", "china": "cn", "australia": "eu", "brazil": "us",
}
LANGS = {"en", "fr", "de", "es", "it", "ja", "jp", "nl", "pt", "sv", "no",
         "da", "fi", "zh", "ko", "ru", "pl"}
TAG_RE = re.compile(r"[\(\[]([^\)\]]*)[\)\]]")
ARTICLES = ("the", "a", "an", "le", "la", "les", "der", "die", "das", "el")


# ── ROM filename parser ─────────────────────────────────────────────────────

def parse_rom(raw: str) -> dict:
    """Break down a ROM filename. The file need not exist."""
    name = Path(raw).name
    ext = ""
    for _ in range(2):                      # handles "game.nds.zip"
        stem, dot, suffix = name.rpartition(".")
        if not dot or len(suffix) > 5 or not suffix.isalnum():
            break
        low = suffix.lower()
        if not ext or low not in ("zip", "7z", "rar"):
            ext = low
        name = stem
        if low not in ("zip", "7z", "rar"):
            break

    tags = [t.strip() for t in TAG_RE.findall(name)]
    title = TAG_RE.sub(" ", name)

    if " " not in title.strip():            # "fifa-19" → "fifa 19"
        title = re.sub(r"[-_.]+", " ", title)
    else:
        title = title.replace("_", " ")
    title = re.sub(r"\s+", " ", title).strip(" -_.")

    region, langs, disc, revision, flags = None, [], None, None, []
    for tag in tags:
        parts = [p.strip() for p in re.split(r"[,+]", tag) if p.strip()]
        low = tag.lower().strip()
        if m := re.fullmatch(r"(?:disc|disk|cd)\s*(\d+)", low):
            disc = int(m.group(1))
        elif m := re.fullmatch(r"(?:rev|v)\s*([\w.]+)", low):
            revision = m.group(1)
        elif not region and low in REGIONS:
            region = REGIONS[low]
        elif parts and all(p.lower() in LANGS for p in parts):
            langs += [p.lower() for p in parts]
        elif not region and (hit := next((REGIONS[p.lower()] for p in parts
                                          if p.lower() in REGIONS), None)):
            region = hit
        elif low:
            flags.append(tag)

    return {"source": raw, "title": title, "ext": ext, "region": region,
            "languages": langs, "disc": disc, "revision": revision,
            "flags": flags, "tags": tags, "systems": EXT_MAP.get(ext, [])}


def normalize(s: str) -> str:
    """Comparable form: no accents, no punctuation, leading article."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = TAG_RE.sub(" ", s)
    # "Zelda, The - Twilight Princess" → "the zelda - twilight princess":
    # the article moves in front of the segment it follows, not the whole tail.
    s = re.sub(rf"^(.*?),\s*({'|'.join(ARTICLES)})\b", r"\2 \1", s, count=1)
    s = re.sub(r"\b(\d+)\b", lambda m: str(int(m.group(1))), s)
    s = re.sub(r"[^a-z0-9]+", "", s)
    for art in ("the", "a", "an"):          # article ignored on both sides
        if s.startswith(art):
            return s[len(art):]
    return s
