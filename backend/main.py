"""GameCore — FastAPI backend."""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from .config import DEBUG
logging.basicConfig(level=logging.DEBUG if DEBUG else logging.WARNING)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .db import init_db
from . import ws
from .routers import systems, games, playtime, covers, metadata, sysinfo, update, overlays, addons
from .routers import auth as auth_routes
from .routers import standby as standby_router
from .routers import controllers as controllers_router
from .routers.settings import wifi, audio, bluetooth
from .services import battery, gamepad_monitor, prefetch, standby
from .config import GAMECORE_ROOT, COVERS_DIR, ASSETS_DIR

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    monitor_task = asyncio.create_task(gamepad_monitor.run())
    battery_task = asyncio.create_task(battery.run())
    standby_task = asyncio.create_task(standby.run())
    prefetch_task = asyncio.create_task(prefetch.run())
    yield
    monitor_task.cancel()
    battery_task.cancel()
    standby_task.cancel()
    prefetch_task.cancel()


app = FastAPI(title="GameCore", version="1.0.0", lifespan=lifespan)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(systems.router, prefix="/api")
app.include_router(games.router, prefix="/api")
app.include_router(playtime.router, prefix="/api")
app.include_router(covers.router, prefix="/api")
app.include_router(metadata.router, prefix="/api")
app.include_router(sysinfo.router, prefix="/api")
app.include_router(update.router, prefix="/api")
app.include_router(overlays.router, prefix="/api")
app.include_router(addons.router, prefix="/api")
app.include_router(standby_router.router, prefix="/api")
app.include_router(controllers_router.router, prefix="/api")
app.include_router(wifi.router, prefix="/api")
app.include_router(audio.router, prefix="/api")
app.include_router(bluetooth.router, prefix="/api")
app.include_router(auth_routes.router, prefix="/api")

# ── Web managers ─────────────────────────────────────────────────────────────
# The ROM manager moved to the rom-manager addon (port 8770) —
# see https://github.com/p4v1c/gamecore-addons

@app.get("/overlay", include_in_schema=False)
def overlay_page():
    return FileResponse(str(frontend_dist / "index.html"), media_type="text/html")


@app.get("/gc/addons", include_in_schema=False)
def gc_addons():
    # Same payload as /api/addons, on a path Caddy proxies to the LAN without
    # auth: the shared nav bar of the addon UIs needs it before login state
    # is known (see docs/SECURITY.md).
    return addons.list_installed()


@app.get("/login", include_in_schema=False)
def login_page():
    # Self-contained login form for LAN clients, proxied without auth by
    # Caddy. The TV never sees it (loopback bypasses Caddy entirely).
    return FileResponse(
        str(Path(__file__).parent / "templates" / "login.html"),
        media_type="text/html",
    )


# ── Static files (covers served directly) ────────────────────────────────────
# Create the directories before mounting: a conditional mount decided at
# import time would leave /covers dead until a restart on a fresh checkout
# (the covers dir used to be created later, in the lifespan).
for _dir, _route, _name in (
    (COVERS_DIR, "/covers", "covers"),
    (ASSETS_DIR / "logos", "/assets/logos", "logos"),
    (ASSETS_DIR / "overlays", "/assets/overlays", "overlays"),
    (GAMECORE_ROOT / "backend" / "data", "/data", "data"),
):
    _dir.mkdir(parents=True, exist_ok=True)
    app.mount(_route, StaticFiles(directory=str(_dir)), name=_name)

# ── WebSocket (must be registered before the catch-all static mount) ──────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws.disconnect(websocket)


# ── Serve built frontend (production) ────────────────────────────────────────
frontend_dist = GAMECORE_ROOT / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
