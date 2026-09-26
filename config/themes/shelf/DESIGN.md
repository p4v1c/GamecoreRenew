# Shelf — design

**Idea:** your library as boxed games on a papered wall. Print, cardboard,
labels: things that exist on a real shelf.

**Type:** Archivo (variable width + weight, `fonts/archivo/`) for everything;
condensed widths for spines, normal for body. Monospace only for real code or
paths. Numbers: `tabular-nums`.

**Palette:** paper `#F4F2ED` / `#E7E4DC`, card `#F8F7F4`, ink `#17161A`,
board `#1C1B19`. Accent (brass) `#B8892B` for focus and the primary action.
System colours tint spines only.

**Shape:** 14 px cards, pills for chips, 18 px overlay; boxes and cartridges
keep physical proportions (no radius on box faces).

**Depth:** real-object shadows only: boxes cast on the shelf, the cartridge has
bevels. No blur, no glow. Gradients only where they model light on cardboard
or plastic.

**Motion:** the box turns (L2), restacks (R2), the cartridge goes in (launch,
`launch.ms`). Spines never move on their own.

**Copy:** printed-label feel in sentence case; publisher on the box back may
be uppercase like real print. No "·" meta, no em dashes as joiners.

**Legibility:** ink-3 `#66646D` is the faintest text (4.6:1 on paper-sink).
Anything read on the wall sits on a paper plate (`base.css`): bare text over
the pattern measured 1.8:1. Pad glyphs on paper: `--gc-pad-cross #2A55B8`,
`-circle #C0303C`, `-square #A8307E`, `-triangle #0F6E52`; the dark drawer
resets them. Settings: accent `#127A6D` (white on it 5.2:1), ink-3 at 0.66.
Box spines and back-of-box fine print are art, exempt from the 14px floor.
