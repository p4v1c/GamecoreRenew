"""Which app id a box means, and what the launcher does about it.

`install.appIds` is only half a fix. The other half is that nothing downstream
may re-freeze the choice: the day Ryujinx original left Flathub, a pack that
had spelled one id in `install.appId` and again in `launch.args` broke twice,
and the second break outlived the first. The installer could be corrected by a
release; the tile in a box's own `config/systems.json` could not, because
`config/` is deliberately excluded from the OTA rsync.

So the assertions here are about the SEAM, not about any particular emulator:

  · the resolver answers deterministically when nothing has been probed, or the
    generated `.dist` files would differ per developer machine;
  · a box that fell back gets its config directory, its BIOS directory and its
    launcher pointing at the SAME id — one drifting from the others is the
    gopher64 bug wearing a new hat;
  · a launcher that cannot be resolved refuses by name instead of handing
    `flatpak run @APPID@` to a shell.

Nothing here runs flatpak. The box is described, never probed — see the
`no_probe` fixture.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.services.catalog import Pack, appid                    # noqa: E402
from backend.services.catalog import launch as catalog_launch       # noqa: E402
from backend.services.catalog.tiles import APPID_TOKEN              # noqa: E402

PRIMARY, FALLBACK = "org.example.Primary", "org.example.Fallback"


def _pack(app_ids=(PRIMARY, FALLBACK), pack_id="probe", **overrides):
    data = {
        "id": pack_id, "kind": "app", "label": "Probe",
        "platform": "probe", "color": "#000000",
        "install": {"provider": "flatpak", "appIds": list(app_ids)},
        "launch": {"path": "flatpak", "args": f"run {APPID_TOKEN} -f"},
        "config": {"dest": "@FLATPAK_CONFIG@/probe"},
        "bios": {"dir": "@FLATPAK_DATA@/probe/keys"},
    }
    data.update(overrides)
    return Pack(id=pack_id, data=data, path=Path("/nonexistent"), origin="shipped")


@pytest.fixture(autouse=True)
def no_probe():
    """Every test starts from "nothing has been probed" and puts it back.

    The resolver's state is module-level by design — a box probes once. Leaking
    it between tests would make results depend on execution order, and leaking
    the DEVELOPER'S installed set into it would make them depend on which
    emulators happen to be on this machine.
    """
    appid.set_installed(None)
    yield
    appid.set_installed(None)


# ── the resolver ───────────────────────────────────────────────────────────

def test_an_unprobed_process_answers_the_declared_order():
    """The build, CI and the test suite never touch flatpak, and the `.dist`
    files they generate are compared byte-for-byte. An answer that depended on
    what is installed would make them differ per machine."""
    assert appid.resolve([PRIMARY, FALLBACK]) == PRIMARY
    assert appid.installed() is None


def test_the_installed_candidate_wins_over_the_preferred_one():
    appid.set_installed({FALLBACK})
    assert appid.resolve([PRIMARY, FALLBACK]) == FALLBACK


def test_the_preferred_candidate_wins_when_both_are_installed():
    appid.set_installed({PRIMARY, FALLBACK})
    assert appid.resolve([PRIMARY, FALLBACK]) == PRIMARY


def test_a_box_with_none_of_them_falls_back_to_the_declared_first():
    """A fresh box has nothing installed, and still has to name a config
    directory and a launcher. "The one we would install" is the only
    defensible answer, and it is what the single-valued field used to give."""
    appid.set_installed(set())
    assert appid.resolve([PRIMARY, FALLBACK]) == PRIMARY


def test_a_failed_probe_is_not_an_empty_box():
    """`flatpak list` failing means we cannot SEE the installation — wrong
    scope, flatpak not initialised, a sandbox. Reading that as "nothing is
    installed" is what would prune every tile off a working grid."""
    appid.set_installed(set())
    assert appid.installed() == frozenset()
    appid.set_installed(None)
    assert appid.installed() is None


def test_a_pack_that_is_not_flatpak_declares_no_app_id():
    """A github-asset pack expressing @FLATPAK_CONFIG@ would resolve its config
    directory against an application it never installs — gopher64, exactly."""
    pack = _pack(install={"provider": "github-asset", "repo": "a/b",
                          "asset": "x", "dest": "bin/x", "magic": "ELF"})
    assert pack.app_ids == []
    assert pack.app_id == ""


# ── the three paths must agree ─────────────────────────────────────────────

def test_config_bios_and_launcher_all_follow_the_same_fallback(monkeypatch):
    """The one that matters. A box that installed the fallback must not write
    its seed under the primary's ~/.var/app: the emulator would read an empty
    config directory while a fully populated one sat next to it, which is the
    gopher64 failure with different names.

    All three answers are taken in one test on purpose. Each is correct on its
    own in the two other files that cover it; what has to hold is that they
    agree, and only comparing them in one place can show that.
    """
    appid.set_installed({FALLBACK})
    pack, home = _pack(), Path("/home/player")
    monkeypatch.setattr(catalog_launch, "load_catalog", lambda *a, **k: {"probe": pack})
    monkeypatch.setattr(catalog_launch.appid, "probe", lambda *a, **k: appid.installed())

    launcher = catalog_launch.resolve_args("probe", pack.data["launch"]["args"])
    config = pack.expand(pack.data["config"]["dest"], home)
    bios = pack.expand(pack.data["bios"]["dir"], home)

    assert pack.app_id == FALLBACK
    assert config == home / f".var/app/{FALLBACK}/config/probe"
    assert bios == home / f".var/app/{FALLBACK}/data/probe/keys"
    assert launcher == f"run {FALLBACK} -f"
    # Spelled out rather than trusted from the three lines above: the failure
    # this guards is two of them agreeing and the third quietly not.
    assert {FALLBACK} == {pack.app_id, config.parts[-3], bios.parts[-4],
                          launcher.split()[1]}


# ── the launcher ───────────────────────────────────────────────────────────

def test_the_launcher_resolves_to_what_is_installed(monkeypatch):
    pack = _pack()
    monkeypatch.setattr(catalog_launch, "load_catalog", lambda *a, **k: {"probe": pack})
    monkeypatch.setattr(catalog_launch.appid, "probe",
                        lambda *a, **k: appid.set_installed({FALLBACK}))

    assert catalog_launch.resolve_args("probe", f"run {APPID_TOKEN} -f") == \
        f"run {FALLBACK} -f"


def test_a_launcher_without_the_token_is_untouched(monkeypatch):
    """Every native emulator and every browser kiosk goes through here. They
    must not pay a `flatpak list` — nor be able to fail because of one."""
    def explode(*_a, **_k):
        raise AssertionError("the catalogue was loaded for a tile with no token")

    monkeypatch.setattr(catalog_launch, "load_catalog", explode)
    assert catalog_launch.resolve_args("duck", "-nogui -fullscreen") == \
        "-nogui -fullscreen"


def test_a_token_no_pack_can_resolve_is_refused_by_name(monkeypatch):
    """Handing `flatpak run @APPID@` to the shell produces an error about an
    app id nobody typed. Refusing here names the system instead."""
    monkeypatch.setattr(catalog_launch, "load_catalog", lambda *a, **k: {})

    with pytest.raises(LookupError) as e:
        catalog_launch.resolve_args("ghost", f"run {APPID_TOKEN}")
    assert "ghost" in str(e.value)


def test_a_token_with_nothing_installed_says_so_rather_than_launching(monkeypatch):
    """The catalogue is fine and the emulator is simply not there. flatpak's
    own message names one id and never mentions that others were tried."""
    pack = _pack()
    monkeypatch.setattr(catalog_launch, "load_catalog", lambda *a, **k: {"probe": pack})
    monkeypatch.setattr(catalog_launch.appid, "probe",
                        lambda *a, **k: appid.set_installed(set()))

    with pytest.raises(LookupError) as e:
        catalog_launch.resolve_args("probe", f"run {APPID_TOKEN} -f")
    assert PRIMARY in str(e.value) and FALLBACK in str(e.value), str(e.value)


def test_an_unprobeable_box_launches_the_preferred_candidate_anyway(monkeypatch):
    """flatpak unqueryable is not "nothing is installed". Refusing the launch
    there would take the grid down over a probe that cannot run — the same
    rule flatpakify's prune already follows."""
    pack = _pack()
    monkeypatch.setattr(catalog_launch, "load_catalog", lambda *a, **k: {"probe": pack})
    monkeypatch.setattr(catalog_launch.appid, "probe", lambda *a, **k: None)

    assert catalog_launch.resolve_args("probe", f"run {APPID_TOKEN} -f") == \
        f"run {PRIMARY} -f"


# ── the shipped catalogue ──────────────────────────────────────────────────

def test_no_shipped_flatpak_launcher_spells_an_app_id_out():
    """The regression that would silently undo this whole phase: a pack added
    later that writes `run org.example.Thing` because that is what the other
    packs looked like before. check-catalog.py refuses it too — this is the
    half that runs in the test suite rather than the build.
    """
    from backend.services.catalog import load_catalog

    guilty = []
    for pack in load_catalog(ROOT / "catalog", ROOT / "config" / "catalog.d").values():
        for block in (pack.data["launch"],
                      pack.data["launch"].get("preferIfPresent") or {}):
            args = block.get("args", "")
            guilty += [f"{pack.id}: {a} in {args!r}" for a in pack.app_ids if a in args]
    assert guilty == [], "\n".join(guilty)
