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
11. [Project structure](#project-structure)

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

---

## Requirements

| | Minimum |
|--|---------|
| OS | Arch Linux / Manjaro **or** Debian / Ubuntu |
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

**Arch / Manjaro:**
```bash
git clone https://github.com/p4v1c/GamecoreRenew.git
cd GamecoreRenew
sudo bash install/arch.sh
```

**Debian / Ubuntu:**
```bash
git clone https://github.com/p4v1c/GamecoreRenew.git
cd GamecoreRenew
sudo bash install/debian.sh
```

**Windows:**
```bat
git clone https://github.com/p4v1c/GamecoreRenew.git
cd GamecoreRenew
install\windows.bat
```

What the installer does:
- Installs Node.js, Python, Flatpak, and all emulators
- Creates a Python virtual environment and installs backend dependencies
- Builds the React frontend
- Installs Node modules for Electron
- Creates a `gamecore` system user
- Configures SDDM auto-login with an openbox session
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

**Option 1 — ROM Manager (recommended)**  
From any device on the same network, open a browser and go to:
```
http://<device-ip>:8765/roms
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
| PlayStation 3 | `.pkg` (installed in RPCS3 separately) |
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

## Overlays (bezels)

Overlays are decorative frames displayed on top of the emulator window.  
They fill the black bars that appear on 4:3 and other non-16:9 systems.

> Overlays only work on **X11 sessions** (the kiosk installer uses openbox/X11).  
> On Wayland dev environments, overlays are silently skipped.

### Uploading an overlay

From the ROM Manager (`http://<device-ip>:8765/roms`):  
Select a system → click the **Overlay** button → drag & drop or browse for a PNG.

Or copy the PNG directly to:
```
assets/overlays/<system_id>.png
```

### Creating an overlay with ImageMagick

**Install ImageMagick:**
```bash
# Arch / Manjaro
sudo pacman -S imagemagick

# Debian / Ubuntu
sudo apt install imagemagick
```

The overlay must be a **1920×1080 PNG** with a **transparent hole** where the game screen appears.  
Start from any 1920×1080 artwork, then cut the hole with:

```bash
convert your_image.png \
  -background "rgb(0,0,0)" -flatten \
  -resize 1920x1080! \
  -alpha set \
  -region <W>x<H>+<X>+<Y> \
  -alpha transparent \
  assets/overlays/<system_id>.png
```

**Hole dimensions per system:**

| System | Ratio | `-region` value | Black bars |
|--------|-------|----------------|-----------|
| GameCube / Wii (`dolphin`) | 4:3 | `1440x1080+240+0` | 240px each side |
| PlayStation 1 (`duckstation`) | 4:3 (Centered) | `1280x960+320+60` | 320px L/R, 60px T/B |
| PlayStation 2 (`pcsx2`) | 4:3 (Centered) | `1280x960+320+60` | 320px L/R, 60px T/B |
| Nintendo 64 (`gopher64`) | 4:3 (Centered) | `1280x960+320+60` | 320px L/R, 60px T/B |
| Game Boy Advance (`mgba`) | 4:3 | `1440x1080+240+0` | 240px each side |
| Nintendo DS (`melonds`) | 2:3 vertical | `720x1080+600+0` | 600px each side |
| Nintendo 3DS (`azahar`) | Stacked (Top 5:3, Bot 4:3) | Two regions (see below) | Variable |

> **16:9 systems** (PS3, PSP, Wii U, Switch) fill the entire screen — no black bars, no overlay needed.

**Example — Nintendo 3DS (stacked screens):**
```bash
convert artwork.png \
  -background "rgb(0,0,0)" -flatten \
  -resize 1920x1080! \
  -alpha set \
  -region 900x540+510+0 -alpha transparent +region \
  -region 720x540+600+540 -alpha transparent +region \
  assets/overlays/azahar.png
```

**Example — PlayStation 1 / 2:**
```bash
convert test.jpg \
  -background "rgb(0,0,0)" -flatten \
  -resize 1920x1080! \
  -alpha set \
  -region 1280x960+320+60 -alpha transparent +region \
  assets/overlays/duckstation.png
```

**Example — Game Boy Advance:**
```bash
convert image_cffc32.jpg \
  -background "rgb(0,0,0)" -flatten \
  -resize 1920x1080! \
  -alpha set \
  -region 1440x1080+240+0 -alpha transparent +region \
  assets/overlays/mgba.png
```

**Example — Nintendo 64:**
```bash
convert pokemonfinale.jpg \
  -background "rgb(0,0,0)" -flatten \
  -resize 1920x1080! \
  -alpha set \
  -region 1280x960+320+60 -alpha transparent +region \
  assets/overlays/gopher64.png
```

**Example — Nintendo DS Mario-themed overlay:**
```bash
convert mario_background.png \
  -background "rgb(0,0,0)" -flatten \
  -resize 1920x1080! \
  -alpha set \
  -region 720x1080+600+0 \
  -alpha transparent \
  assets/overlays/melonds.png
```

> `-background "rgb(0,0,0)" -flatten` fills any accidental transparency in the source image.  
> `1920x1080!` forces exact dimensions (the `!` ignores the source aspect ratio).

---

## Cover art

GameCore scrapes cover images automatically when you browse your library.
It first tries the **libretro thumbnails CDN** (free, no key needed).
For systems with limited libretro coverage (PS3, Switch, etc.), it falls back to **TheGamesDB**.

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

## OTA updates

Via the UI: **Settings → Update → Check for update → Install**

Or manually on the device:
```bash
# Linux
sudo bash update/linux.sh

# Windows
update\windows.bat
```

The update pulls the latest release from GitHub, replaces app files (preserving ROMs, config, and emulators), and restarts the services automatically.

---

## Project structure

```
backend/          FastAPI — systems, games, playtime, covers, settings, OTA
  routers/        API endpoints (systems, games, roms, overlays, sysinfo…)
  services/       Process manager, gamepad monitor, overlay monitor, scraper
frontend/         React + Vite + Framer Motion + Zustand
  src/
    components/   UI components (HomeScreen, LibraryScreen, modals…)
    hooks/        useWebSocket, useGamepad, useStore
electron/         Electron kiosk shell + overlay BrowserWindow
config/           systems.json, overlays.json
assets/           logos/, overlays/
emu/              ROMs per system (emu/dolphin/, emu/melonds/…)
web/              Standalone HTML — ROM manager (/roms)
install/          Platform installers (arch.sh, debian.sh, windows.bat)
update/           OTA update scripts (linux.sh, windows.bat)
```
