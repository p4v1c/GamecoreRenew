# 4 — Backend, services

Where the logic lives. No FastAPI import exists in this directory: a service
is callable from a test, a script, or another service.

[`controller_profiles.py`](08-controller-pipeline.md) is big enough to have its
own document.

---

## process_manager.py

Module-level singleton: `process_manager = ProcessManager()`.

State: `_proc`, `_launching`, `_game_key`, `_system_id`, `_start_time`,
`_exec_path`, `_launch_args`, `_orphan_pgid`.

| Member | Role |
|---|---|
| `_display_env()` | rebuilds a GUI environment for a systemd child — see [1](01-runtime-topology.md#environment-reconstruction). **Synchronous**; memoised |
| `display_env()` | the `async` wrapper every event-loop caller must use |
| `invalidate_display_cache()` | forget the probed display — called after a failed launch |
| `kill_process_group(proc)` | module-level: SIGKILL a process **and its children**. Shared with `routers/update.py` |
| `is_running` | `_launching or (_proc alive) or (_orphan_pgid alive)` |
| `current_game` | `{game_key, system_id}` or `None` |
| `launch(...)` | builds argv (`shlex.split` + ROM), spawns, records the session, broadcasts `game:started`, starts `_watch()` |
| `_save_session()` / `_clear_session()` | write/remove `config/session.json` atomically |
| `adopt_orphan()` | at startup, re-attach to a game a previous backend left running |
| `kill()` | orphan → `_kill_orphan()`; otherwise `_flatpak_kill()` then `_proc_kill()` |
| `_flatpak_kill()` | finds the app-id (token after `run`) and runs `flatpak kill <app-id>`, 1 s timeout |
| `_proc_kill()` | delegates to `kill_process_group()` |
| `_watch()` | awaits exit, clears the session file, records playtime if > 5 s, broadcasts `game:finished` |

Decisions that look odd until you know why:

1. **`_launching` is claimed synchronously**, before the first `await`. Two
   concurrent `launch()` calls would otherwise both pass the `is_running`
   check while the first was still awaiting the spawn.
2. **`start_new_session=True`** puts the child in its own process group. Without
   it, `killpg` would reach the backend itself.
3. **SIGKILL, no SIGTERM.** Several emulators answer SIGTERM with a
   confirmation dialog that cannot be clicked from a gamepad.
4. **The display probe is memoised.** Under systemd neither `DISPLAY` nor
   `XAUTHORITY` is set, so `_probe_display()` ran on *every* launch and *every*
   standby transition — with synchronous `subprocess.run(timeout=5)` calls, on
   the event loop. When X was slow to answer (cold boot, stale xauth cookie, the
   TV resyncing HDMI), an unrelated `GET /api/systems` measured **4.7 s**. The
   display does not move mid-session, so it is probed once; the first probe runs
   off-thread via `display_env()`, and the cache is dropped only when a launch
   fails.
5. **The pgid is persisted, and the game is never killed at shutdown.** See
   `config/session.json` in [7](07-config-and-data.md). Killing it in the
   lifespan would take unsaved progress with it on every OTA, and would do
   nothing for the case that actually strands the player — a crash, where the
   lifespan never runs.

`launch_game` (in `routers/games.py`) catches `FileNotFoundError` and
`PermissionError` and answers **503** naming the system and the binary, plus a
`game:failed` broadcast the UI turns into a toast. It used to escape as a bare
500 with an empty body: the launch silently did not happen and nothing said why.

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
| `exit_standby()` | wake — **unconditional** |
| `resume_after_restart()` | called from the lifespan; forces the screen on at startup |
| `on_input()` | called from the evdev loop on any controller button |
| `run()` | the idle poll loop |

A running game blocks standby entirely.

**The state is in memory; its effect is not.** `xset dpms force off` is a
property of the X server, and X belongs to SDDM — it does not restart with the
backend. So a box asleep when the backend restarted (crash, `systemctl restart`,
the end of an OTA) came back holding `_state == "active"` with the TV still
dark. `on_input()` tests `_state != "active"` before waking, so a button press
did nothing; pad events arrive over evdev rather than X, so DPMS never re-armed
by itself; and `POST /api/standby/exit` returned at its first line. SSH or a USB
keyboard were the only ways out.

Hence both halves: `resume_after_restart()` in the lifespan repairs a box already
in that state, and `exit_standby()` no longer short-circuits on
`_state == "active"` — asking to wake up is never a no-op.

`_run_cmd` awaits `display_env()` rather than calling `_display_env()` inline:
the probe behind it can block for seconds on the first call, and this runs on
every standby transition.

---

## `cover_pipeline.py` (170 l.) — orchestration

| Function | Role |
|---|---|
| `resolve(system, filename, refresh=False)` | the five-tier resolution, [drawn here](02-request-flows.md#3-resolving-a-cover) |
| `_from_gamemedia(sid, target, base, refresh)` | the ScreenScraper / LaunchBox tier — returns `(cover, unreachable)` |
| `_id_urls(kind, value)` | candidate `(url, ext)` pairs for a disc ID, best first |
| `_regions(letter)` | region-code expansion for GameTDB paths |
| `_fetch_by_id(kind, value, base)` | downloads the first candidate that exists; raises `Unreachable` if none answered |

The order is: cache → embedded icon → **gamemedia** → disc-ID lookup → name
scrapers. gamemedia sits below the embedded icon because that one is exact and
costs no network, and above the name scrapers because it is the only tier that
is exact on a **cartridge** — there is no icon to extract and no serial to
read, so everything below it guesses from the filename while a CRC32 the
ScreenScraper database recognises identifies the game outright.

It asks for a flat jacket (`gamemedia.COVER_ORDER`), so what lands in
`emu/covers/` is the same *kind* of picture the pipeline has always produced.
Nothing downstream sees a different shape.

Negative results are written as `.miss` files, honoured for 7 days, so an
offline box does not retry the network on every scroll.

**A `.miss` is only written for a real "not found".** The pipeline could not tell
"nobody has a cover for this game" from "nothing answered": network errors were
swallowed lower down, `resolve()` saw `None` either way, and it wrote the marker
unconditionally. The worst trigger was also the most likely — a new box has no
network until the owner configures Wi-Fi *from the GameCore interface*, and
`prefetch` starts 15 s after boot. The first run therefore walked the whole
library with no connectivity and marked every game; once Wi-Fi was up,
`resolve()` returned 404 from the marker before trying anything, so the library
stayed blank **for a week**, silently, and rebooting did not help. An exhausted
TheGamesDB quota did the same.

`utils.rom_in_root` is the containment guard: `filename` comes from the
`{filename:path}` route parameter, which accepts slashes and `..`, and the value
went straight into `roms_root / filename`. Same rule `launch_game` has always
applied — resolve, then check against the root. It moved to `utils.py` when
`routers/media.py` became its third caller: two near-identical copies were a
convention, three would have been a rule to remember rather than import.
`cover_pipeline._rom_in_root` remains as an alias, because that is the name the
cover tests assert on.

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
| `Unreachable` | raised when **no lookup completed** — distinct from "not found" |
| `_is_transient(status)` | 403, 408, 425, 429 and anything ≥ 500 mean "ask again later" |

`fetch_cover` and `_fetch_by_id` return `None` only when the lookups completed
and nobody has the cover; they raise `Unreachable` otherwise. That distinction is
the whole point — `cover_pipeline` caches the negative result for seven days, and
a dead network is not evidence about a game. `_fetch_tgdb_cover` raises on any
non-200 too: a 429 body has no `games` key either, so an empty result used to be
indistinguishable from a genuine miss.

## `gamemedia/` — ScreenScraper + LaunchBox

Two vendored files (`gamescrape.py`, `gamemedia.py` — standard library only,
see `VENDORED.md` in that folder) and one adapter, `__init__.py`, which is the
**only thing the rest of the backend imports**.

What it adds: identification by **file hash** instead of by filename, and 54
media types per game instead of one cover.

| Function | Role |
|---|---|
| `available()` | is any source configured? Cheap, no network. Everything else is a no-op when it is False |
| `status()` | `{available, screenscraper, launchbox_index, cache}` |
| `resolve(system_id, target, only=…, refresh=…)` | the manifest. `None` = *the tier could not be asked*, distinct from a manifest with `found: false` |
| `media_file(system_id, filename, slug)` | local path to one media, downloading it if it was deferred |
| `media_index(manifest)` | `media` as the API exposes it — descriptors only, **never the source URL** |
| `to_game_meta(manifest)` | a manifest in the `GameMeta` shape `/api/metadata` has always returned |
| `cached(system_id, filename)` | the manifest already on disk. No network, no thread |

**How a game is identified**, best first: the file's CRC32+MD5+SHA1 when it is a
real file under 384 MiB (certain — a renamed or mistagged ROM still lands on the
right game); the `TITLE` its `PARAM.SFO` declares when it is a PS3/PS4/PSP
directory (the directory name is whatever the user typed, and ScreenScraper 404s
on it); the parsed filename otherwise.

**Three states, not a boolean.** "This game is not in the database" is a fact
worth caching. "The quota is spent", "the network is down" and "nothing is
configured" are not, and a manifest carries `unreachable` to say so. Collapsing
them is what would carve a permanent "no such game" over a whole library swept
before the credentials were entered.

Two design points that are GameCore's, not upstream's:

- **Nothing is downloaded before it is asked for.** A scrape fetches
  `EAGER_MEDIA` (the cover, one image — what the default theme displays and
  what the previous pipeline downloaded) and records the rest as `deferred`
  with its URL. `media_file()` fetches one on demand: one HTTP request, no
  second `jeuInfos`, no quota. Fetching all 28 media of a PS3 game up front
  would be ~34 s per title at the 1.2 s rate ScreenScraper requires.
- **A stored URL carries no credentials.** ScreenScraper puts `devid`,
  `devpassword`, `ssid` and `sspassword` in the query of every media URL it
  returns, and a deferred media keeps its URL in `game.json`. They are stripped
  on write and restored from the live configuration on read, so the developer
  account is never written to disk — it is shared by every user of the same
  softname and gets revoked if it leaks.

Synchronous by design (`urllib` + a thread pool), so every call runs in
`asyncio.to_thread` behind a single lock. The lock is about the quota, not
thread safety: prefetch warms three games at a time, and three concurrent
scrapes would put three `jeuInfos` in flight ignoring each other's 1.2 s.

Configured through four environment variables — `SCREENSCRAPER_DEV_ID`,
`SCREENSCRAPER_DEV_PASSWORD`, `SCREENSCRAPER_USER`, `SCREENSCRAPER_PASSWORD`
([where they come from](07-config-and-data.md#environment)). The LaunchBox tier
needs no account at all, only `python3 gamescrape.py --refresh` run once — and
**with `GAMECORE_PATH` set**, or the index lands in `~/.cache/gamescrape` where
the backend never looks. That is not hypothetical: it is where the index sat on
the reference box, with `status()` reporting `launchbox_index: false` and the
tier silently off since the day it was populated. `resolve_index_dir()` now
answers that question once for both the CLI and the backend, and
`test_the_cli_and_the_backend_agree_on_where_the_index_lives` keeps the two
answers equal.

Nothing builds it for you: the installer does not, and the backend **never**
does — 106 MB of download from inside an HTTP handler would block the request
for minutes. A box with no index simply has no LaunchBox tier.

## `metadata.py` (135 l.)

`resolve(system, filename)` → description, year, genres, players, rating.
Disk-cached and negative-cached. Two sources: **gamemedia first** (hash
matching, French synopses when it has them, developer/publisher/age ratings,
and no network at all on the LaunchBox side), then TheGamesDB unchanged —
still the only source on a box with neither configured.
`_genre_names(client)` resolves the genre id table once;
`_search_name(system, filename)` builds the query;
`_fetch_tgdb(platform_id, name)` does the call.

**The seven keys the API has always returned keep their name, type and
meaning** — `found`, `title`, `description`, `year`, `genres`, `players` (a
number), `rating` (the age rating, a string). GameMetaPanel and every theme
already read them. Two traps that shaped the mapping: ScreenScraper writes
players as a range (`"1-3"`), which as a string silently stops the player-count
chip from rendering, so it is reduced to its maximum; and its `rating` is a
score out of 20 where TheGamesDB's is a label, so the normalised 0–1 score
arrives on a new key, `score`, and `rating` stays the label.

A `found: false` from gamemedia is deliberately **not** copied into this
service's cache: gamemedia already caches its own negative, and only when the
tiers really answered. A second copy with a 7-day TTL would outlive the retry
gamemedia does for free the day the credentials appear or the quota resets.

## `sfo.py` (34 l.)

`parse_bytes(d)` and `parse(path)` — PARAM.SFO key/value table, `{}` on any
error. Same binary format on PS3, PS4 and PSP. The addons repo has its own
copy in `shared/py/`; this one additionally exposes `parse_bytes()` for data
already in memory.

## `rom_scanner.py` (126 l.)

`clean_name(filename)` (strips extension and bracketed tags like `[!]`,
`(USA)`), `matches_ext(filename, extensions)`, and
`iter_rom_files(roms_path, extensions, scan_dirs)` — alphabetical, applying the
common exclusions. The rom-manager addon keeps a mirrored copy.

### One game, one entry

`shadowed_by_a_descriptor(entries)` → `{hidden file: the entry that owns it}`.

A PS1 dump is a descriptor plus its tracks, and duckstation scans `*.bin` *and*
`*.cue` — so a single-disc game was listed twice, same name, same artwork. Both
extensions have to stay scannable (a `.cue` is the only launchable file of a
multi-track dump, and plenty of dumps ship as a bare `.bin`), so the dedup is at
the listing level and the descriptor wins.

Two rules, because either alone leaves duplicates on a real library:

- **what the descriptor names** — a multi-track dump's `Game (Track 01).bin`
  shares no stem with `Game.cue`. Transitive: an `.m3u` hides its `.cue` files
  and their tracks go with them in the same pass;
- **what shares its stem** — the common case of a dump renamed while the
  descriptor kept pointing at the old name. Measured on the reference box:
  `Dragon Ball Z .cue` names `Dragon Ball Z (Europe).bin`, which does not
  exist, while `Dragon Ball Z .bin` sits next to it.

`.m3u` lines are read whole rather than tokenised — disc names contain spaces,
and a token pattern matches only the tail after the last one. A directory with
no descriptor is never read, so a library without disc images is untouched.

**A file may only be hidden if the entry replacing it will actually be listed**,
so the system's `extensions` are passed in and a descriptor it does not scan
hides nothing. Forgetting that emptied a library in production: `config/` is
excluded from the OTA, so a box installed before `*.cue` was added to
duckstation keeps a catalogue scanning `*.bin` and not `*.cue`. The `.cue` was
on disk and shadowed the `.bin`; it was then filtered out by `matches_ext`, and
PS1 went from one game to none. Any rule that hides an entry has to check that
something visible takes its place.

The **value** of that mapping is what `playtime_repair` needs: hiding a file
that a player has hours on would orphan them.

## `playtime_repair.py` (105 l.)

`rekey_shadowed_entries()` → number of rows moved. Runs once in the lifespan,
before anything can serve a library.

`game_key` is the filename the library listed. So the day the library stops
listing a file, every hour recorded against it stops being reachable: the row
is still there, nothing points at it, and a game played for hours reports as
never played. Hiding a `.bin` behind its `.cue` does exactly that — measured
before this existed, one row on the reference box: 15 minutes, 21 sessions.

So the rename is followed, in `playtime` and in `sessions`. If both keys
already have a row (the player launched the `.cue` too) they are **merged**,
not picked between: seconds and session counts add up, `last_played` is the
later of the two. Idempotent by construction, and it never deletes a row it has
not merged into its replacement.

The map is built from **what `iter_rom_files` actually returns**, not from
"the descriptor wins" — so it corrects in either direction. That distinction is
not theoretical: `config/` is excluded from the OTA, so a box installed before
`*.cue` was added to duckstation lists the `.bin` and not the `.cue`, and a
release that moved the playtime onto that `.cue` left it as unreachable as the
bug it was fixing. A disc group no member of which is listed is left alone —
moving playtime onto an invisible entry only hides it further.

The covers and metadata caches need no equivalent: both are keyed on the
*stem*, which `.bin` and `.cue` share.

## `prefetch.py` (82 l.)

`run()` walks the library at startup and calls `warm(system, filename)` so the
first scroll is not a spinner. Two passes, in this order:

1. **Cover and metadata**, three games at a time, through the same pipelines the
   API uses — an already-cached game costs one `stat()`.
2. **The rest of the artwork a theme draws**, once every game has a cover:
   `gamemedia.warm()` for each entry, sequentially.

The order is the point. Someone opening the library thirty seconds after boot
wants the grid full, not one title's detail panel complete.

The second pass costs no `jeuInfos`: a scrape downloads `box-front` and records
every other media with its URL, so warming is a plain download of URLs already
on disk. It fetches only what the manifest says the game *has* and does not yet
*hold* — which is why it is nearly free on a warm box and why a game the cover
pipeline has not reached yet is simply skipped until the next boot.

What it pulls is `gamemedia.WARM_MEDIA`: the flat jacket, the three faces the 3D
box is built from (`box-3d`, `box-spine`, `box-back`) and the two captures the
detail panel shows. Override with `GAMECORE_WARM_MEDIA` — comma-separated, empty
to warm nothing, for a box on a slow line or with a very large library.

Measured on the reference box before this existed: `box-front` 47/47, but
`box-3d` and `screenshot-gameplay` only 41/47 — the six missing were simply the
games nobody had opened yet, each one costing a round trip behind the scraper's
1.2 s spacing the moment someone did.

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
