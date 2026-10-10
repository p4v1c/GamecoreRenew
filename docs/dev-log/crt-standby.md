# CRT standby: the room, the TV, the game videos (dev log)

Branch: `claude/modest-noether-4ipr9j`, restarted from `origin/main` at
`38e3a6f` (its older commits were already merged into `main`). Never pushed to
`main`, never merged, no PR: a push to `main` publishes an OTA release to the
console.

`$SCRATCH` below is the session scratchpad,
`/tmp/claude-0/-home-user-GamecoreRenew/1b797080-036c-5ff1-9857-ebc0724751de/scratchpad`.
It may not survive the session; everything needed to re-render or re-test is
committed (see "Files changed").

## Goal

A new standby screen for Orbit and Shelf, built from the validated Blender
scene (`$SCRATCH/scene/ref-hd.png`): a blue room at night, a small maroon CRT
on a white stand. On the TV glass, real game videos (ScreenScraper
`video-normalized` / `video`) play one after the other, with a CRT look, and
the TV's light tints the room. A caption says what is on and when it was last
played, with the clock.

1. **Scene as an asset**: render the plate with the TV screen OFF (dark glass,
   no TV light) and a "TV light only" pass, as webp, plus the screen corners.
2. **Backend**: a service that picks which games get a video (played most and
   most recently first), downloads it through the gamemedia pipeline, never
   while a game runs, under a 5 GB cap with eviction, and an endpoint listing
   the clips on disk.
3. **Frontend**: one shared standby view (`sdk.defaults`), opted into by
   Orbit and Shelf.

## Where I stopped

Steps 1 and 2 done (plates committed; backend clip service + endpoint + tests
+ docs). Next: the frontend standby view (step 3).

## Journal

1. Read the `gamecore-*` skills, the scene script, the current standby
   (`frontend/src/components/Screensaver.tsx`, Summer's
   `config/themes/summer/views/screensaver.js`), the SDK seam
   (`sdk.defaults`, `Shell` part `screensaver`), `backend/services/prefetch.py`
   and the gamemedia facade.
2. Scene script copied into the repo, flags added, low-res test of both new
   modes (`$SCRATCH/plate/t-off.png`, `t-light.png`): fine. Final renders
   launched in the background (`$SCRATCH/plate/render.sh`).
3. Backend: `standby_picks.py`, `standby_videos.py`, `drop_file()`, endpoint,
   worker, tests. First test run found the refetch churn (see Decisions).
   68 tests green across `test_standby_videos.py`, `test_prefetch_after_boot.py`
   and `test_gamemedia.py`.
4. Final renders: plate 1920x1080/128 samples in 7:00, light pass
   1280x720/64 in 1:17 (`$SCRATCH/plate/room-off.png`, `room-tvlight.png`).
   Corners identical to the validated render's. webp q92: 98 KB + 24 KB.

## Decisions

- **Scene script lives in `docs/dev-log/crt-standby-scene/`**, next to this
  log, like the Shelf dev-log tools: it needs Blender and Poly Haven assets,
  so it is not a repo script. Made ruff-clean (the validated `ref.py` had
  `import bpy, math, …` on one line, E401, which a release already failed on).
  The scene code itself is byte-identical except the screen material, the
  `tvl` light switch and the asset/cover paths (diff checked).
- **Two plates, not one**: `room-off` (TV off, dark glass, `tvl` hidden) and
  `room-tvlight` (only the TV's light, white, Standard view transform). The UI
  tints the second with the video's colour and screens it over the first; the
  light pass costs 77 s at 1280x720, so it was cheap.
- **Backend selection = playtime only.** Favourites live in each theme's
  localStorage (Orbit `orbit-favourites`), the backend cannot see them; the
  playlist endpoint takes `?favourite=system:file` to weight them instead.
- **Value** = hours played capped at 50 h (0..10) + recency fading over 30
  days (0..10), summed over every profile. Unplayed games follow in a stable
  hash order so the tail mixes consoles.
- **Eviction keeps the size hint.** `gamemedia.drop_file()` files the clip back
  as `deferred` with URL and `bytes`. Deleting the file alone makes the
  manifest incomplete, which triggers a rescrape (one jeuInfos). The `bytes`
  hint stops a sweep from re-downloading a clip it just evicted (found by the
  cap test: every sweep re-fetched and re-dropped the same clip).
- **Cap** = env `GAMECORE_STANDBY_VIDEO_CAP_GB`, default 5, like
  `GAMECORE_WARM_MEDIA` (no settings UI). `0` drops every clip.
- **Never scrapes**: only games that already have a manifest (the cover pass
  makes them). Deferral reuses `prefetch.wait_until_nobody_is_playing()` (made
  public) before every download.
- **webp quality 92, not 85**: at 85 the wall gradients band (visible on a
  TV in a dark room); 92 is still 98 KB, far under the 600 KB budget.
- **Plates live in `frontend/src/assets/standby/`**, imported by the host
  component, so they ship hashed in the bundle (no new static route). There is
  no `public/` folder in this frontend; `assets/logo.png` is the precedent.
- **Worker** starts 180 s after boot, re-sweeps every 3 h (playtime moves).

## Files changed

Backend (step 2):
- `backend/services/standby_picks.py` (new): value, rank, weighted shuffle,
  playtime across profiles, library scan.
- `backend/services/standby_videos.py` (new): cap, eviction plan, sweep,
  worker, playlist.
- `backend/services/gamemedia/__init__.py`: `drop_file()`.
- `backend/services/prefetch.py`: `wait_until_nobody_is_playing` made public.
- `backend/routers/standby.py`: `GET /api/standby/videos`.
- `backend/main.py`: starts `standby_videos.run()` in the lifespan.
- `backend/tests/test_standby_videos.py` (new, 10 tests).
- Docs: `docs/architecture/03-backend-routers.md`, `04-backend-services.md`,
  `07-config-and-data.md`.

Scene (step 1):
- `docs/dev-log/crt-standby-scene/crt-room.py`: the validated scene script
  with `--screen off|on`, `--pass full|tvlight`, `--covers`, `--assets`.
- `docs/dev-log/crt-standby-scene/README.md`: how to re-render, licences.
- `frontend/src/assets/standby/room-off.webp`, `room-tvlight.webp`,
  `room-screen.json`.

## How to test

```bash
ruff check .
python3 -m pytest backend/tests/test_standby_videos.py -q
python3 scripts/check-docs.py --all
```

## Screenshots

(filled in at the end)

## Known issues and TODO

(filled in as found)
