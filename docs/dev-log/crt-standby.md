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

**Done.** All three parts are committed and pushed. Two visual review passes
(the second found nothing), recordings made, every check run (results below).
What is left is the owner's call: look at the shots, then try it on the TV
with real ScreenScraper clips (see Known issues). Nothing is half-done.

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
5. Frontend: pure helpers first (`homography.ts`, `standbyPlaylist.ts`,
   `tvLight.ts`, 12 vitest), then `components/CrtStandby/`, the SDK export
   (`defaults.CrtStandby`, SDK 11 in both `themeSdk.ts` and
   `backend/services/themes.py`), the Orbit and Shelf opt-ins with their
   caption skins, theme versions bumped (Orbit 4.2.0 → 4.3.0, Shelf 4.3.1 →
   4.4.0). Wake on mouse/key extracted to `hooks/useLocalWake.ts` (was inline
   in `Screensaver.tsx`; now shared).
6. Found while testing: `homography` rounded the projective terms to 9
   decimals, which shifts corners by 1e-4 px on a 640 px box (they are
   ~1e-6); switched to 12 significant digits.
7. Dev data: `docs/dev-log/crt-standby-tools/make-standins.py` files four
   VP9 stand-in clips and four stand-in screenshots in the dev media cache the
   way gamemedia files them. The real `GET /api/standby/videos` and the real
   media route serve them on devserve.
8. Visual review pass 1 (`$SCRATCH/mock/standby-shots/pass1/`): both themes,
   clip, static, stills, no media, 2x caption and TV crops. Legibility audit
   on both: every caption line passes (lowest 5.4:1). Findings and fixes:
   - Shelf title tracking -0.03em closed the word space ("CrashBandicoot")
     → -0.015em.
   - The contrast ratios written in both themes' `css/standby.css` headers
     were estimates → replaced with the audit's measured values.
   - Audit FAIL on Shelf `cz-st-name "DS"`: a home-screen label half off the
     viewport (x=1910) under the standby; the audit cannot prove it is covered.
     Every on-screen label resolves to the standby on top (probe). Artefact,
     not a leak.
9. Visual review pass 2 (`$SCRATCH/mock/standby-shots/`), cold: every state
   re-shot on both themes plus Orbit under reduced motion. Nothing to fix:
   two clips give two light colours on the stand top and bezel; the snow
   throws a white glow; stills push in and tint the room (red for the red
   screenshot); no-media is soft snow with the clock only; reduced motion
   has no canvas dust and no snow (fade). The dots still visible under
   reduced motion are the dust baked into the plate.
10. Recordings, 17 s each, both contain a switch (Orbit: Crash to Advance
    Wars; Shelf: Crash to Mario Kart). Checked with a frame strip.
11. Final checks, all on the last commit:
    - `ruff check .` (0.16.1 from a scratch `pip --target`, and 0.15.20):
      clean. `shellcheck -S warning`: clean.
    - `pytest backend/tests catalog -m "not network"`: 2602 passed, 57
      skipped, 4 failed, the known ones on untouched `main`
      (`test_install_media_index.py` x3,
      `test_system_split.py::test_the_command_dry_runs_by_default`).
    - `vitest run`: 79 files, 704 tests passed. `tsc --noEmit`: clean.
    - `test_theme_versions.py`: 5 passed. `check-theme.mjs` orbit and shelf:
      0 syntax errors, settings reach all 10 pages. `check-docs.py --all`:
      clean. File-size check `--diff`: clean.

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
- **One shared view, host side**: `components/CrtStandby/`, exposed as
  `sdk.defaults.CrtStandby` (SDK 11). Themes **feature-detect** it instead of
  declaring `"api": 11` (precedent: `createWhoIsPlaying?.`): requiring it would
  drop the whole theme on an older host instead of keeping the slideshow.
- **Theme touches are CSS variables only** (`--crt-cap-*` on a `skin` class):
  Orbit a night-blue card in Red Hat with the `--blue` label; Shelf a paper
  label with a brass tab, slightly crooked.
- **Light = light pass x tint, screened.** `room-tvlight` in a group with
  `mix-blend-mode: screen`, a `multiply` div of the mean colour inside it.
  Colour from a 16x12 `drawImage` 4x/s; CSS variables written directly, no
  React render per frame. Opacity 0.18 + 0.62 x luminance, ±4 % flicker.
- **Double-buffered video**: two `<video>` slots, only the shown one plays;
  the next loads paused. On unmount both are paused and emptied.
- **Clip length** = its duration or 25 s, whichever is shorter; 450 ms snow
  between; stills 9 s with a Ken Burns push-in. Reduced motion: no dust, no
  flicker, a 500 ms fade instead of snow.
- **No media**: soft snow on the TV, caption shows only the clock.
- **Scanline period** ~90 lines over the glass: at the TV's real size (about
  210 px wide) a true 240-line raster would alias into moiré.
- **Caption bottom-left** on the carpet corner, on a card in the theme's
  material (never straight on the picture), 34 px title, 20 px meta, 16 px
  hint. Clock 24 h (`fr-FR`, as the TopBar), date in English.
- **slop-audit**: default-ui gradients 20 → 23, all three in the CRT glass
  (reflection, vignette, scanlines): light the metaphor has. Nothing else moved.
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

Frontend (step 3):
- `frontend/src/components/CrtStandby/` (new): `index.tsx`, `TvPicture.tsx`,
  `TvStatic.tsx`, `DustMotes.tsx`, `StandbyCaption.tsx`, `useTvPlacement.ts`,
  `useTvLight.ts`, `crtStandby.css`.
- `frontend/src/lib/homography.ts`, `standbyPlaylist.ts`, `tvLight.ts` (new,
  + tests); `frontend/src/api/standby.ts` (new); `api/index.ts`
  (`standby.videos`); `hooks/useLocalWake.ts` (new); `Screensaver.tsx` uses it.
- `frontend/src/components/defaults.tsx` (`CrtStandby`), `lib/themeSdk.ts`
  (SDK 11), `backend/services/themes.py` (SDK 11).
- `frontend/src/themes/orbitShelfStandby.test.tsx` (new, 5 tests).
- Orbit: `index.js`, `lib/catalog.js` (`favouriteKeys`), `css/standby.css`,
  `theme.css`, `theme.json` 4.3.0, `DESIGN.md`.
- Shelf: `index.js`, `css/standby.css`, `theme.css`, `theme.json` 4.4.0,
  `DESIGN.md`.
- Docs: `docs/architecture/05-frontend.md`, `docs/themes/README.md`,
  `README.md`, `CHANGELOG.md`.
- Dev tools: `docs/dev-log/crt-standby-tools/make-standins.py`,
  `standby-shots.cjs`, `standby-init.js`.

Scene (step 1):
- `docs/dev-log/crt-standby-scene/crt-room.py`: the validated scene script
  with `--screen off|on`, `--pass full|tvlight`, `--covers`, `--assets`.
- `docs/dev-log/crt-standby-scene/README.md`: how to re-render, licences.
- `frontend/src/assets/standby/room-off.webp`, `room-tvlight.webp`,
  `room-screen.json`.

## How to test

```bash
ruff check .
shellcheck -S warning $(git ls-files '*.sh') install/bin/*
python3 -m pytest backend/tests catalog -q -m "not network"
git fetch --tags && python3 -m pytest backend/tests/test_theme_versions.py -q
node scripts/check-theme.mjs config/themes/orbit
node scripts/check-theme.mjs config/themes/shelf
(cd frontend && npx vitest run && npx tsc --noEmit)
python3 scripts/check-docs.py --all
```

Seeing it (dev box, no ScreenScraper):

```bash
SCRATCH=/tmp/claude-0/-home-user-GamecoreRenew/1b797080-036c-5ff1-9857-ebc0724751de/scratchpad
# stand-in clips + screenshots into the dev media cache
GAMECORE_PATH=$PWD GAMECORE_DATA=$SCRATCH/gcdata PYTHONPATH=$PWD \
  python3 docs/dev-log/crt-standby-tools/make-standins.py $SCRATCH/scene/frame.png
(cd frontend && npm run build)
for t in orbit shelf; do rsync -a --delete config/themes/$t/ $SCRATCH/gcdata/config/themes/$t/; done
GAMECORE_PATH=$PWD GAMECORE_DATA=$SCRATCH/gcdata PYTHONPATH=$PWD \
  python3 .claude/skills/gamecore-legibility/scripts/devserve.py &
# shots: real | stills | none, optional --video (17 s recording) or --reduced
node docs/dev-log/crt-standby-tools/standby-shots.cjs orbit $SCRATCH/mock/standby-shots real
# legibility audit in standby (needs a `chromium` on PATH that runs as root:
# a wrapper around Playwright's headless_shell with --no-sandbox, see Known issues)
node .claude/skills/gamecore-legibility/scripts/legibility-audit.mjs --theme orbit \
  --init docs/dev-log/crt-standby-tools/standby-init.js --eval "0;;0;;0;;0" --all
```

Standby is entered by answering `GET /api/standby` with `state: screensaver`
(Playwright route in `standby-shots.cjs`, a fetch wrapper in
`standby-init.js`): devserve is read-only and never runs the standby timer.

## Screenshots

All in `$SCRATCH/mock/standby-shots/`, 1920x1080 (crops at 2x). **Every
picture on the TV is a stand-in** made by `make-standins.py` and labelled
"stand-in clip" / "stand-in screenshot" on screen: the dev box has no
ScreenScraper account. The Chrono Trigger "clip" is the validated scene's own
TV picture (`$SCRATCH/scene/frame.png`) panned; the others are ffmpeg test
sources. The game names, systems and "played N days ago" are real dev data.

| File | Shows |
|---|---|
| `orbit-real-1.png`, `orbit-real-2.png` | Orbit, two clips, two light colours (stand-in clips) |
| `shelf-real-1.png`, `shelf-real-2.png` | Shelf, the same (stand-in clips) |
| `orbit-real-static.png`, `shelf-real-static.png` | the snow between clips |
| `orbit-real-caption.png`, `shelf-real-caption.png` | the caption, 2x |
| `orbit-real-tv.png`, `shelf-real-tv.png` | the TV glass, 2x: warp, scanlines, rounded mask, bezel light |
| `*-stills-1.png`, `*-stills-2.png`, `*-stills-tv.png`, `*-stills-static.png` | screenshot fallback, Ken Burns (stand-in screenshots) |
| `*-none-1.png`, `*-none-tv.png`, `*-none-caption.png` | no media at all: soft snow, clock only |
| `orbit-real-reduced-*.png` | Orbit under `prefers-reduced-motion` (no dust, fade instead of snow) |
| `orbit-switch.webm`, `shelf-switch.webm` | 17 s recordings with one clip switch each (stand-in clips) |
| `pass1/` | the first review pass, before its fixes, plus `*-audit.png` from the legibility audit |

## Known issues and TODO

- **Not seen with real ScreenScraper clips or on the TV.** Real clips are
  H.264 MP4; Electron plays them, Playwright's Chromium cannot, hence VP9
  stand-ins. First thing to check on the box: a real clip on the glass, the
  light colour, and the sweep's log line (`standby videos: N fetched...`).
- Not measured on the box's GPU: two full-screen layers blended (screen +
  multiply), a full-screen dust canvas at 25 fps, the bloom `box-shadow`
  repainted 20x/s. If the box stutters, drop the dust first.

- The floor boxes are baked into the plate (v1, accepted). TODO(standby):
  render the floor empty and lay the library's covers like the video, if the
  owner wants the floor to follow the library.
- Favourites only weight the playlist; the download order cannot see them
  (they live in the theme's localStorage).
- Clips are fetched only for games that already have a gamemedia manifest
  (the cover pass makes them); a game added today gets its clip on the next
  sweep (3 h) after its cover.
- `legibility-audit.mjs` spawns `chromium` from PATH; on this dev box that
  is a scratch wrapper around Playwright's `headless_shell --no-sandbox`
  (`$SCRATCH/bin/chromium`). The full `chrome` build never opened its
  DevTools port here.
- Audit artefact: a half-off-screen Shelf home label under the standby is
  reported FAIL (see journal 8).

## Follow-up: Shelf caption

The owner preferred Orbit's dark card to Shelf's white paper label. Shelf's
caption is now a dark glass card (Archivo, brass label); Shelf 4.4.0 -> 4.4.1.
