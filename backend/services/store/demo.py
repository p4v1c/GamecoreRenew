"""The demo search provider — the only one, and it invents everything.

It reaches nothing. No network, no credentials, no indexer. It exists so that
the Games tab can be built, navigated and tested against the shape a real
provider will have, and so that the shape is exercised by rows that vary the
way real ones do rather than by three identical placeholders.

**It says so about itself.** `live = False` travels with every answer and the
tab prints it. A store that invented plausible rows and looked exactly like
one with a real indexer behind it would be worse than the honest empty state
it replaces — the player would press ✕ on a game that does not exist.

── What "varied and realistic" is for ─────────────────────────────────────
The formats are drawn from the console's **own** declared extensions plus the
two archives every indexer serves, which is what makes the rows useful ahead
of the ingestion steps rather than merely decorative. Reading a search for
`nes` gives both `.nes` and `.zip`, and those are two different ingestion
classes of the same game (matrix §5.1 A: `nes` does not declare `*.zip`, so
that archive must be unpacked or the download is silently wasted). The same
search on `mame` gives `.zip` only, and there the archive **is** the ROM and
unpacking it deletes the game (§2.1). Nothing here classifies anything — that
is steps 14 to 17 — but the material those steps need is already on screen.

── Deterministic ──────────────────────────────────────────────────────────
The same (console, query) yields the same rows, on every box and every run.
Not for caching — nothing caches these — but so a test can assert on a row
and a second search does not reshuffle the list under a cursor that is
standing on one. The randomness is a hash chain rather than `random.Random`:
the values then depend on nothing but the digest, which is a promise the
standard library does not make about its own generator's internals.
"""
from __future__ import annotations

import hashlib
import re

from .search import NEVER_OFFERED as _NEVER_OFFERED
from .search import SearchResult, SearchSystem

_MIB = 1024 * 1024
_GIB = 1024 * _MIB


class _Dice:
    """A deterministic stream of numbers, seeded by the search itself."""

    def __init__(self, *parts: str) -> None:
        self._seed = hashlib.blake2b("\x00".join(parts).encode(),
                                     digest_size=32).digest()
        self._n = 0

    def _next(self) -> int:
        self._n += 1
        return int.from_bytes(
            hashlib.blake2b(self._seed + self._n.to_bytes(4, "big"),
                            digest_size=8).digest(), "big")

    def below(self, n: int) -> int:
        return self._next() % max(1, n)

    def between(self, lo: int, hi: int) -> int:
        return lo + self.below(hi - lo + 1)

    def pick(self, seq):
        return seq[self.below(len(seq))]


# ── what a row is dressed with ─────────────────────────────────────────────

#: " - " and never ": ", which is what real releases do and for the same
#: reason `_UNSAFE` below rejects a colon: the external disks these land on are
#: exFAT and NTFS in practice, and neither will take one in a filename. Spelled
#: correctly here rather than generated and then dropped by the guard — which
#: is what happened first, and quietly cost a third of every result list.
_EDITIONS = ("", "", "", "", " 2", " 3", " - Deluxe Edition",
             " - Anniversary Edition", " Collection", " DX")
_REGIONS = ("USA", "Europe", "Japan", "World", "USA, Europe", "Japan, USA")
_REVISIONS = ("", "", "", "", " (Rev 1)", " (Rev A)", " (v1.1)")
_LANGS = {
    "USA": ("en",), "Europe": ("en", "fr", "de"), "Japan": ("ja",),
    "World": ("en", "fr", "de", "es", "it"), "USA, Europe": ("en", "fr"),
    "Japan, USA": ("ja", "en"),
}

#: Every archive an indexer serves, declared by the pack or not. Offering one
#: a console does not declare is the point rather than an oversight: that is
#: the case the matrix calls the one that bites (§2.3), and the Games tab has
#: to be able to show it long before anything can unpack it.
_ARCHIVES = ("zip", "7z")

#: Extensions that name a disc **set** rather than a file — a `.cue` is two
#: hundred bytes and the dump beside it is six hundred megabytes. An indexer
#: lists the set, so these are sized as the set, which is also what class E
#: has to keep together (§5.1).
_DESCRIPTORS = ("cue", "gdi", "ccd", "mds", "toc", "m3u")

# Declared, and never offered — `_NEVER_OFFERED` is `search.NEVER_OFFERED`,
# imported above. `*.cmd` is in `catalog/mame/pack.json` and is explained
# nowhere in this repository; matrix §6.4 is explicit that until somebody knows
# what it is, "the Store should neither produce nor rewrite one". Inventing a
# plausible `.cmd` in a demo row is exactly producing one, and the Prowlarr
# provider must not read one as proof a release is an arcade romset — one rule,
# two readers, so it lives beside the interface rather than here.

#: Plausible sizes, in bytes, per bare suffix. A range rather than a number:
#: two results for the same console must not all weigh the same, or the one
#: column a player actually compares is a constant.
_SIZES: dict[str, tuple[int, int]] = {
    "nes": (16 * 1024, 1 * _MIB), "unf": (16 * 1024, 1 * _MIB),
    "unif": (16 * 1024, 1 * _MIB), "fds": (64 * 1024, 192 * 1024),
    "sms": (32 * 1024, 1 * _MIB), "bms": (32 * 1024, 1 * _MIB),
    "gg": (32 * 1024, 1 * _MIB), "sg": (16 * 1024, 256 * 1024),
    "sgd": (16 * 1024, 256 * 1024),
    "md": (128 * 1024, 8 * _MIB), "mdx": (128 * 1024, 8 * _MIB),
    "smd": (128 * 1024, 8 * _MIB), "gen": (128 * 1024, 8 * _MIB),
    "68k": (128 * 1024, 8 * _MIB), "32x": (512 * 1024, 4 * _MIB),
    "pce": (64 * 1024, 4 * _MIB), "sgx": (256 * 1024, 4 * _MIB),
    "sfc": (256 * 1024, 6 * _MIB), "smc": (256 * 1024, 6 * _MIB),
    "fig": (256 * 1024, 6 * _MIB), "swc": (256 * 1024, 6 * _MIB),
    "bs": (256 * 1024, 2 * _MIB), "gd3": (256 * 1024, 6 * _MIB),
    "jma": (192 * 1024, 4 * _MIB), "gz": (192 * 1024, 4 * _MIB),
    "gb": (32 * 1024, 1 * _MIB), "gbc": (128 * 1024, 2 * _MIB),
    "gba": (4 * _MIB, 32 * _MIB),
    "nds": (16 * _MIB, 512 * _MIB),
    "3ds": (64 * _MIB, 4 * _GIB), "cia": (32 * _MIB, 2 * _GIB),
    "n64": (4 * _MIB, 64 * _MIB), "z64": (4 * _MIB, 64 * _MIB),
    "v64": (4 * _MIB, 64 * _MIB),
    "iso": (400 * _MIB, 8 * _GIB), "gcm": (1 * _GIB, 1 * _GIB + 400 * _MIB),
    "rvz": (900 * _MIB, 5 * _GIB), "wbfs": (900 * _MIB, 4 * _GIB),
    "wad": (8 * _MIB, 256 * _MIB), "wux": (1 * _GIB, 12 * _GIB),
    "rpx": (600 * _MIB, 8 * _GIB),
    "chd": (100 * _MIB, 3 * _GIB), "cdi": (400 * _MIB, 1200 * _MIB),
    "bin": (100 * _MIB, 700 * _MIB), "img": (100 * _MIB, 700 * _MIB),
    "cso": (200 * _MIB, 1400 * _MIB), "pbp": (100 * _MIB, 1500 * _MIB),
    "xci": (500 * _MIB, 16 * _GIB), "nsp": (300 * _MIB, 12 * _GIB),
    "xex": (100 * _MIB, 2 * _GIB),
    "cmd": (256, 4096),
}
_DEFAULT_SIZE = (8 * _MIB, 900 * _MIB)
#: A dumped disc set, for the descriptor formats above. Every pack that
#: declares one of them is a CD or GD-ROM console, so the range is a disc.
_SET_SIZE = (180 * _MIB, 1200 * _MIB)
#: A `scanDirs` game, which is a directory of thousands of files (§5.1 F).
_FOLDER_SIZE = (2 * _GIB, 50 * _GIB)
#: What an archive of the same game weighs, as a fraction of it. Percent,
#: because the draw is integer arithmetic on a hash.
_ARCHIVE_PCT = (55, 80)

#: Formats whose size does not follow the console they are on. One entry: a
#: `.wad` beside dolphin's discs is a Virtual Console title and weighs what a
#: Mega Drive cartridge weighs, not what a Wii disc does.
_OWN_SCALE: dict[str, tuple[int, int]] = {"wad": (8 * _MIB, 256 * _MIB)}

#: Characters a filename may not carry — a result whose name could not be
#: written flat into `<DATA>/emu/<dir>/` is not a row worth offering.
_UNSAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def _title_case(query: str) -> str:
    """The player's typing, as a release would spell it."""
    words = [w for w in re.split(r"\s+", query.strip()) if w]
    return " ".join(w if w.isupper() else w[:1].upper() + w[1:] for w in words)


def _plain(system: SearchSystem) -> list[str]:
    """The console's own non-archive extensions, in the order it declared them."""
    return [s for s in system.suffixes
            if s not in _ARCHIVES and s not in _NEVER_OFFERED]


def _format_pool(system: SearchSystem) -> list[str]:
    """The formats this console's results may arrive in, weighted.

    Weighted rather than uniform, by repeating entries: a console's first
    declared extension is what most of its dumps are, and drawing evenly from
    five formats produced an NES search whose three results were all archives.

    The archives are offered **whether the pack declares them or not**, and
    that is the point rather than an oversight: an indexer serves `.zip`, and
    for the sixteen packs that do not declare it the download must be unpacked
    or it is silently wasted (matrix §2.3). The tab has to be able to show
    that row long before anything can act on it.
    """
    if system.scan_dirs:
        # `rpcs3` and `shadps4` declare no extensions at all, and the game is
        # the directory. An archive is still what an indexer hands over, so
        # both shapes are offered.
        return ["folder"] * 4 + list(_ARCHIVES)
    pool: list[str] = []
    for i, suffix in enumerate(_plain(system)):
        pool += [suffix] * (4 if i == 0 else 2)
    pool += [a for a in _ARCHIVES if a in system.suffixes] or list(_ARCHIVES)
    return pool


def _base_size(system: SearchSystem) -> tuple[int, int]:
    """What a game weighs on this console.

    Taken from the console's **first** declared extension and then used for
    every format it offers, rather than from a per-format table. The reason is
    that the generic containers mean different things on different machines: a
    `.iso` is 650 MB on a PS1 and 8 GB on an Xbox 360, and a per-extension
    table answered 8 GB for both. The first extension a pack declares is the
    medium it is really about, so one lookup fixes the whole console.
    """
    if system.scan_dirs:
        # No extensions at all to read it from — the game is the directory,
        # and an archive of it weighs a fraction of one.
        return _FOLDER_SIZE
    plain = _plain(system)
    if not plain:
        return _DEFAULT_SIZE
    if plain[0] in _DESCRIPTORS:
        # `saturn`, `megacd` and `pcenginecd` lead with a descriptor, which
        # names the disc rather than being it — so the disc is the scale.
        return _SET_SIZE
    return _SIZES.get(plain[0], _DEFAULT_SIZE)


def _size_for(system: SearchSystem, fmt: str, dice: _Dice) -> int:
    if fmt == "folder":
        lo, hi = _FOLDER_SIZE
    elif fmt in _DESCRIPTORS:
        lo, hi = _SET_SIZE
    elif fmt in _ARCHIVES:
        # The same game, compressed — derived from the console's own scale so
        # it stays plausible beside the plain file it is listed next to.
        lo, hi = _base_size(system)
        pct = dice.between(*_ARCHIVE_PCT)
        lo, hi = lo * pct // 100, hi * pct // 100
    else:
        # The console's scale, not the format's. Every plain format a pack
        # declares is the same medium — dolphin's `.iso`, `.gcm`, `.rvz` and
        # `.wbfs` are four spellings of one disc — so looking the suffix up
        # again here is what put an 8 GB `.iso` on a PlayStation 1.
        #
        # `_OWN_SCALE` is the exception, and it is one line long because there
        # is one: a `.wad` on dolphin is a Virtual Console title, not a disc.
        lo, hi = _OWN_SCALE.get(fmt) or _base_size(system)
    return dice.between(lo, max(lo, hi))


class DemoSearchProvider:
    """Results that are not real, and that say so."""

    name = "demo"
    label = "Demo results"
    live = False

    async def search(self, system: SearchSystem, query: str,
                     limit: int = 40) -> list[SearchResult]:
        cleaned = query.strip()
        # Nothing to make a title out of. A real provider answers empty here
        # too, and the tab needs that state to exist before step 10 produces
        # it for real.
        if not re.search(r"[0-9A-Za-z]", cleaned):
            return []

        dice = _Dice(system.id, cleaned.lower())
        formats = _format_pool(system)
        base = _title_case(cleaned)
        rows: list[SearchResult] = []
        seen: set[str] = set()

        for _ in range(min(limit, dice.between(3, 9))):
            title = f"{base}{dice.pick(_EDITIONS)}"
            region = dice.pick(_REGIONS)
            fmt = dice.pick(formats)
            stem = f"{title} ({region}){dice.pick(_REVISIONS)}"
            filename = stem if fmt == "folder" else f"{stem}.{fmt}"
            if _UNSAFE.search(filename):
                continue
            # The same title in the same format twice is an indexer listing
            # the same upload twice, which is noise a player cannot act on.
            if filename.lower() in seen:
                continue
            seen.add(filename.lower())
            rows.append(SearchResult(
                id=f"{self.name}:{system.id}:"
                   f"{hashlib.blake2b(filename.encode(), digest_size=6).hexdigest()}",
                title=title,
                filename=filename,
                format=fmt,
                size=_size_for(system, fmt, dice),
                system_id=system.id,
                provider=self.name,
                # Deliberately not a URL. Nothing dereferences it, and a
                # scheme no client can follow is the honest spelling of that.
                source=f"demo://{system.id}/{filename}",
                region=region,
                languages=_LANGS.get(region, ("en",)),
            ))
        return rows
