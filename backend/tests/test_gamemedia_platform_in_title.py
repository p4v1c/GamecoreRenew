"""A console's name buried in a filename must not cost a game its artwork.

Release names habitually inject the platform into the title:

    FIFA 22 Nintendo Switch Legacy Edition [0100216014472000][v0][US].nsp

Measured on the reference box: ScreenScraper's `romnom` search found nothing for
that exact file, so the lookup fell through to the offline LaunchBox index,
which matched "FIFA 22: Legacy Edition" at 73 % and carries **one** media — a
front. No back, no spine, no 3D box. Renaming the file with "Nintendo Switch"
removed found it on the first try, with 23 media.

So `ss_everything` now gets a second chance at the name. The tests below pin the
three properties that make that safe rather than merely clever:

  · it only runs when the first sweep found nothing convincing — so a game that
    really is called `Nintendo Switch Sports` matches first and never reaches it;
  · the better score wins, so a reduction landing on the wrong game cannot
    displace a good answer;
  · a game with no console name in it costs no extra request at all.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import pytest

from backend.services.gamemedia import gamemedia as gm
from backend.services.gamemedia.parser import without_platform


# ── The reduction, on its own ────────────────────────────────────────────────

@pytest.mark.parametrize("name, expected", [
    # The case this exists for.
    ("FIFA 22 Nintendo Switch Legacy Edition [0100216014472000][v0][US].nsp",
     "FIFA 22 Legacy Edition [0100216014472000][v0][US].nsp"),
    ("God of War Sony Playstation 3.iso", "God of War.iso"),
    # Nothing to drop — and the empty string is what tells the caller not to
    # spend a second request.
    ("Mario Kart 8 Deluxe.nsp", ""),
    ("Super Mario Party.xci", ""),
    # Dropping it would leave no title at all, which is not worth asking about.
    ("Nintendo Switch.nsp", ""),
    # Short keys are deliberately NOT stripped: taking "Wii" out of this would
    # aim at a different game, and the gain does not justify that risk.
    ("Mario Kart Wii.iso", ""),
])
def test_only_a_full_console_name_is_dropped(name, expected):
    assert without_platform(name) == expected


def test_the_extension_survives_the_reduction():
    """`romnom` is a filename; handing the API a bare title changes the query."""
    assert without_platform("X Nintendo Switch Y.nsp").endswith(".nsp")


# ── The retry, in the lookup ─────────────────────────────────────────────────

def _jeu(name):
    return {"response": {"jeu": {
        "id": "1", "noms": [{"region": "wor", "text": name}],
        "systeme": {"text": "Nintendo Switch"}, "medias": [],
    }}}


@pytest.fixture
def spy(monkeypatch):
    """Record every romnom asked for, and answer per a scripted table."""
    asked = []
    table = {}

    def fake_request(endpoint, params, verbose=False):
        asked.append(params.get("romnom"))
        return table.get(params.get("romnom"))

    monkeypatch.setattr(gm, "ss_request", fake_request)
    monkeypatch.setattr(gm.gs, "ss_credentials", lambda: {"devid": "x"})
    monkeypatch.setattr(gm, "hashes_for", lambda p: None)
    return asked, table


def _parsed(filename):
    return {"source": filename, "title": Path(filename).stem,
            "region": None, "ss_candidates": [4]}


FIFA = "FIFA 22 Nintendo Switch Legacy Edition [0100216014472000][v0][US].nsp"
FIFA_REDUCED = "FIFA 22 Legacy Edition [0100216014472000][v0][US].nsp"


def test_the_console_name_is_dropped_and_the_game_is_found(spy):
    """The defect, end to end: found on the retry, not on the first ask."""
    asked, table = spy
    table[FIFA] = None                                  # ScreenScraper: nothing
    table[FIFA_REDUCED] = _jeu("FIFA 22 Legacy Edition")

    out = gm.ss_everything(_parsed(FIFA), None, False)

    assert out is not None, "the retry never happened — this is the old behaviour"
    assert out["meta"]["title"] == "FIFA 22 Legacy Edition"
    assert FIFA in asked and FIFA_REDUCED in asked
    assert asked.index(FIFA) < asked.index(FIFA_REDUCED), "the retry must be second"


def test_the_match_says_the_console_name_had_to_go(spy):
    """Otherwise the match is a puzzle. It points at the fix: rename the file."""
    _, table = spy
    table[FIFA] = None
    table[FIFA_REDUCED] = _jeu("FIFA 22 Legacy Edition")

    out = gm.ss_everything(_parsed(FIFA), None, False)
    assert "console name dropped" in out["matched_by"]


def test_a_game_really_named_after_its_console_is_never_retried(spy):
    """`Nintendo Switch Sports` is its actual title — reducing it would ruin it.

    It matches on the first attempt, so the retry is not reached. This is the
    whole reason the reduction is a fallback and not a pre-processing step.
    """
    asked, table = spy
    name = "Nintendo Switch Sports.nsp"
    table[name] = _jeu("Nintendo Switch Sports")

    out = gm.ss_everything(_parsed(name), None, False)

    assert out["meta"]["title"] == "Nintendo Switch Sports"
    assert asked == [name], f"asked more than once: {asked}"
    assert "console name dropped" not in out["matched_by"]


def test_a_name_with_no_console_in_it_costs_no_extra_request(spy):
    """The common case must not pay for the rare one."""
    asked, table = spy
    name = "Mario Kart 8 Deluxe.nsp"
    table[name] = None                                  # a genuine miss

    assert gm.ss_everything(_parsed(name), None, False) is None
    assert asked == [name], f"a pointless second request went out: {asked}"


def test_a_worse_reduction_cannot_displace_a_good_answer(spy):
    """The retry may fail to help. It may not do harm.

    Here the first sweep returns something imperfect but right, and the reduced
    query returns a different game. The better score has to win.
    """
    asked, table = spy
    name = "Metroid Prime Nintendo Switch.nsp"
    table[name] = _jeu("Metroid Prime")                 # close, below accept
    table[without_platform(name)] = _jeu("Completely Different Game")

    out = gm.ss_everything(_parsed(name), None, False)

    assert len(asked) == 2, "the retry should have been attempted"
    assert out["meta"]["title"] == "Metroid Prime", \
        f"the weaker reduction won: {out['meta']['title']}"
    assert "console name dropped" not in out["matched_by"]


def test_the_retry_is_scored_against_what_it_actually_asked(spy):
    """Scoring the reply against the ORIGINAL name would sink every retry.

    "FIFA 22 Legacy Edition" compared with "FIFA 22 Nintendo Switch Legacy
    Edition" is penalised for exactly the words the retry removed on purpose —
    so it could never clear NAME_ACCEPT and the fix would silently do nothing.
    """
    _, table = spy
    table[FIFA] = None
    table[FIFA_REDUCED] = _jeu("FIFA 22 Legacy Edition")

    out = gm.ss_everything(_parsed(FIFA), None, False)
    # An exact answer to the reduced question must not be reported as weak.
    assert "weak" not in out["matched_by"], out["matched_by"]
