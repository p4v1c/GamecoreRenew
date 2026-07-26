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
| `config/themes/<id>/preview.png` | thumbnail for the settings page |
| `config/themes/<id>/assets/` | images, fonts, audio |
| `config/theme.json` | the active theme, written by the API |

`config/` is already excluded from the OTA rsync, so themes survive updates
with no change to `update/linux.sh`. That is why they live there and not under
`assets/`.

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
| `provides` | string[] | yes | surfaces this theme overrides (§5) |
| `schedule` | object | no | `{ "from": "MM-DD", "to": "MM-DD" }` — seasonal auto-activation |

`provides` is both declaration and gate: a surface exported by the module but
absent from `provides` is ignored. That stops a theme from silently taking over
a screen its author never considered.

## 5. The shell

A theme provides **one** thing: the shell — the whole frontend body.

| Provided | Owner |
|---|---|
| `shell` | the theme (or the default one) |
| splash, input bus, WebSocket, `gp:guide`, error boundaries, L1+R1 rescue | the kernel, always |

Picking a theme swaps the frontend. Anything the theme does not ship — starting
with the splash — stays with the kernel, so a theme cannot remove the boot
animation or the way out of itself.

### Composing instead of rewriting

`sdk.defaults.Shell` **is** the default frontend, and it takes parts:

| Part | Replaces |
|---|---|
| `background` | a full-screen layer the shell places behind everything |
| `decor` | a full-screen layer above everything, non-interactive |
| `topbar` | clock, IP, storage, controller battery |
| `home` | the dashboard |
| `library` | the game grid, search and metadata panel |
| `screensaver` | the standby slideshow |
| `settings` | the settings screen |
| `powerModal`, `gamepadModal` | the modals |

So "add snow to the dashboard" is a shell that renders `sdk.defaults.Shell` with
a `decor`, and "replace everything" is a shell that renders its own tree. Same
mechanism, effort proportional to ambition.

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

## 6. The SDK

The module receives **one argument**. It imports nothing from the host, so
there is no import map to maintain and only one React instance exists.

| Namespace | Contents | Detail |
|---|---|---|
| `sdk.ui` | `html` (tagged template), `React`, `useState`, `useEffect`, `useRef`, `useMemo`, `useCallback`, `motion`, `AnimatePresence` | Framer Motion is already bundled by the host |
| `sdk.api` | `systems`, `games`, `metadata`, `playtime`, `sysinfo`, `standby`, `update`, `wifi`, `audio`, `bluetooth` | [full signatures](../architecture/05-frontend.md#apiindexts) |
| `sdk.nav` | `use(selector)` for a reactive read inside a component, `get()` for a snapshot in a handler, plus `goHome`, `goLibrary`, `setGridFocus`, `setGridPage`, `setSelectedGameIdx`, `openModal`, `closeModal` | [store reference](../architecture/05-frontend.md#store--storeindexts) |
| `sdk.input` | `onGp(event, handler)`, `useGamepadState()`, `GP_BTN`, `events` | [event bus](../architecture/05-frontend.md#the-gamepad-event-bus--hooksusegamepadts) |
| `sdk.system` | `onWsEvent`, `playSound`, `getAudioContext`, `gamecore`, `asset(path)` | `asset()` resolves a path inside the theme folder |
| `sdk.defaults` | `Shell` (the default frontend, takes parts), every screen, `SettingsOverlay` + `DefaultSettingsPages` (wifi, audio, bluetooth, standby, themes, update, desktop) | compose instead of rewrite |

`modalDepth` and `powerPending` are readable through `get()` but there is no
setter: they are the core's focus and shutdown locks.

`sdk.input.onGp` silently refuses `gp:guide` — the core owns it, because a
double press there kills a running game.

`sdk.defaults` is what makes "add a Santa on top of the existing dashboard" as
cheap as "rewrite everything" — override `home`, render the default inside it,
add your layer.

## 7. Module contract

The entry point default-exports a function taking `sdk` and returning
`{ shell }`. The shell takes no props: everything comes from the SDK.

```js
export default (sdk) => {
  const { html } = sdk.ui
  const Decor = () => html`<img src=${sdk.system.asset('santa.png')} class="t-santa" />`
  return { shell: () => html`<${sdk.defaults.Shell} decor=${Decor} />` }
}
```

A theme may ship a stylesheet for its own markup and load it from its folder.

> **Reusing a default settings page?** They are fragments written for
> `sdk.defaults.SettingsOverlay`, which gives them their width, padding and
> scrolling. Render them inside it, not inside your own panel.

## 8. Fallback and composition

| Situation | Result |
|---|---|
| No `shell` in `provides` | the default frontend |
| Declared but missing from the module | the default frontend + warning |
| The shell throws while rendering | the default frontend, and the crash is recorded |
| Module fails to load | theme rejected, default frontend, reason surfaced |

## 9. Compatibility

- `api` major greater than the host's → theme is listed but **not selectable**,
  with the reason shown.
- `api` major lower → loaded while the host still supports that version.
- Adding a surface or an SDK key does **not** bump the major. Removing one does.
- Theme modules are loaded with a cache-busting parameter. Electron's HTTP cache
  has hidden UI changes before — see the OTA section of
  [`09-gotchas.md`](../architecture/09-gotchas.md).

## 10. Safety

The project had no error boundary at all before this: a React throw produced a
white screen. With themes running arbitrary JS on a TV with no pointer, that was
the failure mode to close first. What is in place:

1. **A boundary per surface** — a broken screen falls back to the default one;
   the rest of the theme keeps running.
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

## 11. Performance

The box also runs emulators, on a TV, at 1080p.

- Decor stops while a game is running — the UI already suppresses everything
  during a session.
- Decor stops during standby and the screensaver.
- Animate `transform` and `opacity` only.
- Cap the number of simultaneously animated elements.

## 12. Sounds

A theme may replace the UI sounds. Two rules:

- The user's **UI sounds setting always wins** — if sounds are off, a theme
  cannot make noise.
- Themes go through `sdk.system.playSound` / `getAudioContext`. The host's
  volume setting applies. Note the default sounds are synthesised, not files:
  a theme shipping audio assets is a new case, not the existing path.

## 13. Authoring loop

1. Copy the skeleton theme.
2. Edit `theme.json`, write one or more surfaces.
3. Drop the folder on the box — drag & drop through the rom-manager addon from
   any browser on the LAN, or over SSH.
4. Settings → Themes → select.
5. Iterate: reload, there is nothing to compile.

## 14. Implementation order

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
