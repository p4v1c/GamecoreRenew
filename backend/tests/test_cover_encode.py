"""Covers re-encoded as lossless WebP — and the paths that must not move with them.

The conversion's whole claim is that it changes the container and nothing else.
Two halves to that, and the second is the one that could break a library:

  · the picture is identical, and only ever smaller;
  · **no URL changes.** `/api/covers/{system}/{filename}` is keyed by the
    GAME's filename, never by the cover file's. The cache is an internal
    detail of cover_pipeline, so a jacket going from `.png` to `.webp` must be
    invisible to the router, the scanner and the frontend alike.

That second half is asserted first and hardest, because it is the one that
would only show up as an empty grid on a box nobody is standing in front of.

Everything here is synthetic — real images built by Pillow, never the box's own
cover directory.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import pytest

from backend.services import cover_encode

# The synthetic game tree test_covers.py builds — see test_http_cache.py.
from .test_covers import setup_root

pytestmark = pytest.mark.skipif(not cover_encode.available(),
                                reason="Pillow is not installed")


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


def _png(path: Path, size=(64, 96), mode="RGBA") -> Path:
    """A PNG with enough structure that lossless WebP actually beats it."""
    from PIL import Image

    im = Image.new(mode, size)
    px = im.load()
    for y in range(size[1]):
        for x in range(size[0]):
            v = (x * 3 + y * 5) % 256
            px[x, y] = (v, (v * 2) % 256, 255 - v, 255)[:len(im.getbands())]
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, "PNG")
    return path


# ── The picture ──────────────────────────────────────────────────────────────

def test_the_pixels_survive_exactly(tmp_path):
    """Lossless means lossless — this is the promise the whole change rests on."""
    from PIL import Image

    src = _png(tmp_path / "game.png")
    before = Image.open(src).convert("RGBA").tobytes()

    out = cover_encode.to_webp(src)

    assert out.suffix == ".webp"
    assert Image.open(out).convert("RGBA").tobytes() == before
    assert not src.exists(), "the source is removed only after the replacement is proved"


def test_a_colour_profile_is_carried_over(tmp_path):
    """12 of the 89 real covers carry one; dropping it would shift the colours.

    "Nothing degraded" has to include the colours, not only the pixel values.
    """
    from PIL import Image, ImageCms

    src = _png(tmp_path / "profiled.png")
    profile = ImageCms.createProfile("sRGB")
    blob = ImageCms.ImageCmsProfile(profile).tobytes()
    Image.open(src).save(src, "PNG", icc_profile=blob)

    out = cover_encode.to_webp(src)
    assert Image.open(out).info.get("icc_profile") == blob


def test_a_jpeg_is_left_alone(tmp_path):
    """Measured, not assumed: the four JPEGs on the box grow 128–382 %.

    Lossless WebP has to reproduce a JPEG's artefacts exactly, so it spends
    bytes storing noise the original discarded, and decodes slower for it.
    """
    from PIL import Image

    src = tmp_path / "boxart.jpg"
    Image.open(_png(tmp_path / "tmp.png")).convert("RGB").save(src, "JPEG", quality=80)

    assert cover_encode.to_webp(src) == src
    assert src.exists()
    assert not src.with_suffix(".webp").exists()


def test_a_result_that_came_out_larger_is_discarded(tmp_path, monkeypatch):
    """The guard for the day a cover is really a re-wrapped photograph.

    It never fires on today's library — all 85 PNGs shrink — which is exactly
    why it is worth having: nothing else would notice.
    """
    src = _png(tmp_path / "game.png")
    monkeypatch.setattr(cover_encode, "_is_worth_it", lambda a, b: False)

    assert cover_encode.to_webp(src) == src
    assert src.exists()
    assert not src.with_suffix(".webp").exists(), "the useless .webp must not linger"


def test_a_round_trip_that_does_not_match_is_refused(tmp_path, monkeypatch):
    """A library bug must cost a missed optimisation, never a wrong picture."""
    src = _png(tmp_path / "game.png")
    monkeypatch.setattr(cover_encode, "_same_pixels", lambda a, b: False)

    assert cover_encode.to_webp(src) == src
    assert src.exists()
    assert not src.with_suffix(".webp").exists()


def test_an_unreadable_file_is_returned_untouched(tmp_path):
    """Every failure path keeps the caller's cover — the worst case is a PNG."""
    src = tmp_path / "truncated.png"
    src.write_bytes(b"\x89PNG\r\n\x1a\nnot really a png")

    assert cover_encode.to_webp(src) == src
    assert src.exists()


# ── The migration over what is already on disk ───────────────────────────────

def test_the_migration_converts_what_is_there_and_repeats_for_free(tmp_path):
    """`emu/` is excluded from the OTA rsync, so nothing else reaches these.

    Conversion at write time only ever touches covers scraped from now on. An
    installed box's library is already scraped, so without this pass its owner
    would see none of the gain.
    """
    for name in ("nes/One.png", "snes/Two.png", "snes/Three.png"):
        _png(tmp_path / name)
    (tmp_path / "snes" / "Four.jpg").write_bytes(b"not a png, left alone")

    converted, saved = cover_encode.migrate(tmp_path)

    assert converted == 3
    assert saved > 0
    assert sorted(p.name for p in tmp_path.rglob("*.webp")) == \
        ["One.webp", "Three.webp", "Two.webp"]
    assert list(tmp_path.rglob("*.png")) == []
    assert (tmp_path / "snes" / "Four.jpg").is_file(), "the JPEG is not touched"

    # Idempotent: a second pass has nothing to do and says so.
    assert cover_encode.migrate(tmp_path) == (0, 0)


def test_the_migration_stops_when_it_is_told_to(tmp_path):
    """A player starting a game must not be sharing the CPU with a re-encode."""
    for name in ("a.png", "b.png", "c.png", "d.png"):
        _png(tmp_path / name)

    calls = []

    def should_continue():
        calls.append(1)
        return len(calls) <= 2

    converted, _ = cover_encode.migrate(tmp_path, should_continue=should_continue)

    assert converted == 2
    assert len(list(tmp_path.rglob("*.png"))) == 2, "the rest is left for later"


def test_a_missing_pillow_changes_nothing(tmp_path, monkeypatch):
    """The dependency is optional: without it, covers simply stay PNG."""
    src = _png(tmp_path / "game.png")
    monkeypatch.setattr(cover_encode, "Image", None)

    assert not cover_encode.available()
    assert cover_encode.to_webp(src) == src
    assert cover_encode.migrate(tmp_path) == (0, 0)
    assert src.is_file()


# ── The half that would empty a library ──────────────────────────────────────

def test_the_url_of_a_cover_does_not_mention_its_container(client):
    """The API path is the GAME's filename. The cache's extension is private.

    This is the assertion that had to exist before the conversion did: if the
    router, the scanner or the frontend named the cover file, changing `.png`
    to `.webp` would 404 every jacket on the box.
    """
    r = client.get("/api/covers/rpcs3/BLUS30443")
    assert r.status_code == 200, r.text
    # The request names the ROM directory, never a picture file.
    assert "BLUS30443" in str(r.url) and ".webp" not in str(r.url)
    assert ".png" not in str(r.url)


def test_a_webp_cover_is_served_with_the_right_type(client, tmp_path):
    """A converted cover must come back as image/webp, not as a mislabelled PNG.

    A browser sniffs its way out of a wrong `Content-Type` on an image, so this
    would not look broken — it would just be wrong, quietly, forever.
    """
    from backend.services import cover_pipeline

    cache = cover_pipeline.COVERS_DIR / "ppsspp"
    cache.mkdir(parents=True, exist_ok=True)
    for stale in cache.glob("SomePspGame.*"):
        stale.unlink()
    _png(cache / "SomePspGame.png")
    converted = cover_encode.to_webp(cache / "SomePspGame.png")
    assert converted.suffix == ".webp", "fixture did not convert — test proves nothing"

    r = client.get("/api/covers/ppsspp/SomePspGame.iso")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/webp"
    assert r.content == converted.read_bytes()


def test_refresh_clears_a_converted_cover_too(client):
    """`?refresh=1` deletes the cached jacket — including the WebP one.

    Missed, this is the bug where re-scraping a game appears to do nothing: the
    pipeline would delete a `.png` that is no longer there and then find the
    stale `.webp` still sitting in the cache.
    """
    from backend.services import cover_pipeline

    cache = cover_pipeline.COVERS_DIR / "rpcs3"
    cache.mkdir(parents=True, exist_ok=True)
    for stale in cache.glob("BLUS30443.*"):
        stale.unlink()
    _png(cache / "BLUS30443.png")
    webp = cover_encode.to_webp(cache / "BLUS30443.png")
    assert webp.suffix == ".webp"
    marker = webp.read_bytes()

    r = client.get("/api/covers/rpcs3/BLUS30443?refresh=1")
    assert r.status_code == 200
    assert r.content != marker, "the stale WebP survived a refresh"
