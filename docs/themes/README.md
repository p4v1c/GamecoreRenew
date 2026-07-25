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

## 5. Surfaces

| Surface | Replaces | v1 |
|---|---|---|
| `background` | a full-screen layer behind everything | yes |
| `decor` | a full-screen layer above everything, non-interactive | yes |
| `home` | the dashboard | yes |
| `library` | the game grid, search and metadata panel | yes |
| `topbar` | clock, IP, storage, controller battery | yes |
| `screensaver` | the standby slideshow | yes |
| `powerModal` | the power menu | yes |
| `gamepadModal` | the controller screen | yes |
| `keyboard` | the on-screen keyboard | **not yet** |
| `splash` | the boot animation | **v1.1** |
| `settings` | the settings screen | **never** |

Four deliberate exclusions:

- **`settings` is not overridable.** It is the only way back to another theme.
  If a theme could break it, the box becomes unusable — and there is no mouse to
  recover with. A theme may style its own entry tile, not the page.
- **`splash` is deferred to v1.1.** Its animation is rAF-driven with a cold-boot
  hold (the first black frame is held ~4 s while the TV re-syncs HDMI). A theme
  replacing it must honour that parameter or the animation plays to nobody.
- **`keyboard` is not wired yet.** The on-screen keyboard is rendered from
  inside `LibraryScreen` and `WifiPage`, not from `App`, so a theme's version
  would never be picked up. Listing it would accept a theme that then silently
  does nothing. It returns when those two call sites go through a surface.
- **The overlay window** (`/overlay`, the emulator bezels) is out of scope. It
  has its own mount point, is driven by `config/overlays.json`, and renders on
  top of running games.

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
| `sdk.defaults` | every default component | lets a theme wrap instead of replace |

`modalDepth` and `powerPending` are readable through `get()` but there is no
setter: they are the core's focus and shutdown locks.

`sdk.input.onGp` silently refuses `gp:guide` — the core owns it, because a
double press there kills a running game.

`sdk.defaults` is what makes "add a Santa on top of the existing dashboard" as
cheap as "rewrite everything" — override `home`, render the default inside it,
add your layer.

## 7. Module contract

The entry point default-exports a function taking `sdk` and returning an object
whose keys are surface names. **Surfaces take no props and pull what they need
from the SDK**, with three exceptions the host has to hand over because they
close over its own state:

| Surface | Props |
|---|---|
| `topbar` | `{ onSettings, onPower }` |
| `powerModal`, `gamepadModal` | `{ onClose }` |

Everything else takes nothing. That is what keeps the contract stable: the host
can reorganise its screens without changing a signature.

Illustrative shape, not an implementation:

```js
export default (sdk) => {
  const { html } = sdk.ui
  const Decor = () => html`<img src=${sdk.system.asset('santa.png')} class="t-santa" />`
  return { decor: Decor }
}
```

A theme may ship a stylesheet for its own markup and load it from its folder.

## 8. Fallback and composition

| Situation | Result |
|---|---|
| Surface not in `provides` | default component |
| Declared in `provides` but missing from the module | default component + warning |
| Surface throws while rendering | default component **for that surface only** |
| Module fails to load | whole theme rejected, default theme, reason surfaced |

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
