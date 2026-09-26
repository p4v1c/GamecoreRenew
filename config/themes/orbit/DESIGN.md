# Orbit — design

**Idea:** a console home you orbit around: dark night-blue space, one bright
cool light for what is in focus. Closest reference: a PS5-style control centre.

**Type:** Red Hat Display (headings, hero titles, weights 300–700) and Red Hat
Text (everything else), shipped in `fonts/red-hat/`. No serif, no italics for
emphasis. Numbers: `tabular-nums`. Small labels ≥ 11 px, tracking ≤ 0.5 px.

**Palette:** background `#101722`, text `--white #f8f9ff`, secondary
`--muted #b8c2d3`, accent `--blue #82beff` (focus, primary action). Per-app
tiles may tint with their own brand colour (`--application-accent`), never the
chrome.

**Shape:** 4–6 px for small controls, 10–12 px for tiles, 25 px pills for dock
and session buttons.

**Depth:** glass (`backdrop-filter: blur`) on floating layers only: dock,
session menu, settings panel. Soft cool glow = focus; no glow on text.

**Motion:** launch/resume/suspend ceremony (`views/ceremony.js`,
`TRAVEL_MS` = `launch.ms`). Focus moves in ~150 ms ease-out. Nothing animates
on idle. `prefers-reduced-motion` gets the handover without movement.

**Copy:** sentence case, no eyebrow caps. Metadata rows use Orbit's drawn
`.dot` separator (a styled element, not a typed "·"), everywhere or nowhere.
App and console lines are plain facts (`lib/catalog.js`), never slogans.

**Legibility:** `css/legibility.css` (loaded last) floors every label at
14px and the pad legend at 16px. Pad glyphs on the near-white primary button
use the dark set (`--gc-pad-*`). Settings ink-3 `#8FA9C9`.
