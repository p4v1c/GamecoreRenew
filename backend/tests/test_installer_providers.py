"""Providers and the download helper.

Every assertion here corresponds to a protection the shell blocks earned the
hard way — the comments in install/arch.sh say which failure each one came
from. They are the reason `duck_fetch` and `xenia_fetch` could be merged at
all: losing one silently is the risk this file exists to remove.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.services.catalog import load_catalog                      # noqa: E402
from backend.services.installer import Context, fetch, install, sandbox_flags  # noqa: E402
from backend.services.installer import providers as prov               # noqa: E402

CATALOG = ROOT / "catalog"
LOCAL = ROOT / "config" / "catalog.d"

ELF = b"\x7fELF" + b"\x00" * 60
ZIP = b"PK\x03\x04" + b"\x00" * 60


@pytest.fixture(scope="module")
def packs():
    return load_catalog(CATALOG, LOCAL)


# ── URLs: the fixed one first, and why ─────────────────────────────────────

def test_the_fixed_release_url_is_used_for_latest():
    """`/releases/latest/download/<asset>` is a plain 302 served OUTSIDE the
    API's 60-requests-per-hour-per-IP budget. Fresh installs kept ending up
    with no PlayStation emulator because the API quota was exhausted and the
    step gave up without ever attempting a download."""
    assert fetch.github_asset_url("stenzek/duckstation", "DuckStation-x64.AppImage") \
        == "https://github.com/stenzek/duckstation/releases/latest/download/DuckStation-x64.AppImage"


def test_a_pinned_version_uses_the_tag_url():
    """New in phase 3: a pack may pin a release instead of tracking latest."""
    assert fetch.github_asset_url("a/b", "x.zip", "v1.2.3") \
        == "https://github.com/a/b/releases/download/v1.2.3/x.zip"


def test_the_api_is_only_the_fallback(monkeypatch, tmp_path):
    calls = []

    def fake_download(url, dest, **kw):
        calls.append(url)
        dest.write_bytes(ELF)
        return True

    monkeypatch.setattr(fetch, "download", fake_download)
    monkeypatch.setattr(fetch, "github_api_asset",
                        lambda *a, **k: pytest.fail("API must not be asked first"))
    assert fetch.fetch_release_asset("a/b", "x", tmp_path / "out", magic="ELF")
    assert calls == ["https://github.com/a/b/releases/latest/download/x"]


def test_the_api_is_asked_when_the_fixed_url_fails(monkeypatch, tmp_path):
    """It earns its place: Xenia Canary tags releases with a commit hash, so
    the asset name is the only fixed part of the URL."""
    seen = []

    def fake_download(url, dest, **kw):
        seen.append(url)
        return url.startswith("https://api-resolved/")

    monkeypatch.setattr(fetch, "download", fake_download)
    monkeypatch.setattr(fetch, "github_api_asset", lambda *a, **k: "https://api-resolved/x.zip")
    assert fetch.fetch_release_asset("a/b", "x.zip", tmp_path / "o", magic="PK")
    assert len(seen) == 2 and seen[1] == "https://api-resolved/x.zip"


def test_an_unreachable_api_returns_empty_not_an_exception(monkeypatch):
    """`|| true` in the shell: an unreachable API left the URL empty instead of
    json.load crashing on an empty stream and killing the install under set -e —
    and that crash still printed a ten-line traceback that reads like a broken
    install."""
    monkeypatch.setattr("urllib.request.urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("no net")))
    assert fetch.github_api_asset("a/b", "x") == ""


# ── the download itself ────────────────────────────────────────────────────

def _fake_curl(monkeypatch, body: bytes | None, rc: int = 0):
    def run(cmd, **kw):
        if cmd[0] == "curl":
            out = Path(cmd[cmd.index("-o") + 1])
            if body is not None:
                out.write_bytes(body)
            return subprocess.CompletedProcess(cmd, rc, "", "")
        return subprocess.CompletedProcess(cmd, 0, "", "")
    monkeypatch.setattr(subprocess, "run", run)


def test_a_wrong_body_is_rejected_even_on_a_200(monkeypatch, tmp_path):
    """`curl -f` cannot catch a proxy or a CDN that answers 200 with something
    else entirely. An AppImage is an ELF — check the magic."""
    _fake_curl(monkeypatch, b"<html>404 not found</html>")
    dest = tmp_path / "duckstation.AppImage"
    assert fetch.download("https://x/y", dest, magic="ELF") is False
    assert not dest.exists()


def test_nothing_is_left_at_the_final_name_on_failure(monkeypatch, tmp_path):
    """A transfer aborted by --speed-limit must never land at the final name
    and get mistaken for a good install on the next run."""
    _fake_curl(monkeypatch, b"junk", rc=28)          # 28 = curl timeout
    dest = tmp_path / "x.AppImage"
    assert fetch.download("https://x/y", dest, magic="ELF") is False
    assert not dest.exists()
    assert not dest.with_name(dest.name + ".part").exists()


def test_a_good_download_lands(monkeypatch, tmp_path):
    _fake_curl(monkeypatch, ELF)
    dest = tmp_path / "x.AppImage"
    assert fetch.download("https://x/y", dest, magic="ELF") is True
    assert dest.read_bytes() == ELF


def test_a_sha256_mismatch_is_refused(monkeypatch, tmp_path):
    """New in phase 3. There is no integrity check anywhere in install/ or
    update/ today: magic bytes catch an error page or a truncated transfer,
    not an altered binary."""
    _fake_curl(monkeypatch, ELF)
    dest = tmp_path / "x"
    assert fetch.download("https://x/y", dest, magic="ELF",
                          sha256="0" * 64) is False
    assert not dest.exists()


def test_a_matching_sha256_is_accepted(monkeypatch, tmp_path):
    _fake_curl(monkeypatch, ELF)
    good = __import__("hashlib").sha256(ELF).hexdigest()
    dest = tmp_path / "x"
    assert fetch.download("https://x/y", dest, magic="ELF", sha256=good) is True


def test_extraction_failure_is_not_fatal(tmp_path):
    """A GitHub hiccup left unzip exiting 9, and because the `case` around it
    was not part of an &&/|| list, set -e aborted the WHOLE install at 52 % —
    before a single systemd unit, sudoers rule or autologin config existed."""
    bad = tmp_path / "broken.zip"
    bad.write_bytes(b"PKnot-really-a-zip")
    assert fetch.extract(bad, tmp_path / "out") is False      # no exception


# ── providers ──────────────────────────────────────────────────────────────

def test_an_existing_appimage_with_the_right_magic_is_left_alone(packs, tmp_path, monkeypatch):
    """`-f dest` alone treats a truncated download or a saved HTML error page
    as 'installed' forever."""
    monkeypatch.setattr(fetch, "download",
                        lambda *a, **k: pytest.fail("must not re-download"))
    dest = tmp_path / "bin" / "duckstation.AppImage"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(ELF)
    r = install(packs["duckstation"], Context(gamecore_path=tmp_path))
    assert r.ok and r.already


def test_a_corrupt_appimage_is_replaced(packs, tmp_path, monkeypatch):
    dest = tmp_path / "bin" / "duckstation.AppImage"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"<html>error</html>")           # what a bad run leaves
    monkeypatch.setattr(prov, "fetch_release_asset",
                        lambda *a, **k: (a[2].write_bytes(ELF), True)[1])
    r = install(packs["duckstation"], Context(gamecore_path=tmp_path))
    assert r.ok and not r.already
    assert dest.read_bytes() == ELF


def test_a_failed_download_costs_one_tile_not_the_install(packs, tmp_path, monkeypatch):
    monkeypatch.setattr(prov, "fetch_release_asset", lambda *a, **k: False)
    r = install(packs["duckstation"], Context(gamecore_path=tmp_path))
    assert r.ok is False
    assert "tile will be missing" in r.message
    assert "nothing else is affected" in r.message


def test_an_archive_pack_checks_its_entrypoint(packs, tmp_path, monkeypatch):
    """xenia_canary.exe missing after extraction means the Xbox 360 tile will
    not launch — reported, not silently 'installed'."""
    monkeypatch.setattr(prov, "fetch_release_asset",
                        lambda *a, **k: (a[2].write_bytes(ZIP), True)[1])
    monkeypatch.setattr(prov, "extract", lambda *a, **k: True)   # extracts nothing
    monkeypatch.setattr(prov, "_pacman_install", lambda *a, **k: True)
    r = install(packs["xenia"], Context(gamecore_path=tmp_path))
    assert r.ok is False and "xenia_canary.exe" in r.message


def test_an_archive_pack_succeeds_when_the_entrypoint_lands(packs, tmp_path, monkeypatch):
    def fake_extract(archive, into):
        (into / "xenia_canary.exe").parent.mkdir(parents=True, exist_ok=True)
        (into / "xenia_canary.exe").write_bytes(b"MZ")
        return True
    monkeypatch.setattr(prov, "fetch_release_asset",
                        lambda *a, **k: (a[2].write_bytes(ZIP), True)[1])
    monkeypatch.setattr(prov, "extract", fake_extract)
    monkeypatch.setattr(prov, "_pacman_install", lambda *a, **k: True)
    r = install(packs["xenia"], Context(gamecore_path=tmp_path))
    assert r.ok and (tmp_path / "lib/xenia/xenia_canary.exe").is_file()


def test_an_unknown_provider_fails_loudly_not_silently(packs, tmp_path):
    # A copy: `packs` is module-scoped, and mutating it here poisoned every
    # later test that reads duckstation's provider.
    import copy
    pack = copy.deepcopy(packs["duckstation"])
    pack.data["install"] = {"provider": "carrier-pigeon"}
    r = install(pack, Context(gamecore_path=tmp_path))
    assert r.ok is False and "carrier-pigeon" in r.message


def test_a_pack_with_no_install_block_installs_nothing(packs, tmp_path):
    r = install(packs["youtube"], Context(gamecore_path=tmp_path))
    assert r.ok and r.already


# ── sandbox policy ─────────────────────────────────────────────────────────

def test_the_emulator_policy_is_the_default(packs, tmp_path):
    flags = sandbox_flags(packs["rpcs3"], Context(gamecore_path=Path("/opt/GameCore")))
    assert flags == ["--filesystem=/opt/GameCore", "--device=all", "--socket=x11"]


def test_stremio_declares_a_different_policy(packs):
    """Two genuinely different policies, so both are explicit rather than one
    being hardcoded in two unrelated places in arch.sh."""
    flags = sandbox_flags(packs["stremio"], Context(gamecore_path=Path("/opt/GameCore")))
    assert "--filesystem=host" in flags
    assert "--socket=x11" not in flags


# ── the catalogue drives it ────────────────────────────────────────────────

def test_every_pack_names_a_provider_that_exists(packs):
    for pack in packs.values():
        spec = pack.data.get("install")
        if spec:
            assert spec["provider"] in prov.PROVIDERS, pack.id


def test_duckstation_and_xenia_are_data_now(packs):
    """Phase 3: the two bespoke shell blocks became pack fields."""
    duck = packs["duckstation"].data["install"]
    assert duck["provider"] == "github-asset"
    assert duck["repo"] == "stenzek/duckstation"
    assert duck["magic"] == "ELF"

    xenia = packs["xenia"].data["install"]
    assert xenia["provider"] == "github-archive"
    assert xenia["entrypoint"] == "xenia_canary.exe"
    assert set(xenia["requires"]) == {"wine", "unzip", "p7zip"}
