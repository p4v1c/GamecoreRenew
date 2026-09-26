# Built-in UI — design

The look with no theme, and what safe mode falls back to.

**Idea:** a quiet dark console; the games carry the colour.

**Type:** Source Sans 3, shipped in `assets/fonts/source-sans-3/` and loaded by
`fonts.css` (`--gc-font-ui`). Monospace (`--gc-font-code`) only for paths,
hashes, logs. Numbers: `tabular-nums`. No tracked caps.

**Palette:** background `#09090f`, text `#fff`, then `--gc-ink-2` / `--gc-ink-3`.
Accent **ember** `#b8501b` (`--gc-accent`), soft `#f2a46a`, bright `#f8cfa9`.
Contrast: white on accent 5.0:1, accent on background 4.0:1, soft/bright text
≥ 9:1. Unknown system tiles are graphite `#5b6470`.

**Shape:** 8–12 px controls and cards, 20 px overlays.

**Depth:** overlay blur behind settings pages only; neutral shadows; no glow
except the controller diagram's pressed-button light.

**Icons:** `Glyph` in `components/ui` (one stroke style, 24 px grid). Toast and
HUD icons come from `electron/hud-tokens.json` `icons`. No emoji as icons.

**Copy:** sentence case, verbs on buttons, errors say what failed and what to
do. See `.claude/skills/gamecore-human-touch`.

**Legibility:** text inks are tokens in `tokens.css`: `--gc-ink`,
`--gc-ink-2` (0.78), `--gc-ink-3` (0.6, the faintest, ≥ 4.5:1 on every card).
No text under 14px. Brand colours as text are mixed 45 % into white.
Measured with `.claude/skills/gamecore-legibility`.
