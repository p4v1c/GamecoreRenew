# 4 — Backend, services

Where the logic lives. No FastAPI import exists in this directory: a service
is callable from a test, a script, or another service.

[`controller_profiles.py`](08-controller-pipeline.md) is big enough to have its
own document.

---

## process_manager.py

Module-level singleton: `process_manager = ProcessManager()`.

State: `_proc`, `_launching`, `_game_key`, `_system_id`, `_start_time`,
`_exec_path`, `_launch_args`.

| Member | Role |
|---|---|
| `_display_env()` | rebuilds a GUI environment for a systemd child — see [1](01-runtime-topology.md#environment-reconstruction) |
| `is_running` | `_launching or (_proc and returncode is None)` |
| `current_game` | `{game_key, system_id}` or `None` |
| `launch(exec_path, exec_args, rom_path, game_key, system_id)` | builds argv (`shlex.split` + ROM), spawns, broadcasts `game:started`, starts `_watch()` |
| `kill()` | `_flatpak_kill()` then `_proc_kill()` |
| `_flatpak_kill()` | finds the app-id (token after `run`) and runs `flatpak kill <app-id>`, 1 s timeout |
| `_proc_kill()` | `os.killpg(os.getpgid(pid), SIGKILL)`, falling back to `proc.kill()` |
| `_watch()` | awaits exit, records playtime if > 5 s, broadcasts `game:finished` |

Three decisions that look odd until you know why:

1. **`_launching` is claimed synchronously**, before the first `await`. Two
   concurrent `launch()` calls would otherwise both pass the `is_running`
   check while the first was still awaiting the spawn.
2. **`start_new_session=True`** puts the child in its own process group. Without
   it, `killpg` would reach the backend itself.
3. **SIGKILL, no SIGTERM.** Several emulators answer SIGTERM with a
   confirmation dialog that cannot be clicked from a gamepad.

The module header also records a real bug: an earlier revision exported
`SDL_GAMECONTROLLERDB`, a variable SDL has never read, so the vendored mapping
database was silently ignored. The correct name is
`SDL_GAMECONTROLLERCONFIG_FILE`.

---

## `themes.py` — discovery and the completeness rule

`SURFACES = {"splash", "shell"}`, `SDK_VERSION = 1`.

`_read_manifest(dir)` returns a validated manifest or `None` with a logged
reason. It rejects a folder whose `theme.json` is unreadable, whose `id` does
not equal the directory name (the id is a directory name, never a path —
`_safe_id` enforces `^[a-z0-9][a-z0-9_-]{0,63}$`), or whose `entry` file is
missing.

A theme is `compatible` only if its `api` is not newer than `SDK_VERSION` **and**
it declares every surface. Anything less is listed but not selectable, with the
reason in `warnings` — the UI needs to say *why*, not just refuse. That rule is
the one users feel: it is what makes a theme all-or-nothing, so there is never a
half-dressed UI.

Covered by `backend/tests/test_themes.py`.

## `gamepad_monitor.py` (280 l.) — evdev, the source of truth for input

Runs as a lifespan task. It exists because the browser Gamepad API cannot be
trusted for the Guide button and cannot see anything while a fullscreen
emulator owns the display.

| Function | Role |
|---|---|
| `run()` | main loop — rescans for devices every few seconds, watches each |
| `_find_gamepad_devices()` | `path → (name, uniq, is_pad, vendor, product)` for every readable `/dev/input/event*` |
| `_can_read(path)` | permission probe |
| `_watch_device(path)` | reads one device until it disconnects or is cancelled |
| `_on_guide_pressed()` | the double-press logic, then `POST /api/games/kill` |

It also drives `controller_registry` on connect/disconnect,
`controller_profiles.apply_profile()` / `release_profile()` for the pad's
per-emulator configuration, and `standby.on_input()` — which is how a
controller button wakes a sleeping box.

---

## `controller_registry.py` (89 l.) — console-style player slots

Assigns P1…P4 and keeps them stable across reconnects.

| Function | Role |
|---|---|
| `normalize_mac(value)` | extracts a lowercased `aa:bb:…` from any MAC-ish string |
| `key_for(uniq, path)` | stable key: the MAC when known, else the device node |
| `has(key)` / `label_for(key)` | lookups |
| `connect(key, label)` | assigns the **lowest free slot**; idempotent for a known key |
| `disconnect(key)` | frees the slot, returns the player number it held |
| `player_for_mac(value)` | slot for any MAC-bearing string — used to attach a sysfs battery to a player |
| `snapshot()` | `[{player, label}]` ordered by slot — what `/api/sysinfo` returns |

---

## `battery.py` (116 l.)

| Function | Role |
|---|---|
| `read_batteries()` | sysfs → `[{name, level, charging}]` |
| `_check(batteries)` | **pure** — returns the alerts to send for this poll, so it is unit-testable |
| `run()` | polls and broadcasts `gp:battery` |

The UI renders it as a toast; in-game Electron paints a native always-on-top
HUD instead, because the React toast is hidden under the emulator.

---

## `standby.py` (152 l.)

| Function | Role |
|---|---|
| `load_config()` / `save_config(cfg)` | `config/standby.json` |
| `get_state()` | `active` / `screensaver` / `asleep` |
| `_run_cmd(*argv)` | helper, returns success |
| `_screen(on)` | DPMS on/off |
| `_governor(gov)` | `cpupower frequency-set -g …` — optional, needs a sudoers rule |
| `_enter(stage)` | stage transition + WS broadcast |
| `exit_standby()` | wake |
| `on_input()` | called from the evdev loop on any controller button |
| `run()` | the idle poll loop |

A running game blocks standby entirely.

---

## `cover_pipeline.py` (132 l.) — orchestration

| Function | Role |
|---|---|
| `resolve(system, filename, refresh=False)` | the four-tier resolution, [drawn here](02-request-flows.md#3-resolving-a-cover) |
| `_id_urls(kind, value)` | candidate `(url, ext)` pairs for a disc ID, best first |
| `_regions(letter)` | region-code expansion for GameTDB paths |
| `_fetch_by_id(kind, value, base)` | downloads the first candidate that exists |

Negative results are written as `.miss` files, honoured for 7 days, so an
offline box does not retry the network on every scroll.

## `local_media.py` (150 l.) — read the game itself

Offline and exact. Nothing here guesses from a filename.

| Function | Role |
|---|---|
| `_ps3_icon(rom)` / `_ps3_sfo(rom)` | `PS3_GAME/ICON0.PNG`, `PARAM.SFO` |
| `_ps4_icon(rom)` / `_ps4_sfo(rom)` | `sce_sys/icon0.png`, `param.sfo` |
| `_psp_read(rom, inner)` / `_psp_sfo(rom)` | pulls a file **out of the ISO** via `iso9660` |
| `_gc_wii_id(rom)` | 6-char game ID from a GameCube/Wii image header |
| `_playstation_serial(rom)` | PS1/PS2 serial (`SLUS-20946`) from `SYSTEM.CNF` inside the image |
| `extract_icon(system_id, rom, dest)` | writes the embedded icon, or `None` |
| `get_title(system_id, rom)` | real title from embedded metadata — why PS3 folders show a name, not `BLES01234` |
| `disc_id(system_id, rom)` | `(kind, id)` for an exact online lookup, e.g. `("wii", "GALE01")` |

## `iso9660.py` (106 l.) — minimal ISO reader

`class Iso9660` with `open(path)` (classmethod, autodetects the sector layout,
returns `None` for a non-ISO such as a compressed `.cso`), `_sector`,
`_read_extent`, `_entries` and `read_file("PSP_GAME/ICON0.PNG")`
(case-insensitive). Supports `with` via `__enter__`/`__exit__` — use it, the
factory only closes the handle on its own failure paths.

## `scraper.py` (242 l.) — the network tier

| Function | Role |
|---|---|
| `_normalize(name)` | lowercase alphanumerics, for fuzzy matching |
| `_name_variants(base)` | the spellings to try against the CDN index |
| `_get_index(client, system_name)` | fetches and caches the libretro directory listing |
| `fetch_cover(rom_path, system_id, dest)` | libretro first, then TheGamesDB |
| `_fetch_tgdb_cover(name, system_id, dest)` | needs `THEGAMESDB_API_KEY`, silently skipped otherwise |
| `_region_rank(n)` | prefers the region you probably want when several match |

## `metadata.py` (119 l.)

`resolve(system, filename)` → description, year, genres, players, rating.
Disk-cached and negative-cached. `_genre_names(client)` resolves the genre id
table once; `_search_name(system, filename)` builds the query;
`_fetch_tgdb(platform_id, name)` does the call.

## `sfo.py` (34 l.)

`parse_bytes(d)` and `parse(path)` — PARAM.SFO key/value table, `{}` on any
error. Same binary format on PS3, PS4 and PSP. The addons repo has its own
copy in `shared/py/`; this one additionally exposes `parse_bytes()` for data
already in memory.

## `rom_scanner.py` (34 l.)

`clean_name(filename)` (strips extension and bracketed tags like `[!]`,
`(USA)`), `matches_ext(filename, extensions)`, and
`iter_rom_files(roms_path, extensions, scan_dirs)` — alphabetical, applying the
common exclusions. The rom-manager addon keeps a mirrored copy.

## `prefetch.py` (60 l.)

`run()` walks the library at startup and calls `warm(system, filename)` so the
first scroll is not a spinner.

---

## `overlay_monitor.py` (277 l.) — X11 watcher, runs as a subprocess

Not imported by the backend: Electron spawns it and speaks JSON-lines over
stdio.

```
stdin  ← {"cmd":"watch","system_id":"dolphin","config":{…}}  |  {"cmd":"stop"}
stdout → {"event":"window:ready","system_id":…,"rect":{x,y,w,h}}
       → {"event":"window:waiting"|"window:closed"|"error", …}
```

| Symbol | Role |
|---|---|
| `emit(obj)` / `emit_error(msg)` | one JSON object per line on stdout, flushed |
| `X11Manager._client_windows()` | top-level windows via `_NET_CLIENT_LIST`, with a recursive fallback |
| `X11Manager.find_window(wm_classes)` | first window whose `WM_CLASS` matches |
| `X11Manager.dump_windows()` | debug helper — all `WM_CLASS` values |
| `X11Manager.force_rect(wid, x, y, w, h)` | leaves fullscreen, removes decorations (Motif hints), moves and resizes |
| `X11Manager.get_rect(wid)` | geometry translated to root coordinates |
| `X11Manager.window_exists(wid)` | liveness |
| `OverlayMonitor.watch(system_id, cfg)` | starts the watch thread |
| `OverlayMonitor.stop()` / `_run()` | lifecycle |
| `main()` | the stdio loop |

`force_rect()` leaves fullscreen with a `_NET_WM_STATE` **ClientMessage to the
root window**, as EWMH requires for a mapped window. Writing the property
directly (what it used to do) clears *every* state at once —
`_NET_WM_STATE_ABOVE` included — and desyncs the WM's bookkeeping.

`_WAYLAND_SESSION` disables the whole module when `WAYLAND_DISPLAY` is set.

## `fullscreen_enforcer.py` (130 l.)

The same EWMH toolbox pointed the other way, for apps with no fullscreen CLI
flag (`"fullscreen"` key on a system entry).

`_iter_client_windows`, `_find_window(disp, wm_classes)`, `_is_fullscreen`,
`_request_fullscreen` (adds `_NET_WM_STATE_FULLSCREEN` by client message),
`_enforce_sync(system_id, wm_classes, timeout_s)`, and the async
fire-and-forget `enforce(system_id, cfg)`.

---

## `auth.py` (150 l.) — shared password

| Function | Role |
|---|---|
| `_write_private(path, data)` | atomic write, **0600 from the very first byte** |
| `_auth()` / `_secret()` | read `config/auth.json` and `config/auth_secret` |
| `is_configured()` | whether a password was ever set |
| `set_password(new, reset_secret=False)` | argon2id hash; **always bumps `generation`** |
| `verify_password(password)` | argon2 verify |
| `_mac(secret, payload)` | HMAC-SHA256 |
| `make_cookie()` | `expiry.generation.HMAC(secret, "expiry.generation")` |
| `check_cookie(value)` | expiry + generation + MAC |
| `blocked_for(ip)` | seconds still to wait — 0 means not blocked |
| `register_failure(ip)` / `register_success(ip)` | in-memory backoff, exponential after 5 failures |

Bumping `generation` is how "change password" invalidates every live session
without storing any session state.

---

## `ws.py` and `db.py` (backend root)

`ws.py` — `connect(ws)` (accepts and replays `game:running` if a game is
already up), `disconnect(ws)`, `broadcast(event, data)` (drops dead clients),
`set_current_game(game)`.

`db.py` — `get_db()` returns a live `aiosqlite` handle, re-opening it if the
cached one has gone stale; `init_db()` creates the `playtime` and `sessions`
tables. Schema in [7](07-config-and-data.md#playtimedb).
