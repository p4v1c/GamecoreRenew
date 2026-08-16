"""The shell no longer wipes the HTTP cache — and may only not, while the rule holds.

`electron/main.js` used to call `session.defaultSession.clearCache()` on every
start. It was there for one real reason: a cached `index.html` surviving an OTA
keeps loading the old bundle, and an update that ships nothing visible is the
worst kind. The cost was the rest of the cache — 47 MB of cover art, measured
on the reference box, re-downloaded and re-decoded on every boot.

Removing it is safe **only** because `backend/services/http_cache.py` now
forbids the browser to store `index.html` at all. That is a dependency between
two files in two languages that nothing else expresses, so it is asserted here:
if either half is undone on its own, this fails.

The direction matters. Re-adding the wipe is not a regression in correctness,
only in speed. Dropping the `no-store` while the wipe is gone is the one that
ships an invisible update, which is why both are checked together.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from backend.services import http_cache

MAIN_JS = REPO / "electron" / "main.js"


def _code() -> str:
    """main.js with its comments stripped — the wipe is *described* there."""
    src = MAIN_JS.read_text(encoding="utf-8")
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return "\n".join(re.sub(r"//.*$", "", line) for line in src.splitlines())


def test_the_shell_does_not_wipe_the_cache_any_more():
    """The whole point: what the browser keeps must survive a restart."""
    assert MAIN_JS.is_file(), MAIN_JS
    assert "clearCache" not in _code(), (
        "electron/main.js clears the HTTP cache again. Every boot then re-downloads "
        "and re-decodes the entire cover library. If an OTA stopped showing up, fix "
        "the Cache-Control header on index.html — do not bring the hammer back."
    )


def test_and_the_rule_that_makes_that_safe_is_still_in_force():
    """`no-store` on index.html is the whole licence for the test above."""
    assert http_cache.for_frontend("index.html") == "no-store", (
        "index.html may be stored again while electron/main.js no longer clears the "
        "cache — an OTA can now leave the old bundle loading, with nothing to say so."
    )


def test_the_bundle_is_still_named_by_content_hash():
    """The other half of the licence: an old asset must be *unreachable*.

    `no-store` on index.html only helps because the bundle it names cannot be
    confused with the previous one. If Vite ever stopped hashing, `immutable`
    would start pinning a URL that gets reused — so this asserts the built
    output actually looks the way the policy assumes.

    Skipped rather than failed when there is no build on disk: a fresh checkout
    has not run `npm run build`, and this is not the test that should say so.
    """
    import pytest

    assets = REPO / "frontend" / "dist" / "assets"
    if not assets.is_dir():
        pytest.skip("no frontend build on disk (npm run build)")

    entries = [p for p in assets.iterdir() if p.is_file()]
    if not entries:
        pytest.skip("frontend build has no assets")

    unhashed = [p.name for p in entries
                if not http_cache.is_hashed_asset(f"assets/{p.name}")]
    assert not unhashed, (
        f"built assets that are not content-hashed: {unhashed}. They would be served "
        "'immutable' under a name that can be reused, which is exactly the stale-bundle "
        "bug clearCache() used to paper over."
    )
