# Shelf: "Studio" home and a smoother library (dev log)

Branch: `claude/modest-noether-4ipr9j`, started from `origin/main` at `1e5126a`.
Never pushed to `main`, never merged, no PR (a push to `main` ships an OTA
release to the console).

`$SCRATCH` below is the session scratchpad,
`/tmp/claude-0/-home-user-GamecoreRenew/1b797080-036c-5ff1-9857-ebc0724751de/scratchpad`.
It may not survive the session, so the test scripts are also committed in
`docs/dev-log/shelf-studio-home-tools/` (paths inside them point at `$SCRATCH`;
edit the constants at the top if you run them elsewhere).

## Goal

1. Replace Shelf's home screen with the approved "Studio" layout (mockups:
   `$SCRATCH/mock/final/1-accueil-console.png`, `2-accueil-app.png`; HTML
   sources `mock/V-final-3ds.html`, `mock/T1-studio-app.html`). The copy block
   sits top left, the console photo on the right, and along the bottom a white
   "studio sweep" carries a row of console photos, then the apps as white icon
   tiles. Shelf's paper wall stays as it is.
2. Fix two smoothness bugs in Shelf's library without changing its look: a
   black flash during the jacket swap, and the swap animation being skipped
   (cut) when the d-pad is pressed quickly.

Only `config/themes/shelf/**` changes, plus two Shelf test files in
`frontend/src/themes/` (see "Shared code touched") and this log. Theme version
4.2.3 → 4.3.0.

## Journal

1. Read `DESIGN.md`, `README.md`, the home and library views, the host's
   `HomeScreen` (`frontend/src/components/HomeScreen/index.tsx`) and the theme
   SDK docs (`docs/themes/README.md` §5f, §5g, §6a, §7.0).
2. Found that the dev server on :8766 serves themes from
   `$SCRATCH/gcdata/config/themes/`, a COPY of the repo's themes, not the
   checkout. `tools/sync.sh` rsyncs `config/themes/shelf/` into it; run it
   after every edit, then reload.
3. Rebuilt `frontend/dist` from `origin/main` (`cd frontend && npm run build`)
   because the bundle on disk had been built from `feat/profiles`.
4. **Home, first pass** (commit `7e0a449`):
   - `views/home.js` rewritten: copy block (eyebrow, name, sentence, stats,
     buttons, recent covers), the console photo, the sweep and its row.
   - `lib/consoles.js` (new): maker, year, kind and one sentence per pack id.
   - `lib/home-data.js` (new): playtime rows + lazy per-console shelf, so the
     home knows recent games, their playtime and the ROM path for △.
   - `lib/trim.js` (new): crops an app logo to its alpha bounding box.
   - `lib/accent.js`: `onPaper()` darkens a pack colour until it reaches a
     contrast ratio on the paper (4.6:1 for text, 3:1 for lines).
   - `views/ceremony.js`: a launch started from the home (△) gets the iris.
   - `css/home.css` rewritten; the dead "row of big icons" block removed from
     `css/quality.css`; entrance selectors updated in `css/transition.css`.
   - Bugs met on the way: the first render was blank (`.cz-home { flex: 1 }`
     lived in the old home.css, so the new root had height 0); the hero image
     overflowed its 680×500 box (percent height on a grid item); the primary
     button's ring was clipped by the column's overflow. All fixed.
5. **Home, comparison pass**: shot 3DS, GBA, PS1, PS2, YouTube, Twitch, Stremio
   (far right), and YouTube held in the background (faked by intercepting
   `/api/games/session` AND the WebSocket hello `game:running`, see
   `tools/lib.cjs` `opts.session`). Compared side by side with the mockups
   (`agent-shots/compare-*.png`). Fixed: title measure (the mockup stacks
   "Nintendo / 3DS"), hero size.
6. Found and fixed a pre-existing Shelf bug: the session ledge said "Game
   paused" for an app (`views/session.js` compared `'application'` with
   `'app'`).
7. **Library, diagnosis** — built a recorder (`tools/burst.cjs`): opens the GBA
   shelf (13 games), presses `gp:dpad-right` N times every I ms, records CDP
   screencast frames and, every animation frame, each jacket's computed 3D
   state (rotateY of `.cz-box`, translate of `.cz-carry`, which images have
   loaded). Findings below ("Library: what was wrong").
8. **Library, rework**: `lib/swap.js` (new), `views/library.js`,
   `css/library.css`, `css/library-motion.css`, `css/quality.css`. Committed
   as `23966ac` (WIP, pushed by the coordinator when I hit a usage limit).
9. **Tests after resume**: the Shelf vitest harnesses build the library view
   without the new `useSwap` dependency → `views/library.js` now defaults it
   from `lib/swap.js`. Two Shelf test files pinned the OLD behaviour and were
   rewritten for the new contract (see "Shared code touched").
10. Capped the per-frame step of the swap (`MAX_DP = 0.12`) after the checker
    still flagged one jacket covering a third of its path in one slow frame.
    Re-ran all bursts: 0 cuts at 60, 120 and 300 ms.

## Library: what was wrong

**Skipped animation.** The swap was two CSS keyframe animations on two keyed
holders (`out` = the jacket going back, 360 ms; `in` = the next coming out,
560 ms after a `--wait`). Keyframes cannot be interrupted, only cancelled, and
the view did cancel: a second press while the next jacket was still "tucked"
(i.e. any press within ~360 ms + the 150 ms artwork lag) removed the outgoing
holder mid-turn (a visible cut) and re-armed the timers, so nothing came out
until the presses stopped. Evidence (`agent-shots/frames-burst-before-120.png`,
`frames-burst-before-300.png`, `samples-before-*.json`): with presses every
120 ms AND every 300 ms, no jacket is out between ~0.3 s and ~1.8 s; at 300 ms
the timeline shows the first box at rotateY 40° vanishing from one sample to
the next.

**Black flash.** Reproduced by delaying every `/api/covers` response by 700 ms
(a slow box with uncached covers): `agent-shots/frames-slow-before.png` shows
solid black slabs at 131–180 ms, 957–1001 ms and 1342–1389 ms (dark-pixel
fraction in the jacket area 0.77 vs 0.16 at rest, `tools/dark.py`). Causes:

1. The jacket going back was a NEW holder with a NEW `Box.Face` (keyed
   `out:<file>`), and the arriving one was re-keyed 150 ms after the press when
   `detailGame` settled. Every new Face starts its `<img>`s from scratch.
2. Every face's background is `--board` (#1C1B19), so a front or back whose
   scan has not decoded yet is drawn as a near-black slab.
3. The holder (the element carrying the perspective) faded to 62 % opacity
   while the artwork caught up; an animated opacity there makes the browser
   re-flatten the 3D scene each frame (a known way for inside faces to show).
   Not reproducible in headless Chromium, removed anyway since it served
   nothing once (1) was fixed.

## Decisions

- **Presentation data is copied from Orbit, not imported.** No shipped theme
  imports another; Orbit can be removed or reshaped and Shelf must not break.
  `lib/consoles.js` names its source (`config/themes/orbit/lib/catalog.js`).
  The "kind" column (Handheld, Hybrid, Add-on, Arcade board, Home console) is
  new: hardware fact, not invented copy. Apps get maker + category + Orbit's
  sentence. A pack missing from the table shows no eyebrow and no sentence.
- **Accent colour = the pack's `color`** (the mockup's pink 3DS and red YouTube
  come from it), darkened by `onPaper()` so the eyebrow clears 4.6:1 and the
  ring/bar clear 3:1. The hue is kept.
- **"·" in the eyebrow** follows the approved mockup although DESIGN.md said
  "No '·' meta"; DESIGN.md now records the exception.
- **△ is bound by the theme on the home only** (the host binds △ only in the
  library). Console: launches the last-played game of that console through
  `sdk.defaults.launchGame` with `CLOSE_MS` as the hold; the ceremony draws the
  iris. App in the background: closes it, but only on a second △ within 3 s
  ("Press again to close"), because closing Steam can kill an unsaved PC game.
  ✕ stays the host's (open library / launch or resume an app; the backend
  foregrounds an app that is already suspended).
- **↑/↓ do nothing on the home**, as before: Shelf has no other zone there and
  the recent covers are history, not a menu.
- **Stats are real or absent**: games count (host's), time played and last
  played (host's per-system playtime), "Open, in the background" for a
  suspended app. The mockup's "2 h 40 this week" has no source and is not shown.
- **Title measure 640px** with `text-wrap: balance` reproduces the stacked
  "Nintendo / 3DS" while one-word names stay on one line.
- **Row scrolling is measured from the DOM** (cell offset, wrap width, 90px
  edge margin) and written straight to `transform`.
- **Swap animation: one interruptible progress value per jacket**
  (`lib/swap.js`), chosen over the three options in the brief because it
  gives all three at once:
  - *interrupt from the current visual state*: p = 0 is "in hand", p = 1 is
    "in its column, edge-on, at the row's depth and lean". The jacket under the
    cursor heads for 0, every other one for 1, every frame, so a box half way
    out simply turns back from where it is. No element is ever replaced while
    it moves (keyed on the game, created at p = 1 and removed only at p = 1,
    the frame its spine reappears), which is also the black-flash fix.
  - *faster with the input rate*: speed = (put-back to hand-over + take-out at
    rest ≈ 760 ms) / (average gap between the last presses), clamped 1×–3×,
    with 1.2× extra on a box being put away while the next one waits. Up to
    ~4 presses a second every box still turns to face you; faster, the
    intermediate boxes visibly start out and go back.
  - *coalescing*: the next jacket starts out once the previous one is edge-on
    and sliding home (p ≥ 0.55) during a burst, strictly after it at rest (the
    original sequence and timings: 360 ms back, then 560 ms out).
  - The landing column is read from the rail's live (mid-transition)
    transform, so a box sent back while the row is sliding lands on its spine.
  - Frame steps are capped (34 ms of time, 12 % of the gesture) so a dropped
    frame slows the motion rather than skipping a stretch of it.
  - At rest in the hand the inline transforms are cleared and the stylesheet
    owns the pose again, so the L2 flip keeps its 620 ms CSS transition;
    `prefers-reduced-motion` makes the swap near-instant.
- **Unloaded printed faces are pale card (#E9E6DF), not board black.** The
  "no cover" and "printed reverse" fallbacks still paint their own dark card
  on top (that is Shelf's designed look and was kept).
- **Neighbours' jackets are prefetched** (±1, ±2) 400 ms after the cursor rests.

## Files changed

Theme (`config/themes/shelf/`):
- `views/home.js` (rewritten), `css/home.css` (rewritten)
- `lib/consoles.js`, `lib/home-data.js`, `lib/trim.js`, `lib/swap.js` (new)
- `lib/accent.js` (`onPaper`), `views/ceremony.js` (launch from home)
- `views/library.js` (swap state → `useSwap`, one holder per jacket on stage)
- `views/session.js` (app/game wording bug)
- `css/library.css`, `css/library-motion.css` (keyframes removed, pale faces,
  no holder fade), `css/quality.css`, `css/transition.css`, `css/base.css`,
  `css/library-detail.css` (dead selectors)
- `index.js` (wiring), `theme.json` (4.3.0), `README.md`, `DESIGN.md`

Shared code touched (strictly needed): `frontend/src/themes/shelfSwap.test.tsx`
and `frontend/src/themes/themeCeremony.test.tsx`. They pinned the old
behaviour this work changes on purpose (the keyed `out`/`in` holders with
`data-phase`/`data-tucked`/`--wait`, and "Shelf's ceremony ignores every
launch"). Rewritten to assert the new contract: a jacket is never replaced
while it moves, a jacket leaves only when back in its column, a burst always
has a jacket on stage, a box sent back mid-way turns from its current angle;
and the iris shows for a launch started from the home but not from the
library. No production frontend code changed.

## How to test

```sh
# theme on the dev server (it serves a copy): sync after every edit
docs/dev-log/shelf-studio-home-tools/sync.sh
node scripts/check-theme.mjs config/themes/shelf          # module syntax
git fetch --tags && python -m pytest backend/tests/test_theme_versions.py
python -m pytest -q backend/tests -k theme                 # 148 passed
python -m pytest -q backend/tests                          # see known issues
cd frontend && npx vitest run && npx tsc --noEmit          # 686 passed, tsc ok

# screenshots / evidence (Playwright from /opt/node22, server on :8766)
cd docs/dev-log/shelf-studio-home-tools
node home-shots.cjs <outdir> azahar gba duckstation youtube twitch stremio
node held.cjs <outdir>           # YouTube suspended, then △ once (armed)
node libshots.cjs <outdir>       # 3DS library: rest, flip, mid-swap, stack, gallery
node burst.cjs <outdir> gba 120 8     # frames + per-frame samples
python3 check.py <outdir>             # cuts / jumps / how many came out
python3 timeline.py <outdir>          # readable per-frame jacket state
python3 sheet.py <outdir> 0 48        # contact sheet of the stage
SLOW_COVERS=700 node burst.cjs <outdir> gba 1200 3 && python3 dark.py <outdir>
```

Results at the last run: theme tests 148 passed; `test_theme_versions` 5
passed (tags fetched, latest `v1.3.15`); frontend 75 files / 686 tests passed;
tsc clean; full backend 2382 passed, 4 failed (pre-existing, see below).

## Screenshots (1920×1080, `$SCRATCH/mock/agent-shots/`)

- Home: `home-3ds.png`, `home-gba.png`, `home-ps1.png`, `home-ps2.png`,
  `home-youtube.png`, `home-twitch.png` (logo trim), `home-far-right.png`
  (Stremio, row clamped at its end), `home-youtube-held.png` and
  `home-youtube-held-armed.png` (suspended app, △ pressed once),
  `home-after-back.png` (○ from the library).
- Side by side with the approved mockups: `compare-3ds.png`, `compare-app.png`,
  `compare-library.png`.
- Library: `lib-3ds.png` (rest), `lib-3ds-flipped.png`, `lib-3ds-swap-mid.png`,
  `lib-3ds-next.png`, `lib-3ds-stack.png`, `lib-3ds-stack-mid.png`,
  `lib-3ds-gallery.png`, `lib-3ds-gallery-mid.png`.
- Fast switching evidence (contact sheets of the stage, times from the first
  press): before `frames-burst-before-120.png`, `frames-burst-before-300.png`;
  after `frames-after-final-60.png`, `-120.png`, `-300.png`; black flash under
  slow covers `frames-slow-before.png` vs `frames-slow-after.png`. Raw
  per-frame samples: `samples-before-*.json`, `samples-after-final-*.json`.

Evidence summary (`check.py`, GBA shelf, 8 presses):

| interval | before: jackets out | before: cuts | after: came out ≥ part way | after: cuts |
|---|---|---|---|---|
| 60 ms | none until the burst ends | outgoing removed mid-turn | 2 of 7, all others visibly start out and go back | 0 |
| 120 ms | none until the burst ends | outgoing removed mid-turn | 3 of 8 | 0 |
| 300 ms | first only, then none | yes | 5 of 8 headless (8 of 8 before the per-frame cap; headless runs at ~25 fps) | 0 |

Slow covers (700 ms): before, max dark fraction 0.78 (black slabs); after 0.52
(= the dark printed spines of the row, the same as between swaps); no slab.

## Deviations from the mockups

- The real top bar (storage, IP, clock, settings, power, profile avatar) is
  kept; the mockup drew a simplified one.
- Stats show only real data, so most apps show no stat chips (the mockup's
  "2 h 40 this week" / "Yesterday" were illustrative), and few consoles have
  4 recent covers on the test box.
- Descriptions are Orbit's sentences (e.g. "The 3D handheld with two screens.
  Runs in Azahar; L3 switches the layout.") rather than the mockup's wording.
- "Resume <game>" uses the full cleaned title ("Resume Mario Kart 7"),
  ellipsised at 440px, instead of a hand-shortened one.
- When a game or app is suspended, the host's session ledge (67px, fixed at
  the bottom) covers the foot hints; the row is lifted 30px so the names stay
  visible. Same as the old home for the foot.
- The library is unchanged visually, except that a still-loading cover face is
  pale card instead of black.

## Known issues / TODO

- 4 backend tests fail identically on untouched `origin/main`
  (`test_install_media_index.py` ×3, `test_system_split.py::test_the_command_dry_runs_by_default`):
  environment, not this branch.
- The black flash could only be reproduced by slowing covers; the GPU-specific
  variant (holder opacity) was not reproducible headless. Worth checking on
  the real console: tap → quickly on a shelf with uncached covers.
- Headless Chromium renders at ~25 fps at 1080p, so the per-frame metrics are
  coarse; the motion is time-based and should be smoother on the box.
- Speed constants (`FASTEST`, `CATCH_UP`, `MAX_DP`, durations) live at the top
  of `lib/swap.js` if the owner wants the burst faster or slower.
- `preview.png` of the theme still shows the old home.
- Hovering the home with a mouse does not move focus (clicking does).

## Where I stopped

Everything above is done, committed and pushed. Last step: the final commit
with the swap step cap, the test updates and this log. Nothing is pending
locally. If resuming: verify on the real console (Electron), and optionally
regenerate `preview.png`.

## Follow-up: back covers warmed too

`lib/swap.js` now warms each resting neighbour's `box-back` as well as its
front (±1, ±2, 400 ms after the cursor stops), so a flipped or turning box
already has its reverse decoded. Spines are not warmed: they already stand in
the row. Disk caching is unchanged and already covers every image at boot
(`backend/services/prefetch.py`, GAMECORE_WARM_MEDIA). Checks: check-theme 0
errors, `npx vitest run src/themes/shelfSwap.test.tsx` 5 passed,
`pytest backend/tests/test_theme_versions.py` passed.
