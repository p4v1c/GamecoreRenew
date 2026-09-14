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
   mid-await. The Store worker is stopped first: its transfer is cancelled,
   its job-owned partial is removed, and its row is settled as interrupted
   before shutdown returns. The running game is deliberately left alone.

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

## `overlays.py` (~310 l.) — resolve, measure, choose, deposit

The whole bezel surface. Everything validates `system_id` against the shared
`SYSTEM_ID_RE` (backend/utils.py) — the id names a directory under a served
root, and `..` in one would read files anywhere the backend user can reach.

| Function | Route | Notes |
|---|---|---|
| `resolve_overlay` | `GET /overlays/resolve/{id}?rom=` | what one launch draws: source/asset/hole/console/announced/measure. **Never 404s** — "no bezel" is the normal answer for the 16:9 systems |
| `install_pack` | `POST /overlays/packs/{id}` | files a Bezel Project pack an addon downloaded; source must resolve inside `addons_dir()` |
| `record_measurement` | `POST /overlays/measured/{id}` | the monitor's report; `console` in the body must be one the pack declares, or a LAN caller could write arbitrary cache keys |
| `overlay_choices` | `GET /overlays/choices/{id}?rom=` | current preference + options that actually exist on this box |
| `set_overlay_choice` | `PUT /overlays/choices/{id}` | `"off"`, a bezel filename, or null for automatic; validated against `available()` |
| `overlay_slots` | `GET /overlays/{id}/slots` | every bezel this system CAN have, filled or not, with measured `ratio` and the pack-declared `expected_ratio` — what a manager UI needs and `choices` cannot answer |
| `upload_console_overlay` | `POST /overlays/{id}/consoles/{cid}` | a bezel for ONE console of a multi-console pack; `cid` must be declared in `roms.consoles` |
| `delete_console_overlay` | `DELETE /overlays/{id}/consoles/{cid}` | the counterpart — without it a bezel dropped on the wrong console could only ever be replaced |
| `get_overlay` / `upload_overlay` / `delete_overlay` | `GET/POST/DELETE /overlays/{id}` | the system-level PNG |
| `_receive_bezel` | — | shared upload body: magic bytes, 10 MB cap (`bezels.MAX_BEZEL_BYTES`), and **a 422 for an image with no transparent area** — a valid PNG with no hole is a rectangle painted over the whole game, and every other check passes it |
| `_looks_like_image(head)` | — | **magic-byte check** — "the client Content-Type header proves nothing" |

Uploads write through `tempfile.mkstemp` in the destination directory —
deliberately NOT `utils.atomic_write`: two concurrent uploads must not share a
temp name, which is a different problem from a power cut.

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

---

## Routers added by the recent phases

These arrived with features that did not exist when the inventory above was
written. Each is listed with what it serves and the decision that is not visible
from the endpoint list.

### `catalog.py` (292 l.) — installing while the box is running

`GET /catalog`, `POST /catalog/{pack_id}/install`, `POST /{pack_id}/remove`,
`POST /{pack_id}/reconfigure`, `GET /catalog/busy`, `GET /catalog/ota/status`,
`POST /catalog/ota/refresh`.

`busy` exists because installing a Flatpak is minutes long and the player is
holding a gamepad: the screen has to be able to say "already working" rather than
queue a second install behind the first. The `ota/*` pair drives the signed
catalogue channel — see [10](10-catalog-and-install.md#three-tiers-and-the-signed-remote-one).

### `store.py` — searching for a game, and the queue of what was asked for

`GET /store/provider`, `GET /store/systems`, `GET /store/search?system=&q=`,
`GET /store/jobs`, `POST /store/jobs`, `POST /store/jobs/{job_id}/cancel`.

Two halves, and the line between them is the point. The search routes ask a
question: they start nothing, hold no lock and remember nothing. The job routes
write down a request that outlives the screen it was made on.

The three search shapes are unchanged by the arrival of a real provider — that
is the point of the seam, and `provider`/`live` are the fields that carry the
difference to the screen.

**Why a search runs here and not in the browser.** A search provider is
configured with an indexer's URL and its API key, and a key that reaches the
browser is a key in the page source and in the devtools pane of a television
nobody logs out of. The frontend asks and never learns how the answer was
obtained. The provider interface is
[`services/store/search.py`](../../backend/services/store/search.py).

**Two providers.** The demo one invents its rows and says so (`live` is `false`
in every answer) and reaches nothing. The
[Prowlarr](../../backend/services/store/prowlarr.py) one queries an indexer
aggregator **the box owner runs themselves**: GameCore never installs, manages,
updates or removes it, and knows only a URL and an API key. That is what keeps
a .NET service unit, a second LAN port and a managed/external split in the pack
manifest off a box whose whole hardening pass was about reducing the LAN
surface to Caddy on `:8443`. The list of indexers is not here either — it is in
the owner's instance, which is the only place that can know what they have
access to, and this repository ships no tracker, no category map and no default
source.

**Which one answers is a file, not a variable.** With
`config/store-prowlarr.json` present and usable, the Prowlarr provider answers;
without it — the state of every box that has never heard of Prowlarr — the demo
one does, banner included. `GAMECORE_STORE_SEARCH_PROVIDER` overrides in both
directions and is not needed in either. See
[7 — `config/store-prowlarr.json`](07-config-and-data.md#configstore-prowlarrjson).

**A result has to prove which console it is for, and prove it better than the
neighbours.** A row survives only when something names this console — a file
suffix only it declares, or one of the names it goes by — and when the name it
carries is one the catalogue *completes*, only when no other console is named
more precisely on the same row. `PlayStation` is a whole word inside
`PlayStation 3`, so without that second half the PlayStation 1 console kept
PlayStation 3, PlayStation 4 and PSP releases; `dolphin` kept Wii U ones, and
`melonds` kept anything with a stray `DS` in it. Which names are abbreviations
is one pass over `catalog/*/pack.json`, exactly like the unique-suffix rule
beside it — there is no console table here to go stale
([14](14-store-ingestion-matrix.md) §5.2).

**The suffix band fired zero times on real rows, and is kept anyway.** Measured
with [`scripts/prowlarr-filter-check.py`](../../scripts/prowlarr-filter-check.py)
against a real Prowlarr — 110 rows over `gran turismo`, `street fighter` and
`mario` — every console's "by suffix" count was 0: those indexers name a
release `Title - Platform` and attach no file extension, so the name band is
carrying the whole filter today. The band stays because it is idle, not wrong:
`.z64` is the one kind of evidence that cannot be mistaken, other sources do
name files, and Prowlarr answers a `fileName` field when the indexer sets one.
That script needs an instance and an API key, so it is a manual check and not a
gate; the gate is `backend/tests/test_store_prowlarr.py`, which runs offline
against recorded answers.

**A 502 says nothing about why.** Down, refusing the key, slow, and answering
something unexpected are four log lines and one answer to the browser: the
reason is logged locally and never returned, because it can carry an address,
and a provider's could carry a key. The provider holds up the other half — every
message it raises is built from safe parts only, and nothing lifted out of a
response reaches a `SearchResult` unredacted (Prowlarr's own `downloadUrl`
carries `?apikey=…`).

**Why `system` is required and never optional.** The ingestion class of a
download is a property of the pair (system, incoming format) — the same `.zip`
is the ROM on `mame` and packaging on `snes9x` — and the directory it has to
land in belongs to the system
([14](14-store-ingestion-matrix.md) §0, §1.3). A result with no console attached
could be neither placed nor classified, and no indexer labels its own results by
console reliably enough to attach one afterwards. A console that is **not
installed** is a 409 rather than an empty answer: the download would land in a
directory nothing scans, for a tile that is not on the grid.

A **search** starts nothing and holds no lock — it is a question, not an
action, so there is no busy state and no `catalog:done` to wait for.

#### The queue — three routes, and deliberately three

Put one in, read them back, take one out. No route restarts a job, no route
deletes a row and there is no "clear finished": each would be a second way to
change a state that
[`services/store/jobs.py`](../../backend/services/store/jobs.py) owns exactly
one way of changing, and that is the shape step 7 already learned not to ship.

```
queued ──► running ──► done
  │           ├──────► failed
  │           └──────► cancelled
  └──────────────────► cancelled
```

**Running a job is resolve, materialize, inspect/classify, shape, check, then
import.**

*Resolving* turns the job's opaque `source` into an `AcquiredTarget`: a direct
HTTPS URL, plus the size and info hash it takes to check the bytes are the ones
that were asked for. It moves no bytes.
[`services/store/realdebrid.py`](../../backend/services/store/realdebrid.py) is
one, and `jobs.acquisition_provider()` answers `None` on a box with no
`config/store-realdebrid.json` — which is every box until its owner puts one
there.

*Materializing* streams that target to
`<DATA>/store/jobs/<job-id>/<filename>`, through `.part` and an atomic rename.
It checks the resolved size and free space first (including 256 MiB left for
the appliance), rejects HTTP errors, mismatched lengths and HTML error pages,
and never receives `roms_dir`. Validation and import remain separate later
stages ([14](14-store-ingestion-matrix.md) §5).

*Inspecting* reads the completed job work area and the selected pack, then
persists one of matrix §5's classes A–F on the job as `ingestion_class`. Its
four predicates are exactly the contract's: archive extension declared;
declared non-archive member present; declared disc descriptor; `scanDirs`.
There is no system table. Archive member names are streamed from `7z l` with
hard limits on count and total name bytes; no member is extracted and no
downloaded path is moved, renamed or deleted.

Completeness is decided here because nothing after the Store checks it. A
declared disc descriptor is class E only with every companion it names (`.ccd`
also requires `.img` and `.sub`, `.mds` its `.mdf`); class F requires a
top-level directory. The current acquisition contract materializes one file,
so a lone `.cue`/`.gdi` or any loose file for a `scanDirs` pack fails early and
names what is missing. Inspection records the class before the worker settles
the failure; it does not repair the multi-file acquisition.

*Transforming* gives those classified bytes the shape their class requires —
§5.1's transform column, read off the persisted verdict and never off a system
list. `A` unpacks if archived, `B` and `C` do nothing (unpacking a `mame`
romset deletes the game, §2.1), `D` unpacks only when the container extension
is undeclared, `E` keeps the descriptor and its tracks together, and `F` keeps
the game directory whole. A and D share one branch, because "is the archive's
own extension declared?" is the one predicate both need (§2.4).

It is the first step allowed to produce modified content, and three properties
bound what that can cost:

- **the source is never touched.** The shape is produced *beside* the download,
  in a fresh `store/jobs/<job-id>/ingest/`; every source path is opened `"rb"`
  and nothing else, every destination is created with `O_EXCL`, and the only
  removal in the module computes its one path from the validated job id plus
  that constant. The download is not deleted here on success or on failure —
  tidying is import's decision. `test_store_transformer.py` fingerprints the
  work area before and after every class, including a transformation that dies
  halfway;
- **space is checked before the first byte.** Producing beside the source
  doubles the footprint, so the plan is built in full, priced, and compared to
  the free space plus the same 256 MiB reserve the download keeps — a refused
  transformation has created nothing at all;
- **it is bounded, cancellable and it reports.** Production streams in chunks
  inside the event loop, exactly as the download does, with progress persisted
  and broadcast on `transformed_bytes` / `transform_total`. Cancellation and
  failure both remove the produced directory and nothing else.

*Validating* judges the produced shape against its class — §5.1's validate
column — and is the last thing that looks at it before import (17). `A` needs a
member with a declared extension, `B` magic bytes, `C` an archive that opens
under the name it arrived with, `D` a readable header, `E` the descriptor and
every file it names, `F` the identity file. The completeness arithmetic is
`inspector._missing_descriptor_files` and the identity parse is
`gamemedia/identity.read_sfo` — the reader the scraper already uses on these
trees, so a tree validation accepts is one the scraper can name.

**It changes nothing.** No `mkdir`, no `unlink`, no `open` in a writing mode:
the source and the produced shape are both byte-identical afterwards, in
success and in refusal, and `test_store_validator.py` fingerprints both in
every class. A download it turns down is still there — the fix may be one
different release away, and deleting what was refused takes that decision away
from the player.

**It reads little.** A signature is a handful of bytes at a known offset, so
that is what is read: `seek`, then `read(len(magic))`. An 8 GB `.xci` is judged
by a few hundred bytes, and a `.cdi` by its *last* eight, which is where
DiscJuggler puts its version word. A whole-file checksum was the obvious
alternative and is worthless here — `AcquiredTarget.info_hash` hashes torrent
metadata, not this file's content, so there is nothing to compare a digest
against.

**What "magic bytes" means when the format has none.** The table in
[`services/store/validator.py`](../../backend/services/store/validator.py) is
keyed on the **format** and never on the system (§0, §5.2), and every entry
carries the source it was taken from plus one of two strengths:

| strength | meaning | a miss |
|---|---|---|
| **proof** | the format's own readers require the field, and the extension names exactly one format | **refuses**: `.zip` `.7z` `.gz` `.chd` `.rvz` `.wbfs` `.cso` `.pbp` `.wux` `.gcm` `.rpx` `.xex` `.nsp` `.3ds` `.cia` `.nes` `.unf` `.unif` `.fds` `.gb` `.gbc` `.gba` `.nds` `.n64` `.z64` `.v64` |
| **hint** | the extension names several formats, or there is material evidence of a variant without the field | **reports**: `.iso` `.cdi` `.wad` `.mds` `.ccd` `.gen` `.32x` `.xci` |

Everything else is **unverifiable** and says so: `.sfc` `.smc` `.sms` `.gg`
`.pce` `.sgx` `.sg` `.md` `.smd` `.bin` are raw memory or track dumps with no
field any reader checks — which is exactly what §5.1 records when it says the
SNES has no exclusive suffix usable as proof. Inventing a check for one of
those would be worse than having none, because it would look like a filter and
catch nothing.

So no class ends in a check that cannot fail: **a file the library would list
must not be empty**, and a set must carry every file its descriptor names. That
floor is what lets a `.sfc` be refused when the download is 0 bytes — which
happens, because the acquisition size is `0` whenever the service does not say
and nothing before this point compared a length.

And a signature never proves the download is the *right* game: the region, the
revision, that it is not a bad dump. Those are questions about content, not
about format, and no header answers them.

**A required BIOS is named, never a refusal.** §5.3 rule 4. Seven systems
declare a `required: true` file and the box refuses the launch without it,
naming the file (`backend/services/bios.py:222-250`). Validation asks
`bios.missing_required` — the same function that gate calls — one step earlier,
so the player learns at download time; the answer lands on the row as
`bios_warning` and changes no verdict. Refusing the import as well would delete
the one thing the player could still act on: the game would not be there to
play once they copied the BIOS in.

Two rules that are not about bytes. A member whose stored name is absolute or
carries `..` is refused, and containment does not depend on that refusal: §2.4
requires flat extraction anyway, so a member is only ever written to
`ingest/<last component of its name>`, with both separators folded first so a
Windows-written `..\..\x.nes` cannot smuggle one past a POSIX basename.
Symlink and directory members are never written. And a name the library scan
would drop in silence — one starting with `.` or containing `example`, §5.3
rule 2 — refuses the transformation and names the file, rather than emitting a
download that reported success and left no tile, or renaming a ROM and filing
the game under an identity that is not its own. The rule reaches the names that
land at the top level of the ROM directory, which is what the scan iterates: a
class F game directory is judged by its own name and never by its contents, and
a track a descriptor already hides is not judged at all.

`AcquiredTarget.info_hash` identifies the torrent; it is a hash of torrent
metadata and piece hashes, not a checksum of the one unrestricted file (which
may be one member of a multi-file torrent). The materializer therefore cannot
compare it to the downloaded bytes. Its available completeness proof is the
resolved byte length over HTTPS; content validation belongs to the later stage.

*Importing* is the only stage allowed to write below `<DATA>/emu/`. It takes
the validated `ingest/` shape and the job's pack-derived `roms_dir`, verifies
that field still equals the system pack's `emu/<dir>`, then publishes A–E as
flat files and F as a top-level game directory. Each complete object crosses
to a hidden name in the target filesystem with `os.rename`; publication is a
no-replace operation, so an existing filename is named and left byte-identical.
If rename reports `EXDEV`, the import is refused: copying is not a fallback,
because a grid scan could observe the partial destination.

The `.nsp` decision is **warn and import**. The repository can prove only that
the bytes are a PFS0 package, not whether they are a base, update or DLC. The
`800` title-id convention remains unverified by §6.2, so it refuses nothing.
Refusing every `.nsp` would reject the working base games that make up the
Switch library; importing silently would hide the known bad-tile risk. The
successful `done` row therefore carries the ambiguity warning.

On success the job work directory is removed, avoiding a second copy that may
be 8 GB. An import refusal removes the produced `ingest/` duplicate but keeps
the downloaded source for retry or diagnosis. Validation refusals retain both
as before, because import was never entered and the validator is read-only.

Jobs stop honestly, with distinct outcomes:

| outcome / reason | what it means |
|---|---|
| *"no acquisition provider is configured on this box"* | no Real-Debrid token; nothing was attempted |
| *"this box can find this download but cannot store it yet"* | the source resolved, and there is nowhere to put what it found |
| `done` | the validated shape was published in the pack's ROM directory |
| *"the library already contains 'X'; it was not overwritten"* | import refused a collision; the existing game is unchanged |
| *"the Store work area and ROM library are on different filesystems…"* | atomic rename is impossible, so no copy was attempted |
| *"Zelda (USA).nes is not an iNES image: the bytes its format requires are not there …"* | validation refused: the file is not what its extension announces |
| *"the download is empty: X has no content …"* | the floor every format has — a complete-looking download of nothing |
| *"this download cannot be added because its name starts with a dot: …"* | the library scan would drop the file without a word (§5.3 rule 2), so it is refused rather than emitted or renamed |
| *"the archive contains a member that points outside the download …"* | an archive tried to write outside the work area; nothing was unpacked |
| *"incomplete class E download: … is missing …"* | acquisition delivered a descriptor without all of its companions |
| *"incomplete class F download: a complete game directory is missing …"* | acquisition delivered loose bytes where the pack requires a directory |

A player who reads the second has a working account and nothing to fix, which
the first would have told them wrongly. Inspection, transformation, validation
and import keep their own reasons for the same reason. `done` is reachable only
after import returns; `downloadReady` is therefore true, while
`materializerReady` continues to describe the separate acquisition capability.

No refresh step follows import. `games.py:list_games()` is the filesystem scan
and runs whenever the grid opens, so the newly published entry appears on that
next listing and queues its normal media prefetch. The import-then-list test
pins this existing design rather than adding an endpoint or database record.

Progress is persisted as `downloaded_bytes` / `download_total` and included in
the queryable job row. Each throttled update also emits `store:jobs`; the socket
is immediacy, not a second source of truth. Cancellation cancels the task and
removes its job directory. Graceful shutdown does the same and settles the row
as interrupted before returning. After a crash, startup removes the stranded
job's work and settles the row before serving.

Interrupted downloads restart from zero. A safe Range resume requires a
persisted ETag or Last-Modified plus validation of a 206 Content-Range, while a
Real-Debrid URL is short-lived. Appending without those facts could combine two
objects; retaining the unusable partial would only consume disk.

**Why acquiring is not downloading.** Fused, they were one step with two jobs:
a conversation with somebody else's service (a token refused, a link nothing
supports, a wait that ran out) and moving bytes onto a disk (no space, a name
that will not sit in a directory, an archive that is not what it claimed).
Every one of those becomes "the download failed" and the player is told
nothing. Split, each says what actually happened — and a resolver has nowhere
to put bytes even by accident, which is what keeps the data-tree guard in
`test_store_jobs.py` meaningful across the success path.

**Why Real-Debrid at all, and why it is external.** It takes a magnet — or a
`.torrent` file — and answers a plain HTTPS URL, so this box needs **no torrent
client**: no daemon, no listening port on the LAN — the thing [`docs/SECURITY.md`](../../docs/SECURITY.md)
spent the hardening pass reducing to Caddy on `:8443` — and nothing extra for
the uninstaller to remove. The owner runs their own account exactly as they run
their own Prowlarr; GameCore knows one token, in one 0600 file, named in
`install/uninstall.sh` and pinned by `test_store_secret_removal.py`.

**Re-finding a release: what `source` had to grow.** `SearchResult.source` is
`prowlarr://<indexerId>/<guid>` and carries no URL on purpose — Prowlarr's own
`downloadUrl` is `…/download?apikey=<this box's key>&link=…`, and `source`
travels to the browser. That pair was chosen to be re-resolvable against
Prowlarr, and **it is not**. Measured against `Prowlarr.Api.V1.dll` 2.5.2.5491:
the only endpoint that accepts it is the grab (`POST /api/v1/search`), which
reads an in-memory cache — the assembly holds *"Couldn't find requested release
in cache, cache timeout probably expired."* — and, on a hit, hands the release
to a **download client**, the one thing this design exists to avoid. The proxy
that `downloadUrl` points at is keyed on `link`, not on `guid`.

So the row carries one thing more: the release's **BitTorrent info hash**, as a
`#btih:<40 hex>` suffix inside `source`. It carries no credential — 20 bytes
saying what the content *is*, never a passkey, and a magnet's `tr=` trackers
are dropped where they are found — it never expires, and it is exactly what a
debrid service consumes, so resolution needs no second Prowlarr round trip and
no guess about which release a re-search meant.
[`services/store/resolve.py`](../../backend/services/store/resolve.py) holds the
evidence and the parse.

**And the rows that publish no hash, which were all of them.** Measured on the
box this was written for, against its one configured indexer:

```
'mario kart' — Prowlarr returned 8 row(s)
    0/8   rows carry an info hash (0%)
```

`protocol=torrent`, no `infoHash`, no `magnetUrl`, a `.torrent` `fileName`, and
the payload behind Prowlarr's own credentialed proxy link. Refusing those rows
was correct and it was also the entire library, so `source` grew a **second**
locator beside the hash rather than a second excuse: `#tor:<token>`, where the
token is the `link` parameter of Prowlarr's `downloadUrl` and nothing else of
it. **The hash still wins** whenever a row has one, so no existing row changes
path.

Storing a link is exactly what the first design refused to do, so the objection
had to be answered rather than waved at: *on a private tracker the indexer's own
download URL carries the owner's passkey.* True of the indexer's URL — and not
true of `link`, measured in Prowlarr's binaries the same way the cache finding
was. `Prowlarr.Core.dll` builds the proxy link in `ConvertToProxyLink` and reads
it back in `ConvertToNormalLink`; both go through `IProtectionService`
(`Protect`/`UnProtect`), and the assembly holds `Aes`, `CreateEncryptor`,
`CreateDecryptor`, `CryptoStream` and `SHA256` beside `Base64UrlEncode`. So
`link` is **AES ciphertext**, keyed on `DownloadProtectionKey` — a `config.xml`
element, hence written to disk and stable across restarts, which is the
durability `remoteReleases` (an in-memory `ICached<T>`) did not have. A passkey
inside it is unreadable to this box, to the browser and to the database; the
only thing that can open it is the owner's own Prowlarr, and reaching that needs
the API key, which never leaves the backend.

That claim is **checked, not trusted**: `resolve.torrent_token_of` refuses any
`link` that base64url-decodes to something containing `://`, because a Prowlarr
handing out plaintext links would be handing out the passkey. Such a row is
offered with no locator and refused at the job, by name.

Acquisition then has two ways in and one way on:

| the row published | locator | Real-Debrid |
|---|---|---|
| an info hash | `#btih:<40 hex>` | `POST /torrents/addMagnet`, trackerless magnet |
| a `.torrent` | `#tor:<token>` | `PUT /torrents/addTorrent`, the file as the raw body |

The file is fetched **server-side**, by
[`prowlarr.fetch_torrent`](../../backend/services/store/prowlarr.py), from
`/api/v1/indexer/{id}/download` with the key in an `X-Api-Key` header — the
route and its `file` requirement are both declared in `Prowlarr.Api.V1.dll`, and
`ApiKeyAuthenticationHandler.ParseApiKey` reads that header before it reads an
`apikey` query parameter, which is why the proxy URL Prowlarr mints is never
built here. The bytes are bounded while they arrive, hashed by
[`torrentfile.py`](../../backend/services/store/torrentfile.py) — SHA-1 of the
bencoded `info` value as it arrived, so the file's `announce` and
`announce-list`, which are where a private tracker's passkey actually lives, are
dropped exactly as a magnet's `tr=` is — and **never written to a disk**.

`addTorrent` is taken over the stated fallback (compute the hash, reuse
`addMagnet`) because `ResolvedSource.magnet` is trackerless on purpose: a magnet
built from a hash alone leaves Real-Debrid to find the metadata itself, and a
release that lives on a private tracker has no public swarm to find it in. The
file carries the piece hashes already. The hash is computed anyway, because it
is what the materializer will check the downloaded bytes against.

It is fetched at **acquisition** and not while a search is being answered, and
that is the same assembly's doing: it holds *"User configurable Indexer Grab
Limit of {0} in last {1} hour(s) reached."* A search that grabbed all 8 rows to
answer a question about 8 rows would spend the owner's hourly budget on 7
releases nobody asked for, every time, and put a round trip per row in front of
a player holding a gamepad. One queued game costs one grab.

Every way it fails says which one, on the job: a token this Prowlarr can no
longer decrypt (HTTP 400 — *"Invalid Prowlarr link"*) says to search for the game
again, which is the only remedy and is what a reinstalled Prowlarr looks like
from here; an unreachable indexer, a 5xx behind an expired link, an answer that
is not a torrent (an HTML login page with a 200 is the common one), a file over
the cap, and a Real-Debrid that refuses are each their own sentence, and none of
them quotes a key, a token, a URL or the content that came back.

A row with **neither** — usenet has no info hash and no torrent — is still
offered and refused at the job, by name. That remains the honest answer rather
than a re-search: searching again for the title and taking whatever comes back
is a guess about which row was meant, and a wrong guess downloads the wrong game
silently.

How many of a given set of indexers publish which of the two is a property of
those indexers and not of this code, so it is measured by hand with
[`scripts/realdebrid-resolve-check.py`](../../scripts/realdebrid-resolve-check.py),
which now reports every row as `hash`, `.torrent` or `not at all` with a rate
for each — so the 0 % above is a number that can be taken again. It takes both
credentials from the environment, reads neither config file, writes nothing and
downloads nothing. It is not a gate, for the same reason `prowlarr-filter-check.py`
is not: the gates are `backend/tests/test_store_realdebrid.py`,
`test_store_resolve.py` and `test_store_torrentfile.py`, and they run offline.

**Cancelling is a state, not a `DELETE`.** Hence `POST /jobs/{id}/cancel` and
no `DELETE /jobs/{id}`. A queue whose cancel removed the row cannot tell "I
changed my mind" from "I never asked", and the player looking at the empty list
is the one who needed to know. The row keeps its reason and its timestamps.

**The worker is one task, not a lock.** Same shape as `_current` in
`catalog.py` above and for the same reason — two requests in one loop tick both
see a lock unlocked. It differs in the one way that matters: `catalog.py` holds
its state in a module variable that dies with the process, and a download
cannot. A row left saying `running` by a hard stop is rewritten to `failed` by
`resume_after_restart()` in the lifespan, before the API answers anything, and
`store_queue` is a required boot step for exactly that reason
([`services/boot.py`](../../backend/services/boot.py)). It is not re-queued:
that would restart an acquisition nobody asked to restart, from a position
nothing recorded.

**What the client is not trusted for.** `POST /jobs` takes the search result
the browser is looking at, because there is nothing to look an id up in — a
search is a question asked of somebody else's indexer and nothing here
remembers the answer. Two facts are therefore taken from the box and not from
the request: **where it would land** (`system_for().roms_dir`, the one field
that decides a directory) and **which provider found it** (checked against the
one answering now, so a tab left open across a change of provider cannot queue
a stale row — a 409, because the request was well formed when it was made).
A filename that is a path is refused where the row is *created*, not where it
is used: the materializer will join that name onto a directory, and a row
sitting in the database since before that code existed is exactly the input
nobody re-checks.

**Only import writes into a ROM directory.**
`backend/tests/test_store_jobs.py` compares the whole data tree path for path:
all earlier writes must remain in the owning work area, and import's additions
must remain below the pack's one directory. Separate negative tests fail if an
earlier stage touches `emu/` or if import targets another system. The upstream
half remains `test_searching_writes_nothing_anywhere` in `test_store_search.py`.

Every transition is announced on the existing WebSocket as `store:jobs`,
carrying the row that changed. The front end uses it as a signal and re-reads
the list, for the reason `useCatalog` re-reads on `catalog:done`: a list
assembled from events is a second source of truth and it is wrong for as long
as the socket was down.

### `bios.py` (27 l.) — one row per system that needs a system file

`GET /bios`. Thin on purpose; the verdicts come from
[`services/bios.py`](04-backend-services.md#biospy-253-l--three-verdicts-not-two).

### `pergame.py` (145 l.) — per-game settings from the sofa

`GET /pergame/{system_id}`, `POST /pergame/{system_id}/profile`,
`POST /pergame/{system_id}/open`.

`open` launches the emulator's **own** settings window. That is the deliberate
half of the design: GameCore never translates a setting's meaning across thirteen
emulators, so the escape hatch is opening the real UI rather than approximating
it. See [10](10-catalog-and-install.md#pergame--and-why-it-is-required-on-every-emulator-pack).

### `storage.py` (74 l.) — external disks

`GET /storage/volumes`, `POST /storage/mount`, `POST /storage/unmount`.
