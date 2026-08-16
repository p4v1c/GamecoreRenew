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

**A media can be a picture of nothing, and that is a fifth state.** Ask
ScreenScraper for a `box-2D-back` and one of the answers is a **chroma-key
plate**: a valid PNG of flat `#00FF00`, cut to the exact box dimensions of the
system. This is not its convention for "I have none" — that answer is a 7-byte
`NOMEDIA` body, which `_looks_like_media()` already rejects. Probed across nine
regions for FIFA 19 on PS3: `de` serves the plate, the other eight serve
`NOMEDIA`. The plate is a placeholder somebody contributed, indistinguishable
from art by anything that does not look at the pixels. It downloads, it decodes and it draws, so nothing downstream could tell
— the Shelf theme ended up recognising them in the browser by quantising the
pixels, and every other consumer showed a green slab. Measured on the reference
box: nine titles across five systems, four distinct files, one per box shape.

Recognised at download time by **compression, with no image decoder** (the
backend has no Pillow, in neither `requirements.txt` nor either venv). A flat
fill is the one thing PNG compresses to nothing, and the two populations do not
touch:

| | bytes per pixel |
|---|---|
| the nine plates | at most **0.0093** |
| the 52 real scans | at least **1.3055** |

`gamescrape.looks_like_flat_plate()` reads the dimensions out of the IHDR — a
fixed offset, nothing decompressed — and compares against `FLAT_PLATE_BPP`,
which sits 5× above the highest plate and 26× below the lowest real scan.

Such a media is recorded `blank` rather than kept. `blank` is **settled, not
incomplete**: `failed` would mean "retry me" and this one comes back identical
every time, so `_manifest_complete()` accepts it and `media_index()` leaves it
out entirely — absent means "this game has no back cover", which is true and
directly actionable, where present-but-green makes every consumer work it out
from the pixels. A plate filed before this existed is still caught: the
completeness check opens any media the manifest records as under 8 KiB, so it
costs one rescrape, once, and cannot loop.

**The tier fallback is per MEDIA as well as per game.** `lb_everything()` used
to be reachable only when ScreenScraper did not find the title at all, was
unreachable, or had no credentials — so a game ScreenScraper knew kept every gap
ScreenScraper had. `_top_up_blanks()` now asks the other tier for the blank
slugs alone, never for a deferred or failed one, and never for `meta` (the text
stays one tier's, in one language, which is what `lang` promises). It costs one
local index lookup and one download per slug replaced; a game with nothing blank
costs nothing. Measured on the reference box, against the index already sitting
there: **all nine plates have a real `Box - Back` in LaunchBox, every one
matched at a similarity of 1.00.**

That number was first reported as seven, and how it was got wrong is worth more
than the number. The two "misses" — FIFA 19 and Breath of the Wild — came from
querying the index with a hand-rolled normalisation instead of `find_game()`:
one dropped the platform filter and matched FIFA's *Windows* entry, the other
could not get `The Legend of Zelda: Breath of the Wild` past its own colon.
`find_game()` has neither problem. That first re-measurement was also taken on
FILENAMES, which is wrong for a PS3, PS4 or PSP dump — those are identified by
the `TITLE` in their PARAM.SFO. Measured properly, through the same path the
code takes, the matcher is **63 for 64**, and the one failure is instructive:
the disc says `FIFA 19`, LaunchBox files it as `FIFA 19: Legacy Edition`, and
`difflib` scores that pair at **0.48** while scoring `FIFA 09` at **0.909**.
Text similarity ranks it exactly backwards, because its ratio is penalised by
the length the two titles do not share.

`search._subtitled()` is the last resort added for it — an identity question
rather than a similarity one, which is what a local index allows and a remote
search endpoint does not. It accepts an entry only when it is our title plus a
subtitle (`:` or ` - `), the stem normalises to exactly our title, the episode
numbers agree, and it is the ONLY such entry on the platform. Skyscraper solves
the same problem with a containment rule (`scraperworker.cpp` promotes a
candidate to 100 % when the search name appears in it and the edit-distance
score is already ≥ 50) — a guard a short title with a long subtitle cannot
clear, so it would not fire here; and its own subtitle stripping sits commented
out in `nametools.cpp`, tried and turned off. Neither is copied. With the rule
in, the library is **64 for 64**, and games that already matched never reach it.

**And the trigger needed a caller.** `_manifest_complete()` refusing a plate is
worth nothing on its own: `cover_pipeline.resolve()` returns as soon as
`emu/covers/<game>.png` exists, so a library whose covers are all cached never
reaches this tier again. Measured after the release that shipped the check — the
nine plates had not moved. `warm()` is what pulls it now, via
`has_stale_plate()`: it already walks every game once per boot with the manifest
open, and it asks a question narrower than completeness on purpose, because that
one answers False for a language change too and would turn a boot into a
rescrape storm.

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

A full install builds it once, in `install/steps/build-media-index.sh`, and
never fails the install over it. `--minimal` and `GAMECORE_SKIP_MEDIA_INDEX=1`
skip it, and both print the single command that adds it later.

The backend **never** builds it — 106 MB of download from inside an HTTP
handler would block the request for minutes. A box with no index simply has no
LaunchBox tier, and says so in the manifest notes.

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

---

## Services added by the recent phases

Ten modules and two sub-packages arrived after the inventory above was written.
These entries are **summaries, not full function inventories**: each names what
the module is for and the one decision that is not recoverable by reading its
signatures. The docstrings carry the rest, and they are unusually good.

### `paths.py` — the two roots

Owns `GAMECORE_ROOT`, `GAMECORE_DATA` and `_LAYOUT`. Nothing outside it may join
a writable directory onto a root; `test_paths.py` enforces that on the AST.
Fully described in [7](07-config-and-data.md#path-resolution--backendservicespathspy).

### `configgen/` — the controller pipeline

`__init__.py` (apply/release/scan/forget), `controllers.py` (SDL resolution,
`Pad`, `ResolvedName`), `snapshots.py`, `mapping_db.py`, `seed.py`, `derive.py`,
plus `helpers/`. One generator per emulator lives in `catalog/<id>/generator.py`,
not here. All of [8](08-controller-pipeline.md).

### `installer/` — obtaining what a pack declares

`providers.py`, `fetch.py`, `applier.py`, `manifest.py`. The applier is what
refuses a pack that names a file it does not carry — the check the repository did
not have when a refactor deleted a directory `arch.sh` still read, and an install
died at 66 % on a fresh machine months later.

### `bios.py` (253 l.) — three verdicts, not two

Whether the system file an emulator needs is present **and right**. The support
ticket it exists to delete: a missing or corrupt BIOS produces no message a player
can act on — the emulator refuses to start, or starts on a black screen, and
nothing on screen names a file. Every case cost three round trips before anyone
knew what was being discussed.

The verdicts are deliberately distinct, because "absent" and "present but wrong"
need different sentences. What a pack declares is data (`bios` in `pack.json`);
how it is checked is here. `required: false` matters: a BIOS gate that blocks a
launch it should not is GameCore inventing a fault.

### `pergame.py` (648 l.) — one game's settings

`<DATA>/config/per-game/<system>/<id>.json` is the original; the emulator's file
is **derived**. Nothing here knows what a setting *means* — no table maps
"internal resolution" onto thirteen vocabularies, because chasing that map across
emulator releases is what makes Batocera's configgen impossible to keep current.
Every write records what it displaced so removal can put it back key by key.
Detail in [10](10-catalog-and-install.md#pergame--and-why-it-is-required-on-every-emulator-pack).

### `gameid.py` (235 l.) — which game this is

A per-game config is a file named after a game, so something must answer "which
game is this" before anything can be written. The answer differs per system only
in **where it is read from**:

| strategy | source |
|---|---|
| `ps3`, `ps4`, `psp` | a Title ID in `PARAM.SFO` |
| `gcwii` | the 6 characters at the top of a disc image |
| `playstation` | the serial in `SYSTEM.CNF` |
| `wiiu` | the title id in the dump's own `meta.xml` |
| `hash` | the CRC32 of the file |
| `filename` | the normalised name — nothing else was available |

Pluggable per system, because an N64 cartridge dump carries no serial at all.

### `bezels.py` (656 l.) — which bezel, and where its window is

Resolves game → system → nothing, like Batocera. The interesting half is **why
the hole is measured rather than read**: `config/` and `assets/overlays/` are both
excluded from the OTA rsync, deliberately, because they are the player's. The
consequence is that a wrong `hole` in a shipped `overlays.json` can *never* be
corrected on a box that already exists — the release carries the fix and the rsync
drops it on the floor.

### `bezel_capture.py` (228 l.) — when the emulator disagrees with itself

A hole is cut for the ratio a system is *supposed* to render at, and the emulator
does not always oblige (an aspect setting left on stretch, a core letterboxing 4:3
inside 16:9, a widescreen hack). The overlay is then perfectly correct about a
picture that is not there, with nothing on screen to suggest which of the two is
wrong. The only witness is the screen: a frame is captured a second into the game,
the drawn region measured, and a disagreement corrects the hole and is remembered.

### `controller_capture.py` (543 l.) — the mapping wizard's engine

Turns "the owner pressed this" into an SDL mapping line. What arrives from the
kernel is an evdev code (`BTN_SOUTH`, 0x130); what must be written is SDL's
vocabulary (`b0`, `a3`, `h0.1`), where the numbers are SDL's joystick indices, not
the kernel's codes.

**Nothing bridges those two by inspection.** SDL assigns indices by walking the
device's declared capabilities in a fixed order, so index 0 is "the first button
this device declares" — and the same physical button is a different number on a
pad that declares one extra key. `sdl_layout()` reproduces that walk. Guessing
here produces a mapping that looks plausible and binds the wrong buttons.

### `usb_devices.py` (260 l.) — the peripherals that are not SDL gamepads

The autoconfig pipeline knows exactly one kind of device: a pad declaring
`BTN_SOUTH` on an evdev node. Everything else — the GameCube adapter Dolphin
drives over raw libusb, light guns, dance mats — is invisible to it. This module
is that second roster, declared per pack under `usb`. It **never refuses a
launch**: a USB accessory is optional by nature, so blocking would be GameCore
inventing a fault. It only speaks.

### `storage.py` (402 l.) — external disks

"I plug my ROM disk in" is one of the first three things anyone expects from a
console in a living room, and before this there was no udisks, no mount, nothing
anywhere in the repository — a disk plugged into the box did exactly nothing.

### `storage_monitor.py` (206 l.) — reacting to a disk arriving or leaving

Mounts an arrival, re-points its stable link, tells the frontend. **Nothing is
invalidated on the way, and that is not an omission**: a system's games are
scanned per request from its `romsPath`, and `romsPath` points at the stable link
rather than at a mount point — so the next scan already reads the new disk. There
is no cached library to clear, and adding a hook for one that does not exist would
be a line nobody could ever prove still works.
