# GameCore

A retro gaming frontend built for kiosk / living-room use.  
React + Electron shell + FastAPI backend — plug in a controller and play.

---

## Table of contents

1. [What it does](#what-it-does)
2. [Requirements](#requirements)
3. [Installation (device)](#installation-device)
4. [Development setup](#development-setup)
5. [First launch](#first-launch)
6. [Adding ROMs](#adding-roms)
7. [Controller navigation](#controller-navigation)
8. [Settings & Wi-Fi](#settings--wi-fi)
9. [Overlays (bezels)](#overlays-bezels)
10. [OTA updates](#ota-updates)
11. [Living-room box setup](#living-room-box-setup)
12. [Project structure](#project-structure)

---

## What it does

GameCore is a full-screen game launcher designed to run on a dedicated machine connected to a TV.  
You navigate with a gamepad, launch emulators, and never touch a keyboard.

**Supported emulators (out of the box):**

| ID | Emulator | System |
|----|----------|--------|
| `dolphin` | Dolphin | GameCube / Wii |
| `duckstation` | DuckStation | PlayStation 1 |
| `pcsx2` | PCSX2 | PlayStation 2 |
| `rpcs3` | RPCS3 | PlayStation 3 |
| `ppsspp` | PPSSPP | PSP |
| `cemu` | Cemu | Wii U |
| `ryujinx` | Ryujinx | Nintendo Switch |
| `azahar` | Azahar | Nintendo 3DS |
| `mgba` | mGBA | Game Boy Advance |
| `melonds` | melonDS | Nintendo DS |
| `gopher64` | Gopher64 | Nintendo 64 |
| `xenia` | Xenia Canary | Xbox 360 |
| `shadps4` | shadPS4 | PlayStation 4 |

> - **PlayStation 1** uses the official DuckStation **AppImage** — the Flatpak was discontinued upstream in 2025.
> - **Xbox 360** runs Xenia Canary **through Wine** (`lib/xenia/xenia_canary.exe`, downloaded by the full installer).
> - **PlayStation 4** uses the shadPS4 Flatpak; games are folders (`emu/shadps4/<Game>/eboot.bin`, `scanDirs`).
> - Everything else installs from Flathub. Full-mode installs grant each emulator `--filesystem` (ROMs) and `--device=all` (controller) overrides automatically.

---

## Requirements

| | Minimum |
|--|---------|
| OS | Arch Linux / Manjaro |
| Display | 1920×1080 (Full HD) |
| GPU | Any — hardware acceleration recommended |
| RAM | 4 GB |
| Storage | 20 GB + (depends on your ROM library) |
| Controller | Any XInput / evdev gamepad |

All emulators are installed via **Flatpak**. Make sure Flatpak is available on your system before running the installer.

---

## Installation (device)

> Run this on the machine that will act as the kiosk.  
> The installer sets up auto-login, auto-start, and all dependencies.

**Graphical installer (recommended)** — a native step-by-step wizard, like any
desktop installer. Download `gamecore-installer` from the
[latest release](https://github.com/p4v1c/GamecoreRenew/releases/latest), then:

```bash
chmod +x gamecore-installer
./gamecore-installer
```

Pick your emulators and addons, paste your API keys (optional), hit Install —
it asks for the administrator password (polkit), downloads the latest GameCore
release and does everything. Re-running it is safe.

**Command line** (SSH / no graphical session):

```bash
git clone https://github.com/p4v1c/GamecoreRenew.git
cd GamecoreRenew
sudo bash install/arch.sh                      # interactive prompts
sudo bash install/arch.sh --unattended my.conf # scripted (see install/gamecore-install.conf.example)
```

What the installer does:
- Installs Node.js, Python, Flatpak, and all emulators
- Creates a Python virtual environment and installs backend dependencies
- Builds the React frontend
- Installs Node modules for Electron
- Creates a `gamecore` system user
- Configures SDDM auto-login with a KDE Plasma (X11) session
- Registers two systemd services: `gamecore-backend` and `gamecore-ui`
- The machine will boot directly into GameCore after a reboot

After installation:
```bash
sudo reboot
```

---

## Development setup

> For development on your own machine — no auto-start, no kiosk mode.

```bash
git clone https://github.com/p4v1c/GamecoreRenew.git
cd GamecoreRenew

# 1. Backend
pip install -r backend/requirements.txt
uvicorn backend.main:app --host 0.0.0.0 --port 8765 --reload

# 2. Frontend (separate terminal)
cd frontend && npm install && npm run dev
# → http://localhost:5173

# 3. Electron (separate terminal)
cd electron && npm install
ELECTRON_DEV=1 npx electron .
```

`DEBUG = True` in `backend/config.py` and `const DEBUG = true` in `electron/main.js` enable:
- DevTools window (detached)
- Dev URLs (localhost:5173 for frontend, localhost:8765 for backend)
- Verbose logging
- No kiosk / fullscreen lock

Set both to `false` before deploying to a device.

---

## First launch

On first boot the splash screen appears, then the **Home** screen.

- **Home** — shows your recently played games and quick-launch apps
- **Library** — full list of all systems and their ROMs, navigate with the D-pad

If no ROMs are found, the library will be empty until you add some (see below).

---

## Adding ROMs

ROMs are stored in `emu/<system_id>/` folders (e.g. `emu/melonds/`, `emu/dolphin/`).

**Option 1 — ROM Manager addon (recommended)**  
The ROM Manager ships as an addon (installed by default by the installer —
or run `gamecore-addon install rom-manager`). From any device on the same
network, open a browser and go to:
```
http://<device-ip>:8770
```
Select a system in the left sidebar, then drag & drop your ROM files.  
They are uploaded directly to the correct folder on the device.

**Option 2 — Copy directly**  
Copy ROM files into the matching `emu/<system_id>/` folder via USB or SSH.

**Supported formats per system:**

| System | Extensions |
|--------|-----------|
| GameCube / Wii | `.iso` `.gcm` `.rvz` `.zip` |
| PlayStation 1 | `.bin` `.cue` `.iso` `.img` `.zip` |
| PlayStation 2 | `.iso` `.bin` `.zip` |
| PlayStation 3 | disc-game **folders** in `emu/rpcs3/` (scanned as directories). Updates/DLC are `.pkg`, installed via the RPCS3 manager addon |
| PSP | `.iso` `.cso` `.zip` |
| Wii U | `.wux` `.rpx` `.iso` `.zip` |
| Switch | `.xci` `.nsp` `.zip` |
| Nintendo 3DS | `.3ds` `.zip` |
| Nintendo DS | `.nds` `.zip` |
| Game Boy Advance | `.gba` `.zip` |
| Nintendo 64 | `.n64` `.z64` `.v64` `.zip` |

---

## Controller navigation

GameCore is designed for full gamepad control — no mouse or keyboard needed.

| Button | Action |
|--------|--------|
| D-pad / Left stick | Navigate menus |
| A / Cross | Confirm / Launch game |
| B / Circle | Back |
| Start / Options | Open Settings |
| Guide / PS button | Kill current game and return home |
| Select / Share | Open Power menu |

Inside a game, press the **Guide button** at any time to exit and return to GameCore.

---

## Settings & Wi-Fi

Open Settings from the top-right icon or press **Start** on the controller.

- **Wi-Fi** — scan and connect to networks
- **Audio** — volume control
- **Bluetooth** — pair controllers
- **Update** — check for and apply OTA updates
- **System** — reboot / shutdown

---

## Addons

Optional modules live in [p4v1c/gamecore-addons](https://github.com/p4v1c/gamecore-addons)
and are managed with one command:

```
gamecore-addon install <name>     # e.g. rom-manager
gamecore-addon list
gamecore-addon update
gamecore-addon remove <name>
```

Each addon runs as its own service on its own port (8770-8799) and shows a
shared nav bar linking every installed web addon — it all feels like one site.
The core only exposes the registry (`GET /api/addons`) and a WebSocket relay
(`POST /api/addons/notify`); it knows nothing about addon internals.

---

## Overlays (bezels)

Overlays are decorative frames displayed on top of the emulator window.  
They fill the black bars that appear on 4:3 and other non-16:9 systems.

> Overlays only work on **X11 sessions** (the installer uses KDE Plasma on X11).  
> On Wayland dev environments, overlays are silently skipped.

### Uploading an overlay

From the ROM Manager addon (`http://<device-ip>:8770`):  
Select a system → click the **Overlay** button → drag & drop or browse for a PNG.

Or copy the PNG directly to:
```
assets/overlays/<system_id>.png
```

### Creating an overlay with ImageMagick

**Install ImageMagick:**
```bash
sudo pacman -S imagemagick
```

The overlay must be a **1920×1080 PNG** with a **transparent hole** where the game screen appears.

> ⚠️ Do **not** use the old `-region … -alpha transparent` recipe: on ImageMagick 7 it
> silently does nothing and produces a fully opaque overlay (the game is then
> completely hidden). Punch the hole with a `DstOut` composite instead:

```bash
magick your_image.png \
  -background "rgb(0,0,0)" -flatten \
  -resize 1920x1080! \
  \( -size <W>x<H> xc:black \) -geometry +<X>+<Y> -compose DstOut -composite \
  assets/overlays/<system_id>.png
```

**Hole dimensions per system** (emulators render the native aspect ratio centered at full screen height):

| System | Native ratio | Hole `<W>x<H>` at `+<X>+<Y>` | Black bars |
|--------|-------------|------------------------------|-----------|
| GameCube / Wii (`dolphin`) | 4:3 | `1440x1080` at `+240+0` | 240px each side |
| PlayStation 1 (`duckstation`) | 4:3 minus PS1 overscan | `1440x968` at `+240+52` | 240px sides, 52px top, 60px bottom |
| PlayStation 2 (`pcsx2`) | 4:3 | `1440x1080` at `+240+0` | 240px each side |
| Nintendo 64 (`gopher64`) | 4:3 | `1440x1080` at `+240+0` | 240px each side |
| Game Boy Advance (`mgba`) | 3:2 (240×160) | `1620x1080` at `+150+0` | 150px each side |
| Nintendo DS (`melonds`) | 2:3 vertical (2 stacked screens) | `720x1080` at `+600+0` | 600px each side |
| Nintendo 3DS (`azahar`) | Stacked (Top 5:3, Bot 4:3) | Two holes (see below) | Variable |

> **16:9 systems** (PS3, PS4, PSP, Wii U, Switch, Xbox 360) fill the entire screen — no black bars, no overlay needed.
> Keep `config/overlays.json` `hole` values in sync with the PNG — the JSON hole is the fallback frame used when the PNG is missing.

**Example — PlayStation 2 / Nintendo 64 / GameCube (full-height 4:3):**
```bash
magick artwork.png \
  -background "rgb(0,0,0)" -flatten \
  -resize 1920x1080! \
  \( -size 1440x1080 xc:black \) -geometry +240+0 -compose DstOut -composite \
  assets/overlays/pcsx2.png     # or gopher64.png / dolphin.png
```

**Example — PlayStation 1 (DuckStation):**

PS1 video output carries its own black overscan bands (slightly off-center: more at
the bottom than the top), so the hole is a bit shorter than full 4:3 and shifted down:

```bash
magick artwork.png \
  -background "rgb(0,0,0)" -flatten \
  -resize 1920x1080! \
  \( -size 1440x968 xc:black \) -geometry +240+52 -compose DstOut -composite \
  assets/overlays/duckstation.png
```

Measured with `AspectRatio = 4:3` in DuckStation. If your games show a different frame,
measure it yourself: take a screenshot in game, then

```bash
magick screenshot.png -resize 1920x1080! -crop 1x1080+960+0 +repage \
  -colorspace gray -threshold 10% -negate -format "%@" info:
```

prints the black band geometry on the centre column — use the bright area's `HxW+X+Y`
as your hole. Remember to mirror the value into the `hole` of `config/overlays.json`.

**Example — Game Boy Advance (3:2):**
```bash
magick mgba.jpg \
  -background "rgb(0,0,0)" -flatten \
  -resize 1920x1080! \
  \( -size 1620x1080 xc:black \) -geometry +150+0 -compose DstOut -composite \
  assets/overlays/mgba.png
```

**Example — Nintendo DS (stacked screens):**
```bash
magick mario_background.png \
  -background "rgb(0,0,0)" -flatten \
  -resize 1920x1080! \
  \( -size 720x1080 xc:black \) -geometry +600+0 -compose DstOut -composite \
  assets/overlays/melonds.png
```

**Example — Nintendo 3DS (two stacked holes):**
```bash
magick artwork.png \
  -background "rgb(0,0,0)" -flatten \
  -resize 1920x1080! \
  \( -size 900x540 xc:black \) -geometry +510+0   -compose DstOut -composite \
  \( -size 720x540 xc:black \) -geometry +600+540 -compose DstOut -composite \
  assets/overlays/azahar.png
```

> `-background "rgb(0,0,0)" -flatten` fills any accidental transparency in the source image.  
> `1920x1080!` forces exact dimensions (the `!` ignores the source aspect ratio).  
> To verify a hole: `magick overlay.png -alpha extract -threshold 50% -negate -format "%@" info:` prints `WxH+X+Y` of the transparent zone.

---

## Cover art

Covers are resolved per game through a tiered pipeline — each tier is only
tried if the previous one found nothing:

1. **Local cache / manual override** — `emu/covers/<system>/<name>.png|.jpg`.
   Drop an image there to force a cover for a game.
2. **Icon embedded in the game itself** (offline, always exact):
   PS3 folders (`PS3_GAME/ICON0.PNG`), PS4 folders (`sce_sys/icon0.png`),
   PSP ISOs (`PSP_GAME/ICON0.PNG` read straight out of the ISO).
   Titles shown in the library also come from the game's `PARAM.SFO`
   for PS3/PS4, so serial-named folders display their real name.
3. **Exact disc-ID lookup** — the ID is read from the image header
   (GameCube/Wii `.iso/.gcm/.rvz`) or from `SYSTEM.CNF` inside the disc
   (PS1/PS2), then fetched from **GameTDB** (GC/Wii/PS3) or the
   **xlenore psx/ps2 cover repos**. No filename guessing involved.
4. **Name-based scraping** — the **libretro thumbnails CDN**, then
   **TheGamesDB** (needs an API key, see below).

Failed lookups are cached for a week (`.miss` files) so browsing the
library stays fast offline. Append `?refresh=1` to a
`/api/covers/<system>/<file>` request to force a re-resolve (e.g. after
renaming a ROM or getting internet back).

### Enable TheGamesDB (recommended)

1. Register for a free API key at **https://thegamesdb.net**
2. Add the key to the backend service:

```bash
sudo systemctl edit gamecore-backend.service
```

In the editor, add:

```
[Service]
Environment=THEGAMESDB_API_KEY=your_key_here
```

Then restart:

```bash
sudo systemctl restart gamecore-backend.service
```

TheGamesDB covers PS3, Switch, Nintendo 64, DS, GBA, PSP, PS1, PS2, GameCube, Wii U, and 3DS.
If no key is set, the scraper silently falls back to libretro only.

---

## Standby

After a configurable idle time (Settings → Standby), GameCore shows a
cover-art screensaver, then turns the screen off via DPMS and drops the
CPU governor to powersave. The box itself stays up: backend, SSH and OTA
updates keep working. **Any controller button wakes it** (evdev-based, so
it works even with the UI asleep); mouse/keyboard input works too. A
running game always blocks standby.

Governor switching is optional and needs a sudoers rule (the screen is
the real power sink — skip this if you don't care):

```
# /etc/sudoers.d/gamecore-standby
your_user ALL=(root) NOPASSWD: /usr/bin/cpupower frequency-set -g powersave, /usr/bin/cpupower frequency-set -g performance
```

---

## OTA updates

Via the UI: **Settings → Update → Check for update → Install**

Or manually on the device:
```bash
bash update/linux.sh
```

The update pulls the latest release from GitHub, replaces app files in place (preserving ROMs, `config/`, and emulators), rebuilds the frontend, then restarts the services through a detached `gamecore-restart.service` unit. That last step needs a one-time root setup:

```bash
sudo install/setup-update-permissions.sh
```

This installs the restart unit and a sudoers rule allowing the GameCore user to start **only** that unit — the update itself runs unprivileged, from the UI, with progress streamed to the settings screen.

---

## Living-room box setup

How the reference box is wired together. GameCore runs from `/opt/GameCore` with two **system** units:

| Unit | Role |
|---|---|
| `gamecore-backend.service` | FastAPI backend (uvicorn, port **8765**). `Environment=GAMECORE_PATH=/opt/GameCore`. The TheGamesDB API key lives in a local drop-in (`systemctl edit gamecore-backend` → `Environment=THEGAMESDB_API_KEY=…`) — never in the repo. |
| `gamecore-ui.service` | Electron shell (`electron/start-ui.sh`), started after the display manager. |

Two companion projects handle TV input and Twitch. **A `--full` install sets both up
automatically** — it clones them, installs their user services, and prompts for the
Twitch Client ID/Secret and the TheGamesDB API key (secrets are written to local
files/systemd drop-ins only, never to git; leave empty for demo mode). It also creates
the Firefox kiosk profiles for the YouTube/Twitch tiles and installs Stremio. The only
manual step left after a full install is copying BIOS/firmwares (PS1/PS2/PS3, DS/3DS,
Switch keys) — those can't be distributed.

For reference, what the installer wires up:

- **[gamepad-tv-bridge](https://github.com/p4v1c/gamepad-tv-bridge)** — daemon translating gamepad input to keyboard events for apps that don't speak gamepad (Firefox kiosk, EmberTV…). Cloned in `/opt/gamepad-tv-bridge`, installed editable in `~/.venv` (`pip install -e .`), runs as the **user** unit `gamepad-tv-bridge.service` (`WantedBy=graphical-session.target`). Per-app YAML profiles in `profiles/` (window-title matching).
- **[Twitch-TV / EmberTV](https://github.com/p4v1c/Twitch-TV)** — controller-first Twitch client. Cloned in `/opt/Twitch-TV`, credentials in `config.json` (copy `config.example.json`), TLS cert via `make-cert.sh`, runs as the **user** unit `embertv.service` (`./install-autostart.sh`), HTTPS port **8097**. GameCore's Twitch app entry (`config/apps.json`) opens it in a Firefox kiosk profile at `https://localhost:8097`.

Apps launched from GameCore that need gamepad access inside Flatpak (e.g. Stremio) use `"gamepadTrigger": true` in `config/apps.json`, which re-triggers udev after launch (requires `NOPASSWD: /usr/bin/udevadm` in sudoers).

---

## Project structure

```
backend/          FastAPI — systems, games, playtime, covers, settings, OTA
  routers/        API endpoints (systems, games, overlays, addons, sysinfo…)
  services/       Process manager, gamepad monitor, overlay monitor, scraper
  data/           gamecontrollerdb.txt (vendored SDL mappings)
frontend/         React + Vite + Framer Motion + Zustand
  src/
    components/   UI components (HomeScreen, LibraryScreen, modals…)
    hooks/        useWebSocket, useGamepad
    store/        Zustand store (screen, selection, modal depth, session)
electron/         Electron kiosk shell + overlay BrowserWindow
config/           runtime state, never in git, never touched by OTA:
                  systems.json, apps.json, overlays.json, addons.json,
                  standby.json, auth.json, playtime.db
assets/           logos/, overlays/
emu/              ROMs per system (emu/dolphin/, emu/melonds/…) + covers/ cache
install/          Installers: arch.sh engine (+ --unattended), installer-gui/ (Qt binary), gamecore-addon CLI, Caddyfile
update/           OTA update script (linux.sh)
docs/             architecture/ (doc détaillée en 10 fichiers, FR), SECURITY.md, CONTROLLER_MODELS.md
```

> **Working on the code?** Start at [`docs/architecture/`](docs/architecture/)
> (French) — runtime topology, sequence diagrams for every flow, a
> function-by-function reference of the backend and frontend, the controller
> pipeline, and the invariants that are easy to break.
