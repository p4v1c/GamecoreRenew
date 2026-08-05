"""Finding a game in the LaunchBox index, and reading its record.

Split out of gamescrape.py. Everything here takes an open database and answers
a question about it: which game a parsed ROM name is, and what that game's
record and images are.

Two decisions in `find_game` are the reason this deserves reading rather than
skimming:

  · an episode number that differs means a DIFFERENT game, whatever the text
    similarity says. "Choplifter III" and "Choplifter II" score very high
    against each other, and text similarity is exactly the measure that finds
    that gap negligible;
  · a Virtual Console release is catalogued by LaunchBox under the ORIGINAL
    console, so the platform filter is dropped for one — otherwise Sonic &
    Knuckles is searched for under Wii and never found.

Imported by gamescrape.py, which re-exports every public name below — no caller
outside this package changes an import.
"""
from __future__ import annotations

import difflib
import re
import sqlite3
import urllib.parse
import zlib

# Two import paths, and both are used. Inside the backend this is a package;
# run as `python3 gamescrape.py <rom>` — the CLI its own docstring documents —
# it is a loose script with no parent package. Same try/except gamemedia.py
# already uses to reach this module, rather than a second mechanism.
try:
    from .common import IMAGE_CDN, out, slug
    from .lb_index import LB_DETAIL_COLS
    from .parser import PLATFORMS, REGION_PREF, normalize
except ImportError:                                    # plain-script CLI
    from common import IMAGE_CDN, out, slug
    from lb_index import LB_DETAIL_COLS
    from parser import PLATFORMS, REGION_PREF, normalize

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
