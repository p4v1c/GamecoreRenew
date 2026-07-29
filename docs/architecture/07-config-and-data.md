# 7 — Config & data

Everything the box stores, and who writes it.

## Path resolution — `backend/config.py`

Nothing hardcodes `/opt/GameCore`. Every path derives from `GAMECORE_ROOT`,
which is `$GAMECORE_PATH` or the repo root.

| Constant | Value |
|---|---|
| `GAMECORE_ROOT` | `$GAMECORE_PATH` or the repo root |
| `SYSTEMS_FILE` | `config/systems.json` |
| `APPS_FILE` | `config/apps.json` |
| `PLAYTIME_DB` | `config/playtime.db` |
| `COVERS_DIR` | `emu/covers` |
| `ASSETS_DIR` | `assets/` |
| `BACKEND_PORT` | `$GAMECORE_BACKEND_PORT` or 8765 |
| `APP_VERSION` | contents of `VERSION` (written by the OTA script) |
| `GITHUB_REPO`, `UPDATE_ASSET` | `p4v1c/GamecoreRenew`, `gamecore-ota.tar.gz` |
| `THEGAMESDB_API_KEY` | env only — never committed |
| `DEBUG` | must be `false` on a device |

`resolve_path(raw)` turns a config-relative string into an absolute `Path`;
absolute inputs pass through unchanged. Every `romsPath` and `iconPath` goes
through it.

## What lives in `config/`

| File | Written by | Read by | In git? |
|---|---|---|---|
| `systems.json` | installer, from `install/systems.json.dist` | `routers/systems.py` | **yes** |
| `apps.json` | installer, from `install/apps.json.dist` | `routers/systems.py` | **yes** |
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
  `install/*.dist` on **every** run, so editing them in place is not durable —
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
`type` (`web` addons get a nav link), `version`.

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
| metadata cache | TheGamesDB text, incl. negative results | as above |
| `~/.config/gamecore-electron/Cache` | Chromium HTTP cache | cleared by the OTA script and on every Electron start |

## Assets

| Path | Contents |
|---|---|
| `assets/logos/` | system tiles — **excluded from OTA**, users add their own |
| `assets/overlays/` | bezel PNGs — excluded from OTA |
| `backend/data/gamecontrollerdb.txt` | vendored SDL_GameControllerDB, exported as `SDL_GAMECONTROLLERCONFIG_FILE` |
| `emu/<system>/` | ROMs — excluded from OTA |
