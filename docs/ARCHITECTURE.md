# GameCore — how it actually works

Reference for anyone (or anything) that needs to change this codebase without
reading all 12 000 lines first. It describes what the code *does*, names the
files and functions that do it, and calls out the traps.

`README.md` is the user manual. This is the map of the machine.

---

## 1. The shape of the thing

GameCore is a TV game launcher. Four processes, one box:

```
┌─ gamecore-backend.service (system unit) ─────────────────────────┐
│  uvicorn → backend.main:app on 127.0.0.1:8765                    │
│  · REST API + WebSocket + serves frontend/dist                   │
│  · owns: the emulator process, playtime DB, covers, standby      │
│  · background tasks: gamepad_monitor, battery, standby, prefetch │
└──────────────────────────────────────────────────────────────────┘
        ▲ HTTP + WS (loopback)             ▲ spawns
        │                                  │
┌─ gamecore-ui.service (system unit) ──┐   │   ┌─ the emulator ─────┐
│  Electron (electron/main.js)         │   └──▶│ flatpak run …      │
│  · kiosk BrowserWindow → :8765       │       │ (its own pgroup)   │
│  · transparent overlay window        │       └────────────────────┘
│  · HUD toast window                  │
│  · spawns overlay_monitor.py (stdio) │
└──────────────────────────────────────┘
                                          ┌─ addons (user units) ───┐
                                          │ :8770 rom-manager        │
                                          │ :8771 rpcs3-manager      │
                                          │ :8772 save-manager       │
                                          └──────────────────────────┘
                                          ┌─ Caddy :8443 (LAN edge) ─┐
                                          │ TLS + shared-password    │
                                          │ auth, proxies the addons │
                                          └──────────────────────────┘
```

Everything except Caddy binds **loopback only**. The TV talks to
`http://localhost:8765` with no auth — physical access is the trust boundary.
The LAN only ever reaches Caddy on `:8443`. See §12.

**Ports:** 8765 core · 8770-8799 addons · 8443 Caddy · 5173 Vite (dev only).

---

## 2. Repository layout

```
backend/          FastAPI app
  main.py         router wiring, static mounts, /ws, lifespan tasks
  config.py       every path in the project derives from GAMECORE_ROOT
  db.py           aiosqlite handle + schema (playtime, sessions)
  ws.py           WebSocket broadcast bus
  routers/        HTTP surface, one module per domain
  services/       the actual logic — no FastAPI imports below this line
  data/           gamecontrollerdb.txt (vendored SDL mapping DB)
  templates/      login.html (served to LAN clients by Caddy)
  tests/          pytest (test_covers.py is the substantial one)
frontend/         React 18 + Vite + Zustand + Framer Motion
electron/         kiosk shell, overlay window, HUD toasts
config/           runtime state — excluded from OTA (see §11)
assets/           logos/, overlays/
emu/              ROMs per system + emu/covers/ cache
install/          arch.sh (952 l.), installer-gui/, gamecore-addon CLI, Caddyfile
update/linux.sh   OTA updater
```

Rule of thumb: `routers/` parse and validate, `services/` decide and act.
A router that grows logic belongs in a service.

---

## 3. Configuration model

`backend/config.py` is the single source of paths. Everything hangs off
`GAMECORE_ROOT`, which is `$GAMECORE_PATH` or the repo root:

| Constant | Value |
|---|---|
| `SYSTEMS_FILE` | `config/systems.json` |
| `APPS_FILE` | `config/apps.json` |
| `PLAYTIME_DB` | `config/playtime.db` |
| `COVERS_DIR` | `emu/covers` |
| `ASSETS_DIR` | `assets/` |
| `BACKEND_PORT` | `$GAMECORE_BACKEND_PORT` or 8765 |
| `APP_VERSION` | contents of the `VERSION` file |
| `THEGAMESDB_API_KEY` | env only — never committed |

`resolve_path(raw)` turns a config-relative string into an absolute `Path`;
absolute inputs pass through. Every `romsPath`/`iconPath` goes through it.

### config/ files

| File | Written by | Read by |
|---|---|---|
| `systems.json` | installer / hand | `routers/systems.py` |
| `apps.json` | installer / hand | `routers/systems.py` |
| `overlays.json` | hand | `routers/overlays.py`, `overlay_monitor.py` |
| `addons.json` | `gamecore-addon` CLI | `routers/addons.py` |
| `standby.json` | `POST /api/standby/config` | `services/standby.py` |
| `auth.json`, `auth_secret` | `services/auth.py` (0600) | idem |
| `playtime.db` | backend | backend |

**None of these are in git and none are touched by OTA.** That is deliberate:
they are the box's identity.

### A system entry (`systems.json`)

```jsonc
{
  "id": "azahar",                     // primary key everywhere
  "type": "emulator",
  "label": "Nintendo 3DS",
  "platform": "3DS",
  "color": "#ff0096",                 // drives the UI accent for this tile
  "iconPath": "assets/logos/3ds.png",
  "path": "flatpak",                  // "flatpak" or an absolute binary path
  "args": "run org.azahar_emu.Azahar -f",
  "romsPath": "emu/azahar/",
  "extensions": ["*.3ds", "*.zip"],
  "libretroSystems": ["Nintendo - Nintendo 3DS"],  // cover scraping key
  "scanDirs": false                   // true = games are folders (PS3/PS4)
}
```

Two optional keys the code honours but the shipped config does not currently
use — worth knowing before you go hunting:

- `"gamepadTrigger": true` → `routers/games.py:_gamepad_trigger()` runs
  `sudo udevadm trigger` three times, 3 s apart, after launch. Some Flatpak
  apps (Stremio) only see a pad if udev re-fires. Needs a sudoers rule.
- `"fullscreen": {…}` → `services/fullscreen_enforcer.py` forces the window
  fullscreen over EWMH for apps with no fullscreen CLI flag.

`apps.json` is the same shape minus the ROM keys, plus `"kind": "app"`.
`routers/systems.py:list_all()` concatenates both; `_hot_load()` re-reads the
file on **every** call, so editing JSON on the box needs no restart.

---

## 4. Backend — routers

All mounted under `/api` (`main.py:41-55`).

| Module | Endpoints | Notes |
|---|---|---|
| `systems.py` | `GET /systems`, `/systems/{id}`, `/assets/logos/{file}` | `list_all()` = systems + apps |
| `games.py` | `GET /systems/{id}/games`, `POST /games/launch`, `POST /games/kill`, `GET /games/session` | see §7 |
| `playtime.py` | `GET /playtime`, `/playtime/system/{id}`, `/playtime/game/{key}` | reads the SQLite tables |
| `covers.py` | `GET /covers/{system}/{file}?refresh=` | delegates to the pipeline, §8 |
| `metadata.py` | `GET /metadata/{system}/{file}` | TheGamesDB description/year/genres |
| `overlays.py` | `GET/POST/DELETE /overlays/{id}` | PNG upload, magic-byte checked |
| `addons.py` | `GET /addons`, `/addons/available`, `POST /addons/notify`, install/update/remove | shells out to the CLI |
| `sysinfo.py` | `GET /sysinfo` | IP, storage, version, controllers |
| `update.py` | `GET /update/check`, `POST /update/apply` | §11 |
| `standby.py` | `GET /standby`, `POST /standby/config`, `POST /standby/exit` | §10 |
| `controllers.py` | `POST /controllers/scan-mapping` | §9 |
| `settings/wifi.py` | networks, status, connect, disconnect | wraps `nmcli` |
| `settings/audio.py` | volume, sinks | wraps `wpctl`/`pactl` |
| `settings/bluetooth.py` | devices, scan, connect, remove | wraps `bluetoothctl` |
| `auth.py` | login, verify, logout, change-password | §12 |

Non-`/api` routes in `main.py`:

- `GET /overlay` — serves the SPA to the transparent Electron overlay window.
- `GET /gc/addons` — same payload as `/api/addons`, on a path Caddy proxies
  **without auth**: the addon nav bar needs it before login state is known.
- `GET /login` — self-contained login page for LAN clients.
- `WS /ws` — registered *before* the catch-all static mount, or the SPA
  would swallow it.
- Static mounts: `/covers`, `/assets/logos`, `/assets/overlays`, `/data`,
  then `/` → `frontend/dist` (SPA fallback, `html=True`).

The mount loop (`main.py:88-95`) calls `mkdir(parents=True, exist_ok=True)`
on each directory first. A conditional mount decided at import time used to
leave `/covers` dead until a restart on a fresh checkout.

---

## 5. Backend — services

### process_manager.py — one game at a time

Module-level singleton `process_manager`. State: `_proc`, `_launching`,
`_game_key`, `_system_id`, `_start_time`, `_exec_path`, `_launch_args`.

- `is_running` is `_launching or (_proc and returncode is None)`.
  `_launching` is claimed **synchronously** at the top of `launch()` because
  two concurrent calls would otherwise both pass the check before the first
  `await`.
- `launch()` builds argv with `shlex.split(exec_args)` + the ROM path,
  spawns with `start_new_session=True` — the child gets its own process
  group so `killpg` can never reach the backend — then broadcasts
  `game:started` and starts `_watch()`.
- `_display_env()` reconstructs a GUI environment for a process started from
  systemd: `DISPLAY` (default `:1`), `XDG_RUNTIME_DIR`, `DBUS_SESSION_BUS_ADDRESS`,
  `XAUTHORITY` (globbed from `/run/user/<uid>/xauth_*`), and
  `SDL_GAMECONTROLLERCONFIG_FILE` → `backend/data/gamecontrollerdb.txt`.
  It **pops `WAYLAND_DISPLAY`** so Qt emulators don't try Wayland and fail
  silently under the unit.
- `kill()` handles Flatpak first: SIGTERM to the `flatpak` wrapper never
  reaches the sandboxed app, so `_flatpak_kill()` digs the app-id out of the
  args (the token after `run`) and calls `flatpak kill <app-id>`, then
  `_proc_kill()` sends **SIGKILL** to the process group — no SIGTERM, because
  some emulators answer it with a confirmation dialog.
- `_watch()` awaits the process, then writes playtime **only if the session
  lasted > 5 s** (an emulator that dies instantly is not a play session), and
  broadcasts `game:finished`.

> The SDL comment at the top of the file is worth reading: an earlier revision
> exported `SDL_GAMECONTROLLERDB`, a variable SDL has never read, so the
> vendored mapping DB was silently ignored for a while.

### gamepad_monitor.py — the Guide button, from evdev

The browser Gamepad API cannot be trusted for the PS/Guide button (Chromium
often hides it) and the UI is buried under a fullscreen emulator anyway. So
the backend reads `/dev/input/event*` directly.

`_find_gamepad_devices()` enumerates readable devices, `_watch_device()` opens
each, and `_on_guide_pressed()` fires the kill. Connect/disconnect feeds
`controller_registry`, which assigns **console-style player slots** (P1…P4)
keyed by MAC (`normalize_mac`) or device path — so the slot survives a
reconnect. `snapshot()` is what `/api/sysinfo` returns.

### standby.py — soft standby

`run()` polls idle time. On threshold: `_enter()` walks the stages, `_screen(False)`
kills the display over DPMS, `_governor("powersave")` drops the CPU (optional,
needs a sudoers rule). `on_input()` from the gamepad monitor wakes it —
which is why standby survives with the UI asleep. A running game blocks it.
Config in `config/standby.json` via `POST /api/standby/config`.

### battery.py — controller battery

`read_batteries()` walks sysfs power supplies, `_check()` fires threshold
alerts, `run()` broadcasts `gp:battery` on the WebSocket. The UI renders it as
a toast; in-game, Electron paints it as a native always-on-top HUD window
because the React toast would be hidden under the emulator.

### overlay_monitor.py — bezels (X11 only)

Spawned by Electron as a **subprocess speaking JSON-lines over stdio**, not
imported. Protocol is in the module docstring:

```
stdin  ← {"cmd":"watch","system_id":"dolphin","config":{…}}  |  {"cmd":"stop"}
stdout → {"event":"window:ready","system_id":…,"rect":{x,y,w,h}}
       → {"event":"window:waiting"|"window:closed"|"error", …}
```

`X11Manager` wraps python-xlib: `find_window(wm_classes)` matches the emulator
window by `WM_CLASS`, `force_rect()` takes it out of fullscreen and moves it,
`get_rect()` reports geometry. `_WAYLAND_SESSION` disables the whole feature
when `WAYLAND_DISPLAY` is set — overlays are silently skipped, not broken.

`force_rect()` leaves fullscreen by sending a `_NET_WM_STATE` **ClientMessage
to the root window**, per EWMH. Writing the property directly on the window
(what it used to do) clears *every* state at once — `_NET_WM_STATE_ABOVE`
included — and leaves the WM's bookkeeping out of step.

### fullscreen_enforcer.py

Same EWMH toolbox, opposite direction: `_request_fullscreen()` for apps with
no fullscreen flag. Driven by the optional `"fullscreen"` key on a system.

### Cover & metadata stack

`cover_pipeline.py` orchestrates, `local_media.py` reads the game itself,
`iso9660.py` reaches inside ISOs, `scraper.py` does the network, `sfo.py`
parses PARAM.SFO, `metadata.py` handles TheGamesDB text. See §8.

### prefetch.py

`run()` warms covers and metadata at startup so the first library scroll is
not a spinner.

### auth.py

argon2id hash in `config/auth.json`, HMAC key in `config/auth_secret`, both
written 0600 by `_write_private()`. Cookie is
`expiry.generation.HMAC-SHA256(secret, "expiry.generation")`. Bumping
`generation` (via `change-password`) invalidates every session at once.
`blocked_for()`/`register_failure()` implement per-IP exponential backoff
after 5 failures.

---

## 6. Frontend

```
src/
  App.tsx                 shell, global gamepad bindings, modal orchestration
  store/index.ts          Zustand: screen, selection, modalDepth, session
  hooks/useGamepad.ts     Gamepad API → CustomEvents (+ live state)
  hooks/useWebSocket.ts   backend events → handler registry
  api/index.ts            typed fetch wrappers, BASE = "/api"
  components/
    HomeScreen/           dashboard + SystemCard
    LibraryScreen/        grid, search, pagination
    TopBar/               clock, IP, storage, ControllerBattery
    modals/               SettingsModal (+ settings/ pages), PowerModal,
                          GamepadModal (+ gamepad/ControllerArt)
    ui/                   Overlay, Toggle, SliderRow, VirtualKeyboard, Toasts
    Splash.tsx            rAF boot animation
    Screensaver.tsx       cover-art idle screen
  lib/                    sounds, systemColors, formatGameName
```

### The gamepad event bus

`useGamepad()` polls `navigator.getGamepads()` at 60 fps and dispatches
`CustomEvent`s on `window`. Components subscribe with `onGp(event, handler)`
and get a cleanup function back — no prop drilling, no context.

```
gp:dpad-up|down|left|right   gp:confirm (A/✕)   gp:back (B/○)
gp:y (Y/△)   gp:x (X/□)      gp:menu (Start)    gp:power (Select/Share)
gp:l1 gp:r1 gp:l2 gp:r2      gp:guide (PS)      gp:connected gp:disconnected
```

Three invariants that are easy to break:

1. **While a game runs, every event is suppressed except `gp:guide`**
   (`isPlaying()` reads Zustand synchronously). Otherwise emulator input would
   drive the launcher behind the game.
2. **`gp:guide` needs a double press within 1 s** (`GUIDE_DOUBLE_PRESS_MS`) —
   one press must never kill a running game by accident.
3. **The left stick is edge-triggered into d-pad events** with a 0.5 dead
   zone, so a held stick emits once, not 60 times a second.

For continuous state (a stick's actual position, a held button), use
`useGamepadState()` / `onGamepadFrame()` from the same module: the poll loop
hands out its raw per-frame snapshot, quantised to 1/50th so a resting stick
re-renders nothing. `GamepadModal`'s pad drawing is the only consumer.

### Modal focus lock

`store.modalDepth` is incremented by every modal on mount and decremented on
unmount. Screens check `modalDepthRef.current > 0` before acting on a gamepad
event — that is what stops the library from navigating behind an open dialog.
`App.tsx` refuses to *open* a modal when `modalDepth !== 0`, but closing
always works.

The controller screen (□) is the exception: it closes on a **double □ within
`CONTROLLER_CLOSE_MS` (1 s)** and ○ does not close it, because every button on
that screen is a test target.

### WebSocket events (backend → UI)

`onWsEvent(event, handler)`; auto-reconnects every 3 s.

| Event | Payload | Effect |
|---|---|---|
| `game:started` | game_key, system_id | Electron shows the bezel overlay |
| `game:finished` | + elapsed | clears the session, hides the overlay |
| `game:running` | current game | sent on connect if a game is already up |
| `gp:battery` | name, level, threshold | toast / native HUD |
| `gp:guide` | — | relayed kill request from evdev |
| addon events | free-form | via `POST /api/addons/notify` |

---

## 7. Launching a game, end to end

1. `LibraryScreen` → `api.games.launch(system_id, rom_path, game_key)`.
2. `routers/games.py:launch_game()`
   - resolves the system from `list_all()`, 404 if unknown;
   - 409 if `process_manager.is_running`;
   - **path check**: `Path(rom_path).resolve().relative_to(roms_root.resolve())`
     — a crafted path cannot launch an arbitrary binary (403 otherwise);
   - `process_manager.launch(...)`;
   - optionally schedules `_gamepad_trigger()` and `fullscreen_enforcer.enforce()`.
3. `process_manager` spawns the process, sets `ws.set_current_game`, broadcasts
   `game:started`.
4. The UI receives it and calls `window.gamecore.overlayStart(system_id)` over
   the preload bridge.
5. Electron looks the system up in `config/overlays.json`, spawns
   `overlay_monitor.py`, waits for `window:ready`, then shows the transparent
   always-on-top overlay window with the PNG.
6. Exit: the emulator dies → `_watch()` records playtime (> 5 s) and
   broadcasts `game:finished`; or the player double-taps PS → evdev monitor →
   `POST /api/games/kill` → `flatpak kill` + `SIGKILL` on the group.

---

## 8. Cover art pipeline

`services/cover_pipeline.py:resolve(system, filename, refresh=False)`. Each
tier only runs if the previous found nothing:

1. **Local cache / manual override** — `emu/covers/<system>/<name>.png|jpg`.
   Drop a file there to pin a cover forever.
2. **Icon inside the game** (offline, always exact) — `local_media.py`:
   `_ps3_icon` (`PS3_GAME/ICON0.PNG`), `_ps4_icon` (`sce_sys/icon0.png`),
   `_psp_sfo`/`_psp_read` (pulls `ICON0.PNG` straight out of the ISO through
   `iso9660.Iso9660`). `get_title()` also feeds the library the real name from
   `PARAM.SFO`, so serial-named folders stop showing as `BLES01234`.
3. **Exact disc-ID lookup** — `disc_id()` reads the GameCube/Wii header or
   `SYSTEM.CNF` (PS1/PS2); `_fetch_by_id()` queries GameTDB or the xlenore
   PSX/PS2 repos. No filename guessing.
4. **Name scraping** — `scraper.py`: libretro thumbnails CDN
   (`_name_variants()` generates the spellings), then TheGamesDB if
   `THEGAMESDB_API_KEY` is set.

Misses are cached as `.miss` files for a week so offline browsing stays fast.
`?refresh=1` forces a re-resolve.

---

## 9. Controller mapping — `controller_profiles.py` (1034 l.)

The hardest part of the project. Two problems it solves:

**(a) Generic SDL mapping.** Emulators linked against SDL read the DB named by
`SDL_GAMECONTROLLERCONFIG_FILE`, exported in `_display_env()`. That covers
anything SDL recognises.

**(b) The GUID-based emulators.** Azahar (3DS), melonDS (DS), mGBA (GBA),
Cemu (Wii U), Ryujinx (Switch) bind a pad by device GUID + raw button indices
that cannot be synthesised. Hence **"Scan mapping"**: configure the pad once
in the emulator's own UI, then hit the button in the Power menu →
`POST /api/controllers/scan-mapping` → `scan_mapping()` snapshots the current
config **per controller** and restores it automatically on every future
connect.

Supporting cast:
- `vidpid_of(guid)` / `swap_vidpid()` — rewrite the vendor/product inside an
  SDL GUID, so one captured profile can be re-pointed at another pad.
- `resolve_name(vendor, product, evdev_name)` — best available human name,
  preferring `sdl3_names()` (live SDL3 DB) then `db_name_for()`.
- `section()` / `set_section()` — surgical INI section replacement; every
  emulator gets its own extract/replace pair (`_az_*` for Azahar, `_mgba_*`,
  `_sect_*`, `_whole_*`) because no two config formats agree.
- `_ryujinx()` builds a full JSON profile; `_ryu_guid_vidpid()` handles
  Ryujinx's dashed GUID dialect.
- `backup(p)` before every write.

See `docs/CONTROLLER_MODELS.md` for the per-emulator format notes.

---

## 10. Standby

Idle → cover-art screensaver (`Screensaver.tsx`) → DPMS screen off →
optional `cpupower` governor drop. The box stays up: SSH, backend and OTA keep
working. Any controller button wakes it (evdev, so it works with the UI
asleep). A running game blocks the whole thing.

---

## 11. Release & OTA

**CI** (`.github/workflows/release.yml`) on push to `main`: auto-tags a patch
version, builds the frontend, then packages two assets —
`gamecore-ota.tar.gz` (backend, **the whole frontend/ including src**, config,
electron, update, install) and `gamecore-full.tar.gz` (+ assets, emu-configs)
— and publishes a GitHub release.

**On the box** (`update/linux.sh`): downloads the OTA asset, extracts, then
`rsync -a` into `GAMECORE_PATH` **excluding** `.venv/`, `emu/`, `config/`,
`emu-configs/`, `assets/overlays/`, `assets/logos/` — the box's own data.
`frontend/dist/` and `frontend/src/` are then mirrored with `--delete`
(pruning stale content-hashed bundles; `node_modules` lives in `frontend/`,
not `frontend/src/`, so it survives). Writes `VERSION`, updates pip deps,
clears the Electron HTTP cache, and schedules a restart through the detached
`gamecore-restart.service` — never from inside the script, which lives in the
backend's cgroup and would kill itself.

> The sources are shipped **because** the box can rebuild. Any `npm run build`
> there — the script's own fallback, or a hand-run one — regenerates `dist/`
> from local sources. When those sources were frozen at first install, a
> rebuild silently reverted the UI by weeks. Keep `frontend/src` in the OTA.

---

## 12. Security model

Full write-up in `docs/SECURITY.md`. The shape:

- **Everything binds `127.0.0.1`.** Core, all addons. No CORS middleware —
  behind Caddy everything is same-origin.
- **Caddy `:8443`** is the only LAN-facing port. `tls internal` (local CA,
  clients fetch it from `/gc/ca.crt`, QR code on the login page).
- **`forward_auth` → `GET /api/auth/verify`** gates every proxied path.
  `/api/*` is **403 from the LAN, always** — the core is never LAN-exposed.
  Addons are reached at `/roms/`, `/saves/`, `/rpcs3/`.
- **Addons contain zero auth code.** Caddy protects them; they only receive
  the `X-GC-User` header. `ADDON_BASE` gives each one its `root_path`.
- **The TV bypasses all of it** over loopback. Physical access is trust.
- Password reset: `gamecore-addon auth-reset`.
- Check with `ss -tlnp`: only `:8443` should be non-loopback.

---

## 13. Non-obvious things that will bite you

- **`config/` is sacred.** Excluded from OTA on purpose. Never write repo
  defaults over it.
- **`_hot_load()` re-reads JSON every call.** Editing `systems.json` on the box
  takes effect immediately — and a syntax error breaks the API immediately too.
- **`/ws` must stay registered before the `/` static mount.** The SPA
  catch-all would otherwise swallow the upgrade.
- **`start_new_session=True` is load-bearing.** Without it `killpg` would
  target the backend's own group.
- **Never SIGTERM an emulator** — several show a confirmation dialog. SIGKILL
  the group.
- **Overlays are X11-only** and silently disabled under Wayland. A dev machine
  on Wayland will never reproduce an overlay bug.
- **The UI is controller-only**, so Chromium's autoplay policy is overridden in
  `electron/main.js` (`autoplay-policy: no-user-gesture-required`) — gamepad
  buttons are not a "user gesture" and UI sounds would never play.
- **HUD toast text is untrusted.** It comes from WebSocket broadcasts, which
  include `/api/addons/notify` and Bluetooth device names. `escHtml()` exists
  for that reason — never interpolate raw.
- **A one-frame emulator crash is not a play session.** Hence the 5 s floor in
  `_watch()`.
- **Backend and Electron each have a `DEBUG` flag** (`backend/config.py`,
  `electron/main.js`). Both must be `false` on a device.

---

## 14. Development

```bash
# backend
pip install -r backend/requirements.txt
uvicorn backend.main:app --port 8765 --reload

# frontend (separate terminal) → http://localhost:5173
cd frontend && npm install && npm run dev

# electron (separate terminal)
cd electron && npm install && ELECTRON_DEV=1 npx electron .
```

`cd frontend && npm run build` runs `tsc` then `vite build` — a type error
fails the build, so it is the cheapest full check of the UI.
Backend tests: `pytest backend/tests`.

Testing gamepad code without hardware: override `navigator.getGamepads` with a
fake pad. Headless Chromium **does not fire `requestAnimationFrame` under
`--virtual-time-budget`**, which freezes both the splash and the 60 fps poll
loop — polyfill rAF onto `setTimeout` in the harness or nothing will happen.
