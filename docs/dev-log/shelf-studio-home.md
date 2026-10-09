# Shelf: "Studio" home and a smoother library (dev log)

Branch: `claude/modest-noether-4ipr9j`, started from `origin/main` at `1e5126a`.
Never pushed to `main`, never merged, no PR (a push to `main` ships an OTA
release to the console).

## Goal

1. Replace Shelf's home screen with the approved "Studio" layout (mockups in
   the session scratchpad, `mock/final/1-accueil-console.png` and
   `mock/final/2-accueil-app.png`): copy block top left, the console photo on
   the right, and along the bottom a white "studio sweep" carrying a row of
   console photos, then the apps as white icon tiles. Shelf's paper wall stays
   as it is.
2. Fix two smoothness bugs in Shelf's library without changing its look:
   a black flash during the jacket swap, and the swap animation being skipped
   (cut) when the d-pad is pressed quickly.

Only `config/themes/shelf/**` changes (plus this log). Every change there bumps
`version` in `config/themes/shelf/theme.json`.

## Journal

1. Read `DESIGN.md`, `README.md`, the home and library views, the host's
   `HomeScreen` (`frontend/src/components/HomeScreen/index.tsx`) and the theme
   SDK docs (`docs/themes/README.md` §5f, §5g, §6a, §7.0).
2. Found that the dev server on :8766 serves themes from
   `$SCRATCH/gcdata/config/themes/`, a COPY of the repo's themes, not the
   checkout. Added `$SCRATCH/work/sync.sh` (rsync of `config/themes/shelf/`
   into that copy); run it after every edit, then reload the page.
3. Rebuilt `frontend/dist` from `origin/main` (`cd frontend && npm run build`)
   because the existing bundle had been built from `feat/profiles`.

4. Home, first pass (commit "feat(shelf): Studio home"):
   - `views/home.js` rewritten: copy block (eyebrow, name, sentence, stats,
     buttons, recent covers), the console photo, the sweep and its row.
   - `lib/consoles.js` (new): maker, year, kind and one line per pack id,
     copied from Orbit's `lib/catalog.js` (see Decisions).
   - `lib/home-data.js` (new): playtime rows + lazy per-console shelf, so the
     home knows the recent games, their playtime and the ROM path for △.
   - `lib/trim.js` (new): crops an app logo to its alpha bounding box.
   - `lib/accent.js`: `onPaper()` darkens a pack colour until it reaches a
     contrast ratio on the paper (4.6:1 for text, 3:1 for lines).
   - `views/ceremony.js`: a launch started from the home (△) gets the iris.
   - `css/home.css` rewritten; the dead "row of big icons" block removed from
     `css/quality.css`; entrance selectors updated in `css/transition.css`.
   - First render was blank: `.cz-home { flex: 1 }` used to live in the old
     home.css, so the new root had height 0. Fixed with `flex: 1` on
     `.cz-studio`.
   - Hero image overflowed its 680x500 box (percent height on a grid item);
     the primary button's ring was clipped by the column's overflow. Both fixed.
   - Theme version 4.2.3 -> 4.3.0.

## Decisions

- **Presentation data is copied from Orbit, not imported.** No shipped theme
  imports another; Orbit can be removed or reshaped and Shelf must not break.
  The header of `lib/consoles.js` says so and names the source file. The
  "kind" column (Handheld, Hybrid, Add-on, Arcade board, Home console) is new;
  it is hardware fact, not invented copy. Apps get maker + category + Orbit's
  sentence. A pack missing from the table shows no eyebrow and no sentence.
- **Accent colour = the pack's `color`** (the mockup's pink 3DS and red YouTube
  come from it), darkened by `onPaper()` so the eyebrow text clears 4.6:1 and
  the ring/bar clear 3:1. The hue is kept.
- **"·" in the eyebrow** follows the approved mockup even though DESIGN.md
  says "No '·' meta"; DESIGN.md is updated to record the exception.
- **△ is bound by the theme on the home only** (the host binds △ only in the
  library). Console: launches the last-played game of that console through
  `sdk.defaults.launchGame` with `CLOSE_MS` as the hold, and the ceremony draws
  the iris. App in the background: closes it, but only on a second △ within
  3 s (the button reads "Press again to close"), because closing Steam can
  kill an unsaved PC game. ✕ stays the host's (open library / launch or resume
  an app; the backend foregrounds an app that is already suspended).
- **↑/↓ do nothing on the home**, as before. Shelf has no other zone there and
  the recent covers are history, not a menu.
- **Stats are real or absent.** Games count (host's count), time played and
  last played (host's per-system playtime); app chips likewise, plus
  "Open, in the background" when the app is suspended. Nothing is shown for a
  value the box does not have (the mockup's "2 h 40 this week" has no source).
- **Title measure 640px** with `text-wrap: balance` reproduces the mockup's
  stacked "Nintendo / 3DS" while one-word names stay on one line.
- **Row scrolling is measured from the DOM** (cell offset, wrap width, a 90px
  edge margin) and written straight to `transform`, not computed from
  constants, so it follows any size change in the CSS.

## Where I stopped

Home first pass done and screenshotted (3DS, PS2). Next: commit, compare GBA,
PS1, Twitch and far-right shots with the mockups, then Part 2 (library).
