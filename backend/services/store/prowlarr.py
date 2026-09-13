"""The Prowlarr search provider — one indexer aggregator, owned by somebody else.

**Prowlarr is external, always.** GameCore does not install it, does not manage
it, does not update it and does not remove it. The box owner runs their own
instance, on whatever machine they like, and configures their own indexers in
it. This file knows two things about it: a URL and an API key.

That is a deliberate trade and it is worth naming, because the alternative is
tempting and worse. A managed Prowlarr would mean a `.NET` service unit on the
box, a second port listening on the LAN — the one thing
[`docs/SECURITY.md`](../../../docs/SECURITY.md) spent the whole hardening pass
reducing to Caddy on `:8443` — a managed/external split in the pack manifest,
and GameCore owning the uptime of a piece of software whose whole job is to talk
to sites GameCore has no relationship with. Two configuration values buy all of
that back.

The second half of the same decision: **the list of indexers is not here.** Not
a tracker, not a category table, not a default source — those live in the
owner's Prowlarr, which is the only place that can know what they have access
to. `indexerIds` and `categories` in the configuration file are pass-throughs
for ids the owner reads off their own instance; both default to "everything you
have configured", and this repository ships no value for either.

── The credential, and where it is not ────────────────────────────────────
`config/store-prowlarr.json`, mode 0600, written the way
[`services/auth.py`](../auth.py) writes `auth.json` — atomically, private from
the first byte. `config/` is excluded from the OTA rsync, so it survives an
update; `install/uninstall.sh` names it, so it does not survive a removal.

The key never leaves this process. It travels as an `X-Api-Key` **header** and
never in a URL, because a URL is what ends up in a proxy log and in an
exception message; redirects are not followed, because following one would hand
the header to whatever host the redirect named; and every string lifted out of a
response is redacted before it becomes a `SearchResult`, because Prowlarr's own
`downloadUrl` carries `?apikey=…` and that field would otherwise travel to the
browser inside `source`.

── What `source` carries, and what it turned out to need ──────────────────
`prowlarr://<indexerId>/<guid>`, plus a `#btih:<hash>` suffix when the release
names one. The pair on its own was chosen to be re-resolvable against Prowlarr
and it is not: measured against `Prowlarr.Api.V1.dll` 2.5.2.5491, the only
endpoint that accepts it is the *grab*, which reads an in-memory cache that
expires and then hands the release to a **download client** — a torrent daemon,
which is the one thing this box does not have. The info hash is what makes the
row resolvable a week later without a URL and without a credential.
[`resolve.py`](resolve.py) holds the evidence and the parse.

── Why a result has to prove which console it is for ──────────────────────
An indexer has no idea what a GameCube is. It answers "zelda" with the N64
game, the 3DS remake, a Wii U port, a soundtrack and a film, and
[`search.py`](search.py) is explicit that guessing which machine each hit is for
is a guess this repository would have to be right about every time. So it does
not guess: a row survives only when something about it **names this console** —
either a suffix only this console declares (`.z64` is `gopher64` and nothing
else) or one of the names the console goes by. No evidence is a drop.

── A console does not claim its successors' releases ──────────────────────
The first version of that rule matched a name whole-word and stopped there,
and a whole word is not enough: "PlayStation" is a whole word inside
"PlayStation 3". Measured against a real indexer — 110 rows over three
queries — `duckstation` kept all seven `gran turismo` rows, `Gran Turismo 6 -
PlayStation 3` among them, and the same fault put Wii U releases on `dolphin`
and anything with a stray "DS" in it on `melonds`. A player on the PlayStation
1 screen was being offered games no PlayStation 1 emulator can run: the import
would have worked, the tile would have appeared, and the screen would have
stayed black.

So the name band now weighs two claims instead of reading one. A name the
catalogue *completes* — `PlayStation`, `Wii`, `DS`, all of them abbreviations
of something longer another pack declares — proves this console only when no
other console is named more precisely on the same row. A name nothing extends
— `PlayStation 3`, `Wii U`, `Nintendo 64`, `MAME` — proves it outright. Which
names are which is not written down anywhere: it is one pass over
`catalog/*/pack.json`, the way `search.unique_suffixes` is, so a pack that
arrives, is renamed or is removed changes the answer in the commit that
changes the pack, and a hand-written console table — matrix §5.2 — never
exists to go stale. `_ConsoleNames` holds the rule.

── The suffix band fired zero times, and stays ────────────────────────────
Same measurement, second finding: across those 110 rows, on every console, the
"by suffix" count was 0. These indexers name a release `Title - Platform` and
attach no file extension, so everything that survives today survives on its
name — which is why the paragraph above is the one that matters. The band is
kept because it is not wrong, only idle here: `.z64` is still the one kind of
evidence that cannot be mistaken, other sources do name files, and Prowlarr
answers a `fileName` field when the indexer sets one. Suffix-backed rows are
still sorted above name-only ones for the same reason.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx

from ..paths import config_dir
from . import resolve
# `console_terms` moved to `search.py` when the catalogue-wide pass there
# needed the same split, and is imported back under its old name: it is used
# below, and the tests still reach for it at this address.
from .search import NEVER_OFFERED, SearchResult, SearchSystem, console_terms

log = logging.getLogger(__name__)

#: Beside `auth.json` and gitignored with it. Namespaced rather than
#: `prowlarr.json`, because `config/` is a directory the whole box shares and
#: "which part of GameCore owns this file" is otherwise a guess.
CONFIG_FILENAME = "store-prowlarr.json"

#: Seconds. A search fans out to every indexer the owner configured and each of
#: those is a third party on the far side of a home connection, so this is
#: generous — but it is also a player holding a gamepad in front of a
#: television, and a minute of nothing is a broken screen rather than a slow
#: one. Overridable per box; clamped, because a zero here is a Store that can
#: never answer and a thousand is one that hangs the tab.
DEFAULT_TIMEOUT = 20.0
_MIN_TIMEOUT, _MAX_TIMEOUT = 1.0, 120.0

#: How many rows to ask Prowlarr for, regardless of how many the router wants.
#: The console filter below runs *after* the answer arrives, so asking for
#: forty would mean forty rows about every console and three about this one.
_FETCH = 100

#: Archive extensions an indexer serves whatever the pack declares. Wider than
#: the demo provider's pair on purpose: this one is *recognising* a name it was
#: handed, not choosing one to invent, and `.rar` is what half of usenet is.
_ARCHIVES = ("zip", "7z", "rar")

#: Region tags, as No-Intro and Redump spell them inside brackets. Recognised,
#: never required — a release that carries none simply has no region, which is
#: the honest answer rather than "World".
_REGIONS = {
    "usa": "USA", "us": "USA", "u": "USA", "ntsc-u": "USA",
    "europe": "Europe", "eur": "Europe", "e": "Europe", "pal": "Europe",
    "japan": "Japan", "jpn": "Japan", "jp": "Japan", "j": "Japan",
    "ntsc-j": "Japan", "world": "World", "usa, europe": "USA, Europe",
    "japan, usa": "Japan, USA", "korea": "Korea", "china": "China",
    "australia": "Australia", "brazil": "Brazil", "spain": "Spain",
    "france": "France", "germany": "Germany", "italy": "Italy",
}
#: `(En,Fr,De)` — the other bracketed group the same conventions use.
_LANG_CODES = {"en", "fr", "de", "es", "it", "ja", "nl", "pt", "sv", "no",
               "da", "fi", "zh", "ko", "ru", "pl"}
_BRACKETED = re.compile(r"[(\[]([^)\]]{1,40})[)\]]")

#: Query parameters whose value is a credential. Redacted out of everything
#: lifted from a response, because Prowlarr answers a `downloadUrl` shaped
#: `http://…/3/download?apikey=<the box's key>&link=…` and that field would
#: otherwise reach the browser inside `SearchResult.source`.
_CREDENTIAL_PARAM = re.compile(
    r"(?i)\b(api[_-]?key|passkey|rss[_-]?key|auth[_-]?key|token|secret)"
    r"=[^&;#\s]*")


class ProwlarrError(RuntimeError):
    """Prowlarr did not answer usefully.

    Raised with a message that is safe to log: no key, no path, no query
    string — see `_where()`. `routers/store.py` logs it and answers a generic
    502, and the two halves of that only work together.
    """


# ── configuration ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ProwlarrConfig:
    """`config/store-prowlarr.json`, validated.

    ``url``          scheme, host and port of the owner's Prowlarr. Path,
                     query and fragment are dropped on load: a key pasted into
                     the URL would otherwise be sent on every request *and*
                     land in every log line.
    ``api_key``      Settings → General → API Key, in that instance.
    ``timeout``      seconds, clamped to [1, 120].
    ``indexer_ids``  optional, ids from the owner's own instance. Empty means
                     every indexer they have configured.
    ``categories``   optional, Newznab category ids from the same place. Empty
                     means no category filter — GameCore ships no mapping from
                     console to category and will not: 17 of the 31 consoles
                     have no console category at all, so a shipped table would
                     silently return nothing for most of the library.
    """

    url: str
    api_key: str
    timeout: float = DEFAULT_TIMEOUT
    indexer_ids: tuple[int, ...] = ()
    categories: tuple[int, ...] = ()


def config_file() -> Path:
    """Resolved on every call, never at import.

    `auth.py` binds its paths at import and the test suite works around it.
    This one is read through `paths.config_dir()` each time, so a test that
    moves the data root moves this file with it — and so does a box whose
    `GAMECORE_DATA` is set after the unit is written.
    """
    return config_dir() / CONFIG_FILENAME


#: Paths already complained about, so the warning below is one line in the
#: journal rather than one per search.
_warned: set[str] = set()


def _warn_if_world_readable(path: Path) -> None:
    """Say so, and read it anyway.

    Not a refusal. This file is written by hand — `nano`, `scp`, a text editor
    over SSH — and a default umask makes it 0644 without the owner doing
    anything wrong. A Store that silently stayed on the demo provider because
    of a permission bit would be a box that looks broken with no way to tell
    why; a loud line in the journal and a working Store is the better trade.
    `save_config()` below writes 0600 whenever GameCore is the one writing.
    """
    try:
        mode = path.stat().st_mode
    except OSError:
        return
    if not mode & (stat.S_IRGRP | stat.S_IROTH):
        return
    key = f"{path}:{stat.S_IMODE(mode):o}"
    if key in _warned:
        return
    _warned.add(key)
    log.warning("store: %s is readable by other accounts (mode %o) — it holds "
                "an API key; chmod 600 it", path, stat.S_IMODE(mode))


def _clean_url(raw: object) -> str:
    """`http://host:9696`, or "" when that is not what was written.

    Everything after the authority is dropped rather than trusted. A key pasted
    into the URL is the shape this is really guarding against: it would be sent
    on the wire in the clear on every search, and it would appear in any log
    line that ever printed the configured address.
    """
    if not isinstance(raw, str) or not raw.strip():
        return ""
    parts = urlsplit(raw.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return ""
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


def _int_list(raw: object) -> tuple[int, ...]:
    """Ids, from whatever a hand-written file put there.

    Accepts `[1, 2]` and `["1", "2"]` and ignores anything else in the list
    rather than refusing the whole file: a typo in an optional narrowing knob
    must not be the reason a configured box falls back to invented rows.
    """
    if not isinstance(raw, list):
        return ()
    out: list[int] = []
    for item in raw:
        try:
            out.append(int(item))
        except (TypeError, ValueError):
            log.warning("store: %s — ignoring %r, which is not an id",
                        CONFIG_FILENAME, item)
    return tuple(out)


def _pick(data: dict, *names: str) -> object:
    """The first of several spellings that is present.

    `apiKey` and `api_key` both work, and so do `indexerIds` and
    `indexer_ids`. The file has no editor behind it — somebody types it at
    midnight over SSH — and refusing it over a capital letter is a support
    question this repository would then have to answer.
    """
    for name in names:
        if name in data:
            return data[name]
    return None


def load_config() -> ProwlarrConfig | None:
    """The configuration, or `None` when there is not a usable one.

    `None` covers absent, unreadable, malformed, and present-but-incomplete,
    and they are one answer on purpose: the caller's behaviour is the same for
    all four — fall back to the demo provider, which says out loud that its
    rows are invented. A missing file is the *normal* state of a box and is not
    logged above debug; a file that exists and cannot be used is a warning,
    because somebody meant it to work.
    """
    path = config_file()
    try:
        raw = path.read_text()
    except FileNotFoundError:
        log.debug("store: no %s — the demo provider answers", CONFIG_FILENAME)
        return None
    except (OSError, UnicodeDecodeError) as e:
        # UnicodeDecodeError is listed for the same reason `auth._auth()` lists
        # it: `read_text()` raises that one, not a JSON error, on a file that
        # is not UTF-8 — a half-written or foreign file.
        log.warning("store: %s cannot be read — %s", CONFIG_FILENAME, e)
        return None
    _warn_if_world_readable(path)

    try:
        data = json.loads(raw)
    except ValueError as e:
        log.warning("store: %s is not valid JSON — %s", CONFIG_FILENAME, e)
        return None
    if not isinstance(data, dict):
        log.warning("store: %s is not a JSON object", CONFIG_FILENAME)
        return None

    url = _clean_url(_pick(data, "url", "baseUrl", "base_url"))
    api_key = _pick(data, "apiKey", "api_key")
    api_key = api_key.strip() if isinstance(api_key, str) else ""
    if not url or not api_key:
        # Named without its value: "url" and "apiKey" are safe to print, the
        # key itself never is.
        missing = [n for n, ok in (("url", url), ("apiKey", api_key)) if not ok]
        log.warning("store: %s is incomplete (%s) — the demo provider answers",
                    CONFIG_FILENAME, ", ".join(missing))
        return None

    timeout = _pick(data, "timeout", "timeoutSeconds", "timeout_seconds")
    try:
        timeout = float(timeout)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        timeout = DEFAULT_TIMEOUT

    return ProwlarrConfig(
        url=url,
        api_key=api_key,
        timeout=min(max(timeout, _MIN_TIMEOUT), _MAX_TIMEOUT),
        indexer_ids=_int_list(_pick(data, "indexerIds", "indexer_ids")),
        categories=_int_list(_pick(data, "categories")),
    )


def save_config(cfg: ProwlarrConfig) -> Path:
    """Write it the way `auth.py` writes a credential: atomically, 0600.

    There is no settings screen behind this yet — the file is created by hand
    today. It exists so that when one arrives it does not invent a second way
    to write a secret, and so that the tests build their fixtures through the
    same code the box would use rather than through a `write_text()` that
    leaves a world-readable key behind.
    """
    path = config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({
        "url": cfg.url,
        "apiKey": cfg.api_key,
        "timeout": cfg.timeout,
        "indexerIds": list(cfg.indexer_ids),
        "categories": list(cfg.categories),
    }, indent=2) + "\n"
    # 0600 from the first byte, and `os.replace` so a reader never sees half a
    # file — the pattern `auth._write_private()` established and the reason
    # `config/` has no `write_text()` in it anywhere.
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(payload)
    os.replace(tmp, path)
    return path


# ── reading one release ────────────────────────────────────────────────────


def _redact(text: str) -> str:
    return _CREDENTIAL_PARAM.sub(lambda m: f"{m.group(1)}=<redacted>", text)


def _where(cfg: ProwlarrConfig) -> str:
    """The address, for a log line — scheme, host and port and nothing else.

    `cfg.url` already has no path or query (see `_clean_url`), so this is
    belt and braces. It is here because every message in this module ends up
    in `routers/store.py`'s warning, and a module that formats its own
    addresses in one place cannot grow a second one that formats them wrong.
    """
    return _redact(cfg.url)


def _alternation(terms: tuple[str, ...]) -> re.Pattern[str] | None:
    r"""One pattern that finds any of these names, whole-word, longest first.

    Two properties, both load-bearing:

      · the boundaries are lookarounds rather than `\b`, because several terms
        end in a digit or a hyphen (`32X`, `SG-1000`, `TurboGrafx-16`) where
        `\b` sits in a different place than the eye does;
      · the alternatives are sorted longest first, so at any one position the
        match is the **longest** name that starts there — `PlayStation 3`
        rather than `PlayStation`. Python's alternation is leftmost-first and
        not longest-first, so this ordering is what makes the comparison in
        `_ConsoleNames.claims()` measure what it says it measures.
    """
    if not terms:
        return None
    body = "|".join(re.escape(t.lower()) for t in
                    sorted(terms, key=len, reverse=True))
    return re.compile(rf"(?<!\w)(?:{body})(?!\w)")


def _longest(pattern: re.Pattern[str] | None, haystack: str) -> str:
    """The longest of this pattern's matches, or "" when it has none."""
    if pattern is None:
        return ""
    return max((m.group(0) for m in pattern.finditer(haystack)),
               key=len, default="")


def _words(term: str) -> tuple[str, ...]:
    """`"Sega Mega-CD"` → `("sega", "mega", "cd")`.

    Split on everything that is not a letter or a digit, so that a name is
    compared by the words it is made of and not by its punctuation: nothing
    should turn on whether a release writes `Mega-CD`, `Mega CD` or `MegaCD`
    — only the first two are caught by this, which is the honest limit and is
    the same one `_alternation()` has.
    """
    return tuple(re.findall(r"[a-z0-9]+", term.lower()))


def _completed_by(term: str, others: tuple[str, ...]) -> bool:
    """Is `term` a *part* of some longer name in this catalogue?

    True when another console name contains this one word for word and says
    more: `PlayStation` is completed by `PlayStation 3`, `Wii` by `Wii U`, `DS`
    by `Nintendo DS`, `Sega Mega Drive` by `Sega Mega Drive 32X`. False for
    `PlayStation 3`, `Wii U`, `Nintendo 64`, `MAME` — nothing in the catalogue
    extends those, so a release that carries one has named a machine and not an
    abbreviation of several.

    Word-for-word and not substring: `NES` must not be read as a part of
    `SNES`, and `DS` must not be read as a part of `Nintendo 3DS`. Those are
    different machines whose short names happen to share letters, which is
    exactly the confusion this function exists to keep out.
    """
    mine = _words(term)
    if not mine:
        return False
    for other in others:
        theirs = _words(other)
        if len(theirs) <= len(mine):
            continue
        if any(theirs[i:i + len(mine)] == mine
               for i in range(len(theirs) - len(mine) + 1)):
            return True
    return False


@dataclass(frozen=True)
class _ConsoleNames:
    """Whether a release names *this* console, or only something it is part of.

    Built once per search and asked once per row. Three fields, and the middle
    one is the whole correction:

    ``own``       the names this console goes by (`console_terms`).
    ``complete``  those of them no other name in the catalogue extends. A
                  release carrying one of these has named this machine.
    ``rivals``    every name the other thirty consoles go by
                  (`SearchSystem.rival_terms`).

    **The rule.** A row names this console when it carries one of `own`, and
    that name is either complete, or the most specific console name on the row.
    An abbreviation loses to a fuller name: `PlayStation` is not evidence of a
    PlayStation 1 game on a row that says `PlayStation 3`, and a bare `DS` is
    not evidence of a Nintendo DS game on a row that says `PlayStation 3`
    either. Length in characters is the measure of "more specific", and a tie
    keeps both — two consoles named equally precisely on one row is a row about
    two consoles, and dropping it for both would be inventing an answer.

    **Why it is not the first rule.** It replaces one that compared this
    console's names and nothing else, which looked right and was measured
    wrong: on 110 rows from a real indexer, `duckstation` kept every one of the
    seven `gran turismo` rows, `Gran Turismo 6 - PlayStation 3` included,
    because `PlayStation` is a whole word inside `PlayStation 3`. Same fault,
    same measurement, for `dolphin` on `Wii U` and `melonds` on any stray `DS`.
    A player on the PlayStation 1 screen was being offered games that no
    PlayStation 1 emulator can run: the import would have worked, the tile
    would have appeared, and the screen would have stayed black.
    """

    own: re.Pattern[str]
    complete: frozenset[str]
    rivals: re.Pattern[str] | None

    def claims(self, haystack: str) -> bool:
        # The longest of this console's names the row carries: `PlayStation 2`
        # rather than `PlayStation` where a pack declares both.
        best = _longest(self.own, haystack)
        if not best:
            return False                      # nothing here names us at all
        if best in self.complete:
            return True                       # …and what it names is a machine
        # An abbreviation. It still proves the console when nothing else on the
        # row is named more precisely — `Crash Bandicoot - PlayStation` is a
        # PlayStation 1 release and must stay one.
        return len(_longest(self.rivals, haystack)) <= len(best)


def _console_names(system: SearchSystem) -> _ConsoleNames | None:
    """The matcher for one console, or `None` when the pack names none.

    `complete` is computed against this console's own names *and* its rivals,
    because both kinds of completion exist: `Wii` is completed by another
    console's `Wii U`, and `Mega Drive` by its own pack's `Sega Mega Drive`.

    A `SearchSystem` built by hand carries no `rival_terms` and therefore has
    no rivals to lose to — every one of its names counts as complete, which is
    what the filter did before any of this and the least surprising thing for a
    console that does not know its neighbours exist.
    """
    own = console_terms(system)
    pattern = _alternation(own)
    if pattern is None:
        return None
    catalogue = (*own, *system.rival_terms)
    return _ConsoleNames(
        own=pattern,
        complete=frozenset(t.lower() for t in own
                           if not _completed_by(t, catalogue)),
        rivals=_alternation(system.rival_terms),
    )


def _suffix_pattern(system: SearchSystem) -> re.Pattern[str] | None:
    """`.z64` and the like — the suffixes only this console declares.

    **Measured inert against the sources this box can reach, and kept anyway.**
    Across 110 rows from a real Prowlarr — `gran turismo`, `street fighter`,
    `mario` — this band fired zero times, on every console: those indexers name
    a release `Title - Platform` and carry no file extension at all, so every
    row that survives today survives on its name. That is a fact about one
    owner's indexers and not about the rule: a release named
    `Super Mario 64 (USA).z64` is still the only kind of evidence here that
    cannot be wrong, other sources do name files, and `fileName` is a field
    Prowlarr answers. Deleting the band would cost that for nothing, so it
    stays — and knowing it is idle is what makes the name band's precision the
    thing worth being careful about.
    """
    if not system.unique_suffixes:
        return None
    body = "|".join(re.escape(s.lower()) for s in system.unique_suffixes)
    return re.compile(rf"\.(?:{body})(?!\w)")


#: How strongly a row is tied to the console, biggest first. Only the ordering
#: matters and only two values exist: a suffix only this console declares, and
#: a name it goes by.
_BY_SUFFIX, _BY_NAME, _NONE = 2, 1, 0


def _suffix_of(name: str, system: SearchSystem) -> str:
    """The row's format, or "" when the name does not carry one.

    Recognised, never inferred. A suffix counts when the console declares it or
    when it is an archive an indexer serves; anything else — including a
    release named "… 1080p" or "… v1.02" whose last dotted group looks like an
    extension — is not a format and is left empty. `search.SearchResult.format`
    documents why empty is a real answer here and not a gap.
    """
    suffix = Path(name).suffix.lstrip(".").lower()
    if not suffix or suffix in NEVER_OFFERED:
        return ""
    if suffix in system.suffixes or suffix in _ARCHIVES:
        return suffix
    return ""


def _region_and_languages(title: str) -> tuple[str, tuple[str, ...]]:
    """`(USA)` and `(En,Fr,De)`, when the release names them."""
    region, langs = "", ()
    for group in _BRACKETED.findall(title):
        body = group.strip()
        if not region and body.lower() in _REGIONS:
            region = _REGIONS[body.lower()]
            continue
        parts = [p.strip().lower() for p in body.split(",") if p.strip()]
        if not langs and parts and all(p in _LANG_CODES for p in parts):
            langs = tuple(parts)
    return region, langs


def _result_from(row: object, system: SearchSystem,
                 names: _ConsoleNames | None,
                 suffixes: re.Pattern[str] | None) -> tuple[int, SearchResult] | None:
    """One release, as a `SearchResult` — or `None` when it is not one for us.

    Returns the evidence strength alongside, so the caller can rank without
    asking twice. `None` means either the row is not usable at all or nothing
    about it names this console, and the two are deliberately the same answer:
    both end with the row not on screen.
    """
    if not isinstance(row, dict):
        return None
    title = row.get("title") or row.get("fileName")
    if not isinstance(title, str) or not title.strip():
        return None
    title = _redact(re.sub(r"\s+", " ", title.strip()))
    filename = row.get("fileName")
    filename = _redact(filename.strip()) if isinstance(filename, str) and \
        filename.strip() else title

    haystack = f"{title} {filename}".lower()
    if suffixes is not None and suffixes.search(haystack):
        evidence = _BY_SUFFIX
    elif names is not None and names.claims(haystack):
        evidence = _BY_NAME
    else:
        return None

    try:
        size = max(0, int(row.get("size") or 0))
    except (TypeError, ValueError):
        size = 0

    # The locator, and the one field a leak would travel in. Prowlarr's
    # `downloadUrl` and `magnetUrl` carry the box's own key as a query
    # parameter, so neither is used whole: the indexer id and the release guid
    # say the same thing and carry nothing. Redacted anyway, because a guid is
    # whatever the indexer chose to put there.
    guid = row.get("guid")
    guid = guid if isinstance(guid, str) and guid.strip() else filename
    indexer = row.get("indexerId")
    indexer = indexer if isinstance(indexer, int) else 0
    # …and the one thing the pair turned out not to be able to do without.
    # `(indexerId, guid)` is a key into a cache Prowlarr expires, not a
    # locator — `resolve.py` holds the measurement — so the info hash rides
    # along as a `#btih:` suffix. It is 20 bytes saying what the content *is*:
    # no key, no session, no passkey, and it does not go stale the way a queue
    # row must not. `info_hash_of` takes the hash out of a `magnetUrl` and
    # leaves the tracker list, which on a private tracker carries the owner's
    # own passkey, behind.
    source = _redact(resolve.stamp(f"prowlarr://{indexer}/{guid.strip()}",
                                   resolve.info_hash_of(row)))

    fmt = _suffix_of(filename, system)
    region, languages = _region_and_languages(title)
    display = title[:-(len(fmt) + 1)] if fmt and title.lower().endswith(
        f".{fmt}") else title
    return evidence, SearchResult(
        id=f"prowlarr:{system.id}:"
           f"{hashlib.blake2b(source.encode(), digest_size=6).hexdigest()}",
        title=display or title,
        filename=filename,
        format=fmt,
        size=size,
        system_id=system.id,
        provider=ProwlarrSearchProvider.name,
        source=source,
        region=region,
        languages=languages,
    )


# ── the provider ───────────────────────────────────────────────────────────


class ProwlarrSearchProvider:
    """Real rows, from an indexer this box does not own."""

    name = "prowlarr"
    label = "Prowlarr"
    live = True

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        # Tests only, and the only seam this class has. It exists because the
        # alternative is a test that either reaches an indexer or patches
        # httpx globally, and `search.get_provider()` never passes it.
        self._transport = transport

    @classmethod
    def configured(cls) -> bool:
        """Whether this box has a URL and a key for an instance.

        `get_provider()` asks before choosing, so an unconfigured box lands on
        the demo provider and its banner instead of on a client that can only
        answer 502.
        """
        return load_config() is not None

    async def search(self, system: SearchSystem, query: str,
                     limit: int = 40) -> list[SearchResult]:
        cfg = load_config()
        if cfg is None:
            # Only reachable if the file went away between `configured()` and
            # here, or if something constructed this provider directly.
            raise ProwlarrError(f"no usable {CONFIG_FILENAME}")

        cleaned = query.strip()
        if not cleaned:
            return []

        rows = await self._get(cfg, cleaned)
        # Built once and asked once per row: both patterns are alternations
        # over every name in the catalogue, and compiling them per row would
        # be a hundred compilations of the same thing.
        names, suffixes = _console_names(system), _suffix_pattern(system)
        scored = [s for s in (_result_from(r, system, names, suffixes)
                              for r in rows) if s is not None]
        # Suffix-backed rows above name-only ones, and Prowlarr's own order
        # kept inside each band — `sorted` is stable, and the indexer's
        # ranking is a better tiebreak than anything invented here.
        scored.sort(key=lambda s: -s[0])
        kept = [r for _, r in scored][:max(0, limit)]
        log.info("store: prowlarr answered %d rows for %r, %d for %s",
                 len(rows), cleaned, len(kept), system.id)
        return kept

    async def _get(self, cfg: ProwlarrConfig, query: str) -> list:
        """The one request, and every way it can fail.

        Every branch raises `ProwlarrError` with a message safe to log, which
        is the half of the 502 contract that lives here: `routers/store.py`
        logs the reason and returns a generic answer precisely because the
        reason *could* carry a URL or a key, and it is this function's job that
        it never does.
        """
        params: dict[str, object] = {
            "query": query,
            # `search` and not `tvsearch`/`moviesearch`: the typed ones make
            # the indexer expect a season or a year, and a ROM release has
            # neither.
            "type": "search",
            "limit": _FETCH,
            "offset": 0,
        }
        if cfg.indexer_ids:
            params["indexerIds"] = list(cfg.indexer_ids)
        if cfg.categories:
            params["categories"] = list(cfg.categories)

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(cfg.timeout),
                # Never followed. A redirect would carry the `X-Api-Key`
                # header to whatever host the redirect named, which is a
                # credential handed to a third party by a configuration
                # mistake — or by an instance somebody else can reconfigure.
                follow_redirects=False,
                transport=self._transport,
            ) as client:
                r = await client.get(
                    f"{cfg.url}/api/v1/search",
                    params=params,
                    # In the header and never in the query string: a URL is
                    # what proxies log, what shells keep in history, and what
                    # an exception prints.
                    headers={"X-Api-Key": cfg.api_key,
                             "Accept": "application/json"},
                )
        except httpx.TimeoutException:
            raise ProwlarrError(
                f"{_where(cfg)} did not answer within {cfg.timeout:g}s") from None
        except httpx.HTTPError as e:
            # Message deliberately not interpolated: httpx puts the full
            # request URL in some of these, and this one is on its way to a
            # log line.
            raise ProwlarrError(
                f"{_where(cfg)} could not be reached "
                f"({type(e).__name__})") from None

        if r.status_code in (401, 403):
            raise ProwlarrError(
                f"{_where(cfg)} refused the API key (HTTP {r.status_code})")
        if r.status_code == 404:
            raise ProwlarrError(
                f"{_where(cfg)} has no /api/v1/search — is that URL the "
                "Prowlarr root?")
        if r.status_code >= 300:
            # 3xx included: redirects are not followed, so one arriving here
            # is a misconfiguration rather than a step on the way somewhere.
            raise ProwlarrError(f"{_where(cfg)} answered HTTP {r.status_code}")

        try:
            body = r.json()
        except ValueError:
            raise ProwlarrError(
                f"{_where(cfg)} answered something that is not JSON") from None
        if not isinstance(body, list):
            raise ProwlarrError(
                f"{_where(cfg)} answered JSON that is not a list of releases")
        return body
