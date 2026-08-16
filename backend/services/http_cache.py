"""What the browser is allowed to keep, and for how long.

This is one policy in one place because it replaces one that lived nowhere: the
box shipped with no `Cache-Control` on anything, and `electron/main.js` called
`session.defaultSession.clearCache()` on every start to make sure a stale
`index.html` could never pin an old bundle after an OTA. That worked, and it
cost the whole cache: 47 MB of cover art re-downloaded and re-decoded on every
single boot, measured on the reference box (89 files, 85 of them PNG).

Removing the clearCache() is only safe once the rules below are in force, so
they are stated here rather than scattered over four routers and three mounts.

Three rules, and the reasoning for each:

`no-store` — **index.html only.** It is the one file whose *name* never
changes while its *content* decides which bundle loads. Anything the browser
keeps here can pin an old bundle, and a revalidation is not enough: a 304 would
be correct HTTP and still wrong for us, because we would rather pay one local
request than risk showing yesterday's UI. It is 1.2 kB served from loopback.

`immutable` — **hash-named build assets only.** Vite writes
`assets/index-Dr_k0yci.js`; a new build is a new name. The URL genuinely can
never change content, which is the only condition under which a year-long
lifetime is honest.

`no-cache` — **everything else that is content, not code.** Covers, game media,
system logos. The name is a trap: it does not mean "do not cache", it means
"keep it, but ask before reusing it". The file stays on disk and the ETag turns
the next request into an empty 304, so a re-scraped cover appears immediately
*and* nothing is transferred twice. This is what makes the second boot cheap
without making a corrected image invisible.

The logos are why `no-cache` rather than `immutable` here. `/assets/logos/*.png`
is served under a fixed name and an OTA can legitimately replace it (packs ship
`catalog/<id>/logo.png`, which is *not* excluded from the rsync). They are the
only images on the box whose URL outlives their content, so they are the only
ones a long lifetime would actually break.

── The half that is easy to forget ──────────────────────────────────────────

`no-cache` is only a saving if something answers **304**, and on this box three
routes hand-build a `FileResponse`: the covers, the game media and the logos.
Starlette's `FileResponse` sets `ETag` and `Last-Modified` and then ignores
`If-None-Match` entirely — it has no 304 path at all. Left like that, `no-cache`
would turn every revalidation into a full re-download and make the boot *worse*
than the no-header behaviour it replaced.

`conditional_file_response` below is that missing half. It borrows Starlette's
own comparison rather than reimplementing conditional GET, so the covers route
and the `/covers` static mount agree on what "unchanged" means.
"""
import re
from pathlib import Path

from starlette.responses import FileResponse
from starlette.staticfiles import NotModifiedResponse, StaticFiles

IMMUTABLE = "public, max-age=31536000, immutable"
REVALIDATE = "no-cache"
NEVER = "no-store"

# A build asset named by content hash. Vite's default `assetFileNames` is
# `assets/[name]-[hash][extname]` with an 8-character base64url digest.
#
# The name alone is NOT enough to decide this, and that is the whole reason
# `for_frontend` takes a path: `Pokemon - Sapphire.png` ends in a hyphen and
# eight word characters, and so does every hash Vite ever emitted. A cover
# wrongly declared immutable would be pinned for a year under a URL that is
# reused the moment the game is re-scraped. So the location does the deciding
# and this only guards against a build config that stops hashing at all.
_HASHED = re.compile(r"-[A-Za-z0-9_-]{8}\.[A-Za-z0-9]+$")

# Where Vite puts them. Nothing else is ever served from here: covers come from
# /api/covers, logos from /assets/logos, themes from /themes.
_BUILD_ASSETS = "assets"


def is_hashed_asset(relpath: str) -> bool:
    """True for a build artefact whose URL changes whenever its bytes do.

    `relpath` is relative to the built frontend root, so `assets/index-Dr_k0yci.js`
    — not an absolute path, and not a bare file name.
    """
    parts = Path(relpath.lstrip("/")).parts
    if len(parts) < 2 or parts[0] != _BUILD_ASSETS:
        return False
    return bool(_HASHED.search(parts[-1]))


def for_frontend(relpath: str) -> str:
    """The header for one file served out of `frontend/dist`.

    Unhashed files fall through to revalidation rather than to `immutable`,
    because guessing wrong in that direction is the bug this module exists to
    prevent: an unhashed asset given a year-long lifetime survives the update
    that was meant to replace it.
    """
    name = Path(relpath.lstrip("/")).name
    if name in ("", "index.html"):
        return NEVER
    return IMMUTABLE if is_hashed_asset(relpath) else REVALIDATE


# One instance, used only for its `is_not_modified` rule — the comparison that
# decides whether an `If-None-Match` / `If-Modified-Since` may be answered with
# a 304. Reused rather than rewritten so that a file served by a route and the
# same file served by a static mount never disagree about being unchanged.
_conditional = StaticFiles()


def conditional_file_response(request, path: Path, *, media_type: str | None = None,
                              cache_control: str = REVALIDATE) -> FileResponse:
    """A file the browser may keep, answered 304 when it already has it.

    This is what makes `no-cache` cheap instead of expensive. Without the 304,
    every revalidation ships the whole image again and the header is a pure
    loss — see the module docstring.
    """
    resp = FileResponse(path, media_type=media_type,
                        headers={"Cache-Control": cache_control})
    # FileResponse fills ETag/Last-Modified from a stat it does lazily, so ask
    # for them now: the comparison below needs them, and so does the 304.
    resp.set_stat_headers(path.stat())
    if _conditional.is_not_modified(resp.headers, request.headers):
        return NotModifiedResponse(resp.headers)
    return resp
