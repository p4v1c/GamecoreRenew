"""The tile contract: one shape, whoever builds it.

A tile is the set of fields `games.py` reads to launch something. It used to be
written down twice — once in `scripts/gen-catalog.py` for the shipped `.dist`,
once in `backend/services/catalog/merge.py` for a tile an OTA adds to a box —
and the two had drifted three ways before anyone looked:

  · Stremio's `fullscreen` block existed only in the first, so the tile was
    fullscreen on a fresh install and windowed on an updated one;
  · `iconPath` was `ps1.png` in one and `duckstation.png` in the other;
  · one crashed on a pack with no `roms` block and the other did not.

None of it was caught, because nothing compared them. This file does.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.services.catalog import load_catalog
from backend.services.catalog.merge import entry_from_pack
from backend.services.catalog.tiles import tile_entry

CATALOG = ROOT / "catalog"
LOCAL = ROOT / "config" / "catalog.d"


@pytest.fixture(scope="module")
def packs():
    return load_catalog(CATALOG, LOCAL)


def test_both_builders_agree_on_the_field_set(packs):
    """The one assertion that would have caught all three divergences.

    The two callers may legitimately differ on the VALUE of path/args — merge
    knows what is installed on this box, the generator does not. They may never
    differ on which fields exist.
    """
    mismatched = {}
    for pack in packs.values():
        shipped = set(tile_entry(pack))
        merged = set(entry_from_pack(pack, ROOT))
        if shipped != merged:
            mismatched[pack.id] = sorted(shipped ^ merged)
    assert not mismatched, f"the two tile builders disagree on fields: {mismatched}"


def test_launch_behaviour_survives_both_paths(packs):
    """An app with no fullscreen flag on the command line is fullscreened only
    by the enforcer, and the enforcer only runs if the tile says so.

    The pack is found by what it declares, not by name: naming it would tie this
    test to the catalogue shipping that particular app for ever.
    """
    declaring = [p for p in packs.values() if (p.data["launch"].get("fullscreen"))]
    assert declaring, "no pack declares launch.fullscreen — has the block been lost again?"
    for pack in declaring:
        for build in (lambda p: tile_entry(p), lambda p: entry_from_pack(p, ROOT)):
            tile = build(pack)
            assert tile["fullscreen"]["wm_class"], f"{pack.id}: no wm_class, the enforcer does nothing"
            assert tile["fullscreen"]["timeout_s"] > 0


def test_every_tile_names_a_logo_after_its_own_pack(packs):
    """One naming rule. There were two — eleven ids mapped to platform names —
    and a table to consult to know which applied."""
    for pack in packs.values():
        icon = tile_entry(pack)["iconPath"]
        assert Path(icon).stem == pack.id, f"{pack.id}: {icon} is not named after the pack"
        assert pack.logo is not None, f"{pack.id} declares {icon} but ships no logo"


def test_an_emulator_without_a_roms_block_does_not_crash_the_build(packs):
    """The schema does not require `roms`. One builder read it with [] and the
    other with .get(), so the same pack crashed CI and merged fine on a box."""
    pack = next(p for p in packs.values() if p.kind == "emulator")
    stripped = type(pack)(id=pack.id, data={k: v for k, v in pack.data.items() if k != "roms"},
                          path=pack.path, origin=pack.origin)
    assert tile_entry(stripped)["romsPath"] == f"emu/{pack.id}/"
    assert entry_from_pack(stripped, ROOT)["romsPath"] == f"emu/{pack.id}/"


def test_prefer_if_present_is_the_only_thing_the_box_changes(packs):
    """merge honours `preferIfPresent` only when that binary is really here;
    the generator always records it. That is the one intended difference — and
    it must show up in path/args and nowhere else."""
    for pack in packs.values():
        shipped = tile_entry(pack)
        merged = entry_from_pack(pack, ROOT)
        differing = {k for k in shipped if shipped[k] != merged.get(k)}
        assert differing <= {"path", "args"}, \
            f"{pack.id}: the two builders differ on {differing - {'path', 'args'}}"


# ── reading the app id out of a flatpak launcher ───────────────────────────

def test_the_app_id_is_the_first_non_option_argument():
    """Found on a real box, and silent in both readers.

    `geforcenow` launches `run --nosocket=wayland --socket=x11
    com.nvidia.geforcenow`. Both readers used to take the token after `run`
    and therefore read `--nosocket=wayland` as the application id:

      · process_manager._flatpak_kill ran `flatpak kill --nosocket=wayland`,
        which kills nothing — and it only warns when `run` is missing, which it
        was not, so quitting the app left its sandbox running and the log said
        the kill had been issued;
      · merge.launcher_is_stale found no pack declaring `--nosocket=wayland`
        and would have rewritten the launcher as stale. Latent only because no
        pack ships flags today.
    """
    from backend.services.catalog.tiles import flatpak_app_id

    assert flatpak_app_id("run --nosocket=wayland --socket=x11 com.nvidia.geforcenow") \
        == "com.nvidia.geforcenow"
    # The ordinary shape every pack uses, and the flags that follow an id.
    assert flatpak_app_id("run net.rpcs3.RPCS3") == "net.rpcs3.RPCS3"
    assert flatpak_app_id("run net.shadps4.shadPS4 --fullscreen true -g") \
        == "net.shadps4.shadPS4"


@pytest.mark.parametrize("args", ["", "kill net.rpcs3.RPCS3", "run", "run --only-flags"])
def test_something_that_is_not_a_flatpak_run_yields_nothing(args):
    """Empty, never a guess. `merge` treats "" as "no opinion" and leaves the
    launcher alone; `_flatpak_kill` warns and falls back to killpg. A wrong id
    would make one rewrite a working launcher and the other kill nothing."""
    from backend.services.catalog.tiles import flatpak_app_id
    assert flatpak_app_id(args) == ""


def test_every_shipped_flatpak_launcher_defers_to_the_catalogue(packs):
    """The fix must not move any pack that was already correct.

    All twelve put the id straight after `run`, so this is the characterisation
    half: whatever the rule becomes, it keeps answering what the catalogue
    declares — which is now the token, not a literal id. A pack that spells the
    id out is a launcher that cannot follow a fallback, and check-catalog.py
    refuses it; here the reader is what is under test, so what matters is that
    it lands on the token and not on a flag that happens to precede it.
    """
    from backend.services.catalog.tiles import APPID_TOKEN, flatpak_app_id

    wrong = []
    for pack in packs.values():
        if not pack.app_ids:
            continue
        _, args = pack.launcher()
        if args.startswith("run ") and flatpak_app_id(args) != APPID_TOKEN:
            wrong.append(f"{pack.id}: read {flatpak_app_id(args)!r}, "
                         f"expected {APPID_TOKEN}")
    assert wrong == [], "\n".join(wrong)
