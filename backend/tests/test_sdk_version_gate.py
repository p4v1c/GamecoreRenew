"""The compatibility gate, and the two ways it stops protecting anything.

`compatible: api <= SDK_VERSION` is what keeps a theme off a front end too old
to run it. It is the only thing standing between "this theme is not compatible,
here is why" and a theme that imports cleanly, throws on its first missing
function, and reads to the player as the theme silently becoming the default
one — then, after CRASH_LIMIT of those, as a theme safe mode refuses outright.

It failed exactly once, and this file is the consequence.

`sdk.defaults.createSettings` and `createPowerView` were added, both shipped
themes were rewritten to destructure them, and `SDK_VERSION` stayed at 1. Shelf
kept declaring `api: 1`, so every bundle — including ones built before those
functions existed — answered "compatible". On a box in the window between the
new theme landing on disk and the front end restarting onto the matching
bundle, that is a crash instead of a refusal.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from backend.services import themes                    # noqa: E402

THEMES = REPO / "config" / "themes"
SDK_TS = REPO / "frontend" / "src" / "lib" / "themeSdk.ts"

#: Surfaces that arrived with a given SDK major. A theme touching one of these
#: must declare at least that number, or an older front end will accept it and
#: then fail on the missing function.
SINCE = {
    2: ("sdk.defaults.createSettings", "sdk.defaults.createPowerView",
        "createSettings", "createPowerView"),
}


def _shipped() -> list[Path]:
    return [d for d in sorted(THEMES.iterdir())
            if d.is_dir() and d.name[0] not in "._" and (d / "theme.json").is_file()]


def test_the_backend_and_the_frontend_agree_on_the_version():
    """Two constants, one contract. The backend computes `compatible` and the
    front end refuses to load — if they disagree, a theme is offered by one and
    rejected by the other, and which one the player meets depends on where they
    clicked."""
    m = re.search(r"export const SDK_VERSION = (\d+)", SDK_TS.read_text())
    assert m, "SDK_VERSION is gone from themeSdk.ts"
    assert int(m.group(1)) == themes.SDK_VERSION, (
        f"themeSdk.ts says {m.group(1)}, backend says {themes.SDK_VERSION}"
    )


@pytest.mark.parametrize("theme_dir", _shipped(), ids=lambda d: d.name)
def test_a_theme_declares_the_sdk_it_actually_uses(theme_dir):
    """What a theme CALLS decides the number it has to declare.

    Read from its sources rather than trusted: the manifest is a claim, and the
    claim being wrong is the failure this file exists for.
    """
    manifest = json.loads((theme_dir / "theme.json").read_text())
    declared = int(manifest.get("api", 1))

    source = "\n".join(p.read_text() for p in theme_dir.rglob("*.js"))
    needed = max((v for v, names in SINCE.items()
                  if any(n in source for n in names)), default=1)

    assert declared >= needed, (
        f"{theme_dir.name} uses an SDK {needed} surface but declares api "
        f"{declared} — an older front end would call it compatible and then "
        f"crash on the missing function"
    )


@pytest.mark.parametrize("theme_dir", _shipped(), ids=lambda d: d.name)
def test_a_shipped_theme_is_not_declaring_a_future_sdk(theme_dir):
    """The other direction, which would take the theme off every box at once."""
    declared = int(json.loads((theme_dir / "theme.json").read_text()).get("api", 1))
    assert declared <= themes.SDK_VERSION, (
        f"{theme_dir.name} declares api {declared}, above this build's "
        f"SDK_VERSION {themes.SDK_VERSION} — no front end would load it"
    )


def test_a_theme_from_the_future_is_refused_rather_than_run():
    """The gate itself, exercised. This is what should have happened."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "future"
        d.mkdir()
        (d / "theme.json").write_text(json.dumps({
            "id": "future", "name": "Future", "version": "1.0.0",
            "api": themes.SDK_VERSION + 1, "provides": ["shell", "splash"],
        }))
        (d / "index.js").write_text("export default () => ({})\n")
        m = themes._read_manifest(d)
    assert m is not None and m["compatible"] is False
