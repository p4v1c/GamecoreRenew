"""GameCore — FastAPI backend."""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from .config import DEBUG
logging.basicConfig(level=logging.DEBUG if DEBUG else logging.WARNING)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .db import init_db
from . import ws
from .routers import systems, games, playtime, covers, sysinfo, update, roms
from .routers.settings import wifi, audio, bluetooth
from .services import gamepad_monitor
from .config import GAMECORE_ROOT, COVERS_DIR, ASSETS_DIR

WEB_DIR = GAMECORE_ROOT / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    monitor_task = asyncio.create_task(gamepad_monitor.run())
    yield
    monitor_task.cancel()


app = FastAPI(title="GameCore", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(systems.router, prefix="/api")
app.include_router(games.router, prefix="/api")
app.include_router(playtime.router, prefix="/api")
app.include_router(covers.router, prefix="/api")
app.include_router(sysinfo.router, prefix="/api")
app.include_router(update.router, prefix="/api")
app.include_router(roms.router, prefix="/api")
app.include_router(wifi.router, prefix="/api")
app.include_router(audio.router, prefix="/api")
app.include_router(bluetooth.router, prefix="/api")

# ── Web managers ─────────────────────────────────────────────────────────────
@app.get("/roms", include_in_schema=False)
def rom_manager():
    return FileResponse(str(WEB_DIR / "roms.html"), media_type="text/html")


# ── Static files (covers served directly) ────────────────────────────────────
if COVERS_DIR.exists():
    app.mount("/covers", StaticFiles(directory=str(COVERS_DIR)), name="covers")

if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")

# ── Serve built frontend (production) ────────────────────────────────────────
frontend_dist = GAMECORE_ROOT / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")


# ── WebSocket ─────────────────────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws.disconnect(websocket)
