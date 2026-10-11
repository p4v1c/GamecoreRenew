"""Lutris games run in a nested gamescope window that opens windowed under
the console's KWin, even with gamescope's `-f`: the tile asks the enforcer."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from backend.services import fullscreen_enforcer as fe              # noqa: E402
from backend.services.catalog import load_catalog                   # noqa: E402
from backend.services.catalog.tiles import tile_entry               # noqa: E402

# WM_CLASS (res_name, res_class) read with xprop on the window of the
# Lutris flatpak's gamescope 3.16.31: SDL2 names it after the binary.
GAMESCOPE_WM_CLASS = ("gamescope-brokey", "gamescope-brokey")


class _Window:
    def get_wm_class(self):
        return GAMESCOPE_WM_CLASS


class _Display:
    def intern_atom(self, name):
        return 1

    def screen(self):
        prop = type("Prop", (), {"value": [0]})()
        root = type("Root", (), {"get_full_property": lambda self, a, k: prop})()
        return type("Screen", (), {"root": root})()

    def create_resource_object(self, kind, wid):
        return _Window()


def test_the_lutris_tile_fullscreens_the_gamescope_window():
    pack = load_catalog(ROOT / "catalog", ROOT / "config" / "catalog.d")["lutris"]
    fs = tile_entry(pack)["fullscreen"]
    assert fe._find_window(_Display(), fs["wm_class"]) is not None
