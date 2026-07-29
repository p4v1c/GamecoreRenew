"""The declared ROM extensions, and the three places that have to agree on them.

rom_scanner.matches_ext filters strictly: a format that is not in `extensions`
is not listed, with nothing said about it. So a missing entry is invisible —
which is how `.cue` went missing for PS1 while the README advertised it, and
why this file exists.

install/systems.json.dist is the one that matters on a box: install/arch.sh
regenerates config/systems.json from it on every run. The two must not drift,
and neither may drift from the README table.

Run under pytest:  pytest backend/tests/test_systems_extensions.py
Or directly:       python backend/tests/test_systems_extensions.py
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

REPO = Path(__file__).resolve().parents[2]
DIST = REPO / "install/systems.json.dist"
LIVE = REPO / "config/systems.json"
README = REPO / "README.md"


def systems(path: Path) -> dict[str, dict]:
    return {s["id"]: s for s in json.loads(path.read_text())}


def readme_table() -> dict[str, str]:
    """{system_id: raw text of the extensions cell} from the 'Supported formats' table.

    Keyed on the `emu/<id>/` folder column rather than the display name, so the
    table stays readable while the pairing stays unambiguous.
    """
    rows = {}
    for line in README.read_text().splitlines():
        m = re.match(r"^\|[^|]+\|\s*`emu/([a-z0-9]+)/`\s*\|(.*)\|\s*$", line)
        if m:
            rows[m.group(1)] = m.group(2).strip()
    return rows


def test_the_two_systems_files_agree():
    """arch.sh regenerates config/systems.json from the .dist on every install,
    so a checkout where they differ is a checkout that lies about the box."""
    dist, live = systems(DIST), systems(LIVE)
    assert set(dist) == set(live), "different systems declared"
    for sid in dist:
        assert dist[sid].get("extensions") == live[sid].get("extensions"), sid


def test_readme_lists_every_system():
    assert set(readme_table()) == set(systems(DIST)), \
        "README table and systems.json.dist disagree on which systems exist"


@pytest.mark.parametrize("sid", sorted(systems(DIST)))
def test_readme_extensions_match_systems_dist(sid):
    system = systems(DIST)[sid]
    declared = [e.lstrip("*") for e in system.get("extensions", [])]
    cell = readme_table()[sid]

    if not declared:
        # rpcs3 / shadps4 are folder-scanned. Their row is prose, and may name
        # formats that are not ROMs at all (rpcs3's .pkg updates), so the cell
        # is not parsed as a list — it only has to say what it scans.
        assert system.get("scanDirs"), f"{sid} declares no extensions and is not scanDirs"
        assert "folder" in cell.lower(), f"{sid} is folder-scanned; the README should say so: {cell!r}"
        return

    documented = re.findall(r"`(\.[a-z0-9]+)`", cell)
    assert declared == documented, f"{sid}: systems.json={declared} README={documented}"


# ── the formats the audit found missing ──────────────────────────────────────

@pytest.mark.parametrize("sid,ext", [
    ("duckstation", "*.cue"),   # the only launchable file of a multi-track dump
    ("duckstation", "*.chd"),
    ("duckstation", "*.pbp"),
    ("azahar", "*.cia"),
    ("dolphin", "*.wbfs"),
    ("dolphin", "*.wad"),
    ("pcsx2", "*.chd"),
    ("ppsspp", "*.pbp"),
])
def test_known_missing_extensions_are_declared(sid, ext):
    assert ext in systems(DIST)[sid]["extensions"]


def test_dolphin_does_not_declare_a_format_that_does_not_exist():
    assert "*.wii" not in systems(DIST)["dolphin"]["extensions"]


def test_a_multitrack_ps1_dump_shows_the_cue_and_the_tracks():
    """The visible symptom: twelve .bin entries and no .cue, and launching
    track 1 boots the game without its CD audio."""
    from backend.services.rom_scanner import matches_ext
    exts = systems(DIST)["duckstation"]["extensions"]
    assert matches_ext("Final Fantasy IX.cue", exts)
    assert matches_ext("Final Fantasy IX (Track 01).bin", exts)


def test_matches_ext_is_case_insensitive():
    from backend.services.rom_scanner import matches_ext
    exts = systems(DIST)["dolphin"]["extensions"]
    assert matches_ext("Melee.ISO", exts)
    assert not matches_ext("readme.txt", exts)


if __name__ == "__main__":
    test_the_two_systems_files_agree()
    print("[OK ] test_the_two_systems_files_agree")
    test_readme_lists_every_system()
    print("[OK ] test_readme_lists_every_system")
    for _sid in sorted(systems(DIST)):
        test_readme_extensions_match_systems_dist(_sid)
        print(f"[OK ] test_readme_extensions_match_systems_dist[{_sid}]")
    for _sid, _ext in (("duckstation", "*.cue"), ("duckstation", "*.chd"), ("duckstation", "*.pbp"),
                       ("azahar", "*.cia"), ("dolphin", "*.wbfs"), ("dolphin", "*.wad"),
                       ("pcsx2", "*.chd"), ("ppsspp", "*.pbp")):
        test_known_missing_extensions_are_declared(_sid, _ext)
        print(f"[OK ] test_known_missing_extensions_are_declared[{_sid},{_ext}]")
    test_dolphin_does_not_declare_a_format_that_does_not_exist()
    print("[OK ] test_dolphin_does_not_declare_a_format_that_does_not_exist")
    test_a_multitrack_ps1_dump_shows_the_cue_and_the_tracks()
    print("[OK ] test_a_multitrack_ps1_dump_shows_the_cue_and_the_tracks")
    test_matches_ext_is_case_insensitive()
    print("[OK ] test_matches_ext_is_case_insensitive")
    print("\nAll tests passed.")
