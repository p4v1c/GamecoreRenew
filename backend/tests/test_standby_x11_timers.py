"""The screen blanking mid-film, and the second, invisible timer.

Reported from the couch: "standby kicks in even when I launch an app or a
game; mid-film the screen goes to sleep". GameCore's standby was not the cause
— the journal shows Stremio 27 min, melonDS 43 min, Ryujinx 74 min with no
`active → screensaver` transition; `_tick()` already counts a foreground game
as activity.

The X server blanked the TV. The GameCore session is X11
(`/usr/share/xsessions/gamecore.desktop`) and PowerDevil does NOT run there.
X keeps its default screensaver and DPMS delays, and DualShock 4 buttons are
`ID_INPUT_JOYSTICK`, which X does not count as input. The existing
counter-measure went through `org.freedesktop.ScreenSaver`, which nobody owns
in this session ("The name is not activatable", fifteen times a minute).
"""
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from backend.services import desktop_power as dp


# Real `xset q` output captured on the box (untranslated, so identical
# everywhere), XWayland half included.
REAL_X = """Keyboard Control:
  auto repeat:  on    key click percent:  0
Screen Saver:
  prefer blanking:  yes    allow exposures:  yes
  timeout:  600    cycle:  600
Colors:
  default colormap:  0x20    BlackPixel:  0x0    WhitePixel:  0xffffff
DPMS (Display Power Management Signaling):
  Standby: 600    Suspend: 900    Off: 1200
  DPMS is Enabled
  Monitor is On
"""

# The desktop session's server: screensaver already 0, no DPMS extension.
# A box with ONE timer, not zero.
XWAYLAND = """Screen Saver:
  prefer blanking:  yes    allow exposures:  yes
  timeout:  0    cycle:  0
DPMS (Display Power Management Signaling):
  Server does not have the DPMS Extension
"""


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def xserver(monkeypatch, tmp_path):
    """An answering X server, and what it was asked to do.

    No KDE: `kreadconfig6` fails, so only the X arm acts (the GameCore
    session, where PowerDevil does not exist).
    """
    state = {"q": REAL_X, "argv": []}

    async def fake_run(*argv, **kw):
        if argv[0] == "xset" and argv[1:] == ("q",):
            return 0, state["q"]
        if argv[0] == "xset":
            state["argv"].append(list(argv))
            return 0, ""
        return 1, ""            # neither kreadconfig6 nor kwriteconfig6 answers

    monkeypatch.setattr(dp, "_run", fake_run)
    monkeypatch.setattr(dp, "available", lambda: True)
    monkeypatch.setattr(dp, "_HANDOFF", tmp_path / "handoff.json")
    return state


# ── taking the X server's timers ───────────────────────────────────────

def test_the_x_servers_idle_timers_are_stopped(xserver):
    assert run(dp.claim()) is True
    assert ["xset", "s", "0", "0"] in xserver["argv"]
    assert ["xset", "dpms", "0", "0", "0"] in xserver["argv"]


def test_the_extension_is_left_enabled(xserver):
    """`xset dpms 0 0 0`, never `xset -dpms`: disabling the extension would
    also kill GameCore standby's own `xset dpms force off`."""
    run(dp.claim())
    assert not any("-dpms" in argv for argv in xserver["argv"])


def test_releasing_never_gives_the_x_delays_back(xserver):
    """Standby switched off blanked Ryujinx after 10 min: the X server's
    delays cannot see a pad or a game, so they are never handed back."""
    run(dp.claim())
    xserver["argv"].clear()
    run(dp.release())
    assert xserver["argv"] == []
    assert not dp._HANDOFF.exists()


def test_claim_x_takes_only_the_x_timers(xserver):
    assert run(dp.claim_x()) is True
    assert ["xset", "dpms", "0", "0", "0"] in xserver["argv"]


# ── servers with nothing to take ────────────────────────────────────

def test_xwayland_has_nothing_to_take(xserver):
    """Screensaver already 0 and no DPMS: nothing to take and no note (the
    desktop session, where PowerDevil's timer is the one that matters)."""
    xserver["q"] = XWAYLAND
    assert run(dp.claim()) is True
    assert xserver["argv"] == []
    assert not dp._HANDOFF.exists()


def test_a_server_with_only_a_screen_saver_is_still_claimed(xserver):
    """The two halves are tracked separately: a screensaver-only server is
    still claimed for that half."""
    xserver["q"] = XWAYLAND.replace("timeout:  0    cycle:  0",
                                    "timeout:  600    cycle:  600")
    assert run(dp.claim()) is True
    assert ["xset", "s", "0", "0"] in xserver["argv"]


def test_a_server_that_will_not_answer_is_not_claimed(monkeypatch, tmp_path):
    async def silent(*argv, **kw):
        return 1, ""

    monkeypatch.setattr(dp, "_run", silent)
    monkeypatch.setattr(dp, "available", lambda: True)
    monkeypatch.setattr(dp, "_HANDOFF", tmp_path / "handoff.json")
    assert run(dp.claim()) is False
    assert not (tmp_path / "handoff.json").exists()


def test_a_claim_that_could_not_write_leaves_no_note_behind(monkeypatch, tmp_path):
    """"There is a note" is what `release()` reads as "we hold the timers"."""
    async def read_ok_write_fails(*argv, **kw):
        if argv[0] == "xset" and argv[1:] == ("q",):
            return 0, REAL_X
        return 1, ""

    monkeypatch.setattr(dp, "_run", read_ok_write_fails)
    monkeypatch.setattr(dp, "available", lambda: True)
    monkeypatch.setattr(dp, "_HANDOFF", tmp_path / "handoff.json")
    assert run(dp.claim()) is False
    assert not (tmp_path / "handoff.json").exists()
    assert run(dp.release()) is False


# ── both arms on the same box ────────────────────────────────────────

@pytest.fixture
def both(monkeypatch, tmp_path):
    state = {"kde": "900", "argv": []}

    async def fake_run(*argv, **kw):
        if argv[0] == "kreadconfig6":
            return 0, state["kde"]
        if argv[0] == "kwriteconfig6":
            state["kde"] = argv[-1]
            state["argv"].append(list(argv))
            return 0, ""
        if argv[0] == "xset" and argv[1:] == ("q",):
            return 0, REAL_X
        state["argv"].append(list(argv))
        return 0, ""

    monkeypatch.setattr(dp, "_run", fake_run)
    monkeypatch.setattr(dp, "available", lambda: True)
    monkeypatch.setattr(dp, "_HANDOFF", tmp_path / "handoff.json")
    return state


def test_both_arms_are_taken_and_only_the_desktop_is_given_back(both):
    assert run(dp.claim()) is True
    assert json.loads(dp._HANDOFF.read_text()) == {"previous": "900"}
    both["argv"].clear()
    assert run(dp.release()) is True
    assert both["kde"] == "900"
    assert not any(argv[0] == "xset" for argv in both["argv"])
    assert not dp._HANDOFF.exists()


def test_an_old_note_with_only_the_kde_half_still_reads(both, tmp_path):
    """A note written before the X arm existed: arms are found by key, not
    by count, so it must still be released."""
    (tmp_path / "handoff.json").write_text(json.dumps({"previous": "900"}))
    both["kde"] = "-1"
    assert run(dp.release()) is True
    assert both["kde"] == "900"
    assert not dp._HANDOFF.exists()


# ── the claim must be RE-MADE, not made once ───────────────────

@pytest.fixture
def watcher(monkeypatch):
    """The standby watcher, with the claim replaced by a counter."""
    from backend.services import standby
    from backend.services import process_manager as pm

    attempts = []

    async def fake_claim():
        attempts.append("both")
        return True

    async def fake_claim_x():
        attempts.append("x")
        return True

    async def fake_run_cmd(*argv, **kw):
        return True

    monkeypatch.setattr(dp, "claim", fake_claim)
    monkeypatch.setattr(dp, "claim_x", fake_claim_x)
    monkeypatch.setattr(standby, "_run_cmd", fake_run_cmd)
    monkeypatch.setattr(type(pm.process_manager), "is_foreground",
                        property(lambda self: True))
    standby._last_claim_attempt = 0.0
    standby._state = "active"
    standby._last_input = time.monotonic()
    yield attempts
    standby._last_claim_attempt = 0.0
    standby._state = "active"


CFG_ON = {"enabled": True, "screensaver_mins": 10, "sleep_mins": 20}
CFG_OFF = {**CFG_ON, "enabled": False}


def test_the_watcher_claims_the_timers(watcher):
    """The core of the report. The backend is a SYSTEM service that starts
    before any session (boot 07:39:06, compositor 07:39:20), so a one-shot
    claim finds nothing; and every session switch brings a new X server with
    default delays. The claim must be re-made."""
    from backend.services import standby
    asyncio.run(standby._tick(CFG_ON))
    assert len(watcher) == 1


def test_it_is_claimed_before_the_foreground_return(watcher):
    """A foreground game is when the timers must already be held — and it is
    the branch that returns early."""
    from backend.services import standby
    asyncio.run(standby._tick(CFG_ON))
    assert watcher, "the foreground early return skipped the claim"


def test_it_is_not_re_attempted_every_fifteen_seconds(watcher):
    """Idempotent but not free (reads before writing): once a minute is
    enough to repair a session switch."""
    from backend.services import standby
    for _ in range(4):
        asyncio.run(standby._tick(CFG_ON))
    assert len(watcher) == 1


def test_a_minute_later_it_is_attempted_again(watcher):
    from backend.services import standby
    asyncio.run(standby._tick(CFG_ON))
    standby._last_claim_attempt -= standby._CLAIM_RETRY_SECS + 1
    asyncio.run(standby._tick(CFG_ON))
    assert len(watcher) == 2


def test_standby_switched_off_still_holds_the_x_timers(watcher):
    """Standby off leaves the desktop's timer alone but must keep X's at zero:
    a new X server (session switch) comes back with 600 s and blanks a game."""
    from backend.services import standby
    asyncio.run(standby._tick(CFG_OFF))
    assert watcher == ["x"]
