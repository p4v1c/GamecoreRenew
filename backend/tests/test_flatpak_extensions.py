"""install.extensions: the branch comes from the runtime, the installation from the app."""
import subprocess
from types import SimpleNamespace

import pytest

from backend.services.installer import flatpak_extensions as fx
from backend.services.installer.applier import AppContext

LAYER = "org.freedesktop.Platform.VulkanLayer.gamescope"
POINT = "org.freedesktop.Platform.VulkanLayer"
# `flatpak info --show-metadata org.gnome.Platform//49`, trimmed, as read on a
# box with the Flathub Lutris of 2026 (spaces around `=` are flatpak's own).
GNOME_49 = """[Runtime]
name=org.gnome.Platform
runtime=org.gnome.Platform/x86_64/49

[Extension org.freedesktop.Platform.GL]
versions = 25.08;25.08-extra;1.4
version = 1.4
directory = lib/x86_64-linux-gnu/GL

[Extension org.freedesktop.Platform.VulkanLayer]
version = 25.08
directory = lib/extensions/vulkan
subdirectories = true
no-autodownload = true
"""
LUTRIS_META = """[Application]
name=net.lutris.Lutris
runtime=org.gnome.Platform/x86_64/49

[Extension org.freedesktop.Platform.Compat.i386]
directory=lib/i386-linux-gnu
version=25.08
"""


class FakeFlatpak:
    """Answers `flatpak …` like a box; records installs."""

    def __init__(self, app_in="system", installed=(), runtime=GNOME_49, app_meta=LUTRIS_META):
        self.app_in, self.installed = app_in, set(installed)
        self.runtime, self.app_meta = runtime, app_meta
        self.calls = []

    def __call__(self, argv, **kw):
        self.calls.append(argv)
        args = argv[1:]
        out, code = "", 0
        if args[0] == "info":
            where = next((a[2:] for a in args if a in ("--system", "--user")), None)
            ref = args[-1]
            if "--show-metadata" in args:
                out = self.runtime if ref.startswith("org.gnome.Platform") else self.app_meta
            elif "--show-runtime" in args:
                out = "org.gnome.Platform/x86_64/49\n"
            elif "--show-origin" in args:
                out = "flathub\n"
            elif ref == "net.lutris.Lutris":
                code = 0 if where == self.app_in else 1
            else:
                code = 0 if (where, ref) in self.installed else 1
        elif args[0] == "install":
            where = next(a[2:] for a in args if a in ("--system", "--user"))
            self.installed.add((where, args[-1]))
        return subprocess.CompletedProcess(argv, code, out, "")


def pack(extensions=({"id": LAYER, "extensionPoint": POINT},)):
    return SimpleNamespace(id="lutris", app_ids=["net.lutris.Lutris"], data={
        "install": {"provider": "flatpak", "appIds": ["net.lutris.Lutris"],
                    "extensions": list(extensions)}})


@pytest.fixture(autouse=True)
def no_manifest(monkeypatch):
    monkeypatch.setattr(fx.manifest, "record_new_flatpak", lambda ref: None)


def ctx(tmp_path, dry=False):
    return AppContext(gamecore_path=tmp_path, dry_run=dry)


def test_the_branch_is_the_one_the_runtime_declares(tmp_path):
    run = FakeFlatpak()
    [result] = fx.ensure(pack(), ctx(tmp_path), run=run)
    assert result.ok and not result.already
    install = next(c for c in run.calls if c[1] == "install")
    assert install == ["flatpak", "install", "-y", "--noninteractive", "--system",
                       "flathub", f"{LAYER}//25.08"]


def test_a_newer_runtime_gets_its_own_branch(tmp_path):
    run = FakeFlatpak(installed={("system", f"{LAYER}//25.08")},
                      runtime=GNOME_49.replace("version = 25.08", "version = 26.08"))
    [result] = fx.ensure(pack(), ctx(tmp_path), run=run)
    assert result.ok and ("system", f"{LAYER}//26.08") in run.installed


def test_a_layer_installed_by_hand_is_left_alone(tmp_path):
    run = FakeFlatpak(installed={("system", f"{LAYER}//25.08")})
    [result] = fx.ensure(pack(), ctx(tmp_path), run=run)
    assert result.already
    assert not any(c[1] == "install" for c in run.calls)


def test_a_user_installed_lutris_gets_a_user_layer(tmp_path):
    run = FakeFlatpak(app_in="user")
    fx.ensure(pack(), ctx(tmp_path), run=run)
    assert ("user", f"{LAYER}//25.08") in run.installed


def test_an_app_that_declares_the_point_itself_wins_over_its_runtime(tmp_path):
    meta = LUTRIS_META + f"\n[Extension {LAYER}]\ndirectory=lib/extensions/vulkan/gamescope\nversion=26.08\n"
    meta += f"\n[Extension {POINT}]\nversion=26.08\n"
    run = FakeFlatpak(app_meta=meta)
    fx.ensure(pack(), ctx(tmp_path), run=run)
    assert ("system", f"{LAYER}//26.08") in run.installed


def test_without_lutris_nothing_is_installed(tmp_path):
    run = FakeFlatpak(app_in=None)
    [result] = fx.ensure(pack(), ctx(tmp_path), run=run)
    assert not result.ok
    assert not any(c[1] == "install" for c in run.calls)


def test_dry_run_and_packs_without_extensions_touch_nothing(tmp_path):
    run = FakeFlatpak()
    assert fx.ensure(pack(), ctx(tmp_path, dry=True), run=run)[0].ok
    assert fx.ensure(pack(extensions=()), ctx(tmp_path), run=run) == []
    assert run.calls == []


@pytest.mark.parametrize("meta, expected", [
    (GNOME_49, "25.08"),
    ("[Extension org.freedesktop.Platform.VulkanLayer]\nversions=24.08;23.08\n", "24.08"),
    ("[Runtime]\nname=x\n", None),
    ("not an ini at all", None),
])
def test_declared_version(meta, expected):
    assert fx.declared_version(meta, POINT) == expected


def test_the_lutris_pack_declares_gamescopes_layer():
    from backend.services.catalog import load_catalog
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    lutris = load_catalog(root / "catalog", root / "nowhere")["lutris"]
    assert lutris.data["install"]["extensions"] == [{"id": LAYER, "extensionPoint": POINT}]
