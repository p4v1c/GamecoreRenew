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

## Where I stopped

Just started: log created, no theme change yet.
