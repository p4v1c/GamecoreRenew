"""Where PS4 system modules are declared, pinned to where shadPS4 reads them."""
import json
from pathlib import Path

BIOS = json.loads((Path(__file__).parents[1] / "pack.json").read_text())["bios"]


def test_modules_sit_in_the_flatpak_user_dir_sys_modules():
    # shadPS4's user dir is $XDG_DATA_HOME/shadPS4 (common/path_util.cpp), and
    # Flatpak points XDG_DATA_HOME at the app's data/, not config/.
    assert BIOS["dir"] == "@FLATPAK_DATA@/shadPS4"
    assert all(f["file"].startswith("sys_modules/") and f["file"].endswith(".sprx")
               for f in BIOS["files"])


def test_no_module_blocks_a_launch():
    # shadPS4 stubs or emulates every missing module, so a game always gets to try.
    assert not any(f["required"] for f in BIOS["files"])
