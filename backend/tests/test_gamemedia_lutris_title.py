"""A `.lutris` stub must be looked up by its title, not by its filename.

`parse_rom` only peeled suffixes of five characters or fewer, so
`FIFA 22.lutris` kept its extension in the title. LaunchBox has
"FIFA 22" on Windows, but "FIFA 22.lutris" scored under the cutoff and
the game came back "launchbox: no match" with no metadata at all.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from backend.services.gamemedia.parser import normalize, parse_rom


def test_lutris_extension_is_not_part_of_the_title():
    parsed = parse_rom("/userdata/emu/lutris/FIFA 22.lutris")
    assert parsed["title"] == "FIFA 22"
    assert parsed["ext"] == "lutris"
    assert normalize(parsed["title"]) == normalize("FIFA 22")


def test_a_dotted_title_word_still_survives():
    assert parse_rom("Dr. Mario (USA).nes")["title"] == "Dr. Mario"


def test_every_pack_extension_is_peeled_off_the_title():
    """The suffix cap must cover whatever a pack declares, or its games miss."""
    from backend.services.catalog.loader import load_catalog
    for pack in load_catalog().values():
        for pattern in (pack.data.get("roms") or {}).get("extensions") or []:
            ext = pattern.lstrip("*.").lower()
            assert parse_rom(f"Some Game.{ext}")["ext"] == ext, (pack.id, ext)
