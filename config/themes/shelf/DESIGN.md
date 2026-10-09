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
`launch.ms`). Moving along the shelf always puts the box back and takes the
next one out; pressing faster makes it faster, never skips it. Spines never
move on their own.

**Sound:** cardboard, wood, plastic (`lib/sounds.js`): a fingertip tap on
move, marimba notes on confirm and back, the cartridge sliding and clunking in
on launch. In the library the d-pad handles boxes, so it sounds like it: a
slide and a knock when a box comes out, the air and the card's flap when L2
turns it over, three boxes knocked square on R2. Synthesized, played into the
host's volume.

**Copy:** printed-label feel in sentence case; publisher on the box back may
be uppercase like real print. No "·" meta, no em dashes as joiners — with one
approved exception: the home's eyebrow (`NINTENDO · 2011 · HANDHELD`), set
uppercase and tracked like a product sheet.

**Home (Studio):** the paper wall, the console's photo on the right, the copy
top left in Archivo (name 100px / 850, -0.045em), stats on white 14px cards,
an ink pill with a ring of the console's colour for ✕, a white pill for △.
The bottom 330px fade to white (#fbfaf7 → #fff), the studio sweep; consoles
stand on it with a contact shadow and a faint reflection, apps as white 124px
tiles (radius 32). Focus: larger, name bold ink, a 44×4 bar in the console's
colour. Never a full-screen colour wash.

**Legibility:** ink-3 `#66646D` is the faintest text (4.6:1 on paper-sink).
Anything read on the wall sits on a paper plate (`base.css`): bare text over
the pattern measured 1.8:1. Pad glyphs on paper: `--gc-pad-cross #2A55B8`,
`-circle #C0303C`, `-square #A8307E`, `-triangle #0F6E52`; the dark drawer
resets them. Settings: accent `#127A6D` (white on it 5.2:1), ink-3 at 0.66.
Box spines and back-of-box fine print are art, exempt from the 14px floor.

**Power / controller:** power is label strips pinned on the wall (no card):
inked title strip, focus = brass tab and the strip slides 14 px; asking again
uses danger ink `#9C1F28` (7.4:1 on card) with words, never colour alone.
The controller screen is an ivory paper panel with a 2 px ruled head: warm
line art, brass `--pd-lit #c5a45a` for what is pressed, `--pd-pos #96732d`
for legend symbols.
