# 3 — Backend, routers

Every HTTP surface, file by file. Line numbers are indicative — the function
names are the contract.

All routers are mounted with `prefix="/api"` in `backend/main.py:41-55`.
Routers parse, validate and delegate; the logic lives in
[services](04-backend-services.md).

## Wiring — `main.py` (111 l.)

| Symbol | What it does |
|---|---|
| `lifespan(app)` | wakes the screen, adopts an orphaned game, creates the four background tasks; on shutdown cancels them and **awaits** them |
| `cross_origin_guard` | HTTP middleware — 403 on a non-GET write driven from another origin |
| `_origin_ok(headers)` | the rule itself, shared with `/ws` |
| `overlay_page()` | `GET /overlay` — serves the SPA to the transparent Electron window |
| `gc_addons()` | `GET /gc/addons` — same payload as `/api/addons`, on a path Caddy proxies **without auth** (the addon nav bar needs it pre-login) |
| `login_page()` | `GET /login` — self-contained login form for LAN clients |
| `websocket_endpoint(websocket)` | `WS /ws` — checks `Origin`, accepts, then reads forever; every send is a broadcast from `ws.py` |

### The lifespan does three things before starting the tasks

1. **`standby.resume_after_restart()`** — forces the screen back on
   unconditionally. Standby state is a module variable but its effect is not:
   `xset dpms force off` belongs to the X server, which SDDM owns and which does
   not restart with the backend. A box asleep when the backend restarted came
   back believing it was awake with the TV dark, and nothing could wake it (pad
   events arrive over evdev, not X, so DPMS never re-armed). Restarting the
   backend is what a stuck user will try — so that is what now fixes it.
2. **`process_manager.adopt_orphan()`** — re-attaches to a game a previous
   process left running, so the double-PS shortcut can still close it. See
   `config/session.json` in doc 7.
3. On shutdown, the four tasks are cancelled **and awaited**
   (`asyncio.gather(..., return_exceptions=True)`). `cancel()` alone only
   schedules the cancellation, so shutdown used to return with tasks still
   mid-await. The running game is deliberately left alone.

### The cross-origin guard

The core has no auth of its own and the box runs browsers that can reach it. A
page in the Firefox kiosk or in Stremio could auto-submit a form at
`http://127.0.0.1:8765/api/games/kill` and kill the running game. Non-GET
requests are refused when `Origin` names somewhere we are not serving, or when
`Sec-Fetch-Site` is `cross-site`.

It is **same-origin against the forwarded `Host`**, not a localhost allowlist:
`/login` and `/api/auth/*` arrive through Caddy from an address nobody can
predict, so an allowlist would have 403'd every LAN login. `localhost` and
`127.0.0.1` are additionally accepted as the same machine *on the backend's own
port* — Electron says one where the socket reports the other — but another local
app on another port is not the UI. A request with no `Origin` passes: curl and
the install scripts have none, and browsers always send one on a cross-origin
write. Full rationale in `docs/SECURITY.md`.

`/ws` needs the same check for a different reason: a WebSocket handshake is a GET
and is not subject to CORS **at all**, so any page could otherwise open
`ws://127.0.0.1:8765/ws` and read every event the UI sees.

Static mounts, in order: `/covers`, `/assets/logos`, `/assets/overlays`,
`/data`, `/themes`, then `/` → `frontend/dist` with `html=True`. The loop
`mkdir`s each directory first — a conditional mount decided at import time used
to leave `/covers` dead until a restart on a fresh checkout.

`/themes` is mounted through `_NoCacheStatic`, a `StaticFiles` subclass that
sets `Cache-Control: no-store` and refuses 304s. A theme is a folder of ES
modules the browser imports directly: the loader can bust the entry point's URL,
but the entry's own relative imports and its stylesheet resolve without that
query, so the browser would pin the first version it ever saw. Editing a theme
would then change nothing on screen, and a fix shipped by update could stay
invisible.

> `@app.websocket("/ws")` **must** stay declared before the `/` mount. The SPA
> catch-all would otherwise swallow the upgrade request.

## `systems.py` (63 l.) — the catalogue

| Function | Route | Notes |
|---|---|---|
| `_hot_load(path)` | — | re-reads the JSON **on every call**; no restart needed after editing, and a syntax error breaks the API instantly |
| `get_systems()` | — | `config/systems.json` |
| `get_apps()` | — | `config/apps.json` |
| `list_all()` | — | merged list — *the* lookup used by `games.py` and the covers pipeline |
| `list_systems()` | `GET /systems` | |
| `get_system(system_id)` | `GET /systems/{id}` | |
| `serve_logo(filename)` | `GET /assets/logos/{filename}` | |

## `games.py` (138 l.) — scanning and launching

| Function | Route | Notes |
|---|---|---|
| `scan_roms(roms_path, extensions, scan_dirs, system_id)` | — | wraps `rom_scanner.iter_rom_files`; skips vanished files instead of 500-ing; for `scan_dirs` systems, prefers the title from `local_media.get_title()` over the folder name (a PS3 folder is often just `BLES01234`) |
| `list_games(system_id)` | `GET /systems/{id}/games` | returns `[]` for apps |
| `launch_game(req)` | `POST /games/launch` | 404 unknown system · 409 already running · **403 if the ROM path resolves outside the system's `romsPath`** |
| `kill_game()` | `POST /games/kill` | |
| `get_session()` | `GET /games/session` | `process_manager.current_game or {}` |
| `_gamepad_trigger(rounds=3, delay=3.0)` | — | `sudo udevadm trigger` ×3, for Flatpak apps that only see a pad after a udev re-fire |

The path check is the security-critical line:

```python
Path(req.rom_path).resolve().relative_to(roms_root.resolve())
```

Without it, a crafted `rom_path` turns `/api/games/launch` into "run any
binary on the box".

## `covers.py` (28 l.) / `metadata.py` (19 l.)

| Function | Route |
|---|---|
| `get_cover(system_id, filename, refresh=False)` | `GET /covers/{system}/{file:path}` → `cover_pipeline.resolve()` |
| `get_metadata(system_id, filename)` | `GET /metadata/{system}/{file:path}` → `metadata.resolve()` |

`{filename:path}` (not `{filename}`) because ROM names contain slashes for
folder-based games.

## `media.py` (135 l.) — every artwork, not just the jacket

| Function | Route |
|---|---|
| `list_media(system_id, filename, refresh=False)` | `GET /media/{system}/{file:path}` → the catalogue + metadata |
| `get_media(system_id, filename, media_type)` | `GET /media/{system}/{file:path}/media/{type}` → one file |

`/covers` answers *"give me a cover"* and answers it exactly as it always has.
This router answers *"what does this game have?"* — `box-3d`, `clear-logo`,
`screenshot-gameplay`, `mix-rbv2`, `video`, `manual`, 54 types in all — so a
theme can be built on something other than a flat box front. Backed by
[`services/gamemedia`](04-backend-services.md#gamemedia--screenscraper--launchbox).

The catalogue is what makes it usable. Each entry carries `category`
(`box`, `cart`, `logo`, `screenshot`, `mix`, `marquee`, `artwork`, `icon`,
`bezel`, `video`, `document`, `theme`, `pinball`), `kind` (`image`, `video`,
`document`, `archive`) and `cached`. Without them a theme would have to
recognise 54 type names by hand to know which one is a box.

Three answers a theme has to tell apart, and the reason the JSON is shaped this
way rather than as a bare 404:

| Response | Meaning |
|---|---|
| `available: false` | no ScreenScraper account and no LaunchBox index on this box. Nothing is wrong with the game |
| `found: false, unreachable: true` | quota spent, or network down. Retrying later is worth something |
| `found: false, unreachable: false` | the sources answered and do not have this game. Final |

**Nothing is downloaded before it is asked for.** A scrape fetches the cover
and records the other ~27 media with their URL; the first request for a 3D box
costs one HTTP call and no ScreenScraper quota, every request after it costs a
`stat()`. Fetching everything up front would be ~34 s per game at the 1.2 s
ScreenScraper requires between calls.

A 404 on the file route carries the list of types the game *does* have, so a
theme never has to guess twice.

## `playtime.py` (36 l.)

`get_all_playtime()`, `get_system_playtime(system_id)`,
`get_game_playtime(game_key:path)` — straight reads of the `playtime` table
([schema](07-config-and-data.md#playtimedb)).

## `overlays.py` (69 l.) — bezel upload

| Function | Route | Notes |
|---|---|---|
| `_overlay_path(system_id)` | — | `assets/overlays/<id>.png` |
| `get_overlay(system_id)` | `GET /overlays/{id}` | |
| `_looks_like_image(head)` | — | **magic-byte check** — "the client Content-Type header proves nothing" |
| `upload_overlay(system_id, file)` | `POST /overlays/{id}` | |
| `delete_overlay(system_id)` | `DELETE /overlays/{id}` | |

## `addons.py` (141 l.) — registry and lifecycle

| Function | Route | Notes |
|---|---|---|
| `_cli()` | — | locates the `gamecore-addon` binary |
| `_registry()` | — | reads `config/addons.json` |
| `list_installed()` | `GET /addons` | consumed by the TV **and** by every addon's nav bar |
| `list_available()` | `GET /addons/available` | runs `gamecore-addon list --json`; may clone the repo |
| `notify(body)` | `POST /addons/notify` | generic hook: an addon pushes an event onto the core WebSocket |
| `_run_cli(action, name)` / `_pump()` | — | runs the CLI, streams its output over the WS |
| `_start(action, name)` | — | guards against two concurrent CLI runs |
| `install_addon` / `update_addon` / `remove_addon` | `POST /{name}/install`, `POST /{name}/update`, `DELETE /{name}` | |

The core never touches addon files itself — it shells out to the CLI. That is
why the registry stays consistent whoever ran the command.

> `/api/addons/notify` is reachable from any addon and its payload ends up in
> HUD toast HTML. See [gotchas](09-gotchas.md#untrusted-strings-reach-the-hud).

## `update.py` (100 l.) — OTA

| Function | Route | Notes |
|---|---|---|
| `_version_int(tag)` | — | tolerant `x.y.z` ordering — `v2.1.0-rc1` or a malformed tag must never crash the check |
| `check_update()` | `GET /update/check` | queries the GitHub releases API |
| `update_status()` | `GET /update/status` | `{running: bool}` — the backend is the source of truth |
| `apply_update()` | `POST /update/apply` | spawns `update/linux.sh` in the background; **409** if one is already running |
| `_run_update()` / `_pump()` | — | streams stdout line by line over the WebSocket, which is what the settings page renders live |

Same busy check as `addons.py`: a module-level task handle, tested and assigned
with no `await` in between, which is what makes it atomic. It is needed because
`update/linux.sh` wipes its work directory on entry and rsyncs from it into
`GAMECORE_PATH` — a second run did `rm -rf` underneath the first one's rsync.
And it was easy to trigger: `installing` was `UpdatePage`'s own component state,
so leaving the page and coming back re-mounted it as false and re-enabled the
button, during minutes in which the screen does not change. `UpdatePage` now
polls `/update/status` instead of trusting itself, and treats a 409 as "keep
following the running update".

The script is spawned with `start_new_session=True` and the 10-minute timeout
kills the **process group**, through the same helper `process_manager` uses to
kill a game. Killing only `bash` left its `rsync`, `pip` and `npm` writing into
`/opt/GameCore` after the UI had been told the update was aborted.

## `themes.py` (37 l.) — the theme catalogue

| Route | What it does |
|---|---|
| `GET /api/themes` | `{ sdk_version, active, themes[] }` — one validated manifest per folder in `config/themes/` |
| `POST /api/themes/active` | `{ id }` or `{ id: null }` for the default; persists to `config/theme.json` |

`POST` refuses an incompatible theme with a reason rather than storing it — an
incomplete theme would otherwise be selectable, fail to load, and leave the
player on the default UI wondering why their choice did nothing.

## `sysinfo.py` (30 l.)

`_primary_ip()` + `get_sysinfo()` → `GET /sysinfo`: IP, storage used/total/free,
`APP_VERSION`, and `controller_registry.snapshot()` (the P1…P4 slots with
battery). The TopBar and the controller screen both read it.

## `standby.py` (30 l.)

`get_standby()` (state + config), `set_config(cfg)` (`StandbyConfig` model,
persisted to `config/standby.json`), `wake()` → `standby.exit_standby()`.

## `controllers.py` (18 l.)

One path, two verbs: `POST /controllers/scan-mapping` →
`controller_profiles.scan_mapping()` and `DELETE` → `forget_mapping()`. The
whole point is in [8](08-controller-pipeline.md): GUID-based emulators cannot
be mapped programmatically, so the user configures the pad once in the
emulator's own UI and this snapshots it per controller.

`DELETE` is the inverse, and it exists because `restore()` refuses a snapshot
whose GUID names a different pad. The box already carries one such file, so
refusing without a way to remove it would only replace a silent overwrite with
a silent deadlock.

## `auth.py` (109 l.) — shared-password login

| Function | Route | Notes |
|---|---|---|
| `_client_ip(request)` | — | reads `X-Forwarded-For` (the request always arrives via Caddy) |
| `_set_session(resp)` | — | `gc_session` cookie: HttpOnly, Secure, SameSite=Lax, 30 days |
| `login(request)` | `POST /auth/login` | rate-limited by `auth.blocked_for(ip)` |
| `verify(request)` | `GET /auth/verify` | **the `forward_auth` endpoint.** 200 → Caddy passes the request through and copies `X-GC-User`; 302 → login page; 401 |
| `tls_ask(domain)` | `GET /auth/tls-ask` | **Caddy's `on_demand_tls` gate.** 200 approves minting a certificate |
| `logout()` | `POST /auth/logout` | |
| `change_password(request)` | `POST /auth/change-password` | bumps `generation` → every existing session dies |

`verify_password` is argon2id with the library defaults — 64 MiB and real CPU
time, deliberately — so `login` and `change_password` call it through
`asyncio.to_thread`. Inline, a burst of failed logins from the LAN froze the TV,
which talks to this same process.

`tls_ask` approves loopback, this machine's addresses on any interface, its
hostname, and any name that resolves to one of those (which is what keeps
MagicDNS working). The gate used to be Caddy's own admin API, which answers 200
to anything — so any LAN client could make the box mint certificates without
limit.

## `settings/` — the OS wrappers

Each module wraps a CLI and is careful about the environment, because a
systemd service has no session bus. All three define a local `_session_env()`
and an async `_run(*args)`.

### `settings/wifi.py` (183 l.) — `nmcli`

| Function | Route |
|---|---|
| `_wifi_iface()` | — active WiFi interface name |
| `scan_networks()` (+ `_rescan()`) | `GET /wifi/networks` |
| `_iface_ip(iface)`, `_ethernet_status()` | — |
| `wifi_status()` | `GET /wifi/status` — SSID, IP **and wired status**, so the UI can skip the WiFi flow entirely on ethernet |
| `connect_wifi(req)` | `POST /wifi/connect` — returns `wrong_password` distinctly |
| `disconnect_wifi()` | `DELETE /wifi/connect` |
| `_spawn_bg(coro, label)` | — background task helper with error logging |

The PSK goes to `nmcli` on **stdin**, via `nmcli --ask`. In argv it was visible
in `/proc/<pid>/cmdline` to every local user for the length of the connect. An
SSID beginning with `-` is refused rather than escaped: the SSID is positional
with nothing marking the end of the options, such a network is vanishingly rare,
and guessing at `nmcli`'s option parsing is not worth being clever about.

### `settings/audio.py` (88 l.)

`get_audio()`, `list_sinks()`, `set_volume(req)`, `set_sink(req)`.

### `settings/bluetooth.py` (118 l.) — `bluetoothctl`

`list_devices()`, `start_scan()` (returns immediately, `_do_scan()` runs 8 s in
the background), `connect_device`, `disconnect_device`, `remove_device(mac)`.

> Bluetooth device names are attacker-controlled strings that reach the UI.
> They are one of the reasons `escHtml()` exists in Electron.
