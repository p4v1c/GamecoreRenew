# 3 — Backend, routers

Every HTTP surface, file by file. Line numbers are indicative — the function
names are the contract.

All routers are mounted with `prefix="/api"` in `backend/main.py:41-55`.
Routers parse, validate and delegate; the logic lives in
[services](04-backend-services.md).

## Wiring — `main.py` (111 l.)

| Symbol | What it does |
|---|---|
| `lifespan(app)` | creates the four background tasks on startup, cancels them on shutdown |
| `overlay_page()` | `GET /overlay` — serves the SPA to the transparent Electron window |
| `gc_addons()` | `GET /gc/addons` — same payload as `/api/addons`, on a path Caddy proxies **without auth** (the addon nav bar needs it pre-login) |
| `login_page()` | `GET /login` — self-contained login form for LAN clients |
| `websocket_endpoint(websocket)` | `WS /ws` — accepts, then reads forever; every send is a broadcast from `ws.py` |

Static mounts, in order: `/covers`, `/assets/logos`, `/assets/overlays`,
`/data`, then `/` → `frontend/dist` with `html=True`. The loop `mkdir`s each
directory first — a conditional mount decided at import time used to leave
`/covers` dead until a restart on a fresh checkout.

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
| `apply_update()` | `POST /update/apply` | spawns `update/linux.sh` in the background |
| `_run_update()` / `_pump()` | — | streams stdout line by line over the WebSocket, which is what the settings page renders live |

## `sysinfo.py` (30 l.)

`_primary_ip()` + `get_sysinfo()` → `GET /sysinfo`: IP, storage used/total/free,
`APP_VERSION`, and `controller_registry.snapshot()` (the P1…P4 slots with
battery). The TopBar and the controller screen both read it.

## `standby.py` (30 l.)

`get_standby()` (state + config), `set_config(cfg)` (`StandbyConfig` model,
persisted to `config/standby.json`), `wake()` → `standby.exit_standby()`.

## `controllers.py` (18 l.)

One route: `POST /controllers/scan-mapping` → `controller_profiles.scan_mapping()`.
The whole point is in [8](08-controller-pipeline.md): GUID-based emulators
cannot be mapped programmatically, so the user configures the pad once in the
emulator's own UI and this snapshots it per controller.

## `auth.py` (109 l.) — shared-password login

| Function | Route | Notes |
|---|---|---|
| `_client_ip(request)` | — | reads `X-Forwarded-For` (the request always arrives via Caddy) |
| `_set_session(resp)` | — | `gc_session` cookie: HttpOnly, Secure, SameSite=Lax, 30 days |
| `login(request)` | `POST /auth/login` | rate-limited by `auth.blocked_for(ip)` |
| `verify(request)` | `GET /auth/verify` | **the `forward_auth` endpoint.** 200 → Caddy passes the request through and copies `X-GC-User`; 302 → login page; 401 |
| `logout()` | `POST /auth/logout` | |
| `change_password(request)` | `POST /auth/change-password` | bumps `generation` → every existing session dies |

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

### `settings/audio.py` (88 l.)

`get_audio()`, `list_sinks()`, `set_volume(req)`, `set_sink(req)`.

### `settings/bluetooth.py` (118 l.) — `bluetoothctl`

`list_devices()`, `start_scan()` (returns immediately, `_do_scan()` runs 8 s in
the background), `connect_device`, `disconnect_device`, `remove_device(mac)`.

> Bluetooth device names are attacker-controlled strings that reach the UI.
> They are one of the reasons `escHtml()` exists in Electron.
