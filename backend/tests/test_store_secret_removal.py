"""Uninstalling the box takes the Store's API key with it.

`install/uninstall.sh` keeps `config/` on purpose — it holds the player's
systems, their themes, their addons — so a credential written there survives a
removal **unless the uninstaller names it**. Line 824 has named `auth.json` and
`auth_secret` since the login was added, with a comment saying why: leaving an
argon2 hash and an HMAC key on a machine somebody is about to sell or hand on
is not acceptable. `config/store-prowlarr.json` holds the URL and API key of
the owner's own Prowlarr instance and the argument is word for word the same.

`config/store-realdebrid.json` holds the API token of the owner's own
Real-Debrid account, which is a paid subscription somebody can spend, and the
argument is word for word the same again.

`docs/reports/store-installer-audit-2026-09-12.md` §S7 is where this failure
mode is written down: a file nobody names survives in silence, and nothing
anywhere reports it. So it is pinned here, twice and in two different ways:

  · **statically** — the path appears on the `safe_rm` line, so deleting it
    from the script fails the build rather than a stranger's disk;
  · **behaviourally** — the script's own `safe_rm` is lifted out and run
    against a throwaway data tree, so the pin survives `safe_rm` itself
    changing (it refuses relative paths, `..`, and anything less than two
    levels deep, and a path that tripped one of those guards would be listed
    and never removed).

**The uninstaller is never executed here**, `--dry-run` included, and nothing
below reads or writes anything outside pytest's `tmp_path`. What runs is the
`safe_rm` function, extracted by pattern, over a fake `/var/lib/gamecore` and a
fake data tree.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
UNINSTALL = REPO / "install/uninstall.sh"

#: The files whose removal is a security property rather than tidying.
CREDENTIALS = ("auth.json", "auth_secret", "store-prowlarr.json",
               "store-realdebrid.json")
#: Written by the installer, wanted by the player, and kept on purpose.
KEPT = ("systems.json", "apps.json", "theme.json")


def _script() -> str:
    return UNINSTALL.read_text()


def _removal_lines() -> str:
    """The `safe_rm "$GC_DATA/config/…"` statement, continuations included."""
    lines = _script().splitlines()
    start = next((i for i, ln in enumerate(lines)
                  if ln.startswith('safe_rm "$GC_DATA/config/')), None)
    assert start is not None, (
        "install/uninstall.sh no longer removes anything from $GC_DATA/config/"
    )
    out = [lines[start]]
    while out[-1].rstrip().endswith("\\"):
        out.append(lines[start + len(out)])
    return "\n".join(out)


def _safe_rm_definition() -> str:
    body = re.search(r"^safe_rm\(\) \{.*?^\}$", _script(), re.S | re.M)
    assert body, "install/uninstall.sh has no safe_rm() to test"
    return body.group(0)


# ── the static pin ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", CREDENTIALS)
def test_the_uninstaller_names_every_stored_credential(name):
    assert f"$GC_DATA/config/{name}" in _removal_lines(), (
        f"config/{name} holds a secret and config/ is kept by default, so the "
        f"uninstaller has to name it — see install/uninstall.sh:824"
    )


def test_the_store_credential_files_are_the_ones_the_backend_reads():
    """The pin is worthless if the two sides drift apart.

    A rename in `prowlarr.py` or `realdebrid.py` that forgot this line would
    leave the old file named in the uninstaller and the new one on disk
    forever. Both are asserted against the constant the backend actually
    opens, not against a string typed twice.
    """
    from backend.services.store.prowlarr import CONFIG_FILENAME as PROWLARR
    from backend.services.store.realdebrid import CONFIG_FILENAME as REALDEBRID

    lines = _removal_lines()
    assert f"$GC_DATA/config/{PROWLARR}" in lines
    assert f"$GC_DATA/config/{REALDEBRID}" in lines


def test_removing_a_credential_is_not_conditional_on_purge():
    """`--purge` deletes the install; the keys go either way.

    The statement sits ahead of the `if $PURGE` block that follows it, and
    that ordering is the whole property: without it, the default uninstall —
    the one that keeps ROMs and configuration — would keep the API key too.
    """
    script = _script()
    removal = script.index(_removal_lines())
    purge = script.index('if [[ -d "$GC_PATH" ]]; then', removal - 2000)
    assert removal < purge


# ── the behavioural pin, on fixtures ───────────────────────────────────────

@pytest.fixture
def fake_box(tmp_path):
    """A throwaway `/var/lib/gamecore` and a throwaway data tree.

    Neither is the real thing and neither is reachable from one: everything is
    under pytest's `tmp_path`, and the only script that runs is `safe_rm`.
    """
    (tmp_path / "var/lib/gamecore").mkdir(parents=True)
    (tmp_path / "var/lib/gamecore/manifest.env").write_text("GC_USER=nobody\n")
    config = tmp_path / "data/config"
    config.mkdir(parents=True)
    for name in CREDENTIALS + KEPT:
        (config / name).write_text('{"pretend": true}\n')
    (tmp_path / "data/emu/nes").mkdir(parents=True)
    (tmp_path / "data/emu/nes/game.nes").write_bytes(b"\x00")
    return tmp_path


@pytest.mark.skipif(shutil.which("bash") is None, reason="no bash")
def test_the_uninstallers_own_safe_rm_removes_the_store_credential(fake_box):
    """The script's real function, over a fake tree.

    Extracted rather than reimplemented: `safe_rm` refuses relative paths,
    paths containing `..` and anything less than two levels deep, and a path
    that tripped one of those would be *listed* by the static test above and
    still never removed. This is the test that would catch that.
    """
    harness = "\n".join([
        "set -uo pipefail",
        'msg() { :; }; ok() { :; }; warn() { echo "WARN: $*"; };',
        'info() { :; }; die() { echo "DIE: $*"; exit 1; }',
        "DRY=false",
        'run() { "$@"; }',
        _safe_rm_definition(),
        f'GC_DATA="{fake_box / "data"}"',
        _removal_lines(),
    ])
    script = fake_box / "harness.sh"
    script.write_text(harness)
    r = subprocess.run(["bash", str(script)], capture_output=True, text=True,
                       timeout=30)

    assert r.returncode == 0, r.stderr
    # `safe_rm` swallows its own refusals into a warning and carries on (the
    # uninstaller has no `set -e` on purpose), so a guard trip is a pass with
    # the file still there. Read the warnings too.
    assert "WARN" not in r.stdout, r.stdout

    config = fake_box / "data/config"
    for name in CREDENTIALS:
        assert not (config / name).exists(), f"config/{name} survived removal"
    for name in KEPT:
        assert (config / name).exists(), f"config/{name} should have been kept"
    # And nothing beyond the three files it names.
    assert (fake_box / "data/emu/nes/game.nes").exists()
    assert (fake_box / "var/lib/gamecore/manifest.env").exists()


@pytest.mark.skipif(shutil.which("bash") is None, reason="no bash")
def test_the_uninstaller_still_parses():
    """`bash -n` only, and on this checkout's copy.

    The script is never executed by the suite and never will be — it removes
    packages, systemd units and a user account, and the machine running the
    tests is in some cases a real box.
    """
    r = subprocess.run(["bash", "-n", str(UNINSTALL)],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
