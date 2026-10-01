# Jelly — design

**Idea.** A party-game playground: soft jelly tiles on a cyan floor, keys that
press down, one burst of confetti at boot. Shapes and textures only, no
character. Approved mockup: "GameCore · Jelly".

**Type.** Red Hat Display only (self-hosted, OFL), 500–900. Sizes are
multiples of `--px` (1 px of the 1920×1080 design): 15 / 17 / 20 / 26 / 40 / 56.
Hints and legends 16 px minimum. Tabular figures on counts and the clock.

**Palette** (`css/base.css`).
- Floor `--jl-cyan #80deed`, paper `--jl-paper #fffdf7`, paper 2 `#f3eefb`.
- Ink `--jl-ink #30204e`, ink 2 `#4f3f68` (5.6:1 on cyan), ink 3 `#64567a` (paper only).
- Accent: `--jl-yellow #ffe66b`, for focus and the primary action, nothing else.
- Brand fills: purple `#5931a0` (hero, rail), pink `#f950a3` (decoration),
  `--jl-pink-ink #b51f66` when pink is text. The eight cover colours live in
  `lib/catalog.js`, one per console family.
- Focus: yellow ring outlined in ink (`--jl-focus`), plus a lift.

**Shape.** Radius by role: card and hero 24, dialog 32, chip and button 14–16,
key 11, badge 9. Hero, pill and count tilt a few degrees; controls never do.

**Depth.** One shadow kind, the jelly step: a hard offset in a darker shade of
the surface (`0 6px 0`), never a glow. Blur only on the scrim under a dialog.
Covers and console photos get a soft drop shadow, as objects.

**Motion.** Focus lifts in 160 ms with a slight overshoot. Pages arrive in
260 ms, dialogs pop in 320 ms. The floor drifts, karts lap, the hero jacket
wobbles; all stop while a game runs or in standby, and reduced motion stops
everything but the focus ring.

**Sound.** Bubbles and wobbly boings (`lib/sounds.js`): a pop on move, two
bouncy plucks on confirm, a squish on back, a wobbly slide on launch.
Synthesized, played into the host's volume.

**Voice.** English, second person, light in titles ("Your turn.", "Find a
game.", settings taglines). Messages, errors and buttons stay plain: a verb,
no exclamation, no arrows, commas not "·".
Eyebrows are small caps in tracked capitals: the mockup's one typographic
signature, kept on purpose and nowhere else.
