"""Auth endpoints consumed by Caddy's forward_auth gate (docs/SECURITY.md).

Three of these are proxied to the LAN without a session — /login, /logout
and /verify, the calls a logged-OUT client needs — and everything else
behind Caddy goes through GET /verify first. /change-password is NOT among
them: it is reachable only with a session already in hand. The TV (loopback)
never calls any of this — the core enforces nothing on its own routes.
"""
import asyncio
import logging
import socket
from urllib.parse import quote

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from ..services import auth

router = APIRouter(prefix="/auth")
log = logging.getLogger(__name__)


def _client_ip(request: Request) -> str:
    # The backend only listens on loopback, so a non-loopback peer is
    # impossible; when the peer is Caddy, X-Forwarded-For carries the real
    # LAN client and is trustworthy.
    peer = request.client.host if request.client else ""
    if peer in ("127.0.0.1", "::1"):
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return peer or "unknown"


def _set_session(resp: Response) -> None:
    cookie = auth.make_cookie()
    if cookie:
        resp.set_cookie(
            auth.COOKIE_NAME, cookie,
            max_age=auth.SESSION_SECONDS, path="/",
            httponly=True, secure=True, samesite="lax",
        )


@router.post("/login")
async def login(request: Request):
    if not auth.is_configured():
        return JSONResponse({"ok": False, "error": "auth_not_configured"}, status_code=503)
    ip = _client_ip(request)
    wait = auth.blocked_for(ip)
    if wait:
        return JSONResponse(
            {"ok": False, "error": "too_many_attempts", "retry_in": wait},
            status_code=429, headers={"Retry-After": str(wait)},
        )
    try:
        body = await request.json()
    except Exception:
        body = {}
    # Off the event loop: argon2id with the library defaults allocates 64 MiB
    # and takes real CPU time by design. Called inline, a burst of failed
    # logins from the LAN froze the TV — the UI talks to this same process.
    ok = await asyncio.to_thread(auth.verify_password, str(body.get("password", "")))
    if not ok:
        auth.register_failure(ip)
        return JSONResponse({"ok": False, "error": "bad_password"}, status_code=401)
    auth.register_success(ip)
    resp = JSONResponse({"ok": True})
    _set_session(resp)
    return resp


@router.get("/verify")
def verify(request: Request):
    """200 → Caddy lets the request through (and copies X-GC-User).
    Anything else → Caddy returns THIS response to the client, so browsers
    get a redirect to /login and API callers a plain 401."""
    if auth.check_cookie(request.cookies.get(auth.COOKIE_NAME)):
        return Response(status_code=204, headers={"X-GC-User": "gamecore"})
    if "text/html" in request.headers.get("accept", ""):
        next_uri = request.headers.get("x-forwarded-uri", "/")
        if not next_uri.startswith("/") or next_uri.startswith("//"):
            next_uri = "/"
        return RedirectResponse(f"/login?next={quote(next_uri, safe='')}", status_code=302)
    return Response(status_code=401)


def _local_addresses() -> set[str]:
    """Every address this machine answers on, plus its names."""
    names = {"localhost", "127.0.0.1", "::1", socket.gethostname().lower()}
    names.add(f"{socket.gethostname().lower()}.local")
    try:
        for fam, _, _, _, sockaddr in socket.getaddrinfo(socket.gethostname(), None):
            names.add(sockaddr[0].split("%")[0].lower())
    except OSError:
        pass
    # The interface list is what actually matters — the LAN address changes with
    # the network, and a Tailscale address only shows up here.
    try:
        import subprocess
        out = subprocess.run(["ip", "-o", "addr", "show"], capture_output=True,
                             text=True, timeout=2).stdout
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[2] in ("inet", "inet6"):
                names.add(parts[3].split("/")[0].split("%")[0].lower())
    except (OSError, subprocess.SubprocessError):
        pass
    return names


@router.get("/tls-ask")
def tls_ask(domain: str = ""):
    """Caddy's on_demand_tls gate: 200 approves issuing a certificate.

    It used to point at Caddy's own admin API, which answers 200 to anything —
    so any LAN client could open a TLS handshake with an arbitrary SNI and make
    the box mint a certificate for it, as many times as it liked.

    Approved: loopback, this machine's own addresses on any interface (the LAN
    address changes with the network, and a Tailscale address only appears
    here), its hostname, and a name that resolves to one of those — which is
    what covers a MagicDNS name.
    """
    name = (domain or "").strip().lower().rstrip(".")
    if not name:
        return Response(status_code=403)

    local = _local_addresses()
    if name in local:
        return Response(status_code=200)

    # A name we do not recognise: accept it only if it points back at us.
    try:
        resolved = {ai[4][0].split("%")[0].lower()
                    for ai in socket.getaddrinfo(name, None)}
    except (OSError, UnicodeError):
        resolved = set()
    if resolved & local:
        return Response(status_code=200)

    log.info("on-demand TLS refused for %r (not an address of this machine)", name)
    return Response(status_code=403)


@router.post("/logout")
def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth.COOKIE_NAME, path="/")
    return resp


@router.post("/change-password")
async def change_password(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    current, new = str(body.get("current", "")), str(body.get("new", ""))
    if not new:
        return JSONResponse({"ok": False, "error": "empty_password"}, status_code=400)
    if not auth.is_configured():
        # This route used to be public (Caddy exempted all of /api/auth/*), so
        # on a box that never got a password — a GUI install before the wizard
        # asked for one — `if auth.is_configured()` used to skip the whole
        # verification block and hand the first caller on the LAN a valid
        # session. Provisioning does not go through here: the installer and
        # `gamecore-addon auth-reset` call auth.set_password() directly.
        return JSONResponse(
            {"ok": False, "error": "auth_not_configured"}, status_code=503
        )
    ip = _client_ip(request)
    wait = auth.blocked_for(ip)
    if wait:
        return JSONResponse(
            {"ok": False, "error": "too_many_attempts", "retry_in": wait},
            status_code=429, headers={"Retry-After": str(wait)},
        )
    # Same reason as /login: argon2 is deliberately expensive, so it does not
    # get to run on the event loop.
    if not await asyncio.to_thread(auth.verify_password, current):
        auth.register_failure(ip)
        return JSONResponse({"ok": False, "error": "bad_password"}, status_code=401)
    auth.register_success(ip)
    await asyncio.to_thread(auth.set_password, new)  # bumps generation → every session dies
    resp = JSONResponse({"ok": True})
    _set_session(resp)  # the caller stays logged in with a fresh cookie
    return resp
