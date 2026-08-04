"""The catalogue: schema, symmetry, seeds, merge rule, data-only rule.

`scripts/check-catalog.py` runs the first three against the real repository and
is what CI calls; the tests here re-run it (so a broken pack fails the suite
too) and cover what a static check cannot: the loader's merge behaviour and the
security rule that strips code-executing blocks from local packs.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from backend.services.catalog import load_catalog, load_schema, validate  # noqa: E402

# NOT the module constants: conftest.py aims GAMECORE_PATH at a throwaway root,
# so `backend.services.catalog.CATALOG_DIR` points at an empty temp directory
# here. These tests are about the catalogue in the repository.
CATALOG = ROOT / "catalog"
LOCAL = ROOT / "config" / "catalog.d"
SCHEMA_FILE = CATALOG / "_schema" / "pack.schema.json"


def _packs():
    return [d for d in sorted(CATALOG.iterdir())
            if d.is_dir() and not d.name.startswith(("_", "."))]


def _load(d: Path) -> dict:
    return json.loads((d / "pack.json").read_text(encoding="utf-8"))


# ── the shipped catalogue ───────────────────────────────────────────────────

def test_the_repository_catalogue_is_clean():
    """Everything scripts/check-catalog.py checks, against the real packs."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "check_catalog", ROOT / "scripts" / "check-catalog.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    problems = mod.check()
    assert problems == [], "\n".join(problems)


@pytest.mark.parametrize("directory", _packs(), ids=lambda d: d.name)
def test_every_pack_validates(directory):
    schema = load_schema(SCHEMA_FILE)
    assert validate(_load(directory), schema, directory.name) == []


@pytest.mark.parametrize("directory", _packs(), ids=lambda d: d.name)
def test_every_pack_has_a_logo(directory):
    assert any((directory / n).is_file() for n in ("logo.png", "logo.svg"))


@pytest.mark.parametrize("directory", _packs(), ids=lambda d: d.name)
def test_an_emulator_declares_a_rom_directory(directory):
    pack = _load(directory)
    if pack["kind"] == "emulator":
        assert pack["roms"]["dir"].startswith("emu/")
    else:
        assert "roms" not in pack


def test_flatpak_config_destinations_derive_from_the_installed_app_id():
    """The gopher64 bug, made structurally impossible.

    `install-emu-configs.sh` deployed the N64 seed to
    ~/.var/app/io.github.gopher64.gopher64/... while the installer installed
    com.github.Rosalie241.RMG. The mkdir CREATED the phantom directory, copied
    the files, printed a tick, and RMG never saw any of it.

    A pack cannot express that: @FLATPAK_CONFIG@ resolves from the SAME
    install.appId the installer uses, so the two cannot drift.
    """
    for directory in _packs():
        pack = _load(directory)
        dest = (pack.get("config") or {}).get("dest", "")
        if "@FLATPAK_CONFIG@" not in dest:
            continue
        install = pack.get("install") or {}
        assert install.get("provider") == "flatpak", directory.name
        assert install.get("appId"), directory.name


def test_no_seed_carries_a_harvest_box_home():
    """A personal username shipped in a public repository for a long time."""
    offenders = []
    for directory in _packs():
        for f in (directory / "seed").rglob("*") if (directory / "seed").is_dir() else []:
            if not f.is_file() or f.suffix.lower() in {".png", ".sqlite3", ".db"}:
                continue
            try:
                if "/home/pavic" in f.read_text(encoding="utf-8"):
                    offenders.append(str(f.relative_to(ROOT)))
            except (OSError, UnicodeDecodeError):
                pass
    assert offenders == [], offenders


def test_the_generated_dist_files_are_in_sync():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "gen_catalog", ROOT / "scripts" / "gen-catalog.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    systems, apps = mod.render(load_catalog(CATALOG, LOCAL))
    assert (ROOT / "install/systems.json.dist").read_text(encoding="utf-8") == systems
    assert (ROOT / "install/apps.json.dist").read_text(encoding="utf-8") == apps


# ── the loader ──────────────────────────────────────────────────────────────

MINIMAL = {
    "id": "demo", "kind": "app", "label": "Demo", "platform": "Web",
    "color": "#123456", "launch": {"path": "true"},
}


@pytest.fixture
def two_locations(tmp_path):
    shipped, local = tmp_path / "catalog", tmp_path / "catalog.d"
    (shipped / "_schema").mkdir(parents=True)
    local.mkdir()
    shutil.copy(SCHEMA_FILE, shipped / "_schema" / "pack.schema.json")
    return shipped, local


def _write(base: Path, pack: dict, **files: str) -> Path:
    d = base / pack["id"]
    d.mkdir(parents=True, exist_ok=True)
    (d / "pack.json").write_text(json.dumps(pack), encoding="utf-8")
    (d / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    for name, content in files.items():
        (d / name.replace("__", ".")).write_text(content, encoding="utf-8")
    return d


def test_a_local_pack_replaces_the_shipped_one_entirely(two_locations):
    shipped, local = two_locations
    _write(shipped, {**MINIMAL, "label": "Shipped", "platform": "Web"})
    _write(local, {**MINIMAL, "label": "Local"})

    packs = load_catalog(shipped, local)

    assert packs["demo"].data["label"] == "Local"
    assert packs["demo"].origin == "local"


def test_the_schema_directory_is_not_a_pack(two_locations):
    shipped, local = two_locations
    _write(shipped, MINIMAL)
    assert set(load_catalog(shipped, local)) == {"demo"}


def test_an_invalid_pack_is_ignored_not_fatal(two_locations, caplog):
    shipped, local = two_locations
    _write(shipped, MINIMAL)
    bad = shipped / "broken"
    bad.mkdir()
    (bad / "pack.json").write_text('{"id": "broken", "kind": "nope"}', encoding="utf-8")

    packs = load_catalog(shipped, local)

    assert set(packs) == {"demo"}, "a broken pack must not take the catalogue down"


def test_a_pack_whose_id_disagrees_with_its_directory_is_ignored(two_locations):
    shipped, local = two_locations
    d = shipped / "elsewhere"
    d.mkdir()
    (d / "pack.json").write_text(json.dumps(MINIMAL), encoding="utf-8")
    assert load_catalog(shipped, local) == {}


# ── code vs data: the security rule for config/catalog.d/ ───────────────────

PRIVILEGED = {
    **MINIMAL,
    "packages": {"pacman": ["firefox"]},
    "sources": [{"git": "https://example.invalid/x.git", "dest": "/opt/x"}],
    "services": [{"unit": "files/x.service", "scope": "user"}],
    "postInstall": [{"run": "steps/x.sh"}],
}


def test_a_local_pack_is_data_only_by_default(two_locations, monkeypatch):
    monkeypatch.delenv("GAMECORE_TRUST_LOCAL_PACKS", raising=False)
    shipped, local = two_locations
    _write(local, PRIVILEGED, generator__py="raise SystemExit('pwned')")

    pack = load_catalog(shipped, local)["demo"]

    for block in ("packages", "sources", "services", "postInstall"):
        assert block not in pack.data, f"{block} must be stripped from a local pack"
    assert pack.generator is None, "a local generator.py must not be offered"
    assert set(pack.stripped) >= {"packages", "sources", "services",
                                  "postInstall", "generator.py"}


def test_a_shipped_pack_keeps_its_privileged_blocks(two_locations):
    shipped, local = two_locations
    _write(shipped, PRIVILEGED, generator__py="# real code")

    pack = load_catalog(shipped, local)["demo"]

    assert pack.data["sources"] and pack.data["services"]
    assert pack.generator is not None


def test_the_opt_in_restores_them(two_locations, monkeypatch):
    monkeypatch.setenv("GAMECORE_TRUST_LOCAL_PACKS", "1")
    shipped, local = two_locations
    _write(local, PRIVILEGED, generator__py="# trusted")

    pack = load_catalog(shipped, local)["demo"]

    assert pack.data["postInstall"] == [{"run": "steps/x.sh"}]
    assert pack.generator is not None
    assert pack.stripped == []


def test_the_opt_in_warns_on_every_load(two_locations, monkeypatch, caplog):
    """Logged every time, not once: an operator who turned this on months ago
    must keep being told."""
    import logging
    monkeypatch.setenv("GAMECORE_TRUST_LOCAL_PACKS", "1")
    shipped, local = two_locations
    _write(local, PRIVILEGED)

    with caplog.at_level(logging.WARNING):
        load_catalog(shipped, local)
        load_catalog(shipped, local)

    warnings = [r for r in caplog.records if "TRUST_LOCAL_PACKS" in r.getMessage()]
    assert len(warnings) == 2


# ── preferIfPresent: the REWRITE pass of flatpakify-systems.sh ──────────────

def test_prefer_if_present_wins_only_when_the_path_exists(two_locations, tmp_path):
    shipped, local = two_locations
    _write(shipped, {**MINIMAL,
                     "launch": {"path": "flatpak", "args": "run net.rpcs3.RPCS3",
                                "preferIfPresent": {"path": "lib/rpcs3",
                                                    "args": "--fullscreen"}}})
    pack = load_catalog(shipped, local)["demo"]

    assert pack.launcher() == ("flatpak", "run net.rpcs3.RPCS3")
    assert pack.launcher(prefer_existing=True, root=tmp_path) == \
        ("flatpak", "run net.rpcs3.RPCS3"), "lib/rpcs3 does not exist here"

    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "rpcs3").touch()
    assert pack.launcher(prefer_existing=True, root=tmp_path) == \
        ("lib/rpcs3", "--fullscreen")
