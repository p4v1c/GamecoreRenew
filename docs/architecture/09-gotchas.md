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

**In-memory state whose effect is on disk (or in the X server) needs a
startup reconciliation.** Two instances of the same bug:

- Standby is a module variable, but `xset dpms force off` belongs to the X
  server, which SDDM owns and which does not restart with the backend. A box
  asleep when the backend restarted came back believing it was awake with the TV
  dark, and no button could wake it. The lifespan now forces the screen on
  unconditionally.
- The running game lived only in `_proc`. A restarted backend saw
  `is_running == False`, so `kill()` returned immediately and the emulator was
  fullscreen and unkillable. The pgid is persisted to `config/session.json` and
  adopted at startup.

The general shape: if the backend can be restarted while the effect persists, ask
at startup rather than assuming a clean slate. Note that a **crash** skips the
lifespan's shutdown half entirely, so cleanup-on-shutdown does not cover it —
which is why the game is persisted rather than killed.

**`task.cancel()` only schedules the cancellation.** The lifespan awaits its
four tasks with `asyncio.gather(..., return_exceptions=True)`; without that,
shutdown returned with them still mid-`await`.

**Killing a shell does not kill what it spawned.** The OTA timeout killed `bash`
and left its `rsync`, `pip` and `npm` writing into `/opt/GameCore` after the UI
had been told the update was aborted. Spawn with `start_new_session=True` and
kill the group — `process_manager.kill_process_group()` is shared for this.

**A blocking call in a coroutine blocks everything.** `_probe_display()` ran
synchronous `subprocess.run(timeout=5)` on the event loop, on every launch and
every standby transition; an unrelated `GET /api/systems` measured 4.7 s. It is
memoised now, and the first probe runs off-thread. Same reason argon2 goes
through `asyncio.to_thread` in the auth router.

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

**Any path built from a route parameter is validated by containment, not by
pattern.** `Path(p).resolve().relative_to(root.resolve())`, in `launch_game()`,
`cover_pipeline._rom_in_root()` and `metadata._search_name()`. A
`{filename:path}` converter accepts slashes and `..`, so the rule has to hold
everywhere and not be re-derived per call site — the cover pipeline was the one
place it had been left out.

**An empty path component is a path too.** `PurePosixPath(".").parts` is the
empty tuple, so an entry id of `"."` passed both the `is_absolute()` and the
`".."` checks in the save-manager addon, resolved to the collection directory
itself, and `DELETE` then `rmtree`'d the whole collection. Guard `not rel.parts`
alongside the other two, and refuse `target == root` outright.

**Overlay uploads are checked by magic bytes.**
`_looks_like_image(head)` — the client's `Content-Type` proves nothing. Check the
byte count too: an **empty** upload never enters the read loop, so it never meets
the magic-byte test, and it used to `os.replace` a working bezel with zero bytes.

**The core is never LAN-exposed.**
`/api/*` is 403 through Caddy. The TV reaches it over loopback only. If you
add an endpoint, assume the LAN can never call it.

**…but "not LAN-exposed" is not "not reachable".** The box runs browsers — the
Firefox kiosk profiles and Stremio — and they can reach `127.0.0.1:8765`. A page
in one of them could auto-submit a form at `/api/games/kill`. Hence the
cross-origin middleware in `main.py`, and the same check on `/ws`, which needs it
most: a WebSocket handshake is a GET and is not subject to CORS at all. Adding a
non-GET endpoint requires nothing from you; adding another *transport* does.

**A rate limiter that can be tripped by an attacker is a denial of service.**
The global login breaker applied to every caller, so 25 failures spread over
throwaway keys — trivially produced by any unauthenticated LAN client — returned
429 to the owner with the correct password. It now only weighs on addresses
already known to have failed.

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

See [`../TESTING.md`](../TESTING.md) for how to run the suite. Two traps that
belong here:

**`GAMECORE_PATH` is read at import time**, so whichever test module pytest
imports first would otherwise decide where the whole suite writes. `conftest.py`
is the only place the override is guaranteed to land in time — it runs before
any test module. It *sets* the variable rather than defaulting it: inheriting a
`GAMECORE_PATH` from the shell would point the suite at a real installation.

**A backend started by hand needs `GAMECORE_BACKEND_PORT`, not just `--port`.**
The cross-origin guard accepts a loopback `Origin` on the backend's *configured*
port, so with only `--port 8899` an `Origin: http://localhost:8899` is refused.

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
