"""The name a bezel is filed under, against fifty filenames from real libraries.

A Bezel Project pack is a directory of PNGs named the way No-Intro and Redump
name their dumps — `Crash Bandicoot (USA).png`. A library is a directory of
ROMs named the same way, except when it is not: the same game arrives as
`(USA)` or `(Europe)`, with `(Disc 1)` or without, as `(Rev 1)` or `(v1.6)`,
and from a GoodTools era that wrote `(U) [!]`. Match on the raw filename and
roughly a third of a real library resolves nothing and falls through to the
system bezel, which looks exactly like the feature not existing.

So the table below is filenames, not a regex somebody believed in. Each row is
a ROM as it sits on a disk and the pack filename it has to reach, and the two
have to produce one string. They are real names; the awkward ones are here
because they are the ones that break — the moved article of
`Legend of Zelda, The`, the apostrophe of `Conker's`, the roman numeral of
`Suikoden II`, the MAME short name that is not a title at all.

`rom_key` is `parse_rom` + `normalize` from the scraper's parser and nothing
else. That is the point: a ROM's identity has to be one answer. A file that
scrapes as one game and resolves a bezel as another would be two bugs wearing
each other's clothes.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.services.bezels import rom_key


# (ROM on disk, PNG in the pack) — the two must land on the same key.
PAIRS: list[tuple[str, str]] = [
    # ── PlayStation, where the Bezel Project's coverage is strongest ────────
    ("Crash Bandicoot (USA).cue", "Crash Bandicoot (USA).png"),
    ("Crash Bandicoot 2 - Cortex Strikes Back (USA).cue",
     "Crash Bandicoot 2 - Cortex Strikes Back (USA).png"),
    # A multi-disc game is one bezel. Disc 2 of Final Fantasy VII must not
    # resolve nothing just because the pack only ever ships one file.
    ("Final Fantasy VII (USA) (Disc 1).chd", "Final Fantasy VII (USA).png"),
    ("Metal Gear Solid (USA) (Disc 1) (Rev 1).chd", "Metal Gear Solid (USA).png"),
    ("Gran Turismo 2 (USA) (Arcade Mode) (Disc 1).chd", "Gran Turismo 2 (USA).png"),
    ("Resident Evil 2 (USA) (Disc 1) (Leon).chd", "Resident Evil 2 (USA).png"),
    # Region differs on the two sides — the usual case for a European library
    # against an American pack, and the one that must not be a miss.
    ("Tekken 3 (Europe).chd", "Tekken 3 (USA).png"),
    ("Spyro the Dragon (USA).cue", "Spyro the Dragon (USA).png"),
    ("Tony Hawk's Pro Skater 2 (USA).cue", "Tony Hawk's Pro Skater 2 (USA).png"),
    ("Castlevania - Symphony of the Night (USA).cue",
     "Castlevania - Symphony of the Night (USA).png"),
    ("Legend of Dragoon, The (USA) (Disc 1).chd", "Legend of Dragoon, The (USA).png"),
    ("Vagrant Story (USA).chd", "Vagrant Story (USA).png"),
    ("Chrono Cross (USA) (Disc 1).chd", "Chrono Cross (USA).png"),
    ("Silent Hill (USA).cue", "Silent Hill (USA).png"),
    ("Driver 2 (USA) (Disc 1).chd", "Driver 2 (USA).png"),
    ("WipEout 3 (Europe) (En,Fr,De,Es,It).chd", "WipEout 3 (Europe).png"),
    ("R-Type Delta (USA).chd", "R-Type Delta (USA).png"),
    ("Um Jammer Lammy (USA).chd", "Um Jammer Lammy (USA).png"),
    # "Bug's Life, A" is the catalogue spelling of "A Bug's Life": the article
    # moves to the front of its own segment before anything else happens.
    ("Bug's Life, A (USA).chd", "Bug's Life, A (USA).png"),
    ("Devil Dice (USA).chd", "Devil Dice (USA).png"),
    ("Croc - Legend of the Gobbos (USA).chd", "Croc - Legend of the Gobbos (USA).png"),
    ("Mega Man X4 (USA).chd", "Mega Man X4 (USA).png"),
    ("Suikoden II (USA).chd", "Suikoden II (USA).png"),
    # A version tag is not part of the name. `(v1.6)` and `(Rev 1)` are the
    # same statement written by two different dumping groups.
    ("Tomb Raider (USA) (v1.6).chd", "Tomb Raider (USA).png"),
    ("Ape Escape (USA).cue", "Ape Escape (USA).png"),

    # ── Nintendo 64 ────────────────────────────────────────────────────────
    ("Legend of Zelda, The - Ocarina of Time (USA) (Rev 2).z64",
     "Legend of Zelda, The - Ocarina of Time (USA).png"),
    ("Super Mario 64 (USA).z64", "Super Mario 64 (USA).png"),
    ("GoldenEye 007 (USA).z64", "GoldenEye 007 (USA).png"),
    ("Mario Kart 64 (USA).n64", "Mario Kart 64 (USA).png"),
    ("Banjo-Kazooie (USA) (Rev 1).z64", "Banjo-Kazooie (USA).png"),
    ("Paper Mario (USA).z64", "Paper Mario (USA).png"),
    ("Star Fox 64 (USA) (Rev 1).z64", "Star Fox 64 (USA).png"),
    ("Perfect Dark (USA) (Rev 1).z64", "Perfect Dark (USA).png"),
    ("Conker's Bad Fur Day (USA).z64", "Conker's Bad Fur Day (USA).png"),
    ("Legend of Zelda, The - Majora's Mask (USA).z64",
     "Legend of Zelda, The - Majora's Mask (USA).png"),

    # ── Game Boy Advance ───────────────────────────────────────────────────
    ("Pokemon - Emerald Version (USA, Europe).gba",
     "Pokemon - Emerald Version (USA, Europe).png"),
    ("Pokemon - FireRed Version (USA).gba", "Pokemon - FireRed Version (USA).png"),
    ("Advance Wars (USA).gba", "Advance Wars (USA).png"),
    ("Metroid Fusion (USA, Australia).gba", "Metroid Fusion (USA).png"),
    ("Golden Sun (USA, Europe).gba", "Golden Sun (USA).png"),
    ("Mario Kart - Super Circuit (USA).gba", "Mario Kart - Super Circuit (USA).png"),
    ("Castlevania - Aria of Sorrow (USA).gba", "Castlevania - Aria of Sorrow (USA).png"),
    ("Fire Emblem (USA, Australia).gba", "Fire Emblem (USA).png"),
    # Two articles, one of which is part of the title and must survive.
    ("Legend of Zelda, The - The Minish Cap (USA).gba",
     "Legend of Zelda, The - The Minish Cap (USA).png"),
    ("Kirby - Nightmare in Dream Land (USA).gba",
     "Kirby - Nightmare in Dream Land (USA).png"),

    # ── GoodTools names, still on plenty of disks ──────────────────────────
    # `(U) [!]` predates No-Intro by a decade. A pack is named the modern way
    # and a library very often is not; this is most of the ~30 % of misses
    # that matching on the raw filename produces.
    ("Super Mario Advance 4 - Super Mario Bros. 3 (U) [!].gba",
     "Super Mario Advance 4 - Super Mario Bros. 3 (USA).png"),
    ("Pokemon - Emerald Version (U) [!].gba",
     "Pokemon - Emerald Version (USA, Europe).png"),
    ("Legend of Zelda, The - A Link to the Past (U) [!].smc",
     "Legend of Zelda, The - A Link to the Past (USA).png"),

    # ── Arcade, where the filename is not a title ──────────────────────────
    # A MAME set is identified by its short name and the pack follows. Nothing
    # here should be "corrected" into English.
    ("sf2ce.zip", "sf2ce.png"),
    ("mslug3.zip", "mslug3.png"),
]


@pytest.mark.parametrize("rom,bezel", PAIRS, ids=[p[0] for p in PAIRS])
def test_a_rom_and_its_bezel_land_on_one_key(rom: str, bezel: str):
    assert rom_key(rom) == rom_key(bezel), (
        f"{rom!r} would not find {bezel!r} — the cascade falls through to the "
        f"system bezel and the per-game pack looks like it did nothing")


def test_the_table_is_the_fifty_names_the_phase_asked_for():
    """A table that quietly shrinks stops being evidence."""
    assert len(PAIRS) == 50


def test_a_key_is_never_empty():
    """An empty key collides with every other empty key, so the first PNG in
    the directory would answer for every game whose name normalised away."""
    for rom, bezel in PAIRS:
        assert rom_key(rom), rom
        assert rom_key(bezel), bezel


def test_different_games_do_not_share_a_key():
    """A collision is not a miss — it is the wrong bezel, confidently drawn.

    The one repeat is deliberate: Emerald appears twice, once No-Intro and
    once GoodTools, and those two ARE the same game.
    """
    counts = Counter(rom_key(rom) for rom, _ in PAIRS)
    repeated = {k: c for k, c in counts.items() if c > 1}
    assert repeated == {"pokemonemeraldversion": 2}, repeated


def test_region_revision_and_disc_are_the_only_things_that_move():
    """The tags that vary between a library and a pack, and nothing else.

    Written as one game wearing every tag it is ever found with: if any of
    these stopped being stripped, the pack would resolve for the copy someone
    happened to dump and not for the copy someone else did.
    """
    same = [
        "Silent Hill (USA).cue",
        "Silent Hill (Europe).cue",
        "Silent Hill (Japan).bin",
        "Silent Hill (USA) (Rev 1).chd",
        "Silent Hill (USA) (v1.1).chd",
        "Silent Hill (USA) (Disc 1).chd",
        "Silent Hill (USA) (En,Fr,De).chd",
        "Silent Hill (U) [!].bin",
        "Silent Hill [SLUS-00707].bin",
        "silent hill (usa).CUE",
    ]
    keys = {rom_key(n) for n in same}
    assert keys == {"silenthill"}, keys


def test_the_extension_is_not_part_of_the_identity():
    """The same dump re-encoded is the same game. `.cue`/`.bin`/`.chd` for one
    PlayStation title is routine, and `.nds.zip` has to lose both halves."""
    assert rom_key("Ridge Racer (USA).cue") == rom_key("Ridge Racer (USA).chd")
    assert rom_key("Ridge Racer (USA).bin") == rom_key("Ridge Racer (USA).png")
    assert rom_key("Advance Wars (USA).gba.zip") == rom_key("Advance Wars (USA).png")


def test_a_full_path_keys_the_same_as_a_bare_filename():
    """The launcher hands over `rom_path`; the pack index sees `p.name`. If
    those disagreed the index would be built under keys nothing ever asks for."""
    assert (rom_key("/home/pi/emu/duckstation/Silent Hill (USA).cue")
            == rom_key("Silent Hill (USA).cue"))


# ── Known limits, written down rather than discovered later ─────────────────

def test_a_leading_article_is_stripped_even_when_it_is_a_first_letter():
    """`Ape Escape` keys as `peescape` and `Advance Wars` as `dvancewars`.

    `normalize` removes punctuation before it looks for a leading article, so
    by then it cannot tell `a bug's life` from `ape escape`. Recorded here and
    NOT fixed in this phase: `normalize` is also what `lb_index` stores in the
    scraped-metadata database, so changing it means a `SCHEMA_VERSION` bump and
    a ~234 MB re-download on every box, unattended, for a defect that costs
    bezels nothing. Both sides of a bezel match go through the same function,
    so a symmetric mangling still matches — it is only a collision risk, and
    no pair in the table above collides.

    The test asserts the current behaviour so that fixing it is a deliberate
    act with a visible diff, not a surprise.
    """
    assert rom_key("Ape Escape (USA).cue") == "peescape"
    assert rom_key("Advance Wars (USA).gba") == "dvancewars"
    # …and the mangling is symmetric, which is why bezels still resolve.
    assert rom_key("Ape Escape (USA).cue") == rom_key("Ape Escape (USA).png")


def test_a_sanitised_filename_does_not_reach_its_pack():
    """`Crash_Bandicoot_USA.cue` keys as `crashbandicootusa`.

    A name with the parentheses stripped out has lost the only marker that
    said `USA` was a region tag and not a word. Nothing can recover it, so this
    library falls through to the system bezel — which is the correct outcome
    and not a crash, but it is worth knowing before someone reports the pack
    as broken.
    """
    assert rom_key("Crash_Bandicoot_USA.cue") != rom_key("Crash Bandicoot (USA).png")
