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
