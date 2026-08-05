"""The LaunchBox dump: download it, index it, open it.

Split out of gamescrape.py. This is the half that owns ~/.cache/gamescrape —
a 234 MB Metadata.zip turned into a local SQLite database, and everything that
decides whether that database is usable.

`SCHEMA_VERSION` and the staleness check are the reason this is worth having on
its own: a database built by an earlier version is still a file on disk, and it
fails every query with "no such column" rather than being absent. "Present" and
"usable" are two different questions and only the second one matters.

Imported by gamescrape.py, which re-exports every public name below — no caller
outside this package changes an import.
"""
from __future__ import annotations

import sqlite3
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
import zlib
from pathlib import Path

# `common` is imported as a MODULE on purpose: CACHE_DIR and DB_PATH move at
# runtime (see common.set_index_dir), and a from-import would freeze whatever
# they pointed at when this file was first imported.
# Two import paths, and both are used. Inside the backend this is a package;
# run as `python3 gamescrape.py <rom>` — the CLI its own docstring documents —
# it is a loose script with no parent package. Same try/except gamemedia.py
# already uses to reach this module, rather than a second mechanism.
try:
    from . import common
    from .common import MAX_AGE_DAYS, METADATA_URL, SCHEMA_VERSION, TIMEOUT, UA
    from .parser import normalize
except ImportError:                                    # plain-script CLI
    import common
    from common import MAX_AGE_DAYS, METADATA_URL, SCHEMA_VERSION, TIMEOUT, UA
    from parser import normalize

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
    common.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = common.CACHE_DIR / "Metadata.zip"
    tmp_db = common.DB_PATH.with_suffix(".tmp")
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
    tmp_db.replace(common.DB_PATH)
    zip_path.unlink(missing_ok=True)        # dump no longer needed, 106 MB back
    gain = (1 - counts["packed"] / counts["raw"]) * 100 if counts["raw"] else 0
    print(f"  ready: {counts['games']:,} games, {counts['images']:,} images, "
          f"{counts['overviews']:,} descriptions "
          f"({counts['raw'] / 1048576:.0f} MB of text → "
          f"{counts['packed'] / 1048576:.0f} MB, -{gain:.0f} %)",
          file=sys.stderr)
    print(f"  {common.DB_PATH} — {common.DB_PATH.stat().st_size / 1048576:.0f} MB", file=sys.stderr)


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
    if not common.DB_PATH.is_file():
        return False
    try:
        db = sqlite3.connect(f"file:{common.DB_PATH}?mode=ro", uri=True)
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
    stale = common.DB_PATH.exists() and not lb_index_ready()
    if not common.DB_PATH.exists() or stale:
        if not auto:
            raise IndexUnavailable(
                "LaunchBox index has a stale schema" if stale else
                "LaunchBox index is missing")
        if stale:
            print("LaunchBox index from an earlier version (no descriptions) "
                  "— rebuilding.", file=sys.stderr)
        build_index()
    db = sqlite3.connect(common.DB_PATH)
    row = db.execute("SELECT value FROM meta WHERE key='built_at'").fetchone()
    age = (time.time() - int(row[0])) / 86400 if row else 999
    if age > MAX_AGE_DAYS:
        print(f"(database is {age:.0f} days old — run `--refresh` to update it)",
              file=sys.stderr)
    return db
