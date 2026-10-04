"""melonDS local multiplayer, runtime half: window layout, menu matching, the
AT-SPI wire format, and the launcher's promise never to outlive melonDS's
start-up by waiting on a dead process."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MP = HERE.parent / "multiplayer"
sys.path.insert(0, str(MP))

import atspi      # noqa: E402
import launcher   # noqa: E402
import windows    # noqa: E402


def test_columns_touch_and_keep_the_ds_shape():
    for players in (2, 3, 4):
        cols = windows.columns(players, 1920, 1080)
        assert len(cols) == players
        for (x1, _y1, w1, _h1), (x2, _y2, _w2, _h2) in zip(cols, cols[1:]):
            assert x1 + w1 == x2                      # no gap between players
        for x, y, w, h in cols:
            assert 0 <= y and y + h <= 1080 and h * 2 == w * 3
        assert cols[0][0] >= 0 and cols[-1][0] + cols[-1][2] <= 1920


def test_four_players_use_the_whole_width():
    cols = windows.columns(4, 1920, 1080)
    assert cols[0][0] == 0 and cols[-1][0] + cols[-1][2] == 1920


def test_two_players_use_the_whole_height_and_are_centred():
    (x1, y, w, h), (x2, _, _, _) = windows.columns(2, 1920, 1080)
    assert (y, w, h) == (0, 720, 1080)
    assert x1 == 1920 - (x2 + w)


def test_player_number_comes_from_the_title():
    assert windows.player_of("[p3] [59/60] melonDS 1.1") == 3
    assert windows.player_of("melonDS 1.1") is None


def test_recent_entry_one_matches_even_shortened_and_with_ampersands():
    match = launcher.recent_rom_matcher("/userdata/emu/melonds/Mario & Luigi (Europe).nds")
    assert match("1.  /userdata/emu/melonds/Mario  Luigi (Europe).nds")
    assert match("1.  /userdata...melonds/Mario  Luigi (Europe).nds")
    assert not match("2.  /userdata/emu/melonds/Mario  Luigi (Europe).nds")
    assert not match("1.  /opt/x/Other.nds")


def test_recent_entry_of_a_zipped_rom_names_the_member():
    match = launcher.recent_rom_matcher("/userdata/emu/melonds/Game (Europe).zip")
    assert match("1.  /userdata/emu/melonds/Game (Europe).zip|Game (Europe).nds")
    assert not match("1.  /userdata/emu/melonds/Game (Europe) (Rev 1).zip|Game.nds")


def test_gvariant_replies_parse():
    assert atspi.parse_gvariant("(<'melonDS'>,)") == ("melonDS",)
    assert atspi.parse_gvariant('(<"Toys\'R\'Us">,)') == ("Toys'R'Us",)
    assert atspi.parse_gvariant("(true,)") == (True,)
    kids = atspi.parse_gvariant("([(':1.44', objectpath '/a/1'), (':1.44', '/a/2')],)")
    assert kids == ([(":1.44", "/a/1"), (":1.44", "/a/2")],)


def test_launcher_returns_melonds_exit_code_without_waiting_out_the_timeout(tmp_path):
    """A melonDS that dies at start-up must end the session at once."""
    env = {**os.environ, "HOME": str(tmp_path)}
    done = subprocess.run(
        [sys.executable, str(MP / "launcher.py"), "--players", "2", "--",
         sys.executable, "-c", "import sys; sys.exit(3)", "/roms/Game.nds"],
        env=env, timeout=launcher.APP_TIMEOUT / 2)
    assert done.returncode == 3
    assert "multiplayer setup stopped" in (tmp_path / ".cache/gamecore/melonds-multiplayer.log").read_text()
