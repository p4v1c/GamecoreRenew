"""The cache policy that lets electron/main.js stop wiping the HTTP cache.

These tests are the safety net for a change made in a specific order: the
headers first, `clearCache()` second. Reversed, the box would reintroduce the
bug the wipe was there to prevent — an `index.html` kept across an OTA, still
naming yesterday's bundle. So the assertions below are not about performance,
they are about what may and may not survive an update:

  · index.html must never be stored — it is the only unhashed file that decides
    which code runs.
  · a hash-named asset may be stored for a year — its URL changes with its
    bytes, so a stale copy is unreachable by construction.
  · covers, media and logos must be revalidated — their URLs outlive their
    content, and a corrected picture has to be able to show through.

test_electron_cache.py asserts the other half: that the wipe is gone, and that
it may only be gone while the rule above holds.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import pytest

from backend.services import http_cache

# The synthetic game tree test_covers.py builds — a real cover to ask for, and
# a systems.json the logo route can walk. Reused rather than reinvented: this
# file is about headers, and a second fake library would be a second thing to
# keep true.
from .test_covers import setup_root


@pytest.fixture(scope="module")
def fake_root():
    return setup_root()


@pytest.fixture(scope="module")
def client(fake_root):
    """TestClient over the real app, with the lifespan running."""
    from fastapi.testclient import TestClient

    from backend.main import app
    with TestClient(app) as c:
        yield c


# ── The rule, in isolation ───────────────────────────────────────────────────

@pytest.mark.parametrize("name", [
    "index.html",
    "/index.html",
    "/",
    "",
])
def test_the_shell_is_never_stored(name):
    """The one file whose name outlives its meaning."""
    assert http_cache.for_frontend(name) == "no-store"


@pytest.mark.parametrize("relpath", [
    # Exactly what `npm run build` writes today.
    "assets/index-Dr_k0yci.js",
    "assets/index-Du2DJp56.css",
    "assets/logo-uGkbPLlq.png",
    "/assets/index-Dr_k0yci.js",
])
def test_a_hash_named_build_asset_is_immutable(relpath):
    assert http_cache.for_frontend(relpath) == "public, max-age=31536000, immutable"
    assert http_cache.is_hashed_asset(relpath)


@pytest.mark.parametrize("relpath", [
    # The trap this rule exists for. `Pokemon - Sapphire.png` ends in a hyphen
    # and eight word characters — the exact shape of every hash Vite emits — so
    # a name-only test would declare a cover immutable and pin it for a year
    # under a URL that is reused the moment the game is re-scraped. What saves
    # it is the location: build artefacts live in assets/, covers do not.
    "Pokemon - Sapphire.png",
    "Sonic-Adventure.png",
    "Need for Speed - Most Wanted.png",
    "gamecube.png",
    "manifest.json",
    "favicon.ico",
])
def test_content_outside_the_build_assets_is_only_revalidated(relpath):
    """The safe direction to be wrong in.

    A file wrongly called immutable survives the update meant to replace it.
    A file wrongly revalidated costs one empty 304. So the fallback is 304.
    """
    assert http_cache.for_frontend(relpath) == "no-cache"
    assert not http_cache.is_hashed_asset(relpath)


def test_an_unhashed_file_inside_assets_is_still_only_revalidated():
    """If a build config ever stops hashing, nothing may be pinned for a year."""
    assert not http_cache.is_hashed_asset("assets/index.js")
    assert not http_cache.is_hashed_asset("assets/bundle-v2.js")
    assert http_cache.for_frontend("assets/index.js") == "no-cache"


# ── The rule, as the box actually serves it ──────────────────────────────────

def test_a_cover_is_revalidated_not_re_downloaded(client):
    """`no-cache` plus an ETag is the whole point: kept, asked about, 304.

    This is the header that decides what the second boot costs. Without it the
    renderer re-transfers and re-decodes 47 MB of cover art every start —
    measured on the reference box, 89 files.
    """
    r = client.get("/api/covers/rpcs3/BLUS30443")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-cache"

    etag = r.headers.get("etag")
    assert etag, "no ETag — 'no-cache' would revalidate into a full re-download"

    again = client.get("/api/covers/rpcs3/BLUS30443",
                       headers={"If-None-Match": etag})
    assert again.status_code == 304, "the revalidation must come back empty"
    assert again.content == b""


def test_the_bundle_mount_reads_the_path_not_the_name(tmp_path):
    """The mount must hand `for_frontend` a path relative to the bundle root.

    Handing it the absolute path or the bare name is the mistake that matters:
    the bare name cannot tell `assets/logo-uGkbPLlq.png` from a cover, and the
    absolute path starts with the checkout directory, not with `assets/`. Both
    would silently fall back to `no-cache` — or worse, match by accident.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.main import _BundleStatic

    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>shell</title>")
    (tmp_path / "assets" / "index-Dr_k0yci.js").write_text("console.log(1)")
    (tmp_path / "assets" / "unhashed.js").write_text("console.log(2)")

    app = FastAPI()
    app.mount("/", _BundleStatic(directory=str(tmp_path), html=True), name="frontend")
    c = TestClient(app)

    assert c.get("/index.html").headers["cache-control"] == "no-store"
    # html=True: "/" serves index.html and must get the same verdict.
    assert c.get("/").headers["cache-control"] == "no-store"
    assert c.get("/assets/index-Dr_k0yci.js").headers["cache-control"] == \
        "public, max-age=31536000, immutable"
    assert c.get("/assets/unhashed.js").headers["cache-control"] == "no-cache"


def test_a_logo_is_revalidated(client):
    """Logos are the reason the policy is `no-cache` and not `immutable`.

    They are served under a fixed name — `assets/logos/<platform>.png` — while
    the file behind them, `catalog/<id>/logo.png`, IS carried by the OTA rsync.
    A long lifetime here is the one way an update could ship a corrected logo
    that nobody ever sees.
    """
    r = client.get("/assets/logos/rpcs3.png")
    if r.status_code == 404:
        pytest.skip("no pack logo resolvable in the test tree")
    assert r.headers["cache-control"] == "no-cache"
