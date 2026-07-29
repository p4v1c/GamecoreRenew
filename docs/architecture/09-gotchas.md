# 9 — Gotchas

Invariants that look like noise until they break something. Each one is here
because it already cost someone a debugging session.

## Process and lifecycle

**`_launching` is claimed synchronously.**
`ProcessManager.launch()` sets it before the first `await`. Two concurrent
launches would otherwise both pass the `is_running` check while the first was
still awaiting the spawn, and the box would run two emulators.

**`start_new_session=True` is load-bearing.**
It puts the emulator in its own process group. Without it, `killpg` in
`_proc_kill()` targets the backend's own group — the kill button would kill
GameCore.

**Never SIGTERM an emulator.**
Several answer it with a confirmation dialog that cannot be clicked from a
gamepad. `_proc_kill()` goes straight to SIGKILL. For Flatpak, `flatpak kill
<app-id>` must come first: a signal to the wrapper never reaches the sandbox.

**A one-frame crash is not a play session.**
`_watch()` only records playtime past 5 s, or a crash-looping emulator would
inflate the library stats.

## Backend wiring

**`/ws` must stay registered before the `/` static mount.**
The SPA catch-all (`html=True`) otherwise swallows the WebSocket upgrade and
the UI silently stops receiving events.

**Static mounts `mkdir` first.**
The mount loop in `main.py` creates each directory before mounting. A
conditional mount decided at import time used to leave `/covers` dead until a
restart on a fresh checkout.

**`_hot_load()` re-reads JSON on every call.**
Editing `systems.json` on the box takes effect with no restart — and a syntax
error breaks the API on the very next request.

**`config/` is the box's identity.**
Never touched by OTA. Not all of it is out of git, though — `systems.json`,
`apps.json`, `overlays.json` and the bundled themes *are* versioned, and the
installer regenerates the first two from `install/*.dist` on every run. What is
never in git is the **state**: `auth.json` and `auth_secret`, `addons.json`,
`standby.json`, `theme.json`, `session.json`, `playtime.db`. Overwriting one of
those is data loss — the password, the addon registry, the play history.

## Input

**While a game runs, the UI ignores every gamepad event except `gp:guide`.**
Otherwise emulator input drives the launcher hiding behind the game.

**Guide needs a double press within 1 s.**
Enforced in both `useGamepad.ts` and `gamepad_monitor.py`. A single press must
never kill a running game.

**The browser cannot see the Guide button reliably.**
Chromium often hides it, and the UI has no focus under a fullscreen emulator.
The evdev monitor in the backend is the primary path; the browser is the
fallback.

**The controller screen closes on a double □, and ○ does not close it.**
Every button there is a test target, so no button may be an action.
`CONTROLLER_CLOSE_MS` in `App.tsx`.

## Display

**Overlays are X11-only.**
`_WAYLAND_SESSION` disables the feature when `WAYLAND_DISPLAY` is set —
silently, by design. A dev machine on Wayland will never reproduce an overlay
bug.

**Leave fullscreen with a ClientMessage, not a property write.**
EWMH reserves `_NET_WM_STATE` for the window manager once a window is mapped.
Writing it directly does clear fullscreen on some WMs, but it clears **every**
state at once (`_NET_WM_STATE_ABOVE` included) and desyncs the WM: the window
then ignores later state requests. `force_rect()` sends the ClientMessage.

**`_display_env()` removes `WAYLAND_DISPLAY`.**
Qt emulators launched from the systemd unit would otherwise try Wayland and
fail silently.

**Gamepad buttons are not a "user gesture".**
Chromium keeps WebAudio suspended until mouse or keyboard input. On a
controller-only kiosk the UI would be mute forever, hence
`autoplay-policy: no-user-gesture-required` in `electron/main.js`.

**`XDG_RUNTIME_DIR` or no audio at all.**
`start-ui.sh` exports it before launching Electron. A systemd service does not
inherit it, and Chromium reaches PipeWire through it.

## Security

### Untrusted strings reach the HUD

HUD toast text comes from WebSocket broadcasts, which include
`POST /api/addons/notify` (any addon can call it) and Bluetooth device names.
`escHtml()` and `safeColor()` exist for that. Never interpolate raw.

**`rom_path` is validated by containment, not by pattern.**
`Path(rom_path).resolve().relative_to(roms_root.resolve())` in `launch_game()`.
Without it, `/api/games/launch` runs arbitrary binaries.

**Overlay uploads are checked by magic bytes.**
`_looks_like_image(head)` — the client's `Content-Type` proves nothing.

**The core is never LAN-exposed.**
`/api/*` is 403 through Caddy. The TV reaches it over loopback only. If you
add an endpoint, assume the LAN can never call it.

## OTA

### The OTA rebuild trap

The OTA archive used to ship `frontend/dist` **without** `frontend/src`. A box
therefore ran a CI-fresh bundle on top of sources frozen at first install, and
nothing reported the drift.

That holds until something rebuilds *on the box* — `update/linux.sh`'s own
fallback when a release ships no `dist/`, or a hand-run `npm run build`. Either
regenerates `dist/` from months-old sources and silently reverts the UI.

It cost a real feature: the "Scan mapping" button shipped in v1.0.62 was
missing from a box running v1.0.66, while its backend route was live and
answering the whole time.

The archive now ships `frontend/` whole and `linux.sh` mirrors `frontend/src/`
with `--delete`. **Keep it that way**, and remember the consequence: local
edits to a box's frontend are erased by the next update. Push them.

**The updater must not restart the services itself.**
`update/linux.sh` runs inside the backend's cgroup. It starts the detached
`gamecore-restart.service` with `--no-block` instead — a direct
`systemctl restart` would kill the script mid-update.

**`VERSION` is written by the updater, not by git.**
The repo pins `v1.0.0`; the real version lives in the tags and in the file the
OTA writes. That is why `VERSION` always shows as modified in `git status` on a
box.

## Testing

**Headless Chromium never fires `requestAnimationFrame` under
`--virtual-time-budget`.**
Both the splash (rAF-driven) and the 60 fps gamepad poll freeze, so nothing
happens and every assertion fails for the wrong reason. Polyfill it:

```js
window.requestAnimationFrame = cb => window.setTimeout(() => cb(performance.now()), 16)
window.cancelAnimationFrame = id => window.clearTimeout(id)
```

**Testing gamepad code needs no hardware.** Override
`navigator.getGamepads` with a fake pad object and drive the real poll loop.

**`npm run build` is the cheapest full check of the UI** — it runs `tsc` first,
so a type error fails the build.

**Two `DEBUG` flags.** `backend/config.py` and `electron/main.js`. Both must be
`false` on a device; `DEV` (Electron loading Vite) is
`DEBUG && ELECTRON_DEV=1`.

**CSS transitions do not progress under `--virtual-time-budget` either.**
The rAF polyfill above does not help: the animation clock is frozen, so a
transitioned property keeps its *starting* value forever. Measuring an element
mid-transition therefore reports "it never moved". Disable the transition in the
harness before asserting on geometry:

```js
const st = document.createElement('style')
st.textContent = '.my-track { transition: none !important; }'
document.head.appendChild(st)
```

Two days of "the carousel is broken" came from this. The carousel was fine.

**Match a component by what it actually renders.** A probe that looked for the
default splash by its `<canvas>` reported "no splash" in every run — that splash
is built entirely from `<div>`s. The test passed while proving nothing. Pin
components on something stable and verified: a root `z-index`, a class the
component owns.

## Themes

**Theme files must not be cached by the browser.** The loader can bust the entry
module's URL, but the entry's own relative imports (`home.js`, `settings.js`, …)
and its stylesheet resolve without that query, so the browser pins the first
version it ever saw. Editing a theme then changes nothing on screen — and a fix
shipped by update stays invisible. `/themes` is therefore mounted through
`_NoCacheStatic` in `backend/main.py`, which sets `Cache-Control: no-store` and
disables 304s.

**The splash must be chosen once, after the theme resolves.** Reading
`theme.splash ?? Splash` on every render mounts the *default* splash first —
the theme is still loading, so its splash is undefined — then swaps in the
theme's mid-animation. Both boot animations play over each other. `App.tsx`
freezes the choice in a ref and shows a plain opaque cover until `theme.loading`
clears.

**`overflow-clip-margin` is not reliably applied**, so do not build a layout that
depends on it. To let a focus ring overflow a clipping container, grow the clip
box with `padding` and pull it back with an equal negative `margin`: the content
box — and everything sized against it — is unchanged, and plain
`overflow: hidden` then clips further out.

**A settings page is a full-screen overlay, not a fragment.** Every page in
`components/modals/settings/` wraps itself in `<Overlay>`. Nesting one inside
another box puts a `position: fixed` layer in a flex container and destroys its
layout. `ThemesPage` was the one page that had forgotten its wrapper, and it
rendered as loose content stacked under the dashboard — invisible for as long as
it also had no route in `SettingsModal`.
