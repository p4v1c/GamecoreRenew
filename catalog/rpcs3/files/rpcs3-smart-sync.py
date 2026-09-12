#!/usr/bin/env python3
"""RPCS3 database synchronizer for the GameCore RPCS3 Smart Pack.

It mirrors RPCS3's own network formats and paths, but never decides how to
emulate a title. RPCS3 remains the source of truth.

Runtime selection mirrors GameCore's existing RPCS3 launch contract:
`<GAMECORE>/lib/rpcs3` wins when present; otherwise the Flatpak runs. The smart
databases follow that same runtime without changing the product's launcher.

A failed sync never deletes or truncates a previously valid cache.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

CONFIG_DB_URL = "https://api.rpcs3.net/config/?api=v1"
PATCH_DB_URL_TEMPLATE = "https://rpcs3.net/compatibility?patch&api=v1&v={version}"
DEFAULT_APP_ID = "net.rpcs3.RPCS3"
_APP_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")

DEFAULT_POLICY: dict[str, Any] = {
    "version": 1,
    "profile": "recommended-original",
    "syncConfigDatabase": True,
    "syncPatchDatabase": True,
    "syncHours": 6,
    "networkTimeoutSeconds": 10,
    "patchEngineVersion": "1.2",
    "autoPatch": {"mode": "exact-whitelist", "approved": []},
}


def _log(message: str) -> None:
    print(f"[gamecore-rpcs3-smart] {message}", flush=True)


def load_policy(path: Path | None) -> dict[str, Any]:
    policy = json.loads(json.dumps(DEFAULT_POLICY))
    if path is None:
        return policy
    try:
        incoming = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _log(f"policy unreadable ({exc}); safe defaults used")
        return policy
    if not isinstance(incoming, dict) or incoming.get("version") != 1:
        _log("policy has unsupported shape/version; safe defaults used")
        return policy

    for key in (
        "profile", "syncConfigDatabase", "syncPatchDatabase", "syncHours",
        "networkTimeoutSeconds", "patchEngineVersion", "autoPatch"
    ):
        if key in incoming:
            policy[key] = incoming[key]
    try:
        policy["syncHours"] = max(1, min(24 * 30, int(policy["syncHours"])))
    except (TypeError, ValueError):
        policy["syncHours"] = 6
    try:
        policy["networkTimeoutSeconds"] = max(
            2, min(30, int(policy["networkTimeoutSeconds"]))
        )
    except (TypeError, ValueError):
        policy["networkTimeoutSeconds"] = 10
    ap = policy.get("autoPatch")
    if not isinstance(ap, dict):
        policy["autoPatch"] = {"mode": "exact-whitelist", "approved": []}
    elif ap.get("mode") != "exact-whitelist" or not isinstance(ap.get("approved", []), list):
        policy["autoPatch"] = {"mode": "exact-whitelist", "approved": []}
    return policy


def validate_app_id(app_id: str) -> str:
    if not _APP_ID_RE.fullmatch(app_id):
        raise ValueError(f"invalid Flatpak app id: {app_id!r}")
    return app_id


def runtime_root(home: Path, gamecore_path: Path, app_id: str) -> tuple[str, Path]:
    """Config tree for the runtime GameCore's existing launcher will choose."""
    native = gamecore_path / "lib" / "rpcs3"
    if native.is_file():
        return "native", home / ".config" / "rpcs3"
    validate_app_id(app_id)
    return "flatpak", home / ".var" / "app" / app_id / "config" / "rpcs3"


def _is_fresh(path: Path, hours: int, now: float | None = None) -> bool:
    try:
        stat = path.stat()
    except OSError:
        return False
    if stat.st_size <= 0:
        return False
    now = time.time() if now is None else now
    age = max(0.0, now - stat.st_mtime)
    return age < hours * 3600


class HTTPSOnlyRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Keep RPCS3 database redirects inside TLS.

    The official endpoints are HTTPS. urllib's default redirect handler also
    accepts a downgrade to HTTP; database content that RPCS3 later parses must
    not silently cross that boundary.
    """
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme.lower() != "https":
            raise urllib.error.HTTPError(
                newurl, code, "refusing non-HTTPS redirect", headers, fp
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _fetch(url: str, timeout: int) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "GameCore-RPCS3-SmartPack/3",
            "Accept": "application/json,text/plain;q=0.9,*/*;q=0.1",
        },
        method="GET",
    )
    opener = urllib.request.build_opener(HTTPSOnlyRedirectHandler())
    with opener.open(request, timeout=timeout) as response:
        status = getattr(response, "status", 200)
        if status != 200:
            raise OSError(f"HTTP status {status}")
        data = response.read(64 * 1024 * 1024 + 1)
    if len(data) > 64 * 1024 * 1024:
        raise ValueError("download exceeds 64 MiB safety limit")
    return data


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def validate_config_database(payload: bytes) -> dict[str, int]:
    try:
        doc = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"RPCS3 config DB is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(doc, dict):
        raise ValueError("RPCS3 config DB root is not an object")
    code = doc.get("return_code")
    if not isinstance(code, int) or code < 0:
        raise ValueError(f"RPCS3 config DB return_code is invalid: {code!r}")
    games = doc.get("games")
    if not isinstance(games, dict) or not games:
        raise ValueError("RPCS3 config DB has no games object")
    usable = sum(
        1 for serial, entry in games.items()
        if isinstance(serial, str)
        and isinstance(entry, dict)
        and isinstance(entry.get("config"), str)
    )
    if not usable:
        raise ValueError("RPCS3 config DB contains no usable config strings")
    return {"games": len(games), "usable": usable}


def decode_patch_database_response(payload: bytes, engine_version: str) -> bytes | None:
    """Decode the envelope and verify its same-response SHA-256 integrity check.

    The checksum detects corruption/inconsistency; TLS to the official endpoint
    is the trust boundary. The digest is not a signature or independent trust
    anchor.
    """
    try:
        doc = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"RPCS3 patch response is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(doc, dict):
        raise ValueError("RPCS3 patch response root is not an object")
    code = doc.get("return_code")
    if code == 1:
        return None
    if code != 0:
        raise ValueError(f"RPCS3 patch endpoint return_code is invalid: {code!r}")
    if doc.get("version") != engine_version:
        raise ValueError(
            f"RPCS3 patch version {doc.get('version')!r} does not match {engine_version!r}"
        )
    patch = doc.get("patch")
    checksum = doc.get("sha256")
    if not isinstance(patch, str) or not patch:
        raise ValueError("RPCS3 patch response has no patch content")
    if not isinstance(checksum, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", checksum):
        raise ValueError("RPCS3 patch response has no valid sha256")
    content = patch.encode("utf-8")
    if hashlib.sha256(content).hexdigest().lower() != checksum.lower():
        raise ValueError("RPCS3 patch response checksum mismatch")
    if not re.search(
        rf"(?m)^\s*Version:\s*[\"']?{re.escape(engine_version)}[\"']?\s*$", patch
    ):
        raise ValueError("RPCS3 patch YAML is missing the expected Version header")
    return content


def sync_config_database(root: Path, policy: dict[str, Any], *, force: bool = False) -> str:
    target = root / "GuiConfigs" / "config_database.dat"
    if not policy.get("syncConfigDatabase", True):
        return "disabled"
    if not force and _is_fresh(target, int(policy["syncHours"])):
        return "fresh"
    payload = _fetch(CONFIG_DB_URL, int(policy["networkTimeoutSeconds"]))
    info = validate_config_database(payload)
    _atomic_write(target, payload)
    return f"updated:{info['usable']}"


def sync_patch_database(root: Path, policy: dict[str, Any], *, force: bool = False) -> str:
    target = root / "patches" / "patch.yml"
    if not policy.get("syncPatchDatabase", True):
        return "disabled"
    if not force and _is_fresh(target, int(policy["syncHours"])):
        return "fresh"
    version = str(policy["patchEngineVersion"])
    payload = _fetch(
        PATCH_DB_URL_TEMPLATE.format(version=version),
        int(policy["networkTimeoutSeconds"]),
    )
    content = decode_patch_database_response(payload, version)
    if content is None:
        return "current"
    _atomic_write(target, content)
    return "updated"


def safe_sync(root: Path, policy: dict[str, Any], *, offline: bool, force: bool) -> dict[str, str]:
    result = {"configDatabase": "offline", "patchDatabase": "offline"}
    if offline:
        return result
    for name, fn in (
        ("configDatabase", sync_config_database),
        ("patchDatabase", sync_patch_database),
    ):
        try:
            result[name] = fn(root, policy, force=force)
        except Exception as exc:
            result[name] = f"error:{type(exc).__name__}"
            _log(f"{name} sync failed: {exc}; existing data kept")
    return result


def auto_patch_status(policy: dict[str, Any]) -> str:
    approved = (policy.get("autoPatch") or {}).get("approved") or []
    if not approved:
        return "none-approved"
    # Deliberately fail closed until a reviewed patch-config writer is shipped.
    # An approval entry alone must never be enough to mutate patch_config.yml.
    return "approvals-present-but-writer-disabled"


def _write_state(home: Path, *, runtime: str, root: Path,
                 policy: dict[str, Any], sync: dict[str, str]) -> None:
    state = {
        "version": 1,
        "profile": policy.get("profile", "recommended-original"),
        "architecture": platform.machine(),
        "runtime": runtime,
        "configRoot": str(root),
        "configDatabase": sync["configDatabase"],
        "patchDatabase": sync["patchDatabase"],
        "autoPatch": auto_patch_status(policy),
        "timestamp": int(time.time()),
    }
    target = home / ".local/share/gamecore/rpcs3-smart/state.json"
    try:
        _atomic_write(
            target,
            (json.dumps(state, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )
    except OSError as exc:
        _log(f"state write failed: {exc}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="GameCore RPCS3 Smart DB synchronizer")
    p.add_argument("--gamecore-path", type=Path, required=True)
    p.add_argument("--app-id", default=DEFAULT_APP_ID)
    p.add_argument("--policy", type=Path)
    p.add_argument("--offline", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--home", type=Path, help=argparse.SUPPRESS)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        validate_app_id(args.app_id)
    except ValueError as exc:
        _log(str(exc))
        return 2

    home = (args.home or Path.home()).expanduser()
    gamecore_path = args.gamecore_path.expanduser()
    runtime, root = runtime_root(home, gamecore_path, args.app_id)
    policy = load_policy(args.policy)
    offline = args.offline or os.environ.get("GAMECORE_RPCS3_OFFLINE") == "1"
    sync = safe_sync(root, policy, offline=offline, force=args.force)
    _write_state(home, runtime=runtime, root=root, policy=policy, sync=sync)
    _log(
        f"runtime={runtime} profile={policy.get('profile')} "
        f"configDB={sync['configDatabase']} patchDB={sync['patchDatabase']} "
        f"autoPatch={auto_patch_status(policy)}"
    )
    # Synchronization errors are intentionally non-fatal to GameCore.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
