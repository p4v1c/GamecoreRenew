"""A theme's launch animation and the hold the host gives it must be one number.

`theme.json` declares `launch.ms`, and `LibraryScreen` holds the launch for
exactly that long before it calls the backend — the animation gets to finish,
and then the game starts. The same hold now covers a resume, because coming
back to a frozen game is a launch as far as the player is concerned.

The number therefore exists twice: once in the manifest the host reads, and once
in whatever the theme animates with. Nothing connected them. Summer's own
warp.js has said so in a comment since it was written —

    **`launch.ms` in theme.json must equal CLOSE_MS below.** Nothing enforces
    it;

— and Shelf is what happens when they merely *look* equal. Its boot was 900ms of
rise plus 620ms of iris, its manifest said 1520, and the two agreed exactly: the
call went out on the very frame the iris closed. The last thing the animation
does is shut to a point, and the screen changed on the same tick, so it never
read as finished. It read as cut off. The fix was a beat of settled black after
the iris — which is a third number, in a third place, and now there is a test.

What is checked is agreement, not aesthetics: a theme may take as long as it
likes over a handover, as long as it has told the host the same thing it told
its own stylesheet.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
THEMES = ROOT / "config" / "themes"


def _declared(theme_dir: Path) -> int | None:
    """`launch.ms` from the manifest, or None when the theme declares no hold."""
    manifest = json.loads((theme_dir / "theme.json").read_text())
    launch = manifest.get("launch") or {}
    ms = launch.get("ms")
    return int(ms) if isinstance(ms, (int, float)) else None


def _constants(theme_dir: Path) -> dict[str, int]:
    """Every `const NAME = <number>` the theme's own JS declares.

    Read rather than executed: these files import the SDK and cannot be run
    outside a browser, and the numbers are what matter.
    """
    found: dict[str, int] = {}
    for js in sorted(theme_dir.rglob("*.js")):
        for name, value in re.findall(
                r"^(?:export\s+)?const\s+([A-Z][A-Z0-9_]*)\s*=\s*(\d+)\s*$",
                js.read_text(), re.M):
            found.setdefault(name, int(value))
    return found


def _shipped():
    for d in sorted(THEMES.iterdir()):
        if not d.is_dir() or d.name[0] in "._" or not (d / "theme.json").is_file():
            continue
        try:
            provides = json.loads((d / "theme.json").read_text()).get("provides") or []
        except json.JSONDecodeError:
            continue
        if "shell" in provides:
            yield pytest.param(d, id=d.name)


CASES = list(_shipped())


def test_there_is_something_to_check():
    assert len(CASES) >= 3, f"expected the shipped themes, found {CASES}"


@pytest.mark.parametrize("theme_dir", CASES)
def test_a_declared_hold_is_a_hold_the_theme_can_fill(theme_dir: Path):
    """A theme that asks the host to wait must animate for that whole wait.

    The host stops the player on a still picture for `launch.ms` whatever
    happens. A theme that declares 1500 and animates for 400 has bought itself
    1.1 seconds of nothing, which is the shape Orbit shipped in: `launch.ms:
    500` and no ceremony drawn at all, so the press landed, the screen sat
    there, and then the emulator appeared.
    """
    declared = _declared(theme_dir)
    if declared is None:
        return                          # no ceremony asked for, none owed
    consts = _constants(theme_dir)
    named = {k: v for k, v in consts.items() if v == declared}
    assert named, (
        f"{theme_dir.name}: theme.json holds the launch for {declared}ms and no "
        f"constant in the theme's own JS is that number. Either the animation "
        f"does not last as long as the hold — which is a still screen the "
        f"player waits on — or the two have drifted apart. Constants found: "
        f"{ {k: v for k, v in sorted(consts.items())} }"
    )


@pytest.mark.parametrize("theme_dir", CASES)
def test_the_launch_hold_is_long_enough_to_be_a_ceremony(theme_dir: Path):
    """Zero and a few hundred milliseconds are not ceremonies, they are stalls.

    A theme is free to declare no `launch` at all and start the game at once —
    that is what every theme did before the hold existed, and it is honest. What
    it may not do is ask for a pause too short to put anything in.
    """
    declared = _declared(theme_dir)
    if declared is None:
        return
    assert declared >= 600, (
        f"{theme_dir.name}: launch.ms is {declared} — long enough to be felt as "
        "a delay and too short to read as a handover. Either draw something or "
        "drop the key and start the game immediately."
    )


@pytest.mark.parametrize("theme_dir", CASES)
def test_a_theme_that_draws_a_handover_reads_the_hosts_flag(theme_dir: Path):
    """The host is the only thing that knows a handover is happening.

    `transition` in the store is set by the launch hold, by the session bar's
    resume and by the backgrounded event. A theme drawing its own resume or
    suspend animation off some other signal — a session list changing length,
    say — is guessing, and it guesses wrong in exactly the cases that matter:
    a resume that failed, a game that exited on its own.
    """
    candidates = [theme_dir / "views" / "ceremony.js",
                  theme_dir / "views" / "warp.js"]
    ceremony = next((path for path in candidates if path.is_file()), None)
    if ceremony is None:
        pytest.skip(f"{theme_dir.name} draws no handover of its own")
    source = ceremony.read_text()
    assert "s.transition" in source, (
        f"{theme_dir.name}: views/ceremony.js does not read `transition` from "
        "the store, so whatever it draws is not driven by the handover itself"
    )


@pytest.mark.parametrize(
    ("theme", "total", "motion", "settle"),
    [("orbit", "TRAVEL_MS", "TRAVEL_MOTION_MS", "TRAVEL_SETTLE_MS"),
     ("shelf", "CLOSE_MS", "CLOSE_MOTION_MS", "CLOSE_SETTLE_MS"),
     ("summer", "CLOSE_MS", "CLOSE_MOTION_MS", "CLOSE_SETTLE_MS")],
)
def test_a_closed_screen_settles_before_the_game_takes_it(
        theme: str, total: str, motion: str, settle: str):
    """The final closed frame needs time to register before the window changes."""
    constants = _constants(THEMES / theme)
    assert constants[total] == constants[motion] + constants[settle]
    assert constants[settle] >= 100
