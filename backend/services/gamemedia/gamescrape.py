#!/usr/bin/env python3
"""gamescrape — every image of a game, from its ROM filename.

    python3 gamescrape.py "fifa-19-(europe)(fr,en).nds" -o output

Two sources, picked by --source (auto by default):

  LaunchBox      the official Metadata.zip dump, downloaded once then indexed
                 into SQLite under ~/.cache/gamescrape — everything is instant
                 and offline from then on. No credentials. Matches by NAME: 92 %
                 hit rate measured over 1950 ROMs, 90 % of them exact.
  ScreenScraper  matches by file HASH (CRC/MD5/SHA1): when the ROM is on disk,
                 the game found is certain even if the file is misnamed. Needs
                 DEVELOPER credentials (devid/devpassword) — see the
                 ScreenScraper section below; without them the script silently
                 fell back to LaunchBox.

Media available: 3D box, box front/back/spine, cartridge, disc, clear logo,
fanart, banner, screenshots (gameplay, title screen, game over…), flyers, arcade
marquee and cabinet, poster…

The filename is enough, the ROM need not exist: the parser strips separators,
region and language tags, disc number and revision, then infers the console from
the extension.

No dependencies: standard library only.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sqlite3
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
import zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

METADATA_URL = "https://gamesdb.launchbox-app.com/Metadata.zip"
IMAGE_CDN = "https://images.launchbox-app.com/"
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "gamescrape"
DB_PATH = CACHE_DIR / "launchbox.sqlite"
MAX_AGE_DAYS = 30
# SQLite schema version. Bump it whenever a column moves: a database built by
# an earlier version would fail every query with "no such column", and an
# unusable index must be rebuilt rather than endured.
SCHEMA_VERSION = 2
TIMEOUT = 60
UA = "gamescrape/2.0"

# --json must print JSON and NOTHING else on stdout. Human-readable lines go to
# stderr in that mode: without this, `--json | jq` broke because the
# "Title / Console" header and the download progress landed in the middle.
_JSON_MODE = False


def out(*a, **kw) -> None:
    print(*a, file=sys.stderr if _JSON_MODE else sys.stdout, **kw)

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


# ── Local database: download and index the LaunchBox dump ───────────────────

def _download(url: str, dest: Path, label: str) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        total = int(r.headers.get("content-length") or 0)
        done = 0
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
                done += len(chunk)
                if total and sys.stderr.isatty():
                    print(f"\r  {label} {done * 100 // total}% "
                          f"({done // 1_000_000}/{total // 1_000_000} MB)",
                          end="", file=sys.stderr)
        if total and sys.stderr.isatty():
            print(file=sys.stderr)


# The `games` columns other than the four used for matching. They are read ONE
# row at a time, once the game is chosen: putting them in the search SELECT
# would push 100 MB of synopsis through Python on every fallback to the full
# scan.
LB_DETAIL_COLS = ("overview", "developer", "publisher", "genres", "players",
                  "rating", "rating_count", "esrb", "released", "coop",
                  "video_url", "wiki_url")


def _lb_text(el: ET.Element, tag: str) -> str:
    return (el.findtext(tag) or "").strip()


def build_index(verbose: bool = False) -> None:
    """Download Metadata.zip and turn it into a local SQLite database."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = CACHE_DIR / "Metadata.zip"
    tmp_db = DB_PATH.with_suffix(".tmp")
    tmp_db.unlink(missing_ok=True)

    print("LaunchBox database: downloading the official dump…", file=sys.stderr)
    _download(METADATA_URL, zip_path, "dump")

    print("  indexing (one to two minutes, once)…", file=sys.stderr)
    db = sqlite3.connect(tmp_db)
    # `overview` is a BLOB: the 172,550 synopses are 103 MB of raw text, which
    # zlib brings down to less than half. One row is decompressed per resolve,
    # so the cost is invisible; uncompressed, the index went from 139 to 245 MB
    # on a box whose disk is meant for games.
    db.executescript("""
        PRAGMA journal_mode = OFF;
        PRAGMA synchronous = OFF;
        CREATE TABLE games (id INTEGER PRIMARY KEY, name TEXT, norm TEXT,
                            platform TEXT, year TEXT,
                            overview BLOB, developer TEXT, publisher TEXT,
                            genres TEXT, players TEXT, rating REAL,
                            rating_count INTEGER, esrb TEXT, released TEXT,
                            coop INTEGER, video_url TEXT, wiki_url TEXT);
        CREATE TABLE alts (gid INTEGER, norm TEXT);
        CREATE TABLE images (gid INTEGER, type TEXT, region TEXT, filename TEXT);
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
    """)
    game_sql = "INSERT INTO games VALUES (" + ",".join("?" * 17) + ")"

    games, alts, images = [], [], []
    counts = {"games": 0, "images": 0, "overviews": 0, "raw": 0, "packed": 0}
    with zipfile.ZipFile(zip_path) as z, z.open("Metadata.xml") as f:
        for _, el in ET.iterparse(f, events=("end",)):
            if el.tag == "Game":
                gid = el.findtext("DatabaseID")
                name = el.findtext("Name") or ""
                if gid and name:
                    # ReleaseDate is a full datetime
                    # ("1997-09-30T00:00:00-07:00"): keep the local date, the
                    # only format the manifest documents and the one
                    # ScreenScraper already returns.
                    released = _lb_text(el, "ReleaseDate")[:10]
                    year = el.findtext("ReleaseYear") or released[:4]
                    over = _lb_text(el, "Overview")
                    blob = None
                    if over:
                        raw = over.encode("utf-8")
                        blob = zlib.compress(raw, 6)
                        counts["overviews"] += 1
                        counts["raw"] += len(raw)
                        counts["packed"] += len(blob)
                    # CommunityRating is out of 5 (measured: 0.50 to 5.00).
                    # Store the 0–1 ratio, the only scale comparable with
                    # ScreenScraper's out of 20 — two raw "4"s do not mean the
                    # same thing.
                    try:
                        rating = round(float(el.findtext("CommunityRating")) / 5, 4)
                    except (TypeError, ValueError):
                        rating = None
                    try:
                        votes = int(el.findtext("CommunityRatingCount"))
                    except (TypeError, ValueError):
                        votes = None
                    games.append((
                        int(gid), name, normalize(name),
                        el.findtext("Platform") or "", year,
                        blob, _lb_text(el, "Developer"), _lb_text(el, "Publisher"),
                        # separator measured on the dump: ";" and nothing else
                        "; ".join(g.strip() for g in _lb_text(el, "Genres").split(";")
                                  if g.strip()),
                        _lb_text(el, "MaxPlayers"), rating, votes,
                        _lb_text(el, "ESRB"), released,
                        1 if _lb_text(el, "Cooperative").lower() == "true" else 0,
                        _lb_text(el, "VideoURL"), _lb_text(el, "WikipediaURL")))
                    counts["games"] += 1
                el.clear()
            elif el.tag == "GameImage":
                gid, fn = el.findtext("DatabaseID"), el.findtext("FileName")
                if gid and fn:
                    images.append((int(gid), el.findtext("Type") or "",
                                   el.findtext("Region") or "", fn))
                    counts["images"] += 1
                el.clear()
            elif el.tag == "GameAlternateName":
                gid, alt = el.findtext("DatabaseID"), el.findtext("AlternateName")
                if gid and alt:
                    alts.append((int(gid), normalize(alt)))
                el.clear()

            if len(games) >= 5000:
                db.executemany(game_sql, games); games.clear()
            if len(images) >= 50000:
                db.executemany("INSERT INTO images VALUES (?,?,?,?)", images); images.clear()
            if len(alts) >= 20000:
                db.executemany("INSERT INTO alts VALUES (?,?)", alts); alts.clear()

    db.executemany(game_sql, games)
    db.executemany("INSERT INTO images VALUES (?,?,?,?)", images)
    db.executemany("INSERT INTO alts VALUES (?,?)", alts)
    db.executescript("""
        CREATE INDEX idx_games_norm ON games(norm);
        CREATE INDEX idx_games_plat ON games(platform);
        CREATE INDEX idx_alts_norm ON alts(norm);
        CREATE INDEX idx_images_gid ON images(gid);
    """)
    db.executemany("INSERT INTO meta VALUES (?,?)", [
        ("built_at", str(int(time.time()))),
        ("source", METADATA_URL),
        ("schema", str(SCHEMA_VERSION)),
    ])
    db.commit()
    db.close()
    tmp_db.replace(DB_PATH)
    zip_path.unlink(missing_ok=True)        # dump no longer needed, 106 MB back
    gain = (1 - counts["packed"] / counts["raw"]) * 100 if counts["raw"] else 0
    print(f"  ready: {counts['games']:,} games, {counts['images']:,} images, "
          f"{counts['overviews']:,} descriptions "
          f"({counts['raw'] / 1048576:.0f} MB of text → "
          f"{counts['packed'] / 1048576:.0f} MB, -{gain:.0f} %)",
          file=sys.stderr)
    print(f"  {DB_PATH} — {DB_PATH.stat().st_size / 1048576:.0f} MB", file=sys.stderr)


class IndexUnavailable(Exception):
    """The LaunchBox index is missing, unreadable, or of a stale schema."""


def _schema_of(db: sqlite3.Connection) -> int:
    try:
        row = db.execute("SELECT value FROM meta WHERE key='schema'").fetchone()
    except sqlite3.Error:
        return 0
    try:
        return int(row[0]) if row else 0
    except (TypeError, ValueError):
        return 0


def lb_index_ready() -> bool:
    """Index present AND usable. The file existing is not enough: a database
    built before the descriptions were added is still on disk and would fail
    every query."""
    if not DB_PATH.is_file():
        return False
    try:
        db = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    except sqlite3.Error:
        return False
    try:
        return _schema_of(db) == SCHEMA_VERSION
    finally:
        db.close()


def open_db(auto: bool = True) -> sqlite3.Connection:
    """Open the index, (re)building it when `auto`.

    `auto=False` raises IndexUnavailable instead of leaving the process: this
    call also comes from an HTTP handler, where a `sys.exit()` stopped the whole
    server — and SystemExit is not caught by `except Exception`.
    """
    stale = DB_PATH.exists() and not lb_index_ready()
    if not DB_PATH.exists() or stale:
        if not auto:
            raise IndexUnavailable(
                "LaunchBox index has a stale schema" if stale else
                "LaunchBox index is missing")
        if stale:
            print("LaunchBox index from an earlier version (no descriptions) "
                  "— rebuilding.", file=sys.stderr)
        build_index()
    db = sqlite3.connect(DB_PATH)
    row = db.execute("SELECT value FROM meta WHERE key='built_at'").fetchone()
    age = (time.time() - int(row[0])) / 86400 if row else 999
    if age > MAX_AGE_DAYS:
        print(f"(database is {age:.0f} days old — run `--refresh` to update it)",
              file=sys.stderr)
    return db


# ── Recherche ───────────────────────────────────────────────────────────────

ROMAN = {"ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8,
         "ix": 9, "x": 10, "xi": 11, "xii": 12, "xiii": 13}


def numbers_of(title: str) -> list[int]:
    """Episode numbers in a title, arabic and roman alike.
    "Choplifter III" and "Choplifter II" are not the same game; that is exactly
    the kind of gap text similarity finds negligible."""
    out = []
    for tok in re.split(r"[^a-z0-9]+", title.lower()):
        if tok.isdigit():
            out.append(int(tok))
        elif tok in ROMAN:
            out.append(ROMAN[tok])
    return out


def find_game(db: sqlite3.Connection, parsed: dict, platforms: list[str],
              cutoff: float) -> tuple[dict | None, float]:
    """Best LaunchBox game for this ROM, with its similarity score."""
    target = normalize(parsed["title"])
    if not target:
        return None, 0.0
    names = [PLATFORMS.get(p, p) for p in platforms]
    # A Virtual Console game is catalogued by LaunchBox under its ORIGINAL
    # console (Sonic & Knuckles = Genesis, not Wii), so search everywhere in
    # that case or nothing is ever found.
    if any("virtual console" in t.lower() or "console virtuelle" in t.lower()
           for t in parsed["tags"]):
        names = []

    def rows(where: str, args: tuple) -> list:
        # Four columns, deliberately: the "1=1" fallback scans all 185,000
        # rows, and joining the synopses would drag 100 MB of text through.
        sql = "SELECT id, name, platform, year FROM games WHERE " + where
        if names:
            sql += f" AND platform IN ({','.join('?' * len(names))})"
            args = args + tuple(names)
        return db.execute(sql, args).fetchall()

    # 1. exact title, 2. exact alternate name (Halo 1 → Halo: Combat Evolved)
    hits = rows("norm = ?", (target,))
    if not hits:
        hits = rows("id IN (SELECT gid FROM alts WHERE norm = ?)", (target,))
    if hits:
        return _pick(db, hits, parsed, names), 1.0

    # 3. Fuzzy: compare only against titles sharing a common prefix.
    prefix = target[:4]
    cands = rows("norm LIKE ?", (prefix + "%",)) if len(prefix) == 4 else []
    if not cands:
        cands = rows("1=1", ())
    want_nums = numbers_of(parsed["title"])
    best, best_score, rejected = None, 0.0, 0.0
    for row in cands:
        score = difflib.SequenceMatcher(None, target, normalize(row[1])).ratio()
        if score <= best_score:
            continue
        # A different episode number means another game, whatever the score.
        if numbers_of(row[1]) != want_nums:
            rejected = max(rejected, score)
            continue
        best, best_score = row, score
    if best and best_score >= cutoff:
        return _pick(db, [best], parsed, names), best_score
    return None, max(best_score, rejected)


def _pick(db: sqlite3.Connection, hits: list, parsed: dict,
          names: list[str]) -> dict:
    """Break a tie between same-named games: requested platform first."""
    def rank(row):
        return (0 if names and row[2] in names else 1, names.index(row[2])
                if names and row[2] in names else 0, row[0])
    row = sorted(hits, key=rank)[0]
    game = {"id": row[0], "name": row[1], "platform": row[2], "year": row[3]}
    game.update(game_details(db, row[0]))
    return game


def game_details(db: sqlite3.Connection, gid: int) -> dict:
    """The rest of the record: description, publisher, genres, rating…

    Read AFTER the game is chosen, never during the search. `overview` comes
    back compressed from disk; plain text is also accepted so a database built
    some other way stays readable.
    """
    sql = f"SELECT {', '.join(LB_DETAIL_COLS)} FROM games WHERE id = ?"
    try:
        row = db.execute(sql, (gid,)).fetchone()
    except sqlite3.Error:
        return {}
    if not row:
        return {}
    d = dict(zip(LB_DETAIL_COLS, row))
    blob = d.get("overview")
    if isinstance(blob, (bytes, bytearray)):
        try:
            d["overview"] = zlib.decompress(blob).decode("utf-8", "replace")
        except zlib.error:
            d["overview"] = blob.decode("utf-8", "replace")
    d["overview"] = d.get("overview") or ""
    d["genres"] = [g for g in (d.get("genres") or "").split(";") if g.strip()]
    d["genres"] = [g.strip() for g in d["genres"]]
    d["coop"] = bool(d.get("coop"))
    return d


def _show_details(game: dict) -> None:
    """The human-readable record, when there is more than a name to show."""
    line = [x for x in (
        " / ".join(x for x in (game.get("developer"), game.get("publisher")) if x),
        ", ".join(game.get("genres") or []),
        f"{game['players']} player(s)" if game.get("players") else "",
        f"rated {game['rating'] * 5:.1f}/5 ({game['rating_count']} votes)"
        if game.get("rating") and game.get("rating_count") else "",
    ) if x]
    if line:
        out("  " + "   ".join(line))
    over = game.get("overview") or ""
    if over:
        flat = " ".join(over.split())
        out(f"  {flat[:220]}{'…' if len(flat) > 220 else ''}")


def game_images(db: sqlite3.Connection, gid: int, parsed: dict,
                wanted: list[str] | None, every: bool) -> dict[str, list[str]]:
    """{LaunchBox type: [url…]}, best region first."""
    order = REGION_PREF.get(parsed["region"], REGION_PREF[None])
    by_type: dict[str, list[tuple[int, str]]] = {}
    for typ, region, filename in db.execute(
            "SELECT type, region, filename FROM images WHERE gid = ?", (gid,)):
        if wanted and slug(typ) not in wanted:
            continue
        rank = order.index(region) if region in order else len(order)
        by_type.setdefault(typ, []).append((rank, filename))

    out: dict[str, list[str]] = {}
    for typ, items in by_type.items():
        items.sort(key=lambda x: x[0])
        keep = items if every else items[:1]
        out[slug(typ)] = [IMAGE_CDN + urllib.parse.quote(fn) for _, fn in keep]
    return out


# ── ScreenScraper (alternate source, searches by file hash) ─────────────────
#
# Why it beats searching by name: ScreenScraper indexes ROMs by CRC32/MD5/SHA1.
# If the file is there, the match is CERTAIN — a misnamed, renamed or untagged
# file still lands on the right game, and LaunchBox's ~2 % of fuzzy matches go
# away.
#
# DEVELOPER credentials (devid/devpassword) are required, granted on request on
# the ScreenScraper forum; a plain member account is not enough and the API
# answers 403. The member account (optional) goes on top to raise the quotas.
#
#   export SCREENSCRAPER_DEV_ID=...        export SCREENSCRAPER_USER=p4v1c
#   export SCREENSCRAPER_DEV_PASSWORD=...  export SCREENSCRAPER_PASSWORD=...
#
# Check them once they arrive with:  gamescrape.py --ss-check
SS_API = "https://api.screenscraper.fr/api2/"
SS_SOFTNAME = "gamecore"
SS_HASH_LIMIT = 4 << 30          # above this, no hashing (compressed formats)

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
# ScreenScraper regions, in preference order given the ROM tag.
SS_REGION_PREF: dict[str | None, list[str]] = {
    "eu": ["eu", "fr", "uk", "de", "sp", "it", "wor", "us", "jp", "ss"],
    "us": ["us", "wor", "eu", "uk", "jp", "ss"],
    "jp": ["jp", "wor", "us", "eu", "ss"],
    "wor": ["wor", "eu", "us", "jp", "ss"],
    None: ["wor", "eu", "us", "jp", "ss"],
}
# ScreenScraper systemeid. Optional (hash search does without it); cross-check
# against the official list with --ss-systems.
SS_SYSTEM_IDS: dict[str, int] = {
    "nds": 15, "3ds": 17, "gba": 12, "gbc": 10, "gb": 9, "nes": 3, "snes": 4,
    "n64": 14, "gamecube": 13, "wii": 16, "wiiu": 18, "switch": 225,
    "psx": 57, "ps2": 58, "ps3": 59, "psp": 61, "vita": 62,
    "megadrive": 1, "mastersys": 2, "gamegear": 21, "saturn": 22,
    "dreamcast": 23, "segacd": 20, "xbox": 32, "x360": 33, "arcade": 75,
}


CRED_FILE = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) \
    / "gamescrape" / "credentials"


def _cred_file_values() -> dict[str, str]:
    """Read CRED_FILE (`KEY=value` per line), or {}.

    Environment variables alone meant re-exporting four secrets in every shell,
    which invariably ends up in a ~/.bashrc — so in backups and in shell
    history. A 0600 file is safer and more convenient. The environment still
    wins (useful in CI).
    """
    try:
        if CRED_FILE.stat().st_mode & 0o077:
            print(f"gamescrape: {CRED_FILE} is readable by other accounts — "
                  f"`chmod 600 {CRED_FILE}`", file=sys.stderr)
        raw = CRED_FILE.read_text(encoding="utf-8")
    except OSError:
        return {}
    vals = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        vals[k.strip()] = v.strip().strip("'\"")
    return vals


def ss_credentials() -> dict[str, str] | None:
    """ScreenScraper credentials, or None if dev access is not configured."""
    filev = _cred_file_values()

    def val(key: str) -> str:
        return (os.environ.get(key) or filev.get(key) or "").strip()

    devid, devpw = val("SCREENSCRAPER_DEV_ID"), val("SCREENSCRAPER_DEV_PASSWORD")
    if not (devid and devpw):
        return None
    creds = {"devid": devid, "devpassword": devpw, "softname": SS_SOFTNAME,
             "output": "json"}
    if user := val("SCREENSCRAPER_USER"):
        creds["ssid"] = user
        creds["sspassword"] = val("SCREENSCRAPER_PASSWORD")
    return creds


def ss_call(endpoint: str, params: dict, verbose: bool) -> dict | None:
    """API call. Returns None on failure — the caller falls back to LaunchBox."""
    url = SS_API + endpoint + "?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            body = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace").strip()[:120]
        # 403 credentials, 426 API closed, 429/430/431 quota reached
        if verbose or e.code in (426, 429, 430, 431):
            print(f"  screenscraper : HTTP {e.code} — {detail or e.reason}",
                  file=sys.stderr)
        return None
    except (urllib.error.URLError, OSError) as e:
        if verbose:
            print(f"  screenscraper : {e}", file=sys.stderr)
        return None
    try:
        return json.loads(body)
    except ValueError:
        if verbose:
            print(f"  screenscraper: unreadable response — {body[:120]}",
                  file=sys.stderr)
        return None


def file_hashes(path: Path, limit: int = SS_HASH_LIMIT) -> dict[str, str] | None:
    """CRC32 + MD5 + SHA1 in a single read, or None if the file is missing or
    over the limit."""
    import hashlib
    import zlib
    try:
        if not path.is_file() or path.stat().st_size > limit:
            return None
    except OSError:
        return None
    crc, md5, sha1 = 0, hashlib.md5(), hashlib.sha1()
    try:
        with open(path, "rb") as f:
            while chunk := f.read(1 << 22):
                crc = zlib.crc32(chunk, crc)
                md5.update(chunk)
                sha1.update(chunk)
    except OSError:
        return None
    return {"crc": f"{crc & 0xFFFFFFFF:08x}", "md5": md5.hexdigest(),
            "sha1": sha1.hexdigest(), "romtaille": str(path.stat().st_size)}


def ss_lookup(parsed: dict, systems: list[str], rom_path: Path | None,
              wanted: list[str] | None, every: bool,
              verbose: bool) -> tuple[dict, dict[str, list[str]]] | None:
    """(game, {type: [url…]}) via ScreenScraper, or None if unavailable."""
    creds = ss_credentials()
    if not creds:
        return None

    params = dict(creds, romtype="rom", romnom=Path(parsed["source"]).name)
    hashes = file_hashes(rom_path) if rom_path else None
    if hashes:
        params.update(hashes)                    # empreinte = certitude
        if verbose:
            print(f"  screenscraper: searching by hash "
                  f"(crc {hashes['crc']})", file=sys.stderr)
    for key in systems:
        if sid := SS_SYSTEM_IDS.get(key):
            params["systemeid"] = str(sid)
            break

    data = ss_call("jeuInfos.php", params, verbose)
    if not data:
        return None
    try:
        jeu = data["response"]["jeu"]
    except (KeyError, TypeError):
        if verbose:
            print("  screenscraper: game not in the database", file=sys.stderr)
        return None

    noms = jeu.get("noms") or []
    name = next((n.get("text") for n in noms if n.get("region") == "wor"),
                noms[0].get("text") if noms else parsed["title"])
    game = {"id": jeu.get("id"), "name": name,
            "platform": (jeu.get("systeme") or {}).get("text", ""),
            "year": ((jeu.get("dates") or [{}])[0].get("text", ""))[:4],
            "matched_by": "hash" if hashes else "filename",
            # The response carries the account quota: the downloader obeys it
            # instead of guessing a parallelism (see main()).
            "source": "screenscraper",
            "maxthreads": ((data.get("response") or {}).get("ssuser") or {}).get("maxthreads")}

    order = SS_REGION_PREF.get(parsed["region"], SS_REGION_PREF[None])
    by_type: dict[str, list[tuple[int, str]]] = {}
    for media in jeu.get("medias") or []:
        name_slug = SS_TO_SLUG.get(media.get("type", ""))
        url = media.get("url")
        if not name_slug or not url:
            continue
        if wanted and name_slug not in wanted:
            continue
        region = (media.get("region") or "ss").lower()
        rank = order.index(region) if region in order else len(order)
        by_type.setdefault(name_slug, []).append((rank, url))

    images: dict[str, list[str]] = {}
    for typ, items in by_type.items():
        items.sort(key=lambda x: x[0])
        images[typ] = [u for _, u in (items if every else items[:1])]
    return (game, images) if images else None


# ── Downloading ─────────────────────────────────────────────────────────────

_SECRET_PARAMS = ("devpassword", "sspassword", "devid", "ssid")


def redact(url: str) -> str:
    """URL without the credentials. Use it EVERYWHERE a URL is displayed.

    ScreenScraper media URLs carry devid/devpassword/ssid/sspassword in their
    query: `mediaJeu.php?devid=…&devpassword=…&ssid=…&sspassword=…`. Without
    this filter, a plain `--dry-run` pasted into a ticket or a log published the
    whole account. It happened.
    """
    parts = urllib.parse.urlsplit(url)
    if not parts.query:
        return url
    kept = [(k, "***" if k.lower() in _SECRET_PARAMS else v)
            for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)]
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(kept)))


def slug(text: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", text.lower())).strip("-")


def safe_dirname(title: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "_", title).strip(" .") or "game"


# Signatures of the formats we agree to write to disk.
_MAGIC = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF8", b"BM",
          b"RIFF", b"%PDF", b"\x00\x00\x00", b"\x1aE\xdf\xa3")  # …ftyp mp4, webm


def _looks_like_media(data: bytes) -> bool:
    if len(data) < 16:
        return False
    if data[:4] == b"RIFF" and data[8:12] not in (b"WEBP", b"AVI "):
        return False
    return any(data.startswith(m) for m in _MAGIC) or data[4:8] == b"ftyp"


def sniff_ext(data: bytes) -> str:
    """Extension from the CONTENT, never from the URL.

    ScreenScraper serves every media through `mediaJeu.php?…`, so the extension
    inferred from the path was ".php": the whole library filled up with
    `box-front.php` files that no frontend and no image viewer opens — and that
    GameCore, which looks for .png/.jpg, simply ignored.
    """
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"GIF8"):
        return ".gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data.startswith(b"%PDF"):
        return ".pdf"
    if data[4:8] == b"ftyp":
        return ".mp4"
    if data.startswith(b"\x1aE\xdf\xa3"):
        return ".webm"
    if data.startswith(b"BM"):
        return ".bmp"
    return ".bin"


def fetch(url: str, dest: Path, verbose: bool) -> Path | None:
    """Download to `dest`, whose extension is fixed from the content.
    Returns the path actually written, or None."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = r.read()
    except (urllib.error.URLError, OSError) as e:
        if verbose:
            print(f"    · {getattr(e, 'code', e)} {redact(url)}", file=sys.stderr)
        return None
    # ScreenScraper answers 200 with a TEXT BODY when the quota is spent or the
    # media is missing ("Erreur : …"). Without this check we wrote that message
    # into a .png, and the library filled up with unreadable thumbnails no
    # frontend can display — and nothing reported it.
    if not _looks_like_media(data):
        if verbose:
            snippet = data[:80].decode("utf-8", "replace").strip()
            print(f"    · non-media response ({len(data)} B): {snippet}",
                  file=sys.stderr)
        return None
    dest = dest.with_suffix(sniff_ext(data))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return dest


# ── CLI ─────────────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(
        description="Every image of a game, from its ROM filename "
                    "(sources: LaunchBox, or ScreenScraper by file hash when "
                    "developer credentials are configured).",
        epilog="Examples:\n"
               "  python3 gamescrape.py \"fifa-19-(europe)(fr,en).nds\" -o output\n"
               "  python3 gamescrape.py \"Mario Kart Wii.rvz\" -t 3d,box,logo\n"
               "  python3 gamescrape.py rom.iso -s ps2 --all -o output\n"
               "  python3 gamescrape.py \"game.nds\" --info",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("rom", nargs="?", help="ROM name or path "
                                          "(the file need not exist)")
    p.add_argument("-o", "--output", default="output", help="output directory")
    p.add_argument("-s", "--system", help="force the console: short key "
                   "(--list-systems) or exact LaunchBox platform name")
    p.add_argument("-t", "--types", default="all",
                   help="comma-separated image types: 3d, box, back, cart, "
                        "disc, logo, snap, title, fanart, banner… "
                        "(--list-types; default: all)")
    p.add_argument("--all", action="store_true",
                   help="every image of each type, not just the best one")
    p.add_argument("--cutoff", type=float, default=0.72,
                   help="minimum title similarity, 0-1 (default: 0.72)")
    p.add_argument("--flat", action="store_true",
                   help="write into -o without a per-game subdirectory")
    p.add_argument("--info", action="store_true",
                   help="parse the name and stop (no request)")
    p.add_argument("-n", "--dry-run", action="store_true",
                   help="list the images found without downloading them")
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--source", choices=("auto", "screenscraper", "launchbox"),
                   default="auto",
                   help="auto: ScreenScraper when developer credentials are "
                        "configured, LaunchBox otherwise or as a fallback")
    p.add_argument("--no-hash", action="store_true",
                   help="ScreenScraper: do not hash the file "
                        "(search by name only)")
    p.add_argument("--refresh", action="store_true",
                   help="re-download and re-index the LaunchBox database")
    p.add_argument("--ss-check", action="store_true",
                   help="test the ScreenScraper credentials and show the quotas")
    p.add_argument("--ss-systems", action="store_true",
                   help="official list of ScreenScraper systemeid values")
    p.add_argument("--list-systems", action="store_true")
    p.add_argument("--list-types", action="store_true")
    p.add_argument("--ss-media-types", action="store_true",
                   help="list the media types ScreenScraper declares and "
                        "confront SS_MEDIA with what it announces")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()
    global _JSON_MODE
    _JSON_MODE = args.json

    if args.ss_check or args.ss_systems:
        if not ss_credentials():
            out("No ScreenScraper developer credentials.\n"
                  "  export SCREENSCRAPER_DEV_ID=...\n"
                  "  export SCREENSCRAPER_DEV_PASSWORD=...\n"
                  "  export SCREENSCRAPER_USER=...        (optional, quotas)\n"
                  "  export SCREENSCRAPER_PASSWORD=...    (optional)",
                  file=sys.stderr)
            return 2
        if args.ss_check:
            data = ss_call("ssuserInfos.php", ss_credentials(), True)
            if not data:
                print("Credentials rejected by the API.", file=sys.stderr)
                return 1
            u = data.get("response", {}).get("ssuser", {})
            out(f"Account : {u.get('id')}  (level {u.get('niveau')})")
            out(f"Threads : {u.get('maxthreads')}")
            out(f"Scrapes : {u.get('requeststoday')} / "
                f"{u.get('maxrequestsperday')} today")
            return 0
        data = ss_call("systemesListe.php", ss_credentials(), True)
        if not data:
            return 1
        for s in data.get("response", {}).get("systemes", []):
            noms = s.get("noms", {})
            out(f"  {s.get('id'):>4}  {noms.get('nom_eu') or noms.get('noms_commun', '')}")
        return 0

    if args.list_systems:
        for k, v in sorted(PLATFORMS.items()):
            out(f"  {k:12} {v}")
        return 0
    if args.list_types:
        out("Shortcuts:")
        for k, v in sorted(TYPE_ALIASES.items()):
            out(f"  {k:12} → {v}")
        out(f"\nScreenScraper — {len(SS_MEDIA)} types, by category:")
        by_cat: dict[str, list[tuple[str, str, str]]] = {}
        for ss_type, (short, cat, kind) in SS_MEDIA.items():
            by_cat.setdefault(cat, []).append((short, ss_type, kind))
        for cat in sorted(by_cat):
            out(f"  [{cat}]")
            for short, ss_type, kind in sorted(by_cat[cat]):
                out(f"    {short:30} {kind:9} ← {ss_type}")
        if DB_PATH.exists():
            out("\nLaunchBox — types present in the local index:")
            db = sqlite3.connect(DB_PATH)
            rows = db.execute("SELECT DISTINCT type FROM images ORDER BY type")
            for (t,) in rows:
                cat, kind = lb_media_info(slug(t))
                out(f"    {slug(t):30} {cat:11} ← {t}")
            db.close()
        return 0
    if args.ss_media_types:
        # The reference behind SS_MEDIA. Run it to see what ScreenScraper has
        # added since — anything missing from the table still resolves through
        # ss_media_slug(), it just has no category.
        creds = ss_credentials()
        if not creds:
            out(f"Developer credentials required — see {CRED_FILE}", file=sys.stderr)
            return 1
        data = ss_call("mediasJeuListe.php", dict(creds), args.verbose)
        entries = ((data or {}).get("response") or {}).get("medias") or {}
        if not entries:
            out("mediasJeuListe.php returned nothing.", file=sys.stderr)
            return 1
        known = missing = 0
        for v in sorted(entries.values(), key=lambda x: (x.get("categorie", ""),
                                                         x.get("nomcourt", ""))):
            name = v.get("nomcourt", "")
            mapped = SS_MEDIA.get(name)
            known += bool(mapped)
            missing += not mapped
            flag = f"→ {mapped[0]}" if mapped else "→ NOT IN SS_MEDIA"
            out(f"  {name:24} {v.get('type', ''):8} {v.get('fileformat', ''):5} "
                f"{flag:34} [{v.get('categorie', '')}]")
        out(f"\n{len(entries)} declared · {known} in SS_MEDIA · {missing} missing")
        out("Note: this endpoint is not exhaustive — pictoliste, pictomonochrome,"
            " pictocouleur and background arrive in jeuInfos without being"
            " declared here.")
        return 0
    if args.refresh:
        build_index(args.verbose)
        if not args.rom:
            return 0
    if not args.rom:
        p.error("a ROM name is required "
                "(or --refresh / --list-systems / --list-types)")

    parsed = parse_rom(args.rom)
    systems = parsed["systems"]
    if args.system:
        systems = [args.system]
        parsed["systems"] = systems

    if not args.json:
        out(f"Title    : {parsed['title']}")
        out(f"Console  : {', '.join(PLATFORMS.get(s, s) for s in systems) or 'unknown'}"
              f"   (extension .{parsed['ext'] or '?'})")
        if parsed["region"] or parsed["languages"]:
            out(f"Region   : {parsed['region'] or '?'}"
                  f"   Languages: {','.join(parsed['languages']) or '-'}")
        extra = [x for x in (f"disc {parsed['disc']}" if parsed["disc"] else "",
                             f"rev {parsed['revision']}" if parsed["revision"] else "",
                             ", ".join(parsed["flags"])) if x]
        if extra:
            out(f"Other    : {'   '.join(extra)}")
    if args.info:
        if args.json:
            print(json.dumps(parsed, ensure_ascii=False, indent=2))
        return 0

    wanted: list[str] | None = None
    if args.types.strip().lower() != "all":
        wanted = []
        for raw in args.types.split(","):
            key = raw.strip()
            if not key:
                continue
            wanted.append(TYPE_ALIASES.get(key.lower(), key))

    game: dict | None = None
    images: dict[str, list[str]] = {}

    # 1. ScreenScraper first when configured: on a file that exists, the hash
    #    search is certain where the name stays a guess.
    if args.source in ("auto", "screenscraper"):
        # The fallback was silent: with no developer credentials, "auto"
        # switched to LaunchBox without saying so, and you believed you were
        # scraping by hash while guessing by name. One line removes the doubt.
        if args.source == "auto" and not ss_credentials():
            out("ScreenScraper: no developer credentials → LaunchBox "
                f"(matching by name). Config: {CRED_FILE}")
        rom_path = None if args.no_hash else Path(args.rom)
        hit = ss_lookup(parsed, systems, rom_path, wanted, args.all, args.verbose)
        if hit:
            game, images = hit
            out(f"\nScreenScraper: \"{game['name']}\" — {game['platform']}"
                  f"{' (' + game['year'] + ')' if game['year'] else ''}"
                  f"   [by {game['matched_by']}, id {game['id']}]")
        elif args.source == "screenscraper":
            sys.stdout.flush()
            out("ScreenScraper returned nothing (missing credentials, quota, "
                  "or game not in the database). Use `--source launchbox` for "
                  "the other source, `--ss-check` to test the credentials.",
                  file=sys.stderr)
            return 1

    # 2. LaunchBox: the default source, and the net when ScreenScraper cannot.
    if game is None:
        try:
            db = open_db()
        except IndexUnavailable as exc:
            sys.stdout.flush()
            out(f"{exc} — run this first: gamescrape.py --refresh",
                file=sys.stderr)
            return 1
        game, score = find_game(db, parsed, systems, args.cutoff)
        if not game:
            sys.stdout.flush()
            out(f"No game found (best similarity {score:.0%}). Try "
                  f"--cutoff 0.6, -s <console>, or a title closer to the "
                  f"official one.", file=sys.stderr)
            return 1
        out(f"\nLaunchBox: \"{game['name']}\" — {game['platform']}"
              f"{' (' + game['year'] + ')' if game['year'] else ''}"
              f"   [similarity {score:.0%}, id {game['id']}]")
        _show_details(game)
        images = game_images(db, game["id"], parsed, wanted, args.all)

    if not images:
        print("This game has no image of the requested type in the database.",
              file=sys.stderr)
        return 1

    outdir = Path(args.output)
    if not args.flat:
        outdir /= safe_dirname(game["name"])

    jobs: list[tuple[str, str, Path]] = []
    for typ, urls in sorted(images.items()):
        for i, url in enumerate(urls, 1):
            ext = Path(urllib.parse.urlparse(url).path).suffix.lower() or ".png"
            suffix = f"-{i}" if len(urls) > 1 else ""
            jobs.append((typ, url, outdir / f"{typ}{suffix}{ext}"))

    if args.dry_run:
        if args.json:
            print(json.dumps({"parsed": parsed, "game": game,
                              "images": {t: [redact(u) for u in us]
                                         for t, us in images.items()}},
                             ensure_ascii=False, indent=2))
        else:
            out(f"\n{len(jobs)} image(s), nothing downloaded (--dry-run):")
            for typ, url, dest in jobs:
                out(f"  {typ:28} {redact(url)}")
        return 0

    # Parallelism is whatever the SOURCE allows, not a fixed number.
    #
    # It was a hardcoded max_workers=8. The LaunchBox CDN does not care, but
    # ScreenScraper grants a thread count per account (`maxthreads`, 1 for a
    # level-1 member) and penalises going over — 8 concurrent downloads on a
    # quota of 1 is a suspended account, not a slowdown.
    workers = 8
    if game.get("source") == "screenscraper":
        workers = max(1, int(game.get("maxthreads") or 1))
        if workers == 1 and len(jobs) > 1:
            out(f"  (ScreenScraper: {workers} thread allowed on this account "
                f"— sequential download)")

    out(f"\n{len(jobs)} image(s) → {outdir}/")
    results: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch, url, dest, args.verbose): (typ, dest)
                   for typ, url, dest in jobs}
        for fut, (typ, dest) in futures.items():
            written = fut.result()
            if written:
                results[written.name] = typ
                out(f"  ✓ {written.name:34} {written.stat().st_size // 1024} Ko")
            else:
                out(f"  ✗ {dest.stem:34} failed")

    if results:
        (outdir / "info.json").write_text(json.dumps(
            {"parsed": parsed, "game": game, "files": results},
            ensure_ascii=False, indent=2), encoding="utf-8")
    if args.json:
        print(json.dumps({"parsed": parsed, "game": game, "files": results},
                         ensure_ascii=False, indent=2))
    return 0 if results else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
