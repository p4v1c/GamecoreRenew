"""The declared ROM extensions, and the three places that have to agree on them.

rom_scanner.matches_ext filters strictly: a format that is not in `extensions`
is not listed, with nothing said about it. So a missing entry is invisible —
which is how `.cue` went missing for PS1 while the README advertised it, and
why this file exists.

install/generated/systems.json.dist is the one that matters on a box: install/arch.sh
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
DIST = REPO / "install/generated/systems.json.dist"
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


# ── One game, one entry ───────────────────────────────────────────────────────
#
# Scanning both halves of a disc dump is right (the descriptor is the only
# launchable file of a multi-track dump, and plenty of dumps are a bare .bin),
# but listing both shows the same game twice — which is what the player sees.

from backend.services.rom_scanner import iter_rom_files  # noqa: E402


def _tree(tmp: Path, files: dict) -> Path:
    for name, body in files.items():
        p = tmp / name
        p.write_bytes(body) if isinstance(body, bytes) else p.write_text(body)
    return tmp


PS1_EXTS = ["*.bin", "*.iso", "*.img", "*.cue", "*.chd", "*.pbp", "*.zip"]


def test_a_cue_hides_the_bin_it_names(tmp_path):
    _tree(tmp_path, {
        "Solo Dump.cue": 'FILE "Solo Dump.bin" BINARY\n',
        "Solo Dump.bin": b"x",
    })
    assert [f.name for f in iter_rom_files(tmp_path, PS1_EXTS)] == ["Solo Dump.cue"]


def test_a_cue_hides_a_bin_it_no_longer_names(tmp_path):
    """The common case: the dump was renamed, the descriptor was not.

    Measured on a real library — `Dragon Ball Z .cue` still points at
    `Dragon Ball Z (Europe).bin`, which does not exist, while
    `Dragon Ball Z .bin` sits next to it. Matching only on what the descriptor
    names would leave both in the library.
    """
    _tree(tmp_path, {
        "Dragon Ball Z .cue": 'FILE "Dragon Ball Z (Europe).bin" BINARY\n',
        "Dragon Ball Z .bin": b"x",
    })
    assert [f.name for f in iter_rom_files(tmp_path, PS1_EXTS)] == ["Dragon Ball Z .cue"]


def test_a_multitrack_dump_shows_only_its_cue(tmp_path):
    """The tracks share no stem with the .cue, so only the reference pass sees them."""
    _tree(tmp_path, {
        "FF IX.cue": 'FILE "FF IX (Track 01).bin" BINARY\nFILE "FF IX (Track 02).bin" BINARY\n',
        "FF IX (Track 01).bin": b"x",
        "FF IX (Track 02).bin": b"x",
    })
    assert [f.name for f in iter_rom_files(tmp_path, PS1_EXTS)] == ["FF IX.cue"]


def test_a_multidisc_playlist_hides_its_discs_and_their_tracks(tmp_path):
    """Transitive: the .m3u hides the .cue files, whose own tracks go with them.

    The .m3u lines are read whole rather than tokenised — disc names contain
    spaces, and any token pattern matches only the tail after the last one.
    """
    _tree(tmp_path, {
        "FF IX.m3u": "FF IX (Disc 1).cue\nFF IX (Disc 2).cue\n",
        "FF IX (Disc 1).cue": 'FILE "FF IX (Disc 1) (Track 01).bin" BINARY\n',
        "FF IX (Disc 2).cue": 'FILE "FF IX (Disc 2) (Track 01).bin" BINARY\n',
        "FF IX (Disc 1) (Track 01).bin": b"x",
        "FF IX (Disc 2) (Track 01).bin": b"x",
    })
    assert [f.name for f in iter_rom_files(tmp_path, ["*.bin", "*.cue", "*.m3u"])] == ["FF IX.m3u"]


def test_an_unrelated_image_is_left_alone(tmp_path):
    """Only files a descriptor claims are hidden — nothing else."""
    _tree(tmp_path, {
        "Solo Dump.cue": 'FILE "Solo Dump.bin" BINARY\n',
        "Solo Dump.bin": b"x",
        "Standalone Game.iso": b"x",
        "Another Game.bin": b"x",
    })
    assert [f.name for f in iter_rom_files(tmp_path, PS1_EXTS)] == [
        "Another Game.bin", "Solo Dump.cue", "Standalone Game.iso"]


def test_a_library_with_no_descriptor_is_untouched(tmp_path):
    """No .cue anywhere means no reading, no hiding — the old behaviour exactly."""
    _tree(tmp_path, {"A.bin": b"x", "B.iso": b"x"})
    assert [f.name for f in iter_rom_files(tmp_path, PS1_EXTS)] == ["A.bin", "B.iso"]


def test_a_descriptor_the_system_does_not_scan_hides_nothing(tmp_path):
    """The regression that took the reference box from one PS1 game to none.

    `config/` is excluded from the OTA, so a box installed before `*.cue` was
    added to duckstation keeps a catalogue scanning `*.bin` and not `*.cue`.
    The .cue is still on disk, so it shadowed the .bin — and was then filtered
    out by matches_ext, leaving an empty library.

    A file may only be hidden if the entry replacing it will actually be
    listed.
    """
    _tree(tmp_path, {
        "Dragon Ball Z .cue": 'FILE "Dragon Ball Z (Europe).bin" BINARY\n',
        "Dragon Ball Z .bin": b"x",
    })
    old_catalogue = ["*.bin", "*.iso", "*.img", "*.zip"]        # no *.cue
    assert [f.name for f in iter_rom_files(tmp_path, old_catalogue)] == \
        ["Dragon Ball Z .bin"], "the game must stay listed"
    # And with the current catalogue, the dedup still happens.
    assert [f.name for f in iter_rom_files(tmp_path, PS1_EXTS)] == ["Dragon Ball Z .cue"]


def test_a_playlist_the_system_does_not_scan_hides_nothing(tmp_path):
    """Same rule one level up: an .m3u nobody lists must not hide its discs."""
    _tree(tmp_path, {
        "FF IX.m3u": "FF IX (Disc 1).cue\n",
        "FF IX (Disc 1).cue": 'FILE "FF IX (Disc 1).bin" BINARY\n',
        "FF IX (Disc 1).bin": b"x",
    })
    assert [f.name for f in iter_rom_files(tmp_path, ["*.bin", "*.cue"])] == \
        ["FF IX (Disc 1).cue"], "no *.m3u in the catalogue → the .cue stays"


def test_no_extension_filter_still_dedups(tmp_path):
    """An empty extension list means 'scan everything' — the dedup applies."""
    _tree(tmp_path, {
        "Solo Dump.cue": 'FILE "Solo Dump.bin" BINARY\n',
        "Solo Dump.bin": b"x",
    })
    assert [f.name for f in iter_rom_files(tmp_path, [])] == ["Solo Dump.cue"]
