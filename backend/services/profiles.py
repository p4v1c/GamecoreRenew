"""Who plays on this box: the profiles and the one that is active.

One JSON file, `<DATA>/config/profiles/profiles.json`:

    {"active": "<id>", "profiles": [{"id", "name", "color", "avatar",
                                     "created", "primary"}]}

The `id` is random and never derived from the name: later work keys saves and
controllers on it, and a rename must never move anything. `primary` marks the
profile that owns everything the box held before profiles existed.
"""
from __future__ import annotations

import json
import logging
import secrets
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from ..utils import atomic_write_json

from . import paths
from .errors import ServiceError

log = logging.getLogger(__name__)

NAME_MAX = 20
DEFAULT_NAME = "Player 1"
# Colour -> the name the UI shows. White initials read at >= 5:1 on every one.
PALETTE = {"#b8501b": "Ember", "#127a6d": "Teal", "#2563a8": "Blue", "#3f7d20": "Green",
           "#b3261e": "Red", "#4b5563": "Slate", "#a3245c": "Rose", "#8a6a00": "Ochre"}
_FIRST_COLOR = next(iter(PALETTE))
# No avatar art ships yet: the UI draws the initial on the colour.
AVATARS: frozenset[str] = frozenset()

# ponytail: one process-wide lock; the backend is a single process.
_lock = threading.Lock()


def _file() -> Path:
    return paths.profiles_dir() / "profiles.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _default_state() -> dict:
    first = {"id": secrets.token_hex(8), "name": DEFAULT_NAME, "color": _FIRST_COLOR,
             "avatar": None, "created": _now(), "primary": True}
    return {"active": first["id"], "profiles": [first]}


def _load() -> dict:
    """Read the file, creating the primary profile the first time.

    An unreadable file is set aside, not overwritten, so a hand edit gone
    wrong can still be recovered.
    """
    f = _file()
    try:
        state = json.loads(f.read_text(encoding="utf-8"))
        if state["profiles"]:
            ids = [p["id"] for p in state["profiles"]]
            if state.get("active") not in ids:
                state["active"] = ids[0]
            return state
    except FileNotFoundError:
        pass
    except (OSError, ValueError, LookupError, TypeError) as e:
        aside = f.with_name(f"{f.name}.broken-{int(time.time())}")
        log.error("profiles: %s unreadable (%s), kept as %s", f, e, aside.name)
        f.replace(aside)
    state = _default_state()
    _save(state)
    return state


def _save(state: dict) -> None:
    atomic_write_json(_file(), state, indent=2, ensure_ascii=False)


def _find(state: dict, profile_id: str) -> dict:
    for p in state["profiles"]:
        if p["id"] == profile_id:
            return p
    raise ServiceError(404, "No such profile.")


def _clean_name(state: dict, raw: str, own_id: str | None = None) -> str:
    name = " ".join(str(raw).split())
    if not name:
        raise ServiceError(400, "Enter a name.")
    if len(name) > NAME_MAX or not name.isprintable():
        raise ServiceError(400, f"Use up to {NAME_MAX} letters, numbers or symbols.")
    if any(p["name"].casefold() == name.casefold() and p["id"] != own_id
           for p in state["profiles"]):
        raise ServiceError(409, f"{name} is already a profile.")
    return name


def _check_look(color: str | None, avatar: str | None) -> None:
    if color is not None and color not in PALETTE:
        raise ServiceError(400, "Pick a colour from the list.")
    if avatar is not None and avatar not in AVATARS:
        raise ServiceError(400, "Unknown avatar.")


def list_profiles() -> dict:
    """`{"active": id, "profiles": [...], "palette": [{"color", "name"}]}`."""
    with _lock:
        state = _load()
    return {**state, "palette": [{"color": c, "name": n} for c, n in PALETTE.items()]}


def create(name: str, color: str | None = None, avatar: str | None = None) -> dict:
    with _lock:
        state = _load()
        clean = _clean_name(state, name)
        _check_look(color, avatar)
        if color is None:
            used = {p["color"] for p in state["profiles"]}
            color = next((c for c in PALETTE if c not in used), _FIRST_COLOR)
        profile = {"id": secrets.token_hex(8), "name": clean, "color": color,
                   "avatar": avatar, "created": _now(), "primary": False}
        state["profiles"].append(profile)
        _save(state)
        return profile


def update(profile_id: str, fields: dict) -> dict:
    """Rename, recolour or change the avatar. Keys absent from `fields` stay."""
    with _lock:
        state = _load()
        profile = _find(state, profile_id)
        if fields.get("name") is not None:
            profile["name"] = _clean_name(state, fields["name"], profile_id)
        _check_look(fields.get("color"), fields.get("avatar"))
        if fields.get("color") is not None:
            profile["color"] = fields["color"]
        if "avatar" in fields:
            profile["avatar"] = fields["avatar"]
        _save(state)
        return profile


def delete(profile_id: str) -> dict:
    """Remove the record only: its saves folder stays on disk, untouched."""
    with _lock:
        state = _load()
        profile = _find(state, profile_id)
        if len(state["profiles"]) == 1:
            raise ServiceError(409, "The last profile cannot be deleted.")
        # Handing `primary` on would give another profile the saves beside the
        # ROMs and hide its own: the owner of the box's existing saves stays.
        if profile.get("primary"):
            raise ServiceError(409, f"{profile['name']} keeps the saves made before profiles and cannot be deleted.")
        state["profiles"].remove(profile)
        if state["active"] == profile_id:
            state["active"] = state["profiles"][0]["id"]
        _save(state)
        return {"active": state["active"]}


def active() -> dict:
    with _lock:
        state = _load()
        return _find(state, state["active"])


def set_active(profile_id: str) -> dict:
    with _lock:
        state = _load()
        profile = _find(state, profile_id)
        state["active"] = profile_id
        _save(state)
        return profile
