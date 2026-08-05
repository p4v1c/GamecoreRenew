"""Applying what a pack declares: files, services, postInstall, sources.

The blocks tested here replace ~230 hand-written lines of install/arch.sh. Every
assertion is a behaviour that block had and that the declaration has to keep —
losing one silently is the risk this file exists to remove.

The one that started it: catalog/<app>/files/ and install/firefox-profiles/ both
held the Firefox user.js, a refactor deleted the second, and nothing noticed
until a fresh box died at 66 %. A pack declaring a file it does not carry is now
a failed Result, not an exception and not a missing tile nobody mentions.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.services.catalog import load_catalog                       # noqa: E402
from backend.services.installer import AppContext, apply, enabled_units   # noqa: E402
from backend.services.installer import applier as ap                      # noqa: E402

CATALOG = ROOT / "catalog"
LOCAL = ROOT / "config" / "catalog.d"


@dataclass
class StubPack:
    id: str
    data: dict
    path: Path


def make_pack(tmp_path: Path, data: dict, files: dict[str, str] | None = None) -> StubPack:
    d = tmp_path / "pack"
    d.mkdir(exist_ok=True)
    for rel, content in (files or {}).items():
        target = d / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    return StubPack(id=data.get("id", "test"), data=data, path=d)


@pytest.fixture
def ctx(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    return AppContext(gamecore_path=tmp_path / "gc", user="", user_home=home,
                      secrets={})


# ── files ──────────────────────────────────────────────────────────────────

def test_a_declared_file_the_pack_does_not_carry_fails_loudly(tmp_path, ctx):
    """The 66 % bug. Nothing raises, nothing installs, and the message names
    the file — the old shell `install` aborted the entire run instead."""
    pack = make_pack(tmp_path, {"files": [{"src": "files/gone.js", "dest": str(tmp_path / "out.js")}]})
    results = ap.apply_files(pack, ctx)
    assert [r.ok for r in results] == [False]
    assert "gone.js" in results[0].message
    assert not (tmp_path / "out.js").exists()


def test_tokens_expand_in_dest_and_in_templates(tmp_path, ctx):
    ctx.secrets = {"TWITCH_CLIENT_ID": "abc", "TWITCH_CLIENT_SECRET": "s3cret"}
    pack = make_pack(tmp_path, {
        "secrets": [{"key": "TWITCH_CLIENT_ID", "label": "x"},
                    {"key": "TWITCH_CLIENT_SECRET", "label": "y"}],
        "files": [{"template": "files/c.tmpl", "dest": "@HOME@/cfg.json", "mode": "600"}],
    }, {"files/c.tmpl": '{"id":"@TWITCH_CLIENT_ID@","secret":"@TWITCH_CLIENT_SECRET@"}'})
    assert all(r.ok for r in ap.apply_files(pack, ctx))
    written = json.loads((ctx.user_home / "cfg.json").read_text())
    assert written == {"id": "abc", "secret": "s3cret"}
    assert oct((ctx.user_home / "cfg.json").stat().st_mode)[-3:] == "600"


def test_when_picks_between_the_real_config_and_the_demo(tmp_path, ctx):
    """One pack ships both and the condition chooses — which is what removed the
    `if [[ -n "$TWITCH_CLIENT_ID" ]]` branch from the installer."""
    data = {
        "secrets": [{"key": "TWITCH_CLIENT_ID", "label": "x"}],
        "files": [
            {"src": "files/real", "dest": "@HOME@/out", "when": "secrets.TWITCH_CLIENT_ID"},
            {"src": "files/demo", "dest": "@HOME@/out", "when": "!secrets.TWITCH_CLIENT_ID"},
        ],
    }
    pack = make_pack(tmp_path, data, {"files/real": "REAL", "files/demo": "DEMO"})

    ctx.secrets = {"TWITCH_CLIENT_ID": "abc"}
    ap.apply_files(pack, ctx)
    assert (ctx.user_home / "out").read_text() == "REAL"

    (ctx.user_home / "out").unlink()
    ctx.secrets = {"TWITCH_CLIENT_ID": ""}
    ap.apply_files(pack, ctx)
    assert (ctx.user_home / "out").read_text() == "DEMO"


def test_if_absent_does_not_overwrite_a_hand_edited_file(tmp_path, ctx):
    """Re-running the installer is documented as safe. For the demo EmberTV
    config — the one the owner is told to edit — safe has to mean untouched."""
    pack = make_pack(tmp_path, {
        "files": [{"src": "files/demo", "dest": "@HOME@/cfg", "ifAbsent": True}],
    }, {"files/demo": "SHIPPED"})
    (ctx.user_home / "cfg").write_text("MINE")
    results = ap.apply_files(pack, ctx)
    assert (ctx.user_home / "cfg").read_text() == "MINE"
    assert results[0].already


def test_a_pack_cannot_read_outside_its_own_directory(tmp_path, ctx):
    """"Drop a directory" must not become "read the rest of the disk"."""
    secret = tmp_path / "secret"
    secret.write_text("nope")
    pack = make_pack(tmp_path, {
        "files": [{"src": "../secret", "dest": str(tmp_path / "leak")}],
    })
    results = ap.apply_files(pack, ctx)
    assert [r.ok for r in results] == [False]
    assert "outside the pack" in results[0].message
    assert not (tmp_path / "leak").exists()


# ── services ───────────────────────────────────────────────────────────────

def test_an_enabled_unit_is_installed_and_wanted_by_default_target(tmp_path, ctx):
    pack = make_pack(tmp_path, {
        "services": [{"unit": "files/app.service", "scope": "user", "enable": True}],
    }, {"files/app.service": "[Service]\nExecStart=/bin/true\n"})
    assert all(r.ok for r in ap.apply_services(pack, ctx))
    unit = ctx.unit_dir / "app.service"
    link = ctx.unit_dir / "default.target.wants" / "app.service"
    assert unit.is_file()
    assert link.is_symlink()
    # Relative, so the tree survives being moved with the home directory.
    assert str(link.readlink()) == "../app.service"


def test_enabled_units_are_reported_so_the_caller_can_restart_them(tmp_path, ctx):
    """A hand-symlinked user unit is invisible to a running user manager until a
    daemon-reload. Without this list the services sit dead until the next boot,
    on a box the installer has just called ready."""
    pack = make_pack(tmp_path, {"services": [
        {"unit": "files/a.service", "scope": "user", "enable": True},
        {"unit": "files/b.service", "scope": "user", "enable": False},
    ]})
    assert enabled_units(pack, ctx) == ["a.service"]


def test_reinstalling_over_an_existing_symlink_is_not_an_error(tmp_path, ctx):
    pack = make_pack(tmp_path, {
        "services": [{"unit": "files/app.service", "scope": "user", "enable": True}],
    }, {"files/app.service": "[Service]\n"})
    assert all(r.ok for r in ap.apply_services(pack, ctx))
    assert all(r.ok for r in ap.apply_services(pack, ctx))


# ── postInstall ────────────────────────────────────────────────────────────

def test_a_failing_step_is_a_warning_and_never_an_exception(tmp_path, ctx):
    """The schema says a postInstall failure never interrupts the install. The
    Xenia block once aborted the whole run at 52 %."""
    pack = make_pack(tmp_path, {
        "postInstall": [{"run": "steps/no.sh", "label": "boom"}],
    }, {"steps/no.sh": "echo 'it broke' >&2\nexit 1\n"})
    results = ap.run_post_install(pack, ctx)
    assert [r.ok for r in results] == [False]
    assert "boom" in results[0].message


def test_a_step_that_hangs_is_bounded_by_its_timeout(tmp_path, ctx):
    pack = make_pack(tmp_path, {
        "postInstall": [{"run": "steps/hang.sh", "label": "hang", "timeoutSec": 1}],
    }, {"steps/hang.sh": "sleep 30\n"})
    results = ap.run_post_install(pack, ctx)
    assert [r.ok for r in results] == [False]
    assert "timed out" in results[0].message


def test_a_step_receives_the_tokens_as_environment(tmp_path, ctx):
    ctx.secrets = {"TWITCH_CLIENT_ID": "abc"}
    pack = make_pack(tmp_path, {
        "secrets": [{"key": "TWITCH_CLIENT_ID", "label": "x"}],
        "postInstall": [{"run": "steps/env.sh", "label": "env"}],
    }, {"steps/env.sh": f'printf "%s" "$HOME/$TWITCH_CLIENT_ID" > {tmp_path}/seen\n'})
    assert all(r.ok for r in ap.run_post_install(pack, ctx))
    assert (tmp_path / "seen").read_text() == f"{ctx.user_home}/abc"


def test_steps_run_in_declaration_order(tmp_path, ctx):
    """Generate a certificate, then trust it. The order is the whole point."""
    pack = make_pack(tmp_path, {"postInstall": [
        {"run": "steps/one.sh", "label": "one"},
        {"run": "steps/two.sh", "label": "two"},
    ]}, {"steps/one.sh": f'echo one >> {tmp_path}/order\n',
         "steps/two.sh": f'echo two >> {tmp_path}/order\n'})
    ap.run_post_install(pack, ctx)
    assert (tmp_path / "order").read_text().split() == ["one", "two"]


# ── the shipped app packs ──────────────────────────────────────────────────

@pytest.fixture(scope="module")
def packs():
    return load_catalog(CATALOG, LOCAL)


def test_every_pack_carries_everything_it_declares(packs):
    """The check the repository did not have. catalog/twitch/pack.json declared
    six payload files and shipped one; the five missing ones only surfaced as a
    dead install on a fresh machine, at 66 %.

    Every pack, not just the apps: an emulator may declare the same blocks, and
    "nobody does that yet" is what made the last gap invisible for months."""
    broken = {}
    for pack in packs.values():
        declared = (
            [f.get("src") or f["template"] for f in pack.data.get("files", [])]
            + [s["unit"] for s in pack.data.get("services", [])]
            + [s["run"] for s in pack.data.get("postInstall", [])]
        )
        missing = [rel for rel in declared if not (pack.path / rel).is_file()]
        if missing:
            broken[pack.id] = missing
    assert not broken, f"packs declaring files they do not carry: {broken}"


def test_each_app_pack_declares_something_to_do(packs):
    """An app that declares nothing installs nothing — and the wizard would
    still offer its tick box. Every app in the catalogue, not a list of four."""
    idle = [p.id for p in packs.values() if p.kind == "app"
            and not any(p.data.get(k) for k in
                        ("install", "sources", "files", "services", "postInstall", "packages"))]
    assert not idle, f"apps that declare no install work at all: {idle}"

def test_the_app_packs_apply_end_to_end_without_touching_the_system(packs, tmp_path):
    """A dry run reaches every block of every app pack. It is what would have
    caught the deleted user.js at build time rather than at 66 % on a box."""
    ctx = AppContext(gamecore_path=tmp_path, user="", dry_run=True,
                     user_home=tmp_path, secrets={"TWITCH_CLIENT_ID": "abc"})
    for pack in (p for p in packs.values() if p.kind == "app"):
        results = apply(pack, ctx)
        assert results, f"{pack.id} applied nothing at all"
        assert all(r.ok for r in results), \
            [r.message for r in results if not r.ok]
