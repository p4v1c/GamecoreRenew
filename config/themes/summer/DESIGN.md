# Summer — design

**Idea:** a beach at the hour it actually is: the WebGL ocean behind, warm
light, sea glass in front.

**Type:** Atkinson Hyperlegible Next (`fonts/atkinson-hyperlegible-next/`),
chosen for reading at 3 m. One family, weights 400–700. Numbers:
`tabular-nums`. No monospace for labels.

**Palette:** accent mandarin `#F0761E` (focus, primary), deep `#B4520F`,
muskmelon `#FE9D7C`, sea `#1D7E93`; states ok `#3FBF8F`, warn `#E8B23A`,
alert `#E4553F`. The sky/sea palette follows time of day (`lib/ocean.js`).

**Shape:** 22 px panels, 18 px tiles, pills for chips.

**Depth:** sea-glass blur on panels over the ocean (the idea itself); one
neutral shadow scale. Sun/moon are drawn icons, not emoji.

**Motion:** the ocean moves; the UI does not drift. Launch = iris
(`views/warp.js`, `CLOSE_MS` = `launch.ms`). Standby boxes turn slowly.

**Copy:** sentence case, calm, short. No "·" meta strings.
