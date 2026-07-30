# 2 — Request flows

The paths worth knowing end to end. Every arrow names the function that runs.

## 1. Launching a game

```mermaid
sequenceDiagram
    participant ui as LibraryScreen
    participant r as routers/games.py
    participant pm as process_manager
    participant ws as ws.py
    participant el as Electron
    participant mon as overlay_monitor
    participant emu as emulator

    ui->>r: POST /api/games/launch {system_id, rom_path, game_key}
    r->>r: list_all() → system, else 404
    r->>pm: is_running? → 409 if busy
    r->>r: rom_path.resolve().relative_to(roms_root) → 403 if outside
    r->>pm: launch(exec_path, exec_args, rom_path, …)
    pm->>pm: _launching = True (synchronous claim)
    pm->>pm: _display_env()
    pm->>emu: create_subprocess_exec(start_new_session=True)
    pm->>ws: set_current_game() + broadcast("game:started")
    pm->>pm: create_task(_watch())
    ws-->>ui: game:started
    ui->>el: window.gamecore.overlayStart(system_id)
    el->>el: loadOverlayConfig() → config/overlays.json
    el->>mon: spawn + {"cmd":"watch","system_id":…,"config":…}
    mon->>mon: find_window(wm_classes) — poll until it appears
    mon-->>el: {"event":"window:ready","rect":{…}}
    el->>el: createOverlayWindow() — transparent, always-on-top
    r-->>ui: {ok: true, game_key}
```

After the response, `launch_game()` may also schedule two fire-and-forget
tasks, both driven by optional keys on the system entry:

- `"gamepadTrigger": true` → `_gamepad_trigger()` runs `sudo udevadm trigger`
  3× at 3 s intervals so Flatpak apps notice the pad.
- `"fullscreen": {…}` → `fullscreen_enforcer.enforce()`.

## 2. Ending a game

Two ways in, one way out.

```mermaid
sequenceDiagram
    participant pad as controller
    participant gm as gamepad_monitor
    participant r as routers/games.py
    participant pm as process_manager
    participant ws as ws.py
    participant ui as React

    alt player presses PS twice within 1 s
        pad->>gm: evdev BTN_MODE
        gm->>gm: _on_guide_pressed()
        gm->>r: POST /api/games/kill
    else emulator exits on its own
        Note over pm: _watch() was already awaiting
    end
    r->>pm: kill()
    pm->>pm: _flatpak_kill() — flatpak kill <app-id>
    pm->>pm: _proc_kill() — SIGKILL the process group
    pm->>pm: _watch() wakes: elapsed = now - _start_time
    alt elapsed > 5 s
        pm->>pm: INSERT/UPDATE playtime (ON CONFLICT DO UPDATE)
    end
    pm->>ws: broadcast("game:finished", {elapsed})
    ws-->>ui: game:finished → clears session, hides overlay
```

Why it is built this way:

- **evdev, not the browser.** Chromium often hides the Guide button, and the
  UI is buried under a fullscreen emulator anyway.
- **Double press.** A single Guide press must never kill a game by accident
  (`GUIDE_DOUBLE_PRESS_MS`, mirrored in the frontend hook).
- **`flatpak kill` first.** SIGTERM to the `flatpak` wrapper never reaches the
  sandboxed app.
- **SIGKILL, never SIGTERM.** Several emulators answer SIGTERM with a
  confirmation dialog nobody can click from a gamepad.
- **The 5 s floor.** An emulator that dies instantly is not a play session.

## 3. Resolving a cover

```mermaid
flowchart TD
    start["GET /api/covers/{system}/{file}"] --> cache{"emu/covers/&lt;system&gt;/&lt;name&gt;<br/>.png / .jpg exists?"}
    cache -->|yes| serve["FileResponse"]
    cache -->|no| miss{".miss file<br/>younger than 7 days?"}
    miss -->|yes| none["404 — UI shows the fallback tile"]
    miss -->|no| t2["local_media.extract_icon()"]
    t2 -->|"PS3 ICON0.PNG · PS4 icon0.png<br/>PSP ICON0.PNG via iso9660"| serve
    t2 -->|nothing| t3["gamemedia.resolve()<br/>(skipped if no source configured)"]
    t3 -->|"ScreenScraper by CRC/MD5/SHA1<br/>or PARAM.SFO title · then LaunchBox"| serve
    t3 -->|nothing| t4["local_media.disc_id()"]
    t4 -->|"GC/Wii header · PS1/PS2 SYSTEM.CNF"| fetch["_fetch_by_id() → GameTDB / xlenore"]
    fetch -->|hit| serve
    fetch -->|miss| t5["scraper.fetch_cover()"]
    t5 -->|"libretro CDN (_name_variants)"| serve
    t5 -->|"then TheGamesDB if key set"| serve
    t5 -->|nothing| write["write .miss"] --> none
```

Entry point: `services/cover_pipeline.py:resolve(system, filename, refresh)`.
`?refresh=1` skips the cache and the `.miss` check.

Tiers 2 and 4 are **offline and exact** — they read the game itself, so they
never mis-identify. Tier 3 is exact too when the ROM is a real file: a
CRC32 the ScreenScraper database recognises identifies the game outright, which
is the only exact method available on a cartridge (no embedded icon, no serial
to read). Tier 5 is fuzzy name matching and is only reached when the game
carries no identity anywhere.

Tier 3 is also the one that can be **absent**: with no ScreenScraper account
and no LaunchBox index, `gamemedia.available()` is False and the flow is the
one that ran before it existed.

## 3b. Resolving any other media

```mermaid
flowchart TD
    start["GET /api/media/{system}/{file}/media/{type}"] --> man{"manifest cached?"}
    man -->|no| scrape["gamemedia.resolve() — one jeuInfos,<br/>downloads the cover, defers the rest"]
    man -->|yes| have{"type in the manifest?"}
    scrape --> have
    have -->|no| l404["404 + the list of types this game has"]
    have -->|"file on disk"| serve["FileResponse, immutable"]
    have -->|"deferred (URL kept, credential-free)"| fetch["fetch_media() — one download,<br/>credentials restored, 1.2 s limiter"]
    fetch --> serve
    fetch -->|failed| e502["502 — URL kept, retried next time"]
```

The manifest is scraped once per game and holds every media the sources have.
Only what is displayed is downloaded: a first request for `box-3d` costs one
HTTP call and **no ScreenScraper quota**, because the URL was already recorded.

## 4. OTA update

```mermaid
sequenceDiagram
    participant ui as UpdatePage
    participant r as routers/update.py
    participant sh as update/linux.sh
    participant gh as GitHub
    participant sd as systemd

    ui->>r: GET /api/update/check
    r->>gh: latest release
    r->>r: _version_int() — tolerant compare
    r-->>ui: {update_available, current, latest}
    ui->>r: POST /api/update/apply
    r->>sh: spawn, _pump() streams stdout
    r-->>ui: WS progress lines
    sh->>gh: download gamecore-ota.tar.gz
    sh->>sh: rsync -a --exclude .venv/ emu/ config/ emu-configs/ assets/{overlays,logos}/
    sh->>sh: rsync --delete frontend/dist/ and frontend/src/
    sh->>sh: write VERSION, pip install, clear Electron cache
    sh->>sd: systemctl start --no-block gamecore-restart.service
    Note over sh,sd: detached on purpose — the script lives in the<br/>backend's cgroup and would otherwise kill itself
```

## 5. Standby, and waking up

```mermaid
stateDiagram-v2
    [*] --> Active
    Active --> Screensaver: idle > screensaver delay
    Screensaver --> Asleep: idle > sleep delay
    Asleep --> Active: on_input() from evdev
    Screensaver --> Active: on_input()
    Active --> Active: a game is running (standby blocked)
```

`services/standby.py:run()` polls. `_enter(stage)` drives the transitions,
`_screen(False)` cuts the display over DPMS, `_governor("powersave")` drops the
CPU (optional, needs a sudoers rule). `on_input()` is called from
`gamepad_monitor`'s evdev loop — which is why a controller wakes the box even
though the UI is asleep and the browser is not listening.

## 6. LAN authentication

```mermaid
sequenceDiagram
    participant c as browser (LAN)
    participant cad as Caddy :8443
    participant core as backend /api/auth
    participant addon as save-manager :8772

    c->>cad: GET /saves/
    cad->>core: forward_auth → GET /api/auth/verify (cookie)
    alt no / bad cookie
        core-->>cad: 302 /login?next=/saves/
        cad-->>c: login page (proxied without auth)
        c->>core: POST /api/auth/login {password}
        core->>core: blocked_for(ip)? argon2 verify
        core->>core: _set_session() → gc_session cookie
    else valid
        core-->>cad: 200 + X-GC-User
        cad->>addon: proxied request + X-GC-User
    end
```

The core's own `/api/*` is **403 from the LAN, always**. Addons contain no
auth code — Caddy is the enforcement point. The TV bypasses all of this over
loopback.

## 7. Overlay lifecycle

```mermaid
sequenceDiagram
    participant ui as React
    participant el as Electron main
    participant mon as overlay_monitor.py
    participant x as X11

    ui->>el: overlayStart(system_id)
    el->>mon: {"cmd":"watch", system_id, config}
    loop until timeout (watch_timeout_s)
        mon->>x: find_window(wm_classes) via _NET_CLIENT_LIST
    end
    mon-->>el: window:waiting … then window:ready {rect}
    el->>el: createOverlayWindow() + loadURL(/overlay?…)
    mon->>x: force_rect() — ClientMessage to leave fullscreen, then configure
    Note over mon,x: writing _NET_WM_STATE directly clears every state<br/>and desyncs the WM — always use the ClientMessage
    mon-->>el: window:closed (emulator exited)
    el->>el: destroyOverlayWindow()
```

The whole feature is disabled when `WAYLAND_DISPLAY` is set
(`_WAYLAND_SESSION`), silently. A dev machine on Wayland will never reproduce
an overlay bug.
