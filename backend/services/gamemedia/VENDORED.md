# Vendored: `gamescrape.py` + `gamemedia.py`

These two files are a standalone project, copied in rather than rewritten.
They have no dependency outside the standard library, which is why vendoring
them costs nothing: no entry in `requirements.txt`, no wheel to build for the
box, and `python3 gamemedia.py --serve 8811` still works from this folder for
debugging.

`__init__.py` is the seam. **The rest of the backend imports that, never these
two files directly** — it is what points their caches at `emu/`, wraps the
synchronous calls in `asyncio.to_thread`, and translates a manifest into the
shapes GameCore already speaks.

## Local changes

Everything GameCore changed is marked `# GameCore:` in the source, so a diff
against a newer upstream copy is a grep away. There are four:

| Change | Why |
|---|---|
| `from . import gamescrape as gs`, with the `sys.path` insert kept as a fallback | the files are a package here; standalone use still works |
| `resolve(..., only={…})` | downloading all ~28 media of a game costs ~34 s at the 1.2 s ScreenScraper asks for. Only what is displayed is fetched during a scrape; the rest is recorded as `deferred` with its URL |
| `fetch_media(system, filename, slug)` | fetches one deferred media on demand — one HTTP request, no second `jeuInfos`, no quota spent |
| `strip_creds()` / `with_creds()` | a deferred media keeps its URL in `game.json`, and a ScreenScraper media URL carries `devid`, `devpassword`, `ssid` and `sspassword` in its query. They are removed on write and restored from the live credentials on read, so the developer account is never written to disk |

`_manifest_complete()` gained one branch for the same reason: `deferred` is a
media that is *deliberately* not downloaded yet, unlike `pending`, which is the
accident that function exists to catch. Confusing the two would rescrape the
whole game — one `jeuInfos` out of the daily quota — every time a theme drew a
cover.

## Upstream documentation

The full design (the three tiers, hash vs name matching, the PARAM.SFO trick
for PS3 directories, the 54 media types, the ScreenScraper rate rules, what may
and may not be cached) is documented by the upstream project. What matters on
the GameCore side is in `docs/architecture/04-backend-services.md`.

## Updating

Copy the two files back over, re-apply the four changes above (`git diff` on
this directory shows them), and run `pytest backend/tests/test_gamemedia.py`.
