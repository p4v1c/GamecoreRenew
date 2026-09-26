# Controller and battery notifications, themed — delivery report (2026-09-23)

Branch `feat/themed-controller-hud`, from `origin/main` at `8502d7b`.

## What changed

- The native HUD reads the active theme's tokens, sent by the renderer with
  each notification. Electron whitelists them before building its own HTML.
  Shared contract: `electron/hud-tokens.json` (names, allowed formats,
  fallback palettes, battery messages), also bundled in the frontend and the
  Electron package. No theme HTML/JS/CSS reaches the HUD; text is escaped and
  a CSP blocks scripts and network loads.
- Orbit: night-blue panel; Shelf: light paper; Summer: cream. Themed titles
  20px, text 18px; themed window 560×240 at y=140 (clears the shipped themes'
  headers). Transparent, unfocusable, click-through, always on top. Legacy
  fallback stays 440×100 at y=66.
- The default React toast uses the same tokens. "Not recognised / Map it now"
  stays in-app with its action and 30 s duration; others stay 10 s. The HUD
  still replaces the previous notification; React queue and routing unchanged.

## Battery

`Controller N battery at X%`, then:

| Level | Text |
| --- | --- |
| ≤ 25 % | Keep a charger nearby. |
| ≤ 15 % | Battery is running low. |
| ≤ 10 % | Battery very low — connect a charger. |
| ≤ 5 % | Battery critical — charge it now. |

Chosen on the real level (it may skip thresholds). Backend thresholds
`(25, 15, 10, 5)`, re-arming and one alert per crossing unchanged (docstring
fixed only). Non-numeric, non-finite or out-of-range levels are rejected.
Theme versions bumped for OTA delivery: Orbit 3.7.3, Shelf 3.9.8, Summer
3.2.3, skeleton 0.3.1; API versions unchanged (Orbit 7, Shelf/Summer 4).

## Token contract

Documented in [the skeleton README](../../config/themes/_skeleton/README.md).
On `:root`, prefix `--gc-hud-`:

| Suffixes | Format |
| --- | --- |
| panel, border, text | hex colour, 6 or 8 digits |
| radius, blur | integer 0–32px |
| font | local family list, unquoted, with a generic fallback |
| connected, disconnected, warning | controller state colours |
| battery-25, battery-15, battery-10, battery-5 | the four severities |

Invalid values are ignored; no valid token = legacy style. A light panel
without an explicit palette gets dark readable colours. Shipped theme colours
tested at ≥ 4.5:1 (measured: Orbit 5.60, Shelf 6.15, Summer 6.03). Fonts are
local only; no web font in the HUD.

## Evidence

- Captures: headless Chromium, temp profile, real `main.js` in the VM bench;
  tokens read by `getComputedStyle` on the real stylesheets. 72 PNG (64 native
  before/after × 4 looks, 4 comparison boards, 4 React). No case overflows
  the window; the 4 unthemed controller cases are pixel-identical before/after.
  Reproduce: `node electron/scripts/capture-hud.cjs <outdir> 8502d7b`.
- New tests: hostile tokens (`red;}</style><script>`, `url(javascript:…)`,
  quoted fonts), fallback, text escaping, four severities, light colours,
  theme change between two IPC sends, window properties, mapping offer kept.
- Suite at delivery: ruff, shellcheck, check-catalog (17 packs),
  gen-catalog --check OK; pytest 2035 passed; vitest 544 passed; build OK;
  electron 33 passed.

## Left as is (other battery/controller displays)

| Display | Finding |
| --- | --- |
| `TopBar/index.tsx` `ControllerBattery` | hardcoded green/yellow/red, thresholds >60 / >20, not the four severities |
| Orbit `views/topbar.js` | no battery/player badges |
| Shelf / Summer `views/topbar.js` | own 4-segment gauges, already themed |
| `GamepadModal.tsx`, `DefaultGamepadView.tsx` | reuse `ControllerBattery` fixed colours |
| Orbit `views/controller.js`, Shelf/Summer `views/gamepad.js` | own renderings, already themed |
| `ControllerArt.tsx`, `MappingWizard.tsx` | fixed colours; not notifications |

## To check on the box

Readability at 3 m, stacking over a running emulator, X11/Wayland compositor
rendering. CSS blur cannot blur another native window. A font only provided
via `@font-face` in the renderer does not reach the HUD. Third-party themes
must reserve the header space and check their own contrast.
