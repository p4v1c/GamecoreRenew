"""Theme discovery and selection.

A theme is a directory under config/themes/ holding a manifest, an ES module and
its assets. config/ is already excluded from the OTA rsync, so themes survive an
update without touching update/linux.sh.

Nothing here executes theme code — the browser imports the module. This module
only reads manifests, validates them and remembers which theme is active.
See docs/themes/README.md for the manifest contract.
"""
import json
import logging
import re
from pathlib import Path

from ..config import GAMECORE_ROOT

log = logging.getLogger(__name__)

THEMES_DIR = GAMECORE_ROOT / "config" / "themes"
STATE_FILE = GAMECORE_ROOT / "config" / "theme.json"

# Bumped only when a surface or an SDK key is removed. Adding one does not.
SDK_VERSION = 1

# The two surfaces a theme owns: the boot animation and the frontend body.
# Both are mandatory — a theme dresses the whole UI or it does not load. Half a
# theme (a beach dashboard behind the stock splash) is what made the first
# version feel broken, so incompleteness is an error, not a fallback.
#
# It used to be nine interleaved surfaces, which is what made themes brittle:
# the theme's tree fought the host's over stacking, the modal stack and the
# containers default pages expect.
SURFACES = {"splash", "shell"}

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def _safe_id(theme_id: str) -> str | None:
    """A theme id is a plain directory name — never a path."""
    return theme_id if _ID_RE.match(theme_id or "") else None


def _read_manifest(d: Path) -> dict | None:
    """Parsed, validated manifest for one directory, or None with a logged reason."""
    f = d / "theme.json"
    if not f.is_file():
        return None
    try:
        m = json.loads(f.read_text())
    except Exception as e:
        log.warning("theme %s: unreadable manifest (%s)", d.name, e)
        return None

    missing = [k for k in ("id", "name", "version", "api", "provides") if k not in m]
    if missing:
        log.warning("theme %s: manifest missing %s", d.name, ", ".join(missing))
        return None
    if m["id"] != d.name:
        log.warning("theme %s: manifest id is %r — must equal the directory name", d.name, m["id"])
        return None
    if not isinstance(m.get("provides"), list):
        log.warning("theme %s: 'provides' must be a list", d.name)
        return None

    unknown = [s for s in m["provides"] if s not in SURFACES]
    absent = sorted(SURFACES - set(m["provides"]))
    entry = m.get("entry", "index.js")
    if not (d / entry).is_file():
        log.warning("theme %s: entry %r not found", d.name, entry)
        return None

    try:
        api_version = int(m["api"])
    except (TypeError, ValueError):
        log.warning("theme %s: 'api' must be an integer", d.name)
        return None

    preview = m.get("preview", "preview.png")
    styles = m.get("styles", "theme.css")
    return {
        "id": m["id"],
        "name": m["name"],
        "version": str(m["version"]),
        "api": api_version,
        "author": m.get("author", ""),
        "description": m.get("description", ""),
        "entry": entry,
        "preview": preview if (d / preview).is_file() else None,
        "styles": styles if (d / styles).is_file() else None,
        "provides": [s for s in m["provides"] if s in SURFACES],
        "schedule": m.get("schedule"),
        # The UI needs a reason, not just a boolean.
        "compatible": api_version <= SDK_VERSION and not absent,
        "warnings": (
            ([f"unknown surface(s) ignored: {', '.join(unknown)}"] if unknown else [])
            + ([f"incomplete: does not provide {', '.join(absent)}"] if absent else [])
        ),
    }


def list_themes() -> list[dict]:
    """Every valid theme on the box, alphabetical. Invalid ones are skipped, not fatal."""
    if not THEMES_DIR.is_dir():
        return []
    out = []
    for d in sorted(THEMES_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        m = _read_manifest(d)
        if m:
            out.append(m)
    return out


def get_active() -> str | None:
    """The selected theme id, or None for the built-in default."""
    try:
        return json.loads(STATE_FILE.read_text()).get("active") or None
    except Exception:
        return None


def set_active(theme_id: str | None) -> str | None:
    """Persist the selection. None (or an unknown id) means the default theme."""
    if theme_id is not None:
        if not _safe_id(theme_id):
            raise ValueError("invalid theme id")
        match = next((t for t in list_themes() if t["id"] == theme_id), None)
        if match is None:
            raise LookupError("no such theme")
        # Refused here rather than at boot: an incomplete theme would otherwise
        # be selectable, fail to load, and leave the player on the default UI
        # wondering why their choice did nothing.
        if not match["compatible"]:
            raise ValueError("; ".join(match["warnings"]) or "theme is not compatible")
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps({"active": theme_id}, indent=2))
    return theme_id
