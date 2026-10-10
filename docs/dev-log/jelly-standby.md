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

Step 0: plan written, nothing built yet.

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
   mockup and its recording.

## Decisions

## Files

## How to test

## Screenshots

## Known issues
