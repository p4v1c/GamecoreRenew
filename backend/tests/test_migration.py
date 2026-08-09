"""The migration, exercised only ever against trees this file built itself.

`scripts/migrate-userdata.py` moves a real person's ROM library, their
playtime and their credentials. The rules it is built on are the ones worth
testing, because each of them exists to make a specific disaster impossible:

  · dry run by default, so a mistyped command is a printout;
  · copy, never delete, so a migration that turns out wrong costs disk space;
  · never overwrite, so a second run cannot damage the first's result;
  · **nothing calls it** — the OTA must not be able to reach it, because a
    release that migrated data on its way in would leave a rollback facing a
    tree the old code cannot read.

That last one is asserted over every tracked file in the repository, and it is
the most important test here: the others check that the script behaves, this
one checks that it is never *invoked*.

Nothing here goes near a real installation. Every path is under `tmp_path`,
and the script refuses `--from`/`--to` pairs that are nested or equal anyway.
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "migrate-userdata.py"


def _old_install(root: Path) -> dict[str, str]:
    """An install laid out the way v1.0.6 laid one out. Returns {rel: content}."""
    tree = {
        "config/systems.json": '[{"id": "duckstation"}]',
        "config/theme.json": '{"active": "shelf"}',
        "config/auth_secret": "32 bytes of secret, in spirit",
        "config/themes/shelf/theme.json": '{"name": "shelf"}',
        "emu/duckstation/Crash Bandicoot.bin": "a ROM",
        "emu/duckstation/Crash Bandicoot.cue": 'FILE "Crash Bandicoot.bin" BINARY\n',
        "emu/covers/duckstation/Crash Bandicoot.png": "cover art",
        "emu/gamemedia/duckstation/crash/game.json": '{"id": 1}',
        "assets/overlays/duckstation.png": "a bezel",
        "assets/logos/duckstation.png": "a logo",
    }
    for rel, content in tree.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    return tree


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                          capture_output=True, text=True, timeout=180)


@pytest.fixture
def box(tmp_path):
    old = tmp_path / "GameCore"
    old.mkdir()
    return old, _old_install(old), tmp_path / "userdata"


def test_without_the_flag_it_writes_nothing_at_all(box):
    """The default has to be the harmless one. Somebody will run this to see
    what it does, and what it does must be: print."""
    old, _, new = box
    r = _run("--from", str(old), "--to", str(new))
    assert r.returncode == 0, r.stderr
    assert not new.exists(), "the dry run created the destination"
    assert "DRY RUN" in r.stdout


def test_the_plan_names_every_section_with_its_size_and_count(box):
    """A human is meant to read this before agreeing to it, so it has to say
    what would move, how much of it, and where from."""
    old, _, new = box
    out = _run("--from", str(old), "--to", str(new)).stdout
    for section in ("config", "roms", "overlays", "logos"):
        assert section in out
    assert str(old / "emu") in out, "the plan must name the source directories"
    assert "TOTAL" in out
    # 10 files were planted; the plan must account for all of them.
    assert "10" in out


def test_it_copies_everything_and_deletes_nothing(box):
    old, tree, new = box
    r = _run("--from", str(old), "--to", str(new), "--i-know-what-i-am-doing")
    assert r.returncode == 0, r.stderr
    for rel, content in tree.items():
        assert (old / rel).read_text() == content, f"{rel} was removed or altered"
        assert (new / rel).read_text() == content, f"{rel} did not arrive"


def test_a_second_run_leaves_the_first_ones_files_alone(box):
    """Not merely idempotent — non-destructive. If the box has been running on
    the new tree, its files are NEWER than the originals, and a second run that
    overwrote them would silently roll the player back."""
    old, _, new = box
    _run("--from", str(old), "--to", str(new), "--i-know-what-i-am-doing")
    moved_on = new / "config" / "theme.json"
    moved_on.write_text('{"active": "summer"}')

    r = _run("--from", str(old), "--to", str(new), "--i-know-what-i-am-doing")
    assert r.returncode == 0, r.stderr
    assert moved_on.read_text() == '{"active": "summer"}'
    assert "Copied 0 file(s)" in r.stdout


@pytest.mark.parametrize("dest", ["same", "nested"])
def test_a_destination_that_would_eat_its_own_source_is_refused(box, dest):
    old, _, _ = box
    target = old if dest == "same" else old / "userdata"
    r = _run("--from", str(old), "--to", str(target), "--i-know-what-i-am-doing")
    assert r.returncode == 2
    assert "ERROR" in r.stderr


def test_it_stops_short_of_switching_the_box_over(box):
    """Copying the bytes is not the migration. The box reads the new tree only
    once GAMECORE_DATA is set, and that stays a separate human step — two
    reversible actions with a person between them."""
    old, _, new = box
    out = _run("--from", str(old), "--to", str(new),
               "--i-know-what-i-am-doing").stdout
    assert "GAMECORE_DATA" in out and "does NOT use the new tree yet" in out


# ── The one that matters most ────────────────────────────────────────────────
# Files allowed to mention the script: itself, and this test.
_MAY_MENTION = {
    "scripts/migrate-userdata.py",
    "backend/tests/test_migration.py",
}


def _executable_text(path: Path) -> str:
    """The file with its prose removed.

    Pointing at the migration in a comment is how the codebase explains
    itself — `services/paths.py` names it precisely to tell the reader where
    the bytes eventually move. What must not exist is a line that *runs* it,
    so docstrings and comments are stripped before the search rather than the
    whole file being exempted.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""
    lines = text.splitlines()
    if path.suffix == ".py":
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return text
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Module, ast.ClassDef,
                                     ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = getattr(node, "body", None)
            if not body or not isinstance(body[0], ast.Expr):
                continue
            first = body[0].value
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                for i in range(first.lineno - 1, (first.end_lineno or first.lineno)):
                    lines[i] = ""
    return "\n".join(ln for ln in lines if not ln.lstrip().startswith("#"))


def test_nothing_the_ota_runs_can_reach_the_migration():
    """A release that migrated data on its way in would be unrollbackable.

    `update/linux.sh` restores the previous *code* from `${GAMECORE_PATH}.prev`
    — it has no idea data exists elsewhere. So if an update moved the data, the
    rollback would hand the old code a tree it cannot read, and there is no
    procedure anywhere to recombine them.

    The temptation this guards against is a real one and it sounds reasonable:
    "the box is already down for the update, may as well migrate while we're
    here". Executable references are therefore banned outright, and the ban is
    checked rather than remembered.
    """
    hits = []
    tracked = subprocess.run(["git", "-C", str(REPO), "ls-files", "-z"],
                             capture_output=True, text=True,
                             check=True).stdout.split("\0")
    for rel in filter(None, tracked):
        if rel in _MAY_MENTION or rel.endswith(".md"):
            continue
        if "migrate-userdata" in _executable_text(REPO / rel):
            hits.append(rel)
    assert not hits, (
        "the migration must stay a command a human types — it is referenced "
        f"from: {hits}")
