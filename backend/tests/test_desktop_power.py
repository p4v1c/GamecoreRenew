"""One owner for the screen, and the handover back.

Two standby systems were configured on the reference box and neither knew the
other existed: GameCore at 4 and 6 minutes, and KDE's power manager at 900 s.
The one with the settings page could not reach the screen, so the number the
owner set was capped by a second, invisible timer — "Never" meant fifteen
minutes, and thirty minutes meant fifteen minutes.

The dangerous half is not the claim, it is the release. Disabling the desktop's
screen-off and then turning GameCore's standby off leaves NOBODY turning the
screen off: the television stays lit all night, behind a switch the owner just
used believing it did the opposite. Most of what is below is about that.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from backend.services import desktop_power as dp


@pytest.fixture
def desktop(monkeypatch, tmp_path):
    """A KDE session that answers, with its timeout in a dict we can read.

    Replaces the module's single subprocess door — everything it does to the
    outside world goes through `_run`, which is the whole reason that function
    exists.
    """
    state = {"timeout": "900", "reparsed": 0, "writes": [], "argv": []}

    async def fake_run(*argv, **kw):
        if argv[0] == "kreadconfig6":
            return 0, state["timeout"]
        if argv[0] == "kwriteconfig6":
            value = argv[-1]
            state["argv"].append(list(argv))
            state["writes"].append(value)
            state["timeout"] = value
            return 0, ""
        if argv[0] == "gdbus":
            state["reparsed"] += 1
            return 0, "()"
        return 1, ""

    monkeypatch.setattr(dp, "_run", fake_run)
    monkeypatch.setattr(dp, "available", lambda: True)
    monkeypatch.setattr(dp, "_HANDOFF", tmp_path / "handoff.json")
    return state


def run(coro):
    return asyncio.run(coro)


# ── claiming ─────────────────────────────────────────────────────────────────

def test_claiming_disables_the_desktops_own_screen_off(desktop):
    assert run(dp.claim()) is True
    assert desktop["timeout"] == "-1"


def test_the_previous_value_is_written_down_before_it_is_lost(desktop):
    run(dp.claim())
    assert json.loads(dp._HANDOFF.read_text())["previous"] == "900"


def test_the_desktop_is_told_to_reread_its_config(desktop):
    # Otherwise it goes on using what it read at login, and on a box nobody
    # logs out of that means the handover never takes effect at all.
    run(dp.claim())
    assert desktop["reparsed"] == 1


def test_claiming_twice_does_not_forget_the_real_setting(desktop):
    # Runs on every startup. A second claim re-reads -1, and writing THAT down
    # would erase the only record of what the owner actually had.
    run(dp.claim())
    run(dp.claim())
    assert json.loads(dp._HANDOFF.read_text())["previous"] == "900"
    assert desktop["writes"] == ["-1"]


# ── releasing, which is the half that matters ────────────────────────────────

def test_releasing_gives_the_desktop_its_timer_back(desktop):
    run(dp.claim())
    assert run(dp.release()) is True
    assert desktop["timeout"] == "900"


def test_a_release_leaves_nothing_behind_to_replay(desktop):
    run(dp.claim())
    run(dp.release())
    assert not dp._HANDOFF.exists()


def test_releasing_without_a_claim_changes_nothing(desktop):
    # A box that never claimed — standby switched off since install, or a
    # desktop that refused the write. Restoring a value we never took would be
    # inventing one.
    assert run(dp.release()) is False
    assert desktop["writes"] == []


def test_claim_release_claim_still_knows_the_original(desktop):
    for _ in range(3):
        run(dp.claim())
        run(dp.release())
    assert desktop["timeout"] == "900"


# ── a box that is not KDE ────────────────────────────────────────────────────

def test_nothing_happens_where_there_is_no_kde(monkeypatch, desktop):
    monkeypatch.setattr(dp, "available", lambda: False)
    assert run(dp.claim()) is False
    assert desktop["writes"] == []


def test_a_desktop_that_will_not_answer_is_not_claimed(monkeypatch, tmp_path):
    async def silent(*argv, **kw):
        return 1, ""

    monkeypatch.setattr(dp, "_run", silent)
    monkeypatch.setattr(dp, "available", lambda: True)
    monkeypatch.setattr(dp, "_HANDOFF", tmp_path / "handoff.json")
    assert run(dp.claim()) is False
    assert not (tmp_path / "handoff.json").exists()


# ── the switch, end to end ───────────────────────────────────────────────────

def test_turning_standby_off_hands_the_screen_back(desktop, monkeypatch, tmp_path):
    """The failure this whole module has to avoid: both disarmed at once."""
    from fastapi.testclient import TestClient

    from backend import main
    from backend.services import standby

    monkeypatch.setattr(standby, "CONFIG_FILE", tmp_path / "standby.json")
    run(dp.claim())
    assert desktop["timeout"] == "-1"

    with TestClient(main.app) as c:
        r = c.post("/api/standby/config", json={"enabled": False})
    assert r.status_code == 200, r.text
    assert desktop["timeout"] == "900", "the television would never go dark again"


# ── the bug that shipped ─────────────────────────────────────────────────────

def test_the_value_is_passed_after_a_separator(desktop):
    """kwriteconfig6 reads a leading dash as an option, and the value we most
    need to write is `-1`:

        $ kwriteconfig6 --file powerdevilrc … --key TurnOff… -1
        kwriteconfig6: Unknown option '1'.        (exit 1)

    Which is how it shipped, and what the box said the first time it ran for
    real: "could not disable the desktop's screen-off (was 900 s)". Every
    positive value worked, so nothing here noticed — these tests drive a fake
    `_run` and never meet the argument parser, which is precisely why this test
    asserts the SHAPE of the command rather than its effect.
    """
    run(dp.claim())
    argv = desktop["argv"][0]
    assert argv[-2:] == ["--", "-1"], argv


def test_a_claim_that_could_not_write_leaves_no_note_behind(monkeypatch, tmp_path):
    """"There is a note" is what release() reads as "we hold the claim"."""
    async def read_ok_write_fails(*argv, **kw):
        if argv[0] == "kreadconfig6":
            return 0, "900"
        return 1, "kwriteconfig6: Unknown option '1'."

    monkeypatch.setattr(dp, "_run", read_ok_write_fails)
    monkeypatch.setattr(dp, "available", lambda: True)
    monkeypatch.setattr(dp, "_HANDOFF", tmp_path / "handoff.json")

    assert run(dp.claim()) is False
    assert not (tmp_path / "handoff.json").exists()
    # And release must then know it holds nothing, rather than writing a value
    # back over a desktop nobody took.
    assert run(dp.release()) is False
