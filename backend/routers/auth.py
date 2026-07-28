"""Auth endpoints consumed by Caddy's forward_auth gate (docs/SECURITY.md).

Only /api/auth/* is proxied to the LAN without a session; everything else
behind Caddy goes through GET /verify first. The TV (loopback) never calls
any of this — the core enforces nothing on its own routes.
"""
from urllib.parse import quote

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from ..services import auth

router = APIRouter(prefix="/auth")


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
    if not auth.verify_password(str(body.get("password", ""))):
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
        # This route is public (Caddy exempts /api/auth/* from forward_auth), so
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
    if not auth.verify_password(current):
        auth.register_failure(ip)
        return JSONResponse({"ok": False, "error": "bad_password"}, status_code=401)
    auth.register_success(ip)
    auth.set_password(new)  # bumps generation → every session dies
    resp = JSONResponse({"ok": True})
    _set_session(resp)  # the caller stays logged in with a fresh cookie
    return resp
