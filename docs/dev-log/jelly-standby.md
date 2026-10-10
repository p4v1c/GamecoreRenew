# Jelly standby: floating jellies (dev log)

Branch: `claude/modest-noether-4ipr9j`, restarted from `origin/main` at
`5ed27a0` (its older commits were already merged into `main`). Never pushed to
`main`, never merged, no PR: a push to `main` publishes an OTA release to the
console.

`$SCRATCH` below is the session scratchpad,
`/tmp/claude-0/-home-user-GamecoreRenew/1b797080-036c-5ff1-9857-ebc0724751de/scratchpad`.
It may not survive the session; the tools needed to re-test are committed.

## Goal

Jelly's own standby screen, from the approved animated mockup "Gelées
flottantes" (`$SCRATCH/jelly-veille/A-gelee-anim.html`, recording
`jelly-veille.webm`): Jelly's cyan floor with drifting white dots, 6 to 8
translucent jelly blobs that drift, bounce off the edges and each other,
squash on impact and morph, each holding one of the player's covers. A paper
caption bottom left ("Wobbling now", the game, "System, played N days ago"),
a huge wobbling clock bottom right with a date pill.

Approved additions: blobs keep out of the caption and clock zones; every ~25 s
one blob comes to the centre, grows and plays its game's clip (screenshot with
a slow pan when there is no clip); now and then a blob pops and a new game
wobbles in. One video at a time, nothing runs outside the `screensaver` stage,
reduced motion holds everything still and cross-fades the featured game.

## Where I stopped

Stopped early at the owner's request (out of tokens). State on the branch:

**Done, tested, pushed**
- Pure core `lib/standby/physics.js`, `director.js` (incl. `deck.add` for
  games that arrive late) and 22 vitest in `jellyStandbyPhysics.test.ts`.
- Views `views/standby/*`, `css/standby.css`, wired as the Shell's
  `screensaver`; 8 component tests in `jellyStandby.test.tsx` (all 30 green
  on the last run).
- SDK 12 helpers (`defaults.useLocalWake`, `format.playedAgo`).
- Visual review pass 1 and its fixes; pass 2 partly shot
  (`$SCRATCH/mock/jelly-standby-shots/pass2/`: real, stills, reduced).

**Last change, not browser-checked**
- `engine.js`: `fill()` + `addGames()` deal jellies when the collection
  loads after standby started (pass 2 `none` mode timed out with an empty
  floor because of that). Unit tests pass; not yet seen in a browser.
- Collection-late fix in `index.js` (`useCollection` → `addGames`): same.

**Not done**
- Pass 2 review of the images (only `real` pop and feature were looked at:
  fine, except the pop shot came too early; the tool now waits 220 ms).
- `none` mode shots, deliverables copied to `$SCRATCH/mock/jelly-standby-shots/`
  (swarm, feature, pop, caption crop, reduced), the ~20 s
  `jelly-standby.webm` (`--video`), comparison with `jelly-veille.webm`.
- Docs: `docs/themes/README.md` (SDK 12 + Jelly standby), Jelly `DESIGN.md`
  (standby tokens: `--jl-sb-green/orange/lilac`, floor light/deep, motion),
  Jelly `README.md` (screens table, files), `CHANGELOG.md`, `README.md`.
- Full runs: `npx vitest run`, `pytest backend/tests -q -m "not network"`,
  `check-docs.py --all`, file-size `--diff`, slop-audit.
- Theme version: 1.5.0 is on the branch; bump to 1.5.1 before the next push.

**Known issues / open decisions**
- Clock: white figures on an ink step; the legibility audit still reads
  white on cyan as 1.5:1 (FAIL). Alternative that passes: ink figures with a
  white step. Owner to choose.
- Headless Chromium here runs 13-22 fps in software; recordings will look
  choppier than the box. Engine time runs on capped dt, so it lags the wall.
- Jellies may overlap each other ~8 % (soft contact) and get squeezed into
  the featured jelly near a zone wall; the zones themselves hold (tested).
- Gather path of the featured jelly can cross a zone corner for 1.6 s.
- All clips and screenshots on screen are stand-ins (`make-standins.py
  --centre`), labelled "stand-in clip".

**Resume**
1. Restart devserve (command in "How to test"), `rsync` the theme, rebuild
   only if host code changed.
2. Run the shot tool for `none`, `real`, `real --reduced`, then `--video`;
   review pass 2 cold; fix; copy finals to `$SCRATCH/mock/jelly-standby-shots/`.
3. Docs listed above, bump 1.5.1, run every check in "How to test", push.

## Plan

1. Pure core in `config/themes/jelly/lib/standby/`: physics step (edges,
   collisions, repel zones, squash), spawn placement, playlist and feature
   scheduling. Vitest first.
2. Views in `config/themes/jelly/views/standby/`: stage and wake, the swarm
   (one rAF loop writing transforms), the feature, caption and clock;
   `css/standby.css`. Wire as the Shell's `screensaver`.
3. Stand-in media, captures, two visual review passes, recording.
4. Docs, checks, final report.

## Journal

1. Read the `gamecore-*` skills, Jelly's DESIGN.md and README, the CRT
   standby (`frontend/src/components/CrtStandby/`) and its dev log, the
   mockup and its recording. Jelly had no standby of its own: the host's
   slideshow showed, and `views/background.js` only pauses the floor during
   standby (kept, nothing to replace).
2. Pure core: `lib/standby/physics.js` and `lib/standby/director.js`, 21
   vitest (`jellyStandbyPhysics.test.ts`). One fix from the first run: the
   edge test stepped 0.1 s, which decays the squash below its own threshold.
3. SDK 12: `defaults.useLocalWake` and `format.playedAgo` exposed (see
   Decisions). `test_sdk_version_gate.py` + `test_themes.py`: 69 passed.
4. Views (`views/standby/`), `css/standby.css`, wired as the Shell's
   `screensaver`. Component tests (`jellyStandby.test.tsx`, 8) with a hand
   pumped frame clock: mount per stage, covers, feature with one video,
   pop, release on `sleep`, reduced motion, wake, old host.
5. First browser run (`$SCRATCH/mock/jelly-standby-shots/pass0/`): works,
   close to the mockup. Headless Chromium here renders 13-22 fps at 1080p in
   software, so the engine's capped dt runs its clock slower than the wall;
   the capture tool waits on `data-phase` instead of fixed delays.
6. Visual review pass 1 (`pass0/`, `pass1/`), findings and fixes:
   - the clip in the featured jelly read as a flat cut-out: the rim film's
     gradient never reached the clipped outline → `closest-side` rim in the
     jelly's colour plus its shade over the picture;
   - the stand-in label sat in the corner the jelly crops away →
     `make-standins.py --centre`;
   - a pop dealt the popped game straight back (Crash popped, Crash wobbled
     in) → popping jellies count as on screen;
   - the splat drops were tiny dots → larger, jelly-shaped, with the step;
   - the big yellow jelly sat over the clock's top edge (a crowd and the
     featured jelly can push past a soft field) → soft field 72 px plus a
     hard wall 24 px from the outline, tested;
   - the white clock is 1.5:1 on the floor (audit FAIL) → solid ink jelly
     step under the white figures (see Decisions, Known issues).

## Decisions

- **Theme code, not host code.** The standby is `views/standby/` in Jelly,
  passed as the Shell's `screensaver` (the CRT room's seam). Two small host
  helpers were exposed instead of copied, SDK 11 → 12 (`themeSdk.ts`,
  `backend/services/themes.py`): `sdk.defaults.useLocalWake` (mouse/key wake,
  already shared by the host's two standbys) and `sdk.format.playedAgo`
  (the CRT caption's "played 3 days ago", so both standbys say it the same
  way). Jelly feature-detects both and keeps `"api": 10`: on an older host
  `createStandby` returns undefined and the Shell keeps its slideshow.
- **Pure core, imperative frame.** Physics and timeline are pure modules;
  `views/standby/engine.js` owns one rAF loop that writes `transform` on
  each jelly and its `border-radius` at 30 Hz (a repaint; the morph is slow
  enough that 30 Hz is smooth). React renders only the room, caption and
  clock. No layout read per frame: the root size and the caption/clock rects
  are read at start, on resize and when the caption's game changes.
- **dt is real and capped at 50 ms**, so a stall never teleports a jelly.
- **Sizes change once per feature**, never per frame: the featured jelly's
  element takes the feature size (860x600 design px) when it is picked and
  is scaled down to where it was, so the clip is drawn at full resolution;
  its own size comes back when it settles.
- **Mass by area** in collisions (the mockup swapped equal masses): a big
  jelly shoves a small one. The featured jelly is pinned, infinite mass.
- **Repel zones:** a soft spring (72 px from the drawn outline) plus a hard
  wall at 24 px, because the soft field alone lost to a crowd. Both from the
  outline, not the soft contact radius: the text must stay uncovered.
- **Featured game:** the reel is the host playlist, clips first then
  screenshots, round robin. If the game has no jelly on screen, the jelly
  nearest the centre pops and the game wobbles in there. No playlist at all:
  a jelly on screen grows with its cover. Every ~25 s of swarm (first at
  8 s), gather 1.6 s, show = the clip's length up to 20 s or 12 s for a
  still, release 1.4 s.
- **Pops** every 10-16 s (first at 5 s), never during a gather or release.
  The new jelly holds the next game of a shuffled deck of the whole
  library, so the library comes round. Caption: the featured game during a
  feature, otherwise the game that last wobbled in.
- **Covers only for games that have one:** each cover is preloaded and a
  404 drops the game from the deck. Games come from Jelly's collection
  (already loaded for Home); if it never loaded, from the playlist.
- **Favourites** (`jelly-favourites`) weight the playlist like Orbit's.
- **No sound.** The host plays nothing in standby and the theme has no hook
  there; a pop is silent.
- **Cheaper jelly than the mockup:** the inner shade and light are radial
  gradients instead of blurred inset shadows (a blur on every outline
  repaint), the highlight is a soft-edged gradient instead of `filter: blur`,
  the dot drift is a `transform` loop instead of `background-position`
  (a full-screen repaint per frame), the cover's float is a CSS loop.
- **Clock:** white digits on a solid ink jelly step (`0 10px 0 --jl-ink`)
  instead of the mockup's 20 % shadow. The pill reads "Saturday 10 October
  Press any button" with a gap instead of the mockup's "·" (human-touch).
- **Reduced motion:** no frame loop at all (a 250 ms timer runs the
  timeline), jellies still, no squash, no dot drift, no cover float, no
  clock wobble; a pop is a 600 ms fade; the featured game fades in on a
  still jelly at the centre (the swarm keeps out of it as a third zone).

## Files

Theme (`config/themes/jelly/`):
- `lib/standby/physics.js` (new): step, edges, collisions, zones, squash, outline, spawn.
- `lib/standby/director.js` (new): deck, feature reel, timings, timeline.
- `views/standby/index.js` (new): stage, wake, data, the room.
- `views/standby/engine.js` (new): the frame loop and actions.
- `views/standby/blob.js` (new): a jelly's element, cover preload, splat.
- `views/standby/media.js` (new): the one video / still of the feature.
- `views/standby/caption.js` (new): caption and clock.
- `css/standby.css` (new), `theme.css` (import), `index.js` (`screensaver`),
  `lib/favourites.js` (`favouriteKeys`), `theme.json` 1.4.6 → 1.5.0.

Host:
- `frontend/src/components/defaults.tsx` (`useLocalWake` re-export),
  `frontend/src/lib/themeSdk.ts` (`format.playedAgo`, SDK 12),
  `backend/services/themes.py` (SDK 12).

Tests: `frontend/src/themes/jellyStandbyPhysics.test.ts`,
`frontend/src/themes/jellyStandby.test.tsx`.

Dev tools: `docs/dev-log/jelly-standby-tools/jelly-standby-shots.cjs`;
`docs/dev-log/crt-standby-tools/make-standins.py` gained `--centre`.

## How to test

```bash
(cd frontend && npx vitest run src/themes/jellyStandbyPhysics.test.ts src/themes/jellyStandby.test.tsx)
(cd frontend && npx vitest run && npx tsc --noEmit)
python3 -m pytest backend/tests -q -m "not network"
git fetch --tags && python3 -m pytest backend/tests/test_theme_versions.py -q
node scripts/check-theme.mjs config/themes/jelly
ruff check .                                   # 0.16.1
shellcheck -S warning $(git ls-files '*.sh') install/bin/*
```

Seeing it (dev box):

```bash
SCRATCH=/tmp/claude-0/-home-user-GamecoreRenew/1b797080-036c-5ff1-9857-ebc0724751de/scratchpad
GAMECORE_PATH=$PWD GAMECORE_DATA=$SCRATCH/gcdata PYTHONPATH=$PWD \
  python3 docs/dev-log/crt-standby-tools/make-standins.py $SCRATCH/scene/frame.png --centre
(cd frontend && npm run build)
rsync -a --delete config/themes/jelly/ $SCRATCH/gcdata/config/themes/jelly/
GAMECORE_PATH=$PWD GAMECORE_DATA=$SCRATCH/gcdata PYTHONPATH=$PWD \
  python3 .claude/skills/gamecore-legibility/scripts/devserve.py &
node docs/dev-log/jelly-standby-tools/jelly-standby-shots.cjs $SCRATCH/mock/jelly-standby-shots real
node docs/dev-log/jelly-standby-tools/jelly-standby-shots.cjs $SCRATCH/mock/jelly-standby-shots real --reduced
node docs/dev-log/jelly-standby-tools/jelly-standby-shots.cjs $SCRATCH/mock/jelly-standby-shots real --video
# legibility (needs the `chromium` wrapper, see crt-standby.md Known issues)
PATH=$SCRATCH/bin:$PATH node .claude/skills/gamecore-legibility/scripts/legibility-audit.mjs --theme jelly \
  --init docs/dev-log/crt-standby-tools/standby-init.js --eval "0;;0;;0;;0" --all
```

## Screenshots

## Known issues
