"""The title a disc calls itself, and the title a catalogue files it under.

A PS3, PS4 or PSP dump is identified by the `TITLE` in its PARAM.SFO, and that
title is the SHORT one. Measured on the reference box: the disc says `FIFA 19`,
LaunchBox files it as `FIFA 19: Legacy Edition`, and nothing in `find_game`
could bridge the two — `difflib` scores `fifa19` against `fifa19legacyedition`
at **0.48**, under any usable cutoff, because its ratio is penalised by the
length the two do not share. The same measure scores `FIFA 09` at **0.909**:
the right answer was the worst-rated candidate on the list, and only the
episode-number guard kept the wrong ones out.

One title in 64 on that box, and the only one that failed. And it mattered
beyond a name: ScreenScraper has NO back cover for that game in any region
(nine probed, `de` returns a chroma-key plate, the other eight return
`NOMEDIA`), so LaunchBox was the only source and the match was the only way to
reach it.

The rule is written against the danger, not against the case: the tests below
that REFUSE are the point of it. A rule that merely accepted the longest prefix
would file `Mario Party` as `Mario Party Superstars`.

Run under pytest:  pytest backend/tests/test_gamemedia_subtitle_match.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import pytest

from backend.services.gamemedia import search as S


@pytest.fixture
def db():
    """A catalogue in the shape `find_game` reads, with the traps in it."""
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE games (id INTEGER PRIMARY KEY, name TEXT, "
                "norm TEXT, platform TEXT, year INTEGER, overview TEXT, "
                "developer TEXT, publisher TEXT, genres TEXT, players TEXT, "
                "rating REAL, rating_count INTEGER, esrb TEXT, released TEXT, "
                "coop INTEGER, video_url TEXT, wiki_url TEXT)")
    con.execute("CREATE TABLE alts (gid INTEGER, norm TEXT)")
    rows = [
        # The case. Note the decoys that score HIGHER on text similarity.
        ("FIFA 19: Legacy Edition", "Sony Playstation 3"),
        ("FIFA 09", "Sony Playstation 3"),
        ("FIFA 14", "Sony Playstation 3"),
        ("FIFA 17", "Sony Playstation 3"),
        # A plain extra word is a DIFFERENT game, not a subtitle.
        ("Mario Party Superstars", "Nintendo Switch"),
        ("Mario Kart Live: Home Circuit", "Nintendo Switch"),
        # A series name with several subtitled entries under it.
        ("Uncharted: Drake's Fortune", "Sony Playstation 3"),
        ("Uncharted: Among Thieves", "Sony Playstation 3"),
        # The spaced-dash form of a subtitle.
        ("Ratchet & Clank - Size Matters", "Sony PSP"),
        # Same stem, another platform: the filter has to hold.
        ("FIFA 19: Legacy Edition", "Microsoft Windows"),
    ]
    from backend.services.gamemedia.parser import normalize
    for i, (name, plat) in enumerate(rows, start=1):
        con.execute("INSERT INTO games (id, name, norm, platform, year) "
                    "VALUES (?,?,?,?,?)", (i, name, normalize(name), plat, 2018))
    con.commit()
    return con


def look(db, title, platform, cutoff=0.72):
    parsed = {"title": title, "tags": [], "systems": [platform]}
    return S.find_game(db, parsed, [platform], cutoff)


# ── the case it exists for ───────────────────────────────────────────────────

def test_a_disc_that_calls_itself_the_short_title_is_found(db):
    game, score = look(db, "FIFA 19", "Sony Playstation 3")
    assert game and game["name"] == "FIFA 19: Legacy Edition"
    assert score == 1.0


def test_the_higher_scoring_wrong_answers_are_still_refused(db):
    """`FIFA 09` scores 0.909 against `fifa19` and `FIFA 19: Legacy Edition`
    scores 0.48. Text similarity ranks this exactly backwards."""
    game, _ = look(db, "FIFA 19", "Sony Playstation 3")
    assert game["name"] != "FIFA 09"


def test_the_spaced_dash_is_a_subtitle_too(db):
    game, _ = look(db, "Ratchet & Clank", "Sony PSP")
    assert game and game["name"] == "Ratchet & Clank - Size Matters"


def test_the_platform_filter_still_holds(db):
    """The same stem exists under Windows. A PS3 lookup must not reach it."""
    game, _ = look(db, "FIFA 19", "Sony Playstation 3")
    assert game["platform"] == "Sony Playstation 3"


# ── what it must refuse, which is the point of it ────────────────────────────

def test_a_plain_extra_word_is_a_different_game(db):
    """The first version of this rule took the only entry starting with the
    title, and filed `Mario Party` as `Mario Party Superstars`."""
    game, _ = look(db, "Mario Party", "Nintendo Switch")
    assert game is None


def test_a_subtitle_further_along_does_not_count(db):
    """`Mario Kart Live: Home Circuit` has a colon, but its stem is
    `Mario Kart Live` and not `Mario Kart`."""
    game, _ = look(db, "Mario Kart", "Nintendo Switch")
    assert game is None


def test_a_series_with_several_subtitles_is_ambiguous(db):
    """Two `Uncharted:` entries means the ROM carries a series name, not a
    title. Measured on the reference box: Uncharted 2, God of War 4, The Legend
    of Zelda on Switch 7 — all refused."""
    game, _ = look(db, "Uncharted", "Sony Playstation 3")
    assert game is None


def test_a_stem_too_short_to_be_a_title_is_refused(db):
    """`Zelda`, `Sonic`. Every subtitle under a five-letter stem is a different
    game, and there is no similarity score that says otherwise."""
    con = db
    from backend.services.gamemedia.parser import normalize
    con.execute("INSERT INTO games (id, name, norm, platform, year) "
                "VALUES (99, 'Zelda: The Wand of Gamelon', ?, "
                "'Philips CD-i', 1993)", (normalize("Zelda: The Wand of Gamelon"),))
    con.commit()
    game, _ = look(con, "Zelda", "Philips CD-i")
    assert game is None


def test_an_episode_number_still_wins_over_a_subtitle(db):
    """The guard the fuzzy step already applies, applied here too: a `FIFA 20`
    disc must not be answered with `FIFA 19: Legacy Edition`."""
    game, _ = look(db, "FIFA 20", "Sony Playstation 3")
    assert game is None


# ── it must not disturb what already worked ──────────────────────────────────

def test_an_exact_title_never_reaches_this_rule(db):
    """`Mario Party Superstars` is in the catalogue verbatim, so step 1 answers
    and the last resort is never consulted. That is what makes the rule safe:
    it only ever runs where the chain had already given up."""
    game, score = look(db, "Mario Party Superstars", "Nintendo Switch")
    assert game and game["name"] == "Mario Party Superstars"
    assert score == 1.0


def test_a_game_nobody_has_is_still_not_found(db):
    game, _ = look(db, "Some Game That Does Not Exist", "Nintendo Switch")
    assert game is None
