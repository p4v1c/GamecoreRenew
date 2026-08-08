"""GameCore — FastAPI backend."""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from .config import DEBUG
logging.basicConfig(level=logging.DEBUG if DEBUG else logging.WARNING)

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .db import init_db
from . import ws
from .routers import systems, games, playtime, covers, media, metadata, sysinfo, update, overlays, addons, catalog
from .routers import auth as auth_routes
from .routers import bios as bios_router
from .routers import standby as standby_router
from .routers import controllers as controllers_router
from .routers import themes as themes_router
from .routers.settings import wifi, audio, bluetooth
from .services import battery, gamepad_monitor, playtime_repair, prefetch, standby
from .services.process_manager import process_manager
from .config import GAMECORE_ROOT, COVERS_DIR, ASSETS_DIR, BACKEND_PORT

log = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    # A game's playtime is keyed by the filename the library listed, so a
    # change in what gets listed silently orphans it. Hiding a .bin behind its
    # .cue does exactly that — the hours are still in the database and nothing
    # points at them any more. Runs once (idempotent), before anything can
    # serve a library.
    try:
        moved = await playtime_repair.rekey_shadowed_entries()
        if moved:
            log.info("playtime: %d entr%s re-keyed onto their disc descriptor",
                     moved, "y" if moved == 1 else "ies")
    except Exception:
        log.exception("lifespan: playtime repair failed")

    # Before anything else: the screen. Standby state lives in memory but its
    # effect does not — `xset dpms force off` belongs to the X server, which
    # SDDM owns and which does not restart with us. A box that went to sleep and
    # then had its backend restarted came back believing it was awake with the
    # TV still dark, and nothing could wake it: pad events arrive over evdev,
    # not X, so DPMS never re-armed on its own. Unconditional, so restarting the
    # backend — what anyone stuck like that will try — actually fixes it.
    try:
        await standby.resume_after_restart()
    except Exception:
        log.exception("lifespan: could not force the screen back on")

    # Re-attach to a game a previous process left running, so the double-PS
    # shortcut can still close it.
    try:
        await process_manager.adopt_orphan()
    except Exception:
        log.exception("lifespan: could not adopt the previous session")

    tasks = [
        asyncio.create_task(gamepad_monitor.run()),
        asyncio.create_task(battery.run()),
        asyncio.create_task(standby.run()),
        asyncio.create_task(prefetch.run()),
    ]
    yield
    for t in tasks:
        t.cancel()
    # Actually wait for them: cancel() only schedules the cancellation, so
    # shutdown used to return with the tasks still mid-await.
    await asyncio.gather(*tasks, return_exceptions=True)
    # The running game is deliberately left alone — see
    # process_manager._save_session(). Killing it here would take the player's
    # unsaved progress with it on any OTA or restart, and would do nothing at
    # all for the case that actually strands them: a crash, where this code
    # never runs. The pgid on disk covers both.


app = FastAPI(title="GameCore", version="1.0.0", lifespan=lifespan)


# ── Cross-origin guard ───────────────────────────────────────────────────────
# The core is unauthenticated on loopback, and the box runs browsers that can
# reach it — the Firefox kiosk profiles arch.sh installs, and Stremio. A page in
# one of those could carry
#     <form action="http://127.0.0.1:8765/api/games/kill" method="post">
# and auto-submit it: the running game dies, the save with it, from an ad on an
# unrelated site. Only endpoints taking no Pydantic body are reachable that way
# — a form can send urlencoded, multipart or text/plain and FastAPI answers 422
# to anything else — which still leaves games/kill, update/apply,
# addons/{name}/install and standby/exit.
#
# There was no middleware at all here: no CORS, no TrustedHost, no origin check.

_LOOPBACK = {"localhost", "127.0.0.1", "::1"}


def _hostport(netloc: str, default_port: int) -> tuple[str, int]:
    """(host, port) from a netloc — lowercased, IPv6 brackets stripped."""
    netloc = netloc.strip().lower()
    if netloc.startswith("["):                      # [::1]:8765
        host, _, rest = netloc.partition("]")
        host, port = host[1:], rest.lstrip(":")
    else:
        host, _, port = netloc.partition(":")
    try:
        return host, int(port) if port else default_port
    except ValueError:
        return host, default_port


def _origin_ok(headers) -> bool:
    """False for a write driven by a page we are not serving."""
    if headers.get("sec-fetch-site") == "cross-site":
        return False

    origin = headers.get("origin")
    if not origin:
        # curl, the addon CLI, the install scripts. A browser always attaches
        # Origin to a cross-origin write, so nothing we are defending against
        # arrives without one.
        return True

    scheme, _, rest = origin.partition("://")
    if not rest:
        return False
    o_host, o_port = _hostport(rest, 443 if scheme == "https" else 80)
    h_host, h_port = _hostport(headers.get("host", ""), o_port)

    # Same-origin. This is the branch that keeps LAN login working: /login and
    # /api/auth/* are proxied by Caddy from https://<whatever address the client
    # used>:8443, the box has no fixed name, and Caddy passes the client's Host
    # through — so comparing the two is the check, with no hardcoded host.
    if (o_host, o_port) == (h_host, h_port):
        return True

    # The TV. Electron loads http://localhost:<BACKEND_PORT> while the socket
    # may report 127.0.0.1; both spellings mean this machine. Deliberately not a
    # blanket loopback pass — another local app on a different port is not the UI.
    return o_host in _LOOPBACK and h_host in _LOOPBACK and o_port in (h_port, BACKEND_PORT)


@app.middleware("http")
async def cross_origin_guard(request: Request, call_next):
    if request.method not in ("GET", "HEAD", "OPTIONS") and not _origin_ok(request.headers):
        return JSONResponse({"detail": "cross-origin request refused"}, status_code=403)
    return await call_next(request)


# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(systems.router, prefix="/api")
app.include_router(games.router, prefix="/api")
app.include_router(playtime.router, prefix="/api")
app.include_router(covers.router, prefix="/api")
app.include_router(media.router, prefix="/api")
app.include_router(metadata.router, prefix="/api")
app.include_router(sysinfo.router, prefix="/api")
app.include_router(update.router, prefix="/api")
app.include_router(overlays.router, prefix="/api")
app.include_router(addons.router, prefix="/api")
# The pack catalogue: what this box could run, and installing it without
# re-running the installer. Same busy-lock and WebSocket shape as addons.
app.include_router(catalog.router, prefix="/api")
app.include_router(bios_router.router, prefix="/api")
app.include_router(standby_router.router, prefix="/api")
app.include_router(controllers_router.router, prefix="/api")
app.include_router(themes_router.router, prefix="/api")
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
# Logos are NOT a static mount any more: they live in catalog/<id>/logo.png
# and only assets/logos/ holds the operator's own replacements. The route in
# routers/systems.py serves both, override first — see public_router there.
app.include_router(systems.public_router)

for _dir, _route, _name in (
    (COVERS_DIR, "/covers", "covers"),
    (ASSETS_DIR / "overlays", "/assets/overlays", "overlays"),
    (GAMECORE_ROOT / "backend" / "data", "/data", "data"),
):
    _dir.mkdir(parents=True, exist_ok=True)
    app.mount(_route, StaticFiles(directory=str(_dir)), name=_name)


class _NoCacheStatic(StaticFiles):
    """Static files that must never be served from the browser cache.

    A theme is a folder of ES modules the browser imports directly. The loader
    can bust the entry point's URL, but the entry's own relative imports
    (home.js, settings.js, ...) and its stylesheet resolve without that query,
    so the browser pins the first version it ever saw. Editing a theme then
    changes nothing on screen, and a fix shipped by update stays invisible.
    These files are small and local; not caching them costs nothing.
    """

    def is_not_modified(self, response_headers, request_headers) -> bool:
        return False

    def file_response(self, *args, **kwargs):
        resp = super().file_response(*args, **kwargs)
        resp.headers["Cache-Control"] = "no-store, must-revalidate"
        return resp


# Theme modules and their assets — imported by the browser from here.
_themes_dir = GAMECORE_ROOT / "config" / "themes"
_themes_dir.mkdir(parents=True, exist_ok=True)
app.mount("/themes", _NoCacheStatic(directory=str(_themes_dir)), name="themes")

# ── WebSocket (must be registered before the catch-all static mount) ──────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # A WebSocket handshake is a GET and is not subject to CORS, so any page in
    # any browser on this box could open ws://127.0.0.1:8765/ws and read every
    # event the UI sees — what launched, what is installed, controller activity.
    # The HTTP middleware never sees this route; check the same rule here.
    if not _origin_ok(websocket.headers):
        await websocket.close(code=1008)   # policy violation
        return
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
