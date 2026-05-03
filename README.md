# GameCore

Gaming frontend (React + Electron + FastAPI) — successor to the Qt version.

## Quick start (dev)

```bash
# 1. Backend
cd backend
pip install -r requirements.txt
uvicorn backend.main:app --host 0.0.0.0 --port 8765 --reload

# 2. Frontend (separate terminal)
cd frontend
npm install
npm run dev        # → http://localhost:5173

# 3. Electron (separate terminal, optional)
cd electron
npm install
ELECTRON_DEV=1 npx electron .
```

## Install on device

```bash
sudo bash install.sh
```

## Structure

```
backend/      FastAPI — systems, games, playtime, covers, WiFi/BT/audio, OTA
frontend/     React + Vite + Framer Motion + Zustand
electron/     Electron kiosk shell
config/       systems.json, apps.json, controller_mappings.json
assets/       logos/, backgrounds/
emu/          ROMs per system + covers cache
web/          Standalone HTML pages — ROM manager
```

## ROM upload

Access `http://<device-ip>:8765/roms` from any device on the network.
Drag & drop ROMs per system — they land in the correct `emu/<system>/` folder.

## Update

Via Settings → Update in the UI, or manually:
```bash
sudo bash update.sh
```

## Overlays

Overlays are decorative bezels displayed on top of the emulator window.
PNG files go in `assets/overlays/<system_id>.png` (e.g. `assets/overlays/melonds.png`).

You can upload overlays directly from the ROM manager: `http://<device-ip>:8765/roms` → select a system → **Overlay** button.

### Creating an overlay with ImageMagick

Install ImageMagick:
```bash
# Arch / Manjaro
sudo pacman -S imagemagick

# Debian / Ubuntu
sudo apt install imagemagick
```

The overlay must be **1920×1080 PNG** with a **transparent hole** where the game screen appears.
Each system has its own hole position. Use the command below and replace the `-region` value with the one matching your system.

```bash
convert your_image.png \
  -background "rgb(0,0,0)" -flatten \
  -resize 1920x1080! \
  -alpha set \
  -region <W>x<H>+<X>+<Y> \
  -alpha transparent \
  assets/overlays/<system_id>.png
```

**Hole dimensions per system (at 1920×1080):**

| System | Ratio | `-region` value | Black bars |
|--------|-------|----------------|-----------|
| GameCube / Wii (`dolphin`) | 4:3 | `1440x1080+240+0` | 240px each side |
| PlayStation 1 (`duckstation`) | 4:3 | `1440x1080+240+0` | 240px each side |
| PlayStation 2 (`pcsx2`) | 4:3 | `1440x1080+240+0` | 240px each side |
| Nintendo 64 (`gopher64`) | 4:3 | `1440x1080+240+0` | 240px each side |
| Game Boy Advance (`mgba`) | 3:2 | `1620x1080+150+0` | 150px each side |
| Nintendo DS (`melonds`) | 2:3 vertical | `720x1080+600+0` | 600px each side |
| Nintendo 3DS (`azahar`) | 5:3 top screen | `1800x1080+60+0` | 60px each side |
| PlayStation 3 (`rpcs3`) | 16:9 | `1920x1080+0+0` | none |
| PSP (`ppsspp`) | 16:9 | `1920x1080+0+0` | none |
| Wii U (`cemu`) | 16:9 | `1920x1080+0+0` | none |
| Switch (`ryujinx`) | 16:9 | `1920x1080+0+0` | none |

**Example — Nintendo DS overlay:**
```bash
convert mario_background.png \
  -background "rgb(0,0,0)" -flatten \
  -resize 1920x1080! \
  -alpha set \
  -region 720x1080+600+0 \
  -alpha transparent \
  assets/overlays/melonds.png
```

> `-flatten` removes any accidental transparency from the source image before cutting the hole.
> `-background "rgb(0,0,0)" -flatten` fills the existing alpha with black first.
> `1920x1080!` forces exact dimensions (the `!` ignores aspect ratio).
