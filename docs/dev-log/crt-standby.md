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

Step 0: dev log created. Nothing else committed yet.

## Journal

1. Read the `gamecore-*` skills, the scene script, the current standby
   (`frontend/src/components/Screensaver.tsx`, Summer's
   `config/themes/summer/views/screensaver.js`), the SDK seam
   (`sdk.defaults`, `Shell` part `screensaver`), `backend/services/prefetch.py`
   and the gamemedia facade.

## Decisions

(filled in as they are taken)

## Files changed

(filled in per step)

## How to test

(filled in per step)

## Screenshots

(filled in at the end)

## Known issues and TODO

(filled in as found)
