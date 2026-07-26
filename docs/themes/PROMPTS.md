# Authoring a theme with two Claude sessions

The workflow this repo is set up for: one session designs, another builds. They
never talk to each other — the **design brief** is the contract between them.

```
you ──▶ Prompt A ──▶ design session ──▶ DESIGN-BRIEF.md ──▶ Prompt B ──▶ build session ──▶ config/themes/<id>/
         (fill in)     no codebase          the contract       (paste brief)   reads README.md
```

Two rules make this work:

1. **The design session never sees the codebase.** It gets the surface list and
   the constraints, nothing else. That keeps it cheap, repeatable, and immune to
   refactors.
2. **The build session never invents design.** If the brief is silent on
   something, it asks or uses the default theme's value — it does not improvise.

## Asset strategy — read before starting

The whole pipeline is text. A language model cannot draw a PNG, so:

- **Prefer SVG.** A Santa, a snowflake, a scanline frame, a bezel — all are SVG
  a design session can author directly. Vector also survives 1080p→4K.
- **Prefer CSS for motion.** Sprite-sheet walking, floating, parallax, twinkle:
  all reachable with `transform`/`opacity` keyframes, no JS, no raster.
- **Raster only when unavoidable** (photographic backgrounds). Then the brief
  lists the file, its exact dimensions and a text description, and you generate
  or source it separately. The build session references it and ships a
  placeholder.

---

# Prompt A — design session

Copy everything below the line. Fill every `[...]`. Delete the optional blocks
you do not want. The more you fill in, the less it improvises.

---

You are designing a **theme for GameCore**, a controller-only game launcher that
runs full-screen on a TV. I need a design brief precise enough that another
model can implement it without seeing your reasoning.

## The theme

- **Name:** `[THEME NAME]`
- **Concept in one sentence:** `[e.g. a cosy Christmas living room, seen through
  a frosted window]`
- **Mood / adjectives:** `[e.g. warm, nostalgic, slightly kitsch — never cold]`
- **Visual references:** `[e.g. 90s console box art / Studio Ghibli interiors /
  Amiga demoscene — or paste images]`
- **Era or platform homage, if any:** `[e.g. PS1 boot screen, CRT, Dreamcast]`

## What to redesign

Design only these surfaces — leave the rest to the default theme:

- [ ] `background` — full-screen layer behind everything
- [ ] `decor` — full-screen layer above everything, **non-interactive**
- [ ] `home` — the dashboard: system tiles, library stats, page dots
- [ ] `library` — game grid, search, per-game metadata panel
- [ ] `topbar` — clock, IP address, storage bar, controller battery
- [ ] `screensaver` — idle slideshow of game cover art
- [ ] `powerModal` — Scan mapping / Restart / Shutdown
- [ ] `gamepadModal` — the live controller diagram
- [ ] `settings` — the settings menu and its sub-pages (Wi-Fi, audio,
      Bluetooth, standby, themes, update). The working sub-pages can be reused
      as-is, so design the menu shell and say which pages you restyle.

`splash` and the on-screen keyboard are out of scope. Do not design them.

## Hard constraints — non-negotiable

- **1920×1080, viewed from a couch.** Minimum body text 14 px, minimum
  interactive label 16 px. Nothing thinner than 2 px.
- **Gamepad only. There is no mouse and no touch.** Every element the user can
  reach must have a visible focus state that is obvious across a room —
  describe it explicitly for every interactive element you design.
- **Never hide the focused item.** No decorative layer may cover it.
- **Motion budget:** `transform` and `opacity` only. Max `[8]` simultaneously
  animated elements. Everything must idle gracefully — this runs for hours.
- **All decor stops** while a game is running and during standby. Design for
  "does nothing" as a legitimate state.
- **Colour:** at least 4.5:1 contrast for text. Do not rely on colour alone to
  signal focus or state.
- **Assets are SVG or CSS** unless I say otherwise. See the asset strategy above.

## Data you are designing around

Real content, so the layouts must survive it:

- **Systems:** ~13, each with a name, a short platform badge, a logo, an accent
  colour, a game count and total playtime.
- **Games:** 0 to several hundred per system. Titles are long and messy
  (`Mario Party DS (Europe) (En,Fr,De,Es,It) (Rev 1)`). Cover art is portrait,
  varying aspect ratios, and **may be missing** — design that fallback.
- **Metadata:** description, year, genres, players, rating. Often absent.
- **Top bar:** clock, IP, storage used/total, up to 4 controllers with battery
  level and charging state.

## Optional — fill in what you care about

- **Palette direction:** `[e.g. deep green + candle gold, near-black base]`
- **Typography:** `[e.g. a heavy rounded display face for titles, system sans for
  body — name families or describe]`
- **Signature element:** `[e.g. a Santa that walks across the dashboard every
  ~40 s, behind the tiles]`
- **Sound:** `[e.g. sleigh bell on confirm, muted thud on back — or "keep
  default"]` (the user's sound setting always wins)
- **Seasonal window:** `[e.g. December 1 → January 6]`
- **What must NOT change:** `[e.g. keep the 4×2 grid, users know it]`

## Deliverable — produce exactly this

A single markdown document, `DESIGN-BRIEF.md`, with these sections and nothing
else. Be specific: exact values, not adjectives.

1. **Concept** — 3 sentences max.
2. **Tokens** — a table of every colour (hex), spacing step, radius, shadow,
   font family/size/weight you use. Named. The implementer uses these names.
3. **Per surface** — one section per surface I ticked. Each contains:
   - layout described spatially (what is where, at what size, aligned how);
   - the exact tokens used for every element;
   - **the focus state**, described precisely;
   - empty/missing states (no cover, no games, no controller);
   - an ASCII wireframe.
4. **Motion** — one table: element, trigger, property, duration, easing, loop.
   Include the idle state of every animated element.
5. **Assets** — one table: filename, format, exact dimensions, what it depicts,
   where it is used. For SVG you may inline the source directly.
6. **Open questions** — anything you had to guess. List it rather than deciding
   silently.

Do not write implementation code, do not reference React, do not mention file
structure. Describe the design.

---

# Prompt B — build session

Copy below the line, paste the brief, attach the spec.

---

Implement a **GameCore theme** from the design brief below.

## Required reading, in this order

1. `docs/themes/README.md` — the Theme SDK spec. It is the contract: manifest
   fields, surface names, the SDK object, the module shape, fallback rules,
   safety and performance rules.
2. `docs/architecture/05-frontend.md` — the gamepad event bus and its three
   invariants, the WebSocket events, the store, the `api` object.
3. The design brief, pasted at the end of this prompt.

## What to produce

A single directory, `config/themes/[THEME-ID]/`, containing:

- `theme.json` — manifest. `api: 1`. `provides` lists **exactly** the surfaces
  you implement, no more.
- `index.js` — native ES module, default-exports a function taking `sdk` and
  returning the surface components. **No JSX, no imports, no build step.** Use
  `sdk.ui.html` for markup and the hooks off `sdk.ui`.
- `theme.css` — your own styles, for your own markup.
- `assets/` — SVGs you author inline; for any raster asset the brief lists,
  create a clearly-named placeholder and list it in your summary.
- `preview.png` — if you cannot produce it, say so and describe the shot to
  take.

## Rules you must follow

- **Surface components take no props.** Everything comes from `sdk`.
- **Read data through `sdk.api`**, navigation through `sdk.nav`, input through
  `sdk.input`. Never fetch a URL directly, never touch `window` beyond
  `sdk.system.gamecore`.
- **Never bind `gp:guide`.** Never write `modalDepth` or `powerPending`.
- **`decor` is non-interactive** and must stop animating while a game runs or
  during standby.
- **Motion:** `transform` and `opacity` only, within the brief's budget.
- **Every interactive element needs the focus state the brief specifies**, and
  it must be reachable by D-pad in a sane order.
- **Handle the empty states** the brief describes — missing cover art, empty
  library, no controller connected.
- If the brief is silent on something, **use the default theme's value and list
  the assumption**. Do not invent design.

## Deliver with it

- A short summary: which surfaces you implemented, which you deliberately left
  to the default, and why.
- The list of assumptions you had to make.
- The list of assets that still need to be produced by hand.
- How to install and test it: where to drop the folder, how to select it, and
  what to look at on screen to verify each surface.

## The design brief

```
[PASTE DESIGN-BRIEF.md HERE]
```

---

# Iterating

- **Fixing the look?** Go back to the design session, amend `DESIGN-BRIEF.md`,
  re-run Prompt B with the updated brief. Do not patch the theme by hand — the
  brief stops being the source of truth the moment you do.
- **Fixing behaviour?** That is a build-session problem. Point it at the surface
  and the rule it broke.
- **Something impossible?** If the build session says the SDK cannot express the
  design, that is a gap in `README.md` §6 — record it there rather than working
  around it in one theme.
