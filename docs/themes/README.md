# Theme SDK — specification

> **Status: implemented.** Items 1–5 and 7 of §14 are in the tree; item 6
> (extracting the whole default UI behind `sdk.defaults`) is partial — the
> surfaces listed in §5 are exposed, the settings sub-pages are not.

A theme **replaces part or all of the UI**. It is not a skin: there is no CSS
layer to override in this app (see below), so a theme ships components, not
styles.

## Read this first

This document only covers what is **new**. Everything a theme consumes already
exists and is documented — do not duplicate it here:

| You need | Read |
|---|---|
| The gamepad event bus, its 3 invariants, the event list | [`../architecture/05-frontend.md`](../architecture/05-frontend.md#the-gamepad-event-bus--hooksusegamepadts) |
| The WebSocket event table | [`../architecture/05-frontend.md`](../architecture/05-frontend.md#the-websocket-event-table) |
| The store fields and actions | [`../architecture/05-frontend.md`](../architecture/05-frontend.md#store--storeindexts) |
| The `api` object and its groups | [`../architecture/05-frontend.md`](../architecture/05-frontend.md#apiindexts) |
| Every backend endpoint behind it | [`../architecture/03-backend-routers.md`](../architecture/03-backend-routers.md) |
| Why the UI must never become unnavigable | [`../architecture/09-gotchas.md`](../architecture/09-gotchas.md) |

## 1. Why themes ship components, not stylesheets

The frontend has **no CSS files**. 21 of its 22 components style themselves with
inline style objects — 131 hardcoded hex colours and 172 `rgba(255,255,255,…)`
values live inside the components. The only global CSS in the project is six
lines in `frontend/index.html` (reset, scrollbar, overlay-mode, one keyframe).

An external stylesheet cannot override an inline style. So a theme cannot
restyle the existing UI — it replaces the components that contain the styling.
Inside its own markup a theme is free to use classes and a stylesheet of its
own.

## 2. Buildless

A theme is a directory of plain files. No bundler, no `node_modules`, no
compile step — the dropped folder is exactly what runs, the same principle the
addons repo already follows.

The entry point is a native ES module. Themes author markup with a tagged
template instead of JSX, which needs no transform. The host supplies React, the
hooks and Framer Motion through the SDK object, so a theme never imports them
and there is never a second React in memory.

## 3. On disk

| Path | Contents |
|---|---|
| `config/themes/<id>/theme.json` | manifest |
| `config/themes/<id>/index.js` | ES module, entry point |
| `config/themes/<id>/views/`, `lib/` | one feature per file (§5) |
| `config/themes/<id>/theme.css` | the theme's own stylesheet |
| `config/themes/<id>/preview.png` | thumbnail for the settings page |
| `config/themes/<id>/assets/` | images, fonts, audio |
| `config/theme.json` | the active theme, written by the API. Per-device: not in git, not in the OTA archive |

They live under `config/` because that whole directory is excluded from the OTA
rsync — that is what protects `systems.json`, your mappings and the playtime DB.

`update/linux.sh` makes one exception, and only one: **a theme the box does not
have yet is installed; a theme it already has is never touched.** The unit is
the directory, so there is no merge and no half-updated theme built from two
releases. Edit a bundled theme and your edit survives every update.

The cost is that a fix to a bundled theme does not reach you on its own.
Updating one is a manual act: delete its folder and run the update again, or
copy the new version in. Your selection (`config/theme.json`) is untouched
either way — it is not in the archive.

## 4. Manifest — `theme.json`

| Field | Type | Required | Meaning |
|---|---|---|---|
| `id` | string | yes | must equal the directory name |
| `name` | string | yes | shown in Settings → Themes |
| `version` | string | yes | the theme's own version |
| `api` | integer | yes | SDK major version targeted — `1` |
| `author` | string | no | |
| `description` | string | no | one line, shown under the name |
| `entry` | string | no | defaults to `index.js` |
| `preview` | string | no | defaults to `preview.png` |
| `styles` | string | no | defaults to `theme.css`; injected automatically when present |
| `provides` | string[] | yes | must list **every** surface: `["splash", "shell"]` (§5) |
| `schedule` | object | no | `{ "from": "MM-DD", "to": "MM-DD" }` — seasonal auto-activation |

A folder whose name starts with `_` is a **template, not a theme**:
`config/themes/_skeleton` is there to be copied, and never appears in
Settings → Themes. Name your own theme without the underscore.

`provides` is both declaration and gate: a surface must be listed here *and*
exported by the module. Miss either and the theme does not load at all — it is
not selectable, and if it was already active the default frontend runs whole.

## 5. The two surfaces

A theme provides **both** of these, always:

| Surface | What it is |
|---|---|
| `splash` | the boot animation |
| `shell` | the whole frontend body |

| Kept by the kernel, always |
|---|
| input bus, WebSocket, `gp:guide`, error boundaries, L1+R1 rescue, the *fact* that a splash runs |

Picking a theme swaps the frontend, so a theme dresses all of it or none of it.
There is no per-surface fallback: half a theme — a beach dashboard behind the
stock purple splash — is the exact look this rule exists to prevent.

A themed splash draws what it likes but does not decide when booting ends: it
must call `onDone`, and the host moves on regardless after 20s.

### What is mandatory, and what is not

The all-or-nothing rule is about **surfaces**, not features. Read it as:

| | Mandatory? |
|---|---|
| `splash` and `shell` — declared in `provides` **and** exported by the module | **yes.** Miss either and the theme does not load at all |
| Which parts of the shell you override (`homeView`, `library`, `topbar`, the modals…) | **no** |

So a theme that ships a splash and a shell, and overrides only the dashboard, is
a perfectly valid theme: everything it did not rewrite is the default UI,
rendered *inside the theme's own shell*. You are never mixing two frontends —
there is one tree, and you decide how much of it you author.

What that buys you is the failure mode: there is no half-loaded theme. Either
your theme runs, or the default one runs whole, and Settings → Themes tells you
which and why.

### Composing instead of rewriting

`sdk.defaults.Shell` **is** the default frontend, and it takes parts:

| Part | Replaces |
|---|---|
| `background` | a full-screen layer the shell places behind everything |
| `decor` | a full-screen layer above everything, non-interactive |
| `topbar` | clock, IP, storage, controller battery |
| `homeView` | the dashboard's **markup** (see below) |
| `libraryView` | the game list, detail panel and metadata — **markup only**, like `homeView` |
| `screensaver` | the standby slideshow |
| `settings` | the settings screen |
| `powerView` | the power menu's markup — the two-press confirmation, the pending lock and the failsafe stay with the host |
| `gamepadView` | the controller screen's markup — the live pad diagram arrives ready-made and bound |

So "add snow to the dashboard" is a shell that renders `sdk.defaults.Shell` with
a `decor`, and "replace everything" is a shell that renders its own tree. Same
mechanism, effort proportional to ambition.

### Views, not screens

`homeView` and `libraryView` are those screens' *markup*, not the screens.
Paging, focus, sorting, search, launching and the d-pad bindings stay in the
host and are handed to the view as props — see
`frontend/src/components/HomeScreen/types.ts` and `LibraryScreen/types.ts`.
The library view is even given the cover-art and metadata components ready-made,
so a theme never reimplements the missing-art or 404 paths.

That seam is deliberate. When themes reimplemented navigation they drifted from
the default in ways nobody notices until a TV is involved — running off the
right of a row stopped dead instead of turning the page. **A view that cannot
navigate cannot navigate differently.** The rule the whole system rests on:
a theme changes the UI, never the behaviour.

### One feature per file

The default frontend is one file per feature (`WifiPage.tsx`, `PowerModal.tsx`,
`GamepadModal.tsx`…) and a theme should be too — see `config/themes/summer`:

```
summer/
  index.js          the wiring, and nothing else
  theme.json  theme.css  preview.png  README.md
  views/            splash.js  home.js  library.js  topbar.js
                    settings.js  themes.js  background.js  decor.js
  lib/              ocean.js  idle.js
```

The directory listing doubles as the check-list of what you still have to dress.

It splits the way the frontend does — what a screen looks like, and what it
needs to look like that — but it is flatter, and deliberately. There is no
`components/HomeScreen/` because a theme supplies only the *view* of a screen:
that folder would hold exactly one file. And there is no `hooks/`, `lib/`,
`store/` or `api/` layer at all — a quarter of the frontend's tree — because a
theme gets all of it from the SDK.

Subfolders work (they are served as-is, and relative imports resolve normally),
so a larger theme can nest further. Just remember there is no build step: the
path you write is the path the browser fetches.

### Why one surface and not nine

The first version substituted nine components inside the host's own layout, so
the theme and the default were **interleaved in one tree**. Every bug came from
that:

- a theme's background painted over the screens it had *not* replaced, because
  stacking was left to the theme's CSS;
- a themed modal never joined the modal stack, so the dashboard kept receiving
  the d-pad behind it and the cursor moved in two places at once;
- default settings pages were torn out of the `Overlay` they were written for
  and dropped into the theme's own box, which broke their layout.

One tree, one owner. The shell owns the stacking (a theme never writes a
`z-index`), and the shell registers whatever it shows as a modal — for default
and themed alike, so forgetting is not possible.

## 5b. Asking for a different dashboard grid

The dashboard is `cols × rows` cards per page — 4 × 2 unless the manifest says
otherwise:

```json
{ "id": "shelf", "home": { "cols": 8, "rows": 1 } }
{ "id": "shelf", "home": { "rows": 1, "paged": false } }
```

`"paged": false` puts the whole list on one page: no L1/R1, no boundary to walk
into, and `cols` is then derived from how many items there are rather than
declared. A number could not do that job — it would be right until the owner
installs one more system.

Absent, it is the host's grid, which is what every theme written before this
said by saying nothing. Naming only one of the two is fine; the other keeps the
host's value.

**Why this is negotiable when so little else is.** The grid is layout, and
layout is the theme's side of the line. A theme that wants one long row of big
icons cannot fake it: `HomeScreen.navigate()` walks the grid and wraps at the
row end, so a rail drawn as one continuous line would silently skip half its
contents whenever `rows > 1` — and a row that lies about where the cursor goes
is worse than a visible second row. What stays the host's is everything the
grid is walked *by*: paging, focus, wrap, the bindings.

`cols` and `rows` must be integers 1–16. Outside that they are dropped with a
warning and the host's value stands: a theme is code its owner installed, but 0
divides by zero in `pageCount` and 400 asks the host to render every system on
one page. Neither is a look; both are a broken screen. A bad value does not
take a good one down with it — `{"cols": 8, "rows": 0}` yields `cols` 8 and the
host's rows.

> A page holds `cols × rows`, so `8 × 1` keeps the 8-per-page of the default
> `4 × 2`: one row of eight instead of two rows of four, and L1/R1 behave
> exactly as before.

## 5c. Check it loads before you ship it

```bash
node scripts/check-theme.mjs config/themes/<id>
```

It imports every module the way the browser will. `node --check` is **not**
enough, and the gap is not theoretical — it has bitten twice:

```js
html`
  <!-- `key` on this node restarts the animation -->
  <div class="hold" key=${id}>
`
```

A backtick inside an HTML comment inside an `html``` template closes the
template early. The file still parses, so `node --check` passes; the module
throws `Unexpected identifier` the moment it is loaded, and the theme is
disabled at runtime with no clue as to which line.

**So: no backticks inside HTML comments.** Write `key` instead of `` `key` ``.
The same goes for `${...}`, which is interpolation wherever it appears —
comment or not.

## 6. What a theme can do

The whole surface, in one table. Everything marked **no** is a deliberate line,
not a gap waiting to be filled — the reasons are in §11.

| | |
|---|---|
| **Redraw every screen** | yes — dashboard, library, top bar, settings menu, theme picker, power menu, controller screen, screensaver, boot animation |
| **Paint behind and in front** | yes — `background` and `decor` are full-screen layers the shell places for you |
| **Ship a stylesheet** | yes, and it is the only place in GameCore where CSS works: the default UI styles itself inline |
| **Restyle the screens it did *not* rewrite** | yes — the Wi-Fi, Bluetooth, audio and update pages read `--gc-overlay-*` and `--gc-accent*` (§7) |
| **Read the box's real data** | yes — systems, games, playtime, metadata, cover art, storage, network, controllers and their battery, through `sdk.api` |
| **Draw something other than the jacket** | yes — 3D box, clear logo, gameplay screenshot, title screen, ready-made mix, trailer, 54 types in all (§7.1) |
| **React to what happens** | yes — `sdk.system.onWsEvent` for standby, ROM uploads, controller connect/disconnect, battery, theme changes |
| **Read input** | yes — `sdk.input.onGp` for every pad event, `useGamepadState()` for the raw 60 fps state (that is how a live pad diagram works) |
| **Know where the player is** | yes — `sdk.nav.use()` inside a component, `sdk.nav.get()` in a handler |
| **Move the player** | yes — `goHome`, `goLibrary`, `setGridFocus`, `setGridPage` |
| **Make sound** | yes — `sdk.system.getAudioContext()` for its own synthesis (Summer's surf), `sdk.system.playSound()` for the host's set, `sdk.system.sound` to respect the player's setting |
| **Ship assets** | yes — anything in the theme folder, resolved with `sdk.system.asset('…')` |
| **Change the *five* UI sounds** | **no** — `move`, `confirm`, `back`, `launch`, `startup` are the host's, fired centrally by the input bus. A theme can add sounds, not replace those |
| **Change how a screen behaves** | **no** — paging, focus, sorting, search, launching, the shutdown confirmation. It supplies the markup, the host keeps the decisions |
| **Write a `z-index`** | **no** — the shell owns stacking. This is what let the first version paint over screens it had not replaced |
| **Skip the boot animation** | **no** — a theme draws its own, but `onDone` is the host's and a 20s watchdog sits behind it |
| **Take `gp:guide`** | **no** — the double press that kills a running game is reserved |
| **Take the rescue combo** | **no** — L1 + R1 held 2s forces the default theme, from anywhere |
| **Remove itself from the picker** | **no** — Settings → Themes is always reachable, so a theme can always be left |
| **Reach the network or the DOM outside its tree** | **no** — see §11 |

## 7. The SDK

The module receives **one argument**. It imports nothing from the host, so
there is no import map to maintain and only one React instance exists.

| Namespace | Contents | Detail |
|---|---|---|
| `sdk.ui` | `html` (tagged template), `React`, `useState`, `useEffect`, `useRef`, `useMemo`, `useCallback`, `motion`, `AnimatePresence` | Framer Motion is already bundled by the host |
| `sdk.api` | `systems`, `games`, `metadata`, `media`, `playtime`, `sysinfo`, `standby`, `update`, `wifi`, `audio`, `bluetooth` | [full signatures](../architecture/05-frontend.md#apiindexts) |
| `sdk.nav` | `use(selector)` for a reactive read inside a component, `get()` for a snapshot in a handler, plus `goHome`, `goLibrary`, `setGridFocus`, `setGridPage`, `setSelectedGameIdx`, `openModal`, `closeModal` | [store reference](../architecture/05-frontend.md#store--storeindexts) |
| `sdk.input` | `onGp(event, handler)`, `useGamepadState()`, `GP_BTN`, `events` | [event bus](../architecture/05-frontend.md#the-gamepad-event-bus--hooksusegamepadts) |
| `sdk.system` | `onWsEvent`, `playSound`, `getAudioContext`, `sound` (read-only `enabled` / `volume`), `gamecore`, `asset(path)` | `asset()` resolves a path inside the theme folder |
| `sdk.themes` | `list()`, `select(id \| null)` | so a theme can dress its own theme picker. `select()` is the host's: it clears safe mode, resets the crash count and reloads the frontend |
| `sdk.defaults` | `Shell` (the default frontend, takes parts), every screen, `DefaultSettingsPages` (wifi, audio, bluetooth, standby, themes, update, desktop), `SettingsOverlay`, `DefaultKeyboard`, `launchApp` | compose instead of rewrite. The pages already carry their own overlay — render them bare; `SettingsOverlay` is only there if you write a page of your own |

`modalDepth` and `powerPending` are readable through `get()` but there is no
setter: they are the core's focus and shutdown locks.

`sdk.input.onGp` silently refuses `gp:guide` — the core owns it, because a
double press there kills a running game.

`sdk.defaults` is what makes "add a Santa on top of the existing dashboard" as
cheap as "rewrite everything" — override `homeView`, render the default inside it,
add your layer.

### 7.1 Artwork other than the jacket

The default library draws a flat box front, because that is what every game has.
A theme is not tied to it: a game carries up to 54 media types, and any of them
can be the thing your library is built on.

Two ways in, and the first one covers most themes:

```js
// The Cover component you already receive takes an optional type.
html`<${Cover} filename=${game.filename} systemId=${systemId}
               color=${color} type="box-3d" />`
```

Leave `type` out and it draws the jacket from `/api/covers` exactly as before —
same URL, same cache, same fallback. Pass one and it draws that instead, falling
back to the jacket when this particular game does not have it. That fallback is
the point: the 3D box is a rarer artwork than the flat scan, and a theme built
on it would otherwise show a hole for every game nobody photographed in
perspective.

```js
// Or ask what a game actually has, and decide.
const index = await sdk.api.media.list(systemId, game.filename)
// index.media = { "box-3d": { category: "box", kind: "image",
//                             region: "wor", cached: true }, … }
const hero = index.media['mix-rbv2'] ? 'mix-rbv2' : 'box-front'
const src  = sdk.api.media.url(systemId, game.filename, hero)
```

The types worth knowing, by `category`:

| Category | Useful slugs | What it gives you |
|---|---|---|
| `box` | `box-front` `box-back` `box-3d` `box-spine` | the jacket, and **the box in perspective** — transparent background, irregular ratio, so do not force it into a fixed-ratio frame |
| `logo` | `clear-logo` `clear-logo-hd` | the game's logo cut out on transparency — what a title over a background wants |
| `screenshot` | `screenshot-gameplay` `screenshot-game-title` | in-game capture, title screen |
| `mix` | `mix-rbv2` `mix-rbv1` | **ready-made compositions** (box + screenshot + logo) built for TV grids. Often the best single image to show, and the cheapest way to look designed |
| `video` | `video-normalized` `video` | trailer or gameplay clip, ~15 MB `.mp4`. `video-normalized` is the better default: consistent format and loudness |
| `artwork` | `fanart-background` `square` | wallpapers, square thumbnail |
| `marquee`, `icon`, `bezel`, `document`, `theme`, `pinball` | | banners, list pictograms, 4:3 side fillers, the `.pdf` manual, Hyperspin themes, virtual pinball art |

Three things to design around:

- **Nothing exists for every game.** `available: false` on the index means the
  box has no ScreenScraper account and no offline index — not that the game is
  unknown. Draw the jacket and move on; do not show an error.
- **The first display of a type costs a round trip.** Media are fetched on
  demand, so `cached: false` means one download. On a slow link, prefer a type
  the index reports as cached for anything that has to appear instantly, and
  let the fancy one arrive after.
- **A video is not a cover.** 15 MB per game, and the library selection moves
  with the d-pad. Debounce it the way the host debounces `detailGame` (150 ms),
  or a fast scroll queues a download per step.

## 8. Module contract

The entry point default-exports a function taking `sdk` and returning
`{ splash, shell }` — both, always. Neither takes props beyond the ones listed
here: everything else comes from the SDK.

```js
export default (sdk) => {
  const { html, useEffect } = sdk.ui

  const Splash = ({ onDone }) => {
    useEffect(() => { const t = setTimeout(onDone, 1200); return () => clearTimeout(t) }, [onDone])
    return html`<div class="t-splash">GAMECORE</div>`
  }

  const Decor = () => html`<img src=${sdk.system.asset('santa.png')} class="t-santa" />`

  return { splash: Splash, shell: () => html`<${sdk.defaults.Shell} decor=${Decor} />` }
}
```

A theme may ship a stylesheet for its own markup and load it from its folder.

> **Reusing a default settings page?** Render it **bare** — each one already is
> a full-screen overlay, so putting it in your own panel nests a `position:
> fixed` layer inside a flex box and shatters its layout. To make it match your
> theme, set these in your stylesheet instead:
>
> ```css
> :root {
>   --gc-overlay-scrim:  rgba(6, 18, 26, 0.55);   /* the full-screen backdrop */
>   --gc-overlay-blur:   blur(18px) saturate(115%);
>   --gc-overlay-panel:  rgba(12, 26, 33, 0.82);  /* the card itself */
>   --gc-overlay-border: rgba(255, 253, 247, 0.14);
>   --gc-overlay-radius: 22px;
> }
> ```
>
> The defaults are the dark UI's, including a near-opaque scrim — leave them
> alone on a light or photographic background and every settings page goes
> black.
>
> The same applies to the accent. The host's settings widgets — focus rings,
> toggles, sliders, signal bars, the on-screen keyboard, the theme picker's
> marker — are drawn with inline styles and read three more variables:
>
> ```css
> :root {
>   --gc-accent:        #F0761E;   /* focus, fills */
>   --gc-accent-soft:   #FE9D7C;   /* secondary text */
>   --gc-accent-bright: #FFFDF7;   /* figures, emphasis */
> }
> ```
>
> Set them or your settings screen stays the default purple on your own
> background.

## 9. Fallback and composition

| Situation | Result |
|---|---|
| A surface missing from `provides`, or from the module | the theme does not load; the default frontend runs whole, reason shown in Settings → Themes |
| The shell throws while rendering | the default frontend, and the crash is recorded |
| A themed splash throws, or never calls `onDone` | the default splash, or the host moves on after 20s |
| Module fails to load | theme rejected, default frontend, reason surfaced |

Note what is *not* in this table: a per-screen fallback. Completeness is checked
once, at load. Either the theme runs or the default does.

## 10. Compatibility

- `api` major greater than the host's → theme is listed but **not selectable**,
  with the reason shown.
- `api` major lower → loaded while the host still supports that version.
- Adding a surface or an SDK key does **not** bump the major. Removing one does.
- Theme files are never cached. The entry module's URL is timestamped, and
  `/themes` is served with `Cache-Control: no-store` — the entry's own relative
  imports and its stylesheet resolve without that query, so a header is the only
  thing that covers them. Electron's HTTP cache has hidden UI changes before —
  see the OTA section of [`09-gotchas.md`](../architecture/09-gotchas.md).

## 11. Safety

The project had no error boundary at all before this: a React throw produced a
white screen. With themes running arbitrary JS on a TV with no pointer, that was
the failure mode to close first. What is in place:

1. **A boundary around the shell** — the theme renders one tree, so one throw
   inside it hands the whole frontend back to the default. There is no
   half-running theme to reason about, which is the point: the first design had
   a boundary per surface and left you with a UI that was partly one theme and
   partly another. The splash has its own boundary, for the same reason.
2. **A global boundary** — anything that escapes lands on a readable message
   naming the rescue combo, never a white screen.
3. **Crash counting with an amnesty** — two crashes and the theme is refused at
   load. The counter is cleared only after the theme has stayed up 20 s without
   a surface crashing; clearing it merely because the *module* loaded meant a
   theme that broke on every boot never reached the limit.
4. **Persisted safe mode** — the reason is shown in Settings → Themes, and
   picking the theme again is what retries it.
5. **A rescue input** — hold **L1 + R1 for 2 s** anywhere to force the default
   theme, even if nothing renders.

Enforced by the core, not by convention:

- a theme cannot capture `gp:guide` (double-press kills a running game);
- it cannot write `modalDepth` or `powerPending`;
- the `decor` layer is `pointer-events: none`;
- a theme cannot remove the focus indicator.

A theme has access to `sdk.api`, so it can launch games and power off the box.
On your own machine that is "don't install junk". If themes are ever shared
between users, it becomes a real threat model.

## 12. Performance

The box also runs emulators, on a TV, at 1080p.

- Decor stops while a game is running — the UI already suppresses everything
  during a session.
- Decor stops during standby and the screensaver.
- Animate `transform` and `opacity` only.
- Cap the number of simultaneously animated elements.

## 13. Sounds

A theme can **add** sound. It cannot **replace** the five UI sounds.

`move`, `confirm`, `back`, `launch` and `startup` are synthesized in
`frontend/src/lib/sounds.ts` and fired centrally by the input bus — before any
screen is involved — so there is no hook for a theme to take them over. What a
theme gets instead:

- `sdk.system.playSound(name)` — trigger one of the host's, on its own terms;
- `sdk.system.getAudioContext()` — the shared context, to synthesize whatever
  it likes. `config/themes/summer/lib/ambience.js` is the worked example: surf
  from filtered noise, no audio file, no loop seam.

Two rules, whichever route you take:

- **The player's sound setting always wins.** `playSound` refuses when sound is
  off and scales to their volume. A loop *you* start does neither, so read
  `sdk.system.sound` (`enabled`, `volume`) and follow it — including while it
  changes, which it can, from Settings → Audio.
- **Stop when nobody is listening.** A game running or the box asleep means
  silence; `useIdle` in Summer shows the pattern.

The default sounds are synthesized, not files. A theme shipping audio assets is
a new case, not the existing path.

## 14. Editing a theme

Theme files are served with `Cache-Control: no-store`, so **save and reload** is
the whole loop — no version bump, no cache clearing. (The loader also
timestamps the entry module and the stylesheet, but only the backend header
covers the entry's own relative imports.)

If a reload seems to change nothing, the theme almost certainly failed to load
rather than loading unchanged: open Settings → Themes, where an unusable theme
is listed as not selectable with the reason next to it.

## 15. Authoring loop

1. Copy the skeleton theme.
2. Edit `theme.json`, write one or more surfaces.
3. Drop the folder on the box — drag & drop through the rom-manager addon from
   any browser on the LAN, or over SSH.
4. Settings → Themes → select.
5. Iterate: reload, there is nothing to compile.

## 16. Implementation order

| # | Work | Size |
|---|---|---|
| 1 | Error boundaries + persisted safe mode + rescue input | small, **blocking** |
| 2 | Assemble the `sdk` object from existing modules | small |
| 3 | Backend: list themes, serve their files, persist the active one | small |
| 4 | Theme loader: dynamic import, surface resolution, fallback | medium |
| 5 | Settings → Themes page (follows `StandbyPage`, gamepad nav is free) | small |
| 6 | Extract the default UI into the components exposed as `sdk.defaults` | medium |
| 7 | Skeleton theme + [`PROMPTS.md`](PROMPTS.md) workflow | small |

Step 6 validates the spec: if the default UI cannot be expressed through this
SDK, the SDK is incomplete.
