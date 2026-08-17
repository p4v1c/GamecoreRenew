"""The ScreenScraper client: rate limit, retries, hashes, and match scoring.

Split out of gamemedia.py. Everything here talks to one API and nothing here
knows what a cache entry is — which is why it came out cleanly: the block had
no reference to any other part of the file.

The two things worth reading before changing anything:

  · `_Limiter` and `SS_MIN_INTERVAL` exist because the account has a quota and
    a thread count, and both are enforced server-side. Exceeding them does not
    return an error you can retry — it returns a closed account.
  · `_hash_confirmed` is what separates a CERTAIN match from a likely one. A
    hash match is the file itself; a name match is a guess with a good score,
    and the two must never be recorded as the same thing.

Imported by gamemedia.py, which re-exports every public name below — no caller
outside this package changes an import.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path

try:
    from . import gamescrape as gs
except ImportError:                                    # plain-script CLI
    import gamescrape as gs

log = logging.getLogger(__name__)

# ── Client ScreenScraper ─────────────────────────────────────────────────────
#
# These rules are not precautions invented here: they come from reading
# Skyscraper (muldjord), the reference CLI scraper, which learned them in
# production over hundreds of thousands of ROMs.
#
#   · 1.2 s MINIMUM between two requests. Their source comment is explicit:
#     "set a bit above 1.0 as requested by the good folks at ScreenScraper.
#     Don't change!" Without it you get blacklisted, and it is the devid — so
#     everyone using it — that goes down.
#   · Errors are classified on the FIRST RAW BYTES, not on the parsed JSON:
#     "It's more stable than checking the potentially faulty JSON."
#     ScreenScraper regularly returns raw text with a 200 code.
#   · The JSON itself is sometimes invalid and gets repaired (trailing comma).
#   · The thread count comes from the account, capped at 8 even if the API
#     offers more.
#
# Each error case is handled distinctly, and that is the whole point: "game not
# found" is final and gets cached, "quota reached" is
# temporaire et ne doit RIEN mettre en cache.

SS_MIN_INTERVAL = 1.2
SS_RETRIES = 3
SS_MAX_THREADS = 8


class ScreenScraperClosed(Exception):
    """API closed, quota spent, or software blacklisted — cache nothing."""


class ScreenScraperUnreachable(Exception):
    """No usable response — unknown state, cache nothing."""


class _Limiter:
    """One call every SS_MIN_INTERVAL seconds, across all threads."""

    def __init__(self, interval: float) -> None:
        import threading
        self._interval, self._lock, self._last = interval, threading.Lock(), 0.0

    def wait(self) -> None:
        with self._lock:
            gap = self._interval - (time.monotonic() - self._last)
            if gap > 0:
                time.sleep(gap)
            self._last = time.monotonic()


_ss_limiter = _Limiter(SS_MIN_INTERVAL)
# Requests left for the day, known from the first response. None = not yet
# known. 0 = stop insisting.
ss_remaining: int | None = None


def ss_request(endpoint: str, params: dict, verbose: bool = False) -> dict | None:
    """Rate-limited ScreenScraper call, with retries and classified errors.

    Returns the JSON, or None when the API clearly says "game not found".
    Raises ScreenScraperClosed / ScreenScraperUnreachable in every other failure
    case, so the caller knows whether it is allowed to cache.
    """
    global ss_remaining
    import urllib.error
    import urllib.parse
    import urllib.request

    if ss_remaining == 0:
        raise ScreenScraperClosed("daily quota spent")

    url = gs.SS_API + endpoint + "?" + urllib.parse.urlencode(params)
    last = "no response"
    for attempt in range(SS_RETRIES):
        _ss_limiter.wait()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": gs.UA})
            with urllib.request.urlopen(req, timeout=gs.TIMEOUT) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            raw, code = e.read(), e.code
            head = raw[:1024].decode("utf-8", "replace")
            if code == 404 or "non trouv" in head:
                return None
            last = f"HTTP {code} — {head.strip()[:120]}"
            # 401/403 credentials, 426 API closed, 429/430/431 quota reached.
            # Without those last three, a 429 with an empty body triggered 3
            # attempts at 1.2 s — 3 requests burned on an already spent quota,
            # for every game in the library.
            if code in (401, 403, 426, 429, 430, 431):
                if code in (426, 429, 430, 431):
                    ss_remaining = 0                   # short-circuits the rest
                raise ScreenScraperClosed(last)
        except (urllib.error.URLError, OSError) as e:
            last = str(e)
            time.sleep(1.5 * (attempt + 1))
            continue
        else:
            head = raw[:1024].decode("utf-8", "replace")

        # Classify on the raw bytes, before any parsing (cf. Skyscraper).
        # The needles below are FRENCH on purpose: they are fragments of
        # ScreenScraper's own error messages, which the API returns in French
        # regardless of the caller. Translating them would break the matching.
        low = head.lower()
        if "non trouv" in low:
            return None
        for fatal in ("api totalement ferm", "quota de scrape est",
                      "blacklist", "closed for non-registered"):
            if fatal in low:
                ss_remaining = 0
                raise ScreenScraperClosed(head.strip()[:160])
        if "maximum threads" in low or "api ferm" in low:
            last = head.strip()[:160]
            time.sleep(2.0 * (attempt + 1))
            continue

        # ScreenScraper sometimes returns JSON with a trailing comma.
        txt = raw.decode("utf-8", "replace").replace("],\n\t\t}", "]\n\t\t}")
        try:
            data = json.loads(txt)
        except ValueError:
            last = f"JSON illisible : {head.strip()[:120]}"
            continue

        user = ((data.get("response") or {}).get("ssuser") or {})
        try:
            ss_remaining = int(user["maxrequestsperday"]) - int(user["requeststoday"])
        except (KeyError, TypeError, ValueError):
            pass
        _seed_threads(data)          # free: the response already has maxthreads
        return data

    raise ScreenScraperUnreachable(last)


# CONTAINER formats: compressed or re-encoded. Their hash exists in no DAT —
# No-Intro and Redump index the raw dump or the tracks, not the archive. Hashing
# them costs minutes of disk reads for no gain whatsoever.
_CONTAINER_EXTS = {"chd", "rvz", "cso", "zso", "wbfs", "gcz", "wia", "pbp",
                   "ecm", "7z", "rar", "squashfs", "nsz", "xcz"}
# Hashing ceiling. It was 4 GiB: a PS2 .iso was read IN FULL inside the HTTP
# handler — over two minutes of blocking on a USB disk. ES-DE cuts at 384 MiB by
# default, Skyscraper at 50 for its cache key.
HASH_MAX_BYTES = int(os.environ.get("GAMEMEDIA_HASH_MAX", 384 * 1024 * 1024))


def _year_of(released: str) -> str:
    """The year, whatever date format the source returned."""
    m = re.search(r"(19|20)\d{2}", released or "")
    return m.group(0) if m else ""


def _rating_01(raw: str) -> float | None:
    """The rating brought back to 0-1, or None. ScreenScraper rates out of 20."""
    try:
        v = float(str(raw).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    return round(min(v, 20.0) / 20.0, 3)


def hashes_for(path: Path) -> dict[str, str] | None:
    """File hashes, or None when computing them makes no sense."""
    try:
        if not path.is_file():
            return None
        size = path.stat().st_size
    except OSError:
        return None
    if path.suffix.lower().lstrip(".") in _CONTAINER_EXTS:
        return None
    if size > HASH_MAX_BYTES:
        return None
    return gs.file_hashes(path, limit=HASH_MAX_BYTES)


# GameCore: how close the title that came back is to the one we asked for.
#
# ScreenScraper's romnom search is fuzzy and always answers *something*. Asked
# for "Mario Kart Wii" on GameCube it returns "Mario Kart: Double Dash!!" — and
# since any answer ended the loop, that is what the box displayed. The Wii
# candidate, which would have answered "Mario Kart Wii", was never asked.
#
# Both figures below come from measuring this library, not from taste:
#
#   correct match, article reordered   1.000  ("Legend of Zelda, The - Skyward
#                                              Sword" vs ScreenScraper's "The
#                                              Legend of Zelda - Skyward Sword")
#   wrong console                      0.581  (Double Dash)
#   *different game in the same series* 0.909  (Mario Party 4 vs Mario Party 7)
#
# That 0.909 is why a threshold alone cannot do this. One character apart, two
# genuinely different games — so the rule is not "is this good enough", it is
# "which candidate is closest". A candidate is only accepted outright when it
# is nearly exact; anything short of that keeps looking and the best wins.
NAME_ACCEPT = 0.95


def _title_score(parsed: dict, jeu: dict, want: str | None = None) -> float:
    """Best similarity between the name we asked for and any name returned.

    `want` overrides what `parsed` says was asked for, and the caller that
    passes it is the retry that drops the console's name from the query: scoring
    a reply to "FIFA 22 Legacy Edition" against the original "FIFA 22 Nintendo
    Switch Legacy Edition" would penalise it for the very words that were
    removed on purpose, and the retry could never win.
    """
    import difflib
    want = gs.normalize(want or parsed.get("romnom") or parsed.get("title") or "")
    if not want:
        return 0.0
    names = [str(n.get("text") or "") for n in (jeu.get("noms") or [])
             if isinstance(n, dict)]
    if not names:
        return 0.0
    return max(difflib.SequenceMatcher(None, want, gs.normalize(n)).ratio()
               for n in names)


def _hash_confirmed(jeu: dict, hashes: dict | None) -> bool:
    """The server echoed one of our digests — certain, never second-guessed."""
    return _matched_by(jeu, hashes) == "hash"


def _matched_by(jeu: dict, hashes: dict | None) -> str:
    """How the game was REALLY found — verified, not declared.

    Returning "hash" because we sent one describes what we asked, not what the
    server used: the frontend received a certainty that was not one. ES-DE
    re-parses the <rommd5> from the response and compares it with the local
    digest, with three states (ScreenScraper.cpp:635-636,
    GuiScraperSearch.cpp:488-508). Same thing here.
    """
    if not hashes:
        return "name"
    echo = jeu.get("rom") or {}
    pairs = (("romcrc", "crc"), ("rommd5", "md5"), ("romsha1", "sha1"))
    seen = [(str(echo.get(k) or "").lower(), str(hashes.get(h) or "").lower())
            for k, h in pairs if echo.get(k)]
    if not seen:
        return "hash (unverifiable)"
    return ("hash" if any(a == b for a, b in seen)
            else "name (hash sent, not confirmed)")


# maxthreads does not change within a session, and ssuserInfos.php costs one
# quota unit + 1.2 s. Calling it per game doubled the consumption. The value is
# also seeded from any jeuInfos response, which already carries it.
_ss_threads: int | None = None


def _seed_threads(data: dict) -> None:
    global _ss_threads
    n = ((data.get("response") or {}).get("ssuser") or {}).get("maxthreads")
    try:
        _ss_threads = max(1, min(SS_MAX_THREADS, int(n)))
    except (TypeError, ValueError):
        pass


def ss_threads() -> int:
    """Parallelism the account allows, capped the way Skyscraper caps it."""
    global _ss_threads
    if _ss_threads is not None:
        return _ss_threads
    creds = gs.ss_credentials()
    if not creds:
        return 1
    try:
        data = ss_request("ssuserInfos.php", creds)
    except (ScreenScraperClosed, ScreenScraperUnreachable):
        return 1
    if data:
        _seed_threads(data)
    return _ss_threads if _ss_threads is not None else 1
