# Skeleton theme

1. Copy this folder to `config/themes/<your-id>/` — the folder name **must**
   match `id` in `theme.json`.
2. List the surfaces you implement in `provides`.
3. Return one component per declared surface from `index.js`.
4. Settings → Themes → pick it.

No build step: this folder is what runs. Reload to see a change.

Stuck with a broken theme? Hold **L1 + R1 for 2 seconds** — the default theme
comes back from anywhere, even if nothing renders.

Reference: `docs/themes/README.md` · Prompts for AI-assisted authoring:
`docs/themes/PROMPTS.md`


## Controller HUD and notification tokens (API 7, optional)

Declare these on `:root`, never on your shell. The host reads computed values
for each notification and passes **only validated values** through the existing
battery/controller IPC. The native HUD is a separate document: it cannot read
your stylesheet. The default React toast view uses the same contract, including
the “Map it now” offer; that offer stays in-app and remains clickable.

| CSS token (`--gc-hud-…`) | Accepted value / purpose |
| --- | --- |
| `panel`, `border`, `text` | `#RRGGBB` or `#RRGGBBAA`: panel, outline, body text |
| `radius`, `blur` | Integer `0px` to `32px`; blur is a radius, not `blur(…)` |
| `font` | Unquoted comma-separated local font families, ASCII letters/digits/spaces/hyphens; starts with a letter |
| `connected`, `disconnected`, `warning` | Colors for controller status, title and icon background |
| `battery-25`, `battery-15`, `battery-10`, `battery-5` | Colors for the four battery severities |

Example (light panel):

```css
:root {
  --gc-hud-panel: #fffdf7;
  --gc-hud-border: #b4520f;
  --gc-hud-text: #173039;
  --gc-hud-radius: 22px;
  --gc-hud-blur: 18px;
  --gc-hud-font: Figtree, Outfit, sans-serif;
  --gc-hud-battery-5: #ae2834;
}
```

Values are capped at 160 characters. Gradients, URLs, quoted fonts, CSS functions
and arbitrary declarations are rejected. A `var()` is fine in the stylesheet
only when its **computed value** resolves to the allowed format. Each invalid or
missing token falls back independently; with no valid tokens the original native
440×100 / React appearance is retained (battery wording/severity still improves).
With valid tokens, the host uses 20px titles and 18px body text. The native window
is 560×240 at y=140, below the shipped headers; React reserves the same header
space. Reserve at most 140px for a custom theme header if using this HUD.

The default palette is for the historical dark panel. A light panel (relative
luminance > 0.45) automatically gets dark text/status colors unless overridden.
Use opaque panels for predictable contrast; verify every override at 4.5:1 or
better against its composited background. The shipped palettes have an AA check
in the Electron test bench. Alpha and backdrop blur cannot guarantee contrast
against arbitrary game content; a native transparent window cannot blur pixels
from another application's window using CSS alone.

Fonts are **local-only** in the native HUD. An installed named face is used;
otherwise Chromium takes the next installed/generic family. Renderer `@font-face`
fonts are not transferred, and the HUD never fetches fonts or other resources
(network and script blocked by CSP). Include a generic fallback. Do not rely on
a downloaded font to make a long message fit.

The host owns icons, English wording, severity selection from actual battery
level, routing, replacement/queue and timeouts (10 seconds, 30 seconds for an
action). This contract changes none of the backend threshold/rearm rules.
Custom `ToastsView` renderers still own their markup; use these tokens to match
the native HUD, and retain the supplied action and dismissal behavior.

Reproduce the before/after captures without the console display:

```bash
npm ci --prefix frontend
node electron/scripts/capture-hud.cjs /tmp/gamecore-hud-captures origin/main
```

Requires a local `chromium` executable. The harness uses headless Chromium with
empty DISPLAY/WAYLAND_DISPLAY and a temporary profile, evaluates the real HUD
code in the Electron VM bench, and renders the real React view. It makes no
backend call and loads no remote page. Open `index.html` in the output directory.
