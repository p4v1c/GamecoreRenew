# 7 — Config & data

Everything the box stores, and who writes it.

## Path resolution — `backend/services/paths.py`

Nothing hardcodes `/opt/GameCore`, and nothing outside this one module decides
where anything lives. There are **two roots**:

| Root | Env | Holds | Writable |
|---|---|---|---|
| `GAMECORE_ROOT` | `$GAMECORE_PATH` or the repo root | backend, venv, frontend build, catalogue, installers | no (that is the goal) |
| `GAMECORE_DATA` | `$GAMECORE_DATA`, **defaulting to `GAMECORE_ROOT`** | ROMs, generated config, covers, scraped media, overlays, playtime | yes |

**The default is the whole safety property, not a placeholder.** The release
that introduced the split reaches production boxes over OTA with nobody in
front of them, and `update/linux.sh` rsyncs into `GAMECORE_PATH` while
excluding `emu/` and `config/` — the two directories a split moves. If the new
code looked for data anywhere other than where the rsync left it, every box
would boot with an empty library and no settings, and the rollback would hand
the *old* code a tree the *new* code had moved. So the pointer moves and the
bytes do not: after the update every path resolves to the byte-identical
location it did before. Moving the bytes is a separate, human-typed operation
(`scripts/migrate-userdata.py`), deliberately unreachable from the updater.

`paths._LAYOUT` is the table of writable locations, and it deliberately keeps
today's names (`emu/`, `config/`, `assets/overlays/`) rather than the eventual
`roms/ overlays/ media/`. Renaming there either moves bytes on every installed
box or ships a second layout no test and no real box has exercised. The rename
is one edit to that table, and it belongs with the move.

`backend/tests/test_paths.py` enforces both halves mechanically — no module
outside `paths.py` may join a writable directory onto the code root, and none
may read the root variables from the environment. It works on the AST, not on
a grep, because half these modules discuss `config/` and `emu/` at length in
their docstrings.

`backend/config.py` re-exports the names the backend has always imported:

| Constant | Value |
|---|---|
| `GAMECORE_ROOT` | the installation |
| `GAMECORE_DATA` | the data root |
| `SYSTEMS_FILE` | `<DATA>/config/systems.json` |
| `APPS_FILE` | `<DATA>/config/apps.json` |
| `PLAYTIME_DB` | `<DATA>/config/playtime.db` |
| `COVERS_DIR` | `<DATA>/emu/covers` |
| `OVERLAYS_DIR` | `<DATA>/assets/overlays` |
| `LOGOS_DIR` | `<DATA>/assets/logos` |
| `ASSETS_DIR` | `<ROOT>/assets/` — the shipped tree |
| `BACKEND_PORT` | `$GAMECORE_BACKEND_PORT` or 8765 |
| `APP_VERSION` | contents of `VERSION` (written by the OTA script) |
| `GITHUB_REPO`, `UPDATE_ASSET` | `p4v1c/GamecoreRenew`, `gamecore-ota.tar.gz` |
| `THEGAMESDB_API_KEY` | env only — never committed |
| `SCRAPER_LANG` | `$GAMECORE_SCRAPER_LANG` or `en,fr` — language of the scraped text |
| `DEBUG` | must be `false` on a device |

### Environment

Read straight from the process environment, never from a file in the repo. The
installer writes them into one systemd drop-in,
`/etc/systemd/system/gamecore-backend.service.d/override.conf`, mode 600.

| Variable | For |
|---|---|
| `GAMECORE_PATH` | the install root (code) |
| `GAMECORE_DATA` | the data root. Unset = the install root, which is what every box installed before the split runs |
| `GAMECORE_BACKEND_PORT` | the API port |
| `THEGAMESDB_API_KEY` | `services/scraper.py`, `services/metadata.py` |
| `SCREENSCRAPER_DEV_ID` / `SCREENSCRAPER_DEV_PASSWORD` | **developer** credentials, granted per software on the ScreenScraper forum. The id is the developer's *pseudonym*, not the number in the `devinfos.php` URL |
| `SCREENSCRAPER_USER` / `SCREENSCRAPER_PASSWORD` | a **member** account. It carries the daily quota and the thread count |
| `GAMECORE_SCRAPER_LANG` | comma-separated, most preferred first. Default `en,fr` |
| `GAMECORE_WARM_MEDIA` | which media `prefetch` downloads at boot beyond the cover. Comma-separated, empty to warm nothing. Default `box-front,box-3d,box-spine,box-back,screenshot-gameplay,screenshot-game-title` ([why](04-backend-services.md#prefetchpy-82-l)) |

**The N64 slot is keyed `gopher64` and runs Rosalie's Mupen GUI.** That
mismatch is deliberate. gopher64 sets no `WM_CLASS` on its window, so
`overlay_monitor` could never find it and the bezel never drew; RMG reports
`"RMG", "Rosalie's Mupen GUI"`, which `config/overlays.json` already listed.

The id was not renamed because `config/` is excluded from the OTA. A renamed id
reaches new installs only, and leaves every existing box pointing at an
emulator the installer no longer installs — the same failure mode as the PS1
`*.cue` extension. It is also the key for `emu/gopher64/`, the covers, the
metadata cache, the playtime rows and the overlay entry, so renaming it means a
five-store migration for no user-visible gain: the label reads "Nintendo 64"
either way.

`update/linux.sh` reports a box whose N64 entry still launches gopher64, with
the commands to switch it.

RMG's controller config is **captured, never synthesised** — it joins azahar,
mGBA and Cemu on the "Scan mapping" path. Two attempts to write it failed
against what RMG actually produces:

```ini
[Rosalie's Mupen GUI - Input Plugin Profile 0]
PluggedIn = True
DeviceName = "PS4 Controller"
DevicePath = "/dev/hidraw0"
DeviceSerial = "40:1b:5f:b9:ea:8d"
A_Name = "cross"        # not the generic "a" of the shipped fallback_profile
```

`PluggedIn` is what attaches a controller to the N64 port. Without it the game
itself refuses to start — *"connect a controller to socket 1"* — however
complete the rest of the section looks, and `ControllerMode 0` ("automatic")
does not supply it. `DevicePath` is a host path that can move between boots,
and the button names are per-controller. Reproducing that means reimplementing
RMG's own dialog, and being wrong about it is silent; capturing what RMG wrote
is not.

Do it once per pad: configure the controller in RMG (Settings → Input), then
press **Scan mapping** in GameCore. The snapshot is restored whenever that pad
reconnects. `_rmg_extract` takes the `[Rosalie's Mupen GUI - Input Plugin…]`
sections and nothing else, so a restore never rolls back the video settings
living in the same `mupen64plus.cfg`.

**Language.** ScreenScraper localises synopses **and genre names**, so a French
preference gives `Course, Conduite` where an English one gives
`Racing, Driving`. English is the default because the interface is: a library
whose buttons read "PLAY TIME" and whose synopses are in French is not a choice
anyone made. Upstream `gamescrape` prefers French — right for its own users,
wrong here.

It is applied **at scrape time**, not at display time: the chosen text is what
lands in the cache. So the language is recorded with the entry (`lang`, in both
the gamemedia manifest and the metadata cache) and an entry in another language
is reconsidered on read. Changing the variable therefore re-scrapes the library
by itself — one `jeuInfos` per game, and the already-downloaded media are kept,
so no artwork is transferred twice.

The two ScreenScraper levels are not interchangeable and both are needed:
`jeuInfos.php` answers `403` without the first, and gives a level-0 quota
without the second. Confusing them is the usual cause of a scrape that returns
nothing. With none of them set, the gamemedia tier reports itself unavailable
and covers resolve exactly as they did before it existed.

The developer credential is shared by everyone running the same softname, so it
is never committed and never read from the repo — that is also why the 1.2 s
rate limit in `services/gamemedia` is not negotiable: exceeding it blacklists
the id for every GameCore box, not just this one.

`resolve_path(raw)` turns a config-relative string into an absolute `Path`;
absolute inputs pass through unchanged. Every `romsPath` and `iconPath` goes
through it.

## External disks — `services/storage.py`, `services/storage_monitor.py`

"I plug my ROM disk in" is one of the first three things anyone expects from a
console in a living room. Two roots, and the difference between them is the
whole design:

| | what it is |
|---|---|
| the **mount point** | where udisks decided to put the filesystem. Not ours, **not stable**, and not something to record anywhere |
| the **stable link** | `<DATA>/volumes/<slug>` — a symlink GameCore owns, named after the disk's label, re-pointed at wherever it landed today |

The split exists because udisks mounts at `/run/media/<user>/<label>` and the
name it picks is not reproducible: plug the same disk in twice without a clean
unmount in between and the second mount is `LABEL 1`. A `romsPath` recorded
against a real mount point is a library that works until someone pulls the
cable, and then silently scans nothing.

`<DATA>/volumes/my-disk/nintendo` is a relative path like any other in
`systems.json`, so `resolve_data_path` already resolves it and **no consumer
needed changing** — that is the P3 split paying for itself.

`storage_monitor` polls every 3 s: it mounts an arrival, re-points its link, and
broadcasts `storage:mounted` / `storage:removed` / `storage:failed`. Polled and
not udev-driven on purpose — reaching udev events means either a netlink socket
held open with the right group membership or a rule running something as root on
every device change, and that is a privilege the box does not otherwise need to
save a few seconds on an event that happens when a human walks across a room.

Nothing is cache-invalidated on the way, and that is not an omission: games are
scanned per request from `romsPath`, so the moment the link is re-pointed the
next scan already reads the new disk.

### A disk pulled out mid-game

Expected, not exceptional — a living-room box meets it sooner or later, and
pulled without warning is the default. `storage:lost` names the game and says
what was lost. It cannot be repaired from here: the emulator holds an open
descriptor on a device that is gone, so it fails on its next read and its next
save does not land. Saying so beats a freeze with no explanation, which is what
this looked like before.

Every reader treats a vanished path as a normal state — `iter_rom_files`
already returns nothing for a directory that is not there — so hot removal
costs an empty system, never a traceback that takes the grid down.

### ⚠ exFAT and NTFS carry no POSIX permissions

**ROMs are fine on them. Emulator saves are not.**

Every file on exFAT takes the uid, gid and mode the mount options impose, for
the whole filesystem. A Flatpak emulator writing a save there does not behave as
it does on ext4: permissions cannot be preserved, a lock file cannot be trusted,
and an interrupted write has no atomic rename to fall back on.

`storage.NO_POSIX_PERMISSIONS` lists them and `describe()` attaches
`saves_warning`, which the storage screen shows in amber — never red. A disk
formatted the way every disk in a shop is formatted must not read as broken;
it must read as "put your ROMs here, keep your saves on the internal disk".

GameCore does **not** currently relocate saves onto an external disk, and this
is why. See also the open decision on Flatpak saves below.

## What lives in `config/`

| File | Written by | Read by | In git? |
|---|---|---|---|
| `systems.json` | installer, from `install/generated/systems.json.dist` | `routers/systems.py` | **yes** |
| `apps.json` | installer, from `install/generated/apps.json.dist` | `routers/systems.py` | **yes** |
| `overlays.json` | by hand | `routers/overlays.py`, `electron/main.js`, `overlay_monitor.py` | **yes** |
| `themes/` | shipped + `update/linux.sh` (adds only what is missing) | `services/themes.py` | **yes** |
| `theme.json` | `services/themes.set_active()`, atomically | `services/themes.get_active()` | no |
| `addons.json` | `gamecore-addon` CLI | `routers/addons.py` | no |
| `standby.json` | `POST /api/standby/config`, atomically | `services/standby.py` | no |
| `session.json` | `services/process_manager.py`, atomically | idem, at startup | no |
| `auth.json`, `auth_secret` | `services/auth.py`, mode 0600 | idem | no |
| `playtime.db` | backend (SQLite) | backend | no |

**The OTA rsync excludes `config/` entirely** — but "not in git" is *not* true of
all of it, and the distinction matters when deciding whether overwriting a file
is data loss:

- The **catalogues** (`systems.json`, `apps.json`, `overlays.json`, and the
  bundled themes) are versioned. `install/arch.sh` regenerates the first two from
  `install/generated/*.dist` on **every** run, so editing them in place is not durable —
  edit the `.dist` files.
- The **state** (`theme.json`, `addons.json`, `standby.json`, `session.json`,
  `auth.json`, `auth_secret`, `playtime.db`) is never in git and exists only on
  the box. That is its identity: credentials, installed addons, play history,
  the selected theme. Treat overwriting one as data loss.

Everything written here uses the tmp-file + `os.replace` pattern from
`auth._write_private()`. `write_text()` truncates before it writes, so an
interrupted write left a JSON file that could not be parsed — and the selected
theme, or the standby timings, silently reverted to defaults.

---

## `config/systems.json`

An array. One entry per emulator:

```jsonc
{
  "id": "azahar",                    // primary key used everywhere
  "type": "emulator",
  "label": "Nintendo 3DS",           // shown on the tile
  "platform": "3DS",                 // short badge
  "color": "#ff0096",                // UI accent for this system
  "iconPath": "assets/logos/3ds.png",
  "path": "flatpak",                 // "flatpak" or an absolute binary path
  "args": "run org.azahar_emu.Azahar -f",
  "romsPath": "emu/azahar/",
  "extensions": ["*.3ds", "*.zip"],
  "libretroSystems": ["Nintendo - Nintendo 3DS"],   // cover scraping key
  "scanDirs": false                  // true → games are folders (PS3, PS4)
}
```

| Key | Consumed by |
|---|---|
| `id` | everything — `list_all()` lookups, cover cache paths, overlay config |
| `path` + `args` | `process_manager.launch()`; `args` goes through `shlex.split`, the ROM path is appended |
| `romsPath` | `list_games()`, **and the containment check in `launch_game()`** |
| `extensions` | `rom_scanner.matches_ext` (glob patterns) |
| `scanDirs` | `iter_rom_files` yields directories; enables `local_media.get_title()` |
| `libretroSystems` | `scraper._get_index()` |
| `color`, `iconPath`, `label`, `platform` | UI only |

Two optional keys the code honours but the shipped config does not currently
use:

| Key | Effect |
|---|---|
| `"gamepadTrigger": true` | `_gamepad_trigger()` runs `sudo udevadm trigger` ×3 after launch, for Flatpak apps that only see a pad after a udev re-fire. Needs a sudoers rule. |
| `"fullscreen": {…}` | `fullscreen_enforcer.enforce()` forces the window fullscreen over EWMH, for apps with no fullscreen flag |

## `config/apps.json`

Same shape, minus the ROM keys, plus `"kind": "app"`:

```jsonc
{ "id": "steam", "kind": "app", "type": "application", "label": "Steam",
  "platform": "Steam", "color": "#1f6fb3", "iconPath": "assets/logos/steam.png",
  "path": "flatpak", "args": "run com.valvesoftware.Steam" }
```

`list_all()` concatenates systems + apps. `list_games()` returns `[]` for
anything with `kind == "app"` or `type == "application"`.

## `config/overlays.json`

Keyed by system id:

```jsonc
"melonds": {
  "label": "Nintendo DS",
  "wm_class": { "linux": ["melonds", "melonDS", "net.kuribo64.melonDS", "AppRun.wrapped"] },
  "window_rect": { "x": 0, "y": 0, "w": 1920, "h": 1080 },
  "overlay_asset": "assets/overlays/melonds.png",
  "hole": { "x": 600, "y": 0, "w": 720, "h": 1080 },
  "watch_timeout_s": 60
}
```

| Key | Used by |
|---|---|
| `wm_class.linux` | `X11Manager.find_window()` — several spellings because Flatpak wrappers rename the class (note `AppRun.wrapped`) |
| `window_rect` | `force_rect()` target geometry |
| `overlay_asset` | the PNG the overlay window displays |
| `hole` | the transparent zone — **must match the PNG**; it is the fallback frame drawn when the PNG is missing |
| `watch_timeout_s` | how long the monitor waits for the window before giving up |

## `config/addons.json`

Written by the `gamecore-addon` CLI from each addon's `addon.json`. Served
verbatim by `GET /api/addons` and `GET /gc/addons`. Fields that matter
downstream: `name`, `label`, `port`, `path` (`/roms`, `/saves`, `/rpcs3`),
`type` (`web` addons get a nav link), `version`, `api`.

It lives under `<DATA>/config/`, and the CLI and `routers/addons.py` had to
move together — the CLI writes it, the backend reads it, and a box where only
one of them had moved would show an empty Addons screen while having addons
installed.

### The hook contract — `api: 1`

**This is a public contract, and versioning it is a breaking change.** It is
the part of the split that reaches outside this repository: third-party addons
were written when `$GAMECORE_PATH` was writable, and a read-only root breaks
them at install time, on a box in somebody's living room, with the Addons
screen showing a script's stderr.

So an addon must declare `"api": 1` in its `addon.json`. One that does not is
**refused before anything runs**, by name, with the porting instructions — the
person reading that message is a player on a television, not the addon's
author.

What `install.sh` / `uninstall.sh` receive:

| Variable | Meaning |
|---|---|
| `GAMECORE_DATA` | the data root. **Write here.** |
| `ADDON_DATA_DIR` | `<DATA>/addons/<id>/`, created before the hook runs — an addon should not have to know the layout to keep a config file |
| `GAMECORE_PATH` | the install root. **Read-only.** Passed so an addon can find shipped code, never so it can write |
| `GAMECORE_ADDON_API` | the version the CLI speaks |
| `ADDON_DIR`, `USER_NAME`, `GAMECORE_BACKEND_PORT`, `OFFLINE`, `PAYLOAD_DIR` | unchanged |

**The gate is on install and update, never on remove.** A box updated to this
release has addons installed by the old CLI, none of which declares a version.
Refusing to remove them would strand the player with something they cannot
uninstall from the screen that installed it — the update would have taken away
the exit.

### `/opt/gamecore-addons` — the fourth category

The checkout is git-managed code, but the player installs and removes it at
runtime, so it can live on neither a read-only root nor the OTA. It is
**mutable code**, which the code/data split had no name for, and it belongs on
the data side: new installs put it at `<DATA>/addons/_repo` (addon ids cannot
start with `_`, so it cannot collide with an addon's own directory).

An existing `/opt/gamecore-addons` keeps being used. Boxes installed before
this release have their addons there with services already pointing into it;
relocating it from under them would break running addons for no gain, and the
player would have no way to tell why.

## `config/standby.json`

`{enabled, screensaver_delay, sleep_delay, governor}` — shape enforced by the
`StandbyConfig` pydantic model in `routers/standby.py`.

## `config/auth.json` + `auth_secret`

`auth.json` = `{hash: argon2id, generation: int}`. `auth_secret` = 32 random
bytes, the HMAC key for session cookies. Both 0600, written atomically by
`_write_private()`. Bumping `generation` invalidates every live session.

`_auth()` swallows `UnicodeDecodeError` as well as the JSON and OS errors:
`read_text()` raises that one on a non-UTF-8 file, and every LAN request goes
through here — a truncated or foreign `auth.json` used to 500 the whole proxied
surface, `/login` included, leaving no way back in short of SSH.

## `config/session.json`

`{pgid, game_key, system_id, exec_path, launch_args, started_at}` — the process
group of the running game, written by `process_manager` at launch and removed
when it exits.

It exists so a **restarted backend can still reach a game it did not start**.
Without it the new process came up with `_proc = None`, so `is_running` was
false, `kill()` returned at its first line, and the emulator stayed fullscreen
and unkillable — the double-PS shortcut could never close it again. The UI is a
separate service and does not restart with the backend, so it kept asking and
nothing answered.

`adopt_orphan()` runs in the lifespan: if the pgid is still alive, the session is
adopted (reported by `/api/games/session`, killable via `POST /api/games/kill`);
if not, the file is discarded. This was chosen over killing the game on shutdown,
which would take unsaved progress with it on every OTA **and** would still leave
a crash — where no shutdown code runs at all — stranding the player.

---

## `playtime.db`

Created by `db.py:init_db()`.

> **`game_key` is a filename.** It is whatever the library listed, which makes
> it a *reference to something outside the database* — so anything that changes
> what gets listed orphans the rows keyed on the old name. They are not
> deleted, they simply stop being reachable, and a game played for hours
> reports as never played. That is not hypothetical: hiding a `.bin` behind its
> `.cue` did it to one row on the reference box. Any future change to what
> `rom_scanner` lists needs the same treatment
> ([`playtime_repair`](04-backend-services.md#playtime_repairpy-105-l)).

```sql
CREATE TABLE playtime (
    game_key      TEXT PRIMARY KEY,
    system_id     TEXT NOT NULL,
    total_secs    INTEGER NOT NULL DEFAULT 0,
    session_count INTEGER NOT NULL DEFAULT 0,
    last_played   TEXT
);
CREATE TABLE sessions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    game_key   TEXT NOT NULL,
    system_id  TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at   TEXT,
    duration   INTEGER
);
```

`_watch()` writes with an upsert:

```sql
INSERT INTO playtime (…) VALUES (…)
ON CONFLICT(game_key) DO UPDATE SET
    total_secs = total_secs + excluded.total_secs,
    session_count = session_count + 1,
    last_played = excluded.last_played
```

`game_key` is the ROM filename (or the system id for an app), which is why
renaming a ROM resets its history.

`get_db()` re-opens the handle if the cached connection has gone stale — a
long-lived aiosqlite connection can die under the box's suspend cycles.

---

## Caches on disk

| Path | Contents | Invalidation |
|---|---|---|
| `emu/covers/<system>/<name>.png\|jpg` | resolved cover art | manual — **drop a file here to pin a cover** |
| `emu/covers/<system>/<name>.miss` | negative cache | 7 days, or `?refresh=1` |
| metadata cache | game text, incl. negative results | as above |
| `emu/gamemedia/<system>/<key>/game.json` | one game's manifest — metadata + every media it has | none. A game does not change; `?refresh=1` rescrapes |
| `emu/gamemedia/<system>/<key>/<type>.png\|mp4\|pdf` | the media actually downloaded | idem |
| `emu/gamemedia/systems.json` | ScreenScraper's 250-system registry (~4 MB) | none — it is the source of the console aliases |
| `emu/gamescrape/launchbox.sqlite` | offline LaunchBox index, 185 k games (234 MB) | built once by `install/steps/build-media-index.sh` (full installs only), then never touched. The backend does NOT rebuild it: a stale schema disables the tier rather than triggering a 234 MB download from an HTTP handler. `gamescrape.py --refresh` is the manual cure |

Everything gamemedia writes lives under `emu/`, with the ROMs and the covers,
because that directory is excluded from both git and the OTA rsync. A manifest,
a 234 MB index and the artwork all survive an update. Upstream defaults to
`~/.cache`, which under systemd resolves against whichever `HOME` the unit
happens to have.
| `~/.config/gamecore-electron/Cache` | Chromium HTTP cache | cleared by the OTA script and on every Electron start |

## OPEN DECISION — Flatpak saves are in neither tree

**This one is not settled, and it is deliberately not settled here.** It needs a
call from the project owner; what follows is the material to make it with.

The split promises that `tar czf backup.tgz /userdata` restores a box. Today it
does not, and the reason is that the emulators are Flatpaks: they write under
`~/.var/app/<the installed appIds entry>/`, which is neither the installation
nor the data tree.

Worse, saves are **not** in a directory of their own — several sit inside what
looks like a configuration tree, which is why "back up the config directory,
skip the saves" is not an available option:

| Emulator | Where the saves are |
|---|---|
| RPCS3 | `config/rpcs3/dev_hdd0/home/*/savedata/` — inside the config tree |
| Dolphin | `data/dolphin-emu/GC/`, `.../Wii/` |
| PCSX2, DuckStation | `memcards/` |
| Cemu | `mlc01/usr/save/` |
| Ryujinx | `bis/user/save/` |
| azahar | `sdmc/`, `nand/` |
| mGBA, melonDS | `.sav` files **next to the ROMs** |

The last row is the one bright spot: those `.sav` files live in `emu/<system>/`
and are therefore already inside `/userdata` and already backed up. Every other
row is outside it.

The `save-manager` addon covers backup and restore, and it works — but
`install/installer-gui/gamecore_installer.py` offers it with `"default": False`,
so a box installed by clicking through the installer has no save backup at all
and nothing says so.

### Option A — turn `save-manager` on by default

Change the one `default` flag. The addon already exists, is already tested, and
already knows each emulator's layout.

- Backups become opt-out rather than opt-in, which matches what a player
  expects from a console.
- It is a *backup*, not a relocation: saves still live under `~/.var/app`, so
  `tar czf backup.tgz /userdata` still does not capture them. The promise of the
  split stays half-true, and the restore procedure stays two commands.
- Costs a service and its port on every box, including ones whose owner would
  never open the screen.

### Option B — redirect the save directories into `/userdata`

Point each emulator's save location at `<DATA>/saves/<system>/`, by
configuration where the emulator supports it and by symlink where it does not.

- `tar czf backup.tgz /userdata` becomes literally true, which is the property
  the whole phase is for.
- The redirection has to be right for **each** emulator, and being wrong is
  silent in the worst way: the emulator starts, finds no save, and offers a new
  game. That is indistinguishable from a corrupt save to the person holding the
  pad.
- Symlinks into a Flatpak sandbox need a filesystem override per app, so this
  also enlarges the Flatpak permission surface.
- It touches live save data on existing boxes, so it needs its own migration —
  with the same care as `scripts/migrate-userdata.py`, and probably after it.

### What is true either way

Nothing in this phase touches `~/.var/app`. Both options are additive and can
be taken later; taking neither leaves saves exactly as safe (or not) as they
were before the split, which is the status quo and not a regression.

## Assets

| Path | Contents |
|---|---|
| `assets/logos/` | system tiles — **excluded from OTA**, users add their own |
| `assets/overlays/` | bezel PNGs — excluded from OTA |
| `backend/data/gamecontrollerdb.txt` | vendored SDL_GameControllerDB, exported as `SDL_GAMECONTROLLERCONFIG_FILE` |
| `emu/<system>/` | ROMs — excluded from OTA |
