"""Shared-password login for the LAN — enforced by Caddy, not by the core.

The core stays unauthenticated on loopback (the TV talks to it directly).
These helpers exist so Caddy's forward_auth can ask GET /api/auth/verify
whether a LAN request carries a valid session cookie (docs/SECURITY.md).

State on disk — config/ is excluded from the OTA rsync, so both files
survive updates, and both are gitignored:
    config/auth.json    {"hash": "<argon2id>", "generation": N}   0600
    config/auth_secret  32 random bytes, HMAC key for cookies     0600

Cookie value: "<expiry>.<generation>.<hmac>" where hmac is
HMAC-SHA256(secret, "<expiry>.<generation>"). Bumping the generation
(change-password / auth-reset) invalidates every session at once.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error, InvalidHashError, VerifyMismatchError

from .paths import config_dir

AUTH_FILE = config_dir() / "auth.json"
SECRET_FILE = config_dir() / "auth_secret"
COOKIE_NAME = "gc_session"
SESSION_SECONDS = 30 * 24 * 3600  # 30 days

_ph = PasswordHasher()  # argon2id with library defaults


def _write_private(path: Path, data: bytes) -> None:
    """Atomic write, 0600 from the very first byte."""
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def _auth() -> dict | None:
    # UnicodeDecodeError is in the list because read_text() raises it, not
    # JSONDecodeError, when the file is not UTF-8 — and every LAN request goes
    # through here. An auth.json truncated mid-write, or written by something
    # else, used to 500 the whole proxied surface including /login, leaving no
    # way back in short of SSH.
    try:
        return json.loads(AUTH_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError, OSError):
        return None


def _secret() -> bytes | None:
    try:
        s = SECRET_FILE.read_bytes()
        return s if len(s) >= 16 else None
    except OSError:
        return None


def is_configured() -> bool:
    return _auth() is not None and _secret() is not None


def set_password(new: str, *, reset_secret: bool = False) -> None:
    """Set/replace the shared password. Always bumps the generation, so
    every existing session dies. reset_secret additionally rotates the
    HMAC key (gamecore-addon auth-reset)."""
    if not new:
        raise ValueError("empty password refused")
    if reset_secret or _secret() is None:
        _write_private(SECRET_FILE, secrets.token_bytes(32))
    current = _auth() or {}
    data = {"hash": _ph.hash(new), "generation": int(current.get("generation", 0)) + 1}
    _write_private(AUTH_FILE, (json.dumps(data) + "\n").encode())


def verify_password(password: str) -> bool:
    auth = _auth()
    if not auth or not password:
        return False
    try:
        return _ph.verify(auth["hash"], password)
    except (VerifyMismatchError, InvalidHashError, Argon2Error, KeyError):
        return False


def _mac(secret: bytes, payload: str) -> str:
    return hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()


def make_cookie() -> str | None:
    auth, secret = _auth(), _secret()
    if not auth or not secret:
        return None
    payload = f"{int(time.time()) + SESSION_SECONDS}.{int(auth.get('generation', 1))}"
    return f"{payload}.{_mac(secret, payload)}"


def check_cookie(value: str | None) -> bool:
    if not value:
        return False
    auth, secret = _auth(), _secret()
    if not auth or not secret:
        return False
    parts = value.split(".")
    if len(parts) != 3 or not (parts[0].isdigit() and parts[1].isdigit()):
        return False
    expiry, generation, mac = parts
    if not hmac.compare_digest(_mac(secret, f"{expiry}.{generation}"), mac):
        return False
    return int(expiry) >= time.time() and int(generation) == int(auth.get("generation", 1))


# ── In-memory anti-bruteforce ────────────────────────────────────────────────
# Per-IP consecutive failures (the IP comes from Caddy's X-Forwarded-For, see
# routers/auth.py) plus a global circuit breaker against distributed sprays.

_MAX_FREE_FAILS = 5
_BASE_BLOCK = 30.0  # seconds; doubles per extra failure, capped below
_MAX_BLOCK = 900.0

_fails: dict[str, tuple[int, float]] = {}  # ip -> (consecutive fails, blocked until)
_global = {"fails": 0, "until": 0.0}


def blocked_for(ip: str) -> int:
    """Seconds the caller still has to wait (0 = not blocked)."""
    until = _fails.get(ip, (0, 0.0))[1]
    # The global breaker slows the spray down; it does not bar the door. It used
    # to be unioned in for *every* caller, which made it a denial of service
    # anyone on the LAN could trigger: 25 failures spread over throwaway keys and
    # the owner got 429 with the correct password. Replayed once a minute, that
    # locked them out of the ROM, save and RPCS3 managers for as long as the
    # attacker cared to keep it up.
    #
    # It applies only to callers already known to have got a password wrong. A
    # client that has never failed is not part of the spray, and register_success
    # takes an address back out of _fails, so one typo does not stick.
    if ip in _fails:
        until = max(until, _global["until"])
    return max(0, int(until - time.time()) + 1) if until > time.time() else 0


def register_failure(ip: str) -> None:
    count = _fails.get(ip, (0, 0.0))[0] + 1
    until = 0.0
    if count >= _MAX_FREE_FAILS:
        until = time.time() + min(_BASE_BLOCK * 2 ** (count - _MAX_FREE_FAILS), _MAX_BLOCK)
    if len(_fails) > 1000:  # crude memory cap; blocks in flight are lost, fine
        _fails.clear()
    _fails[ip] = (count, until)
    _global["fails"] += 1
    if _global["fails"] >= 25:
        _global["until"] = time.time() + 60
        _global["fails"] = 0


def register_success(ip: str) -> None:
    _fails.pop(ip, None)
