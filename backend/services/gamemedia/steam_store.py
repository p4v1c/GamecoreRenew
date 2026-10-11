"""A PC game's minimum spec, read from the public Steam store API.

GameCore's own module, not part of the vendored scraper: neither ScreenScraper
nor LaunchBox carries system requirements, and the Shelf PC case prints them on
the box reverse (`meta.requirements`: os, cpu, ram, gpu, disk).

Two anonymous calls: `storesearch` turns the title the scrape settled on into
an app id, `appdetails` returns `pc_requirements.minimum` as HTML. A hit is
accepted only on the same title test as the ScreenScraper name match plus the
episode-number guard of the LaunchBox search: "FIFA 22" must never print the
spec of FIFA 23, and "Grand Theft Auto V" scores 0.97 against "IV".

The answer is stored in the game's manifest under `steam`, a miss included, so
the store is asked once per scrape. A network failure stores nothing.
"""
from __future__ import annotations

import html
import json
import logging
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from .common import UA
from .helpers import entry_dir, write_json
from .paths import MANIFEST
from .search import numbers_of
from .ss_client import NAME_ACCEPT, _title_score

log = logging.getLogger(__name__)

SEARCH_URL = "https://store.steampowered.com/api/storesearch/"
DETAILS_URL = "https://store.steampowered.com/api/appdetails"
TIMEOUT = 10
# Longer than this does not fit one line of the printed panel; it ellipsises.
MAX_VALUE = 48

# Steam's row labels vary by publisher ("Operating System", "Memory", "RAM",
# "Hard Drive", "Storage", "Video Card"). Matched by prefix, in this order.
LABELS = (
    ("os", ("os", "operating")),
    ("cpu", ("processor", "cpu")),
    ("ram", ("memory", "ram")),
    ("gpu", ("graphics", "video", "gpu")),
    ("disk", ("storage", "hard", "disk", "hdd")),
)
_SIZE_RE = re.compile(r"\d+(?:[.,]\d+)?\s*[KMGT]B", re.I)
_MARKS_RE = re.compile("[\u2122\u00ae\u00a9]")  # trade marks: ™ ® ©


class SteamUnreachable(Exception):
    """The store could not be asked. Says nothing about the game."""


def _get_json(url: str, params: dict) -> object:
    req = urllib.request.Request(f"{url}?{urllib.parse.urlencode(params)}",
                                 headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (OSError, ValueError) as e:      # URLError, HTTPError, timeout, bad JSON
        raise SteamUnreachable(f"{type(e).__name__}: {e}") from e


def same_game(title: str, name: str) -> bool:
    """True when a store entry's `name` is the game called `title`."""
    name = _MARKS_RE.sub("", name)
    score = _title_score({"title": title}, {"noms": [{"text": name}]})
    return score >= NAME_ACCEPT and numbers_of(title) == numbers_of(name)


def find_appid(title: str) -> int | None:
    """The app id of `title` on the store, or None when no entry is that game."""
    data = _get_json(SEARCH_URL, {"term": title, "l": "english", "cc": "US"})
    for item in (data or {}).get("items") or []:
        if item.get("id") and same_game(title, str(item.get("name") or "")):
            return int(item["id"])
    return None


def _shorten(key: str, value: str) -> str:
    """One TV-readable line: first alternative, no clock speed, no fine print."""
    value = re.sub(r"\([^)]*\)", " ", _MARKS_RE.sub("", value))
    if key in ("ram", "disk") and (m := _SIZE_RE.search(value)):
        value = m.group(0)
    elif key != "os":
        value = re.split(r"\s+or\s+|\s*/\s*|,\s*|\s+\|\s+", value, maxsplit=1)[0]
        value = value.split("@")[0]
    else:
        value = re.split(r",\s*|\s+or\s+", value, maxsplit=1)[0]
    value = " ".join(value.split()).strip(" -,;")
    return value if len(value) <= MAX_VALUE else value[:MAX_VALUE - 1].rstrip() + "…"


def parse_requirements(raw: str) -> dict[str, str]:
    """`pc_requirements.minimum` (HTML list) as {os, cpu, ram, gpu, disk}."""
    out: dict[str, str] = {}
    for item in re.split(r"<li[^>]*>", raw or "", flags=re.I)[1:]:
        text = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", item)).split())
        label, sep, value = text.partition(":")
        if not sep or not value.strip():
            continue
        label = re.sub(r"[^a-z]", "", label.lower())
        for key, prefixes in LABELS:
            if key not in out and label.startswith(prefixes):
                if short := _shorten(key, value):
                    out[key] = short
                break
    return out


def requirements_for(appid: int) -> dict[str, str]:
    """The minimum spec of a store GAME (a soundtrack or a DLC gives {})."""
    data = _get_json(DETAILS_URL, {"appids": appid, "l": "english", "filters": "basic"})
    entry = (data or {}).get(str(appid)) or {}
    details = entry.get("data") if entry.get("success") else None
    if not isinstance(details, dict) or details.get("type") != "game":
        return {}
    pc = details.get("pc_requirements")
    # The store sends `[]` rather than `{}` when a game lists nothing.
    return parse_requirements(pc.get("minimum", "")) if isinstance(pc, dict) else {}


def opted_in_systems() -> frozenset[str]:
    """Pack ids whose `scraper.steamStore` is true. Never fatal."""
    try:
        from ..catalog import load_catalog
        return frozenset(p.id for p in load_catalog().values()
                         if (p.data.get("scraper") or {}).get("steamStore"))
    except Exception:  # noqa: BLE001 — no catalogue means no lookup, not a crash
        log.warning("steam store: catalogue unreadable, lookup off", exc_info=True)
        return frozenset()


def add_requirements(system: str, manifest: dict) -> dict:
    """Fill `meta.requirements` from the store once, and save it. Never raises."""
    if not manifest.get("found") or "steam" in manifest:
        return manifest
    meta = manifest.setdefault("meta", {})
    title = meta.get("title") or (manifest.get("parsed") or {}).get("title") or ""
    try:
        appid = find_appid(title) if title else None
        reqs = requirements_for(appid) if appid else {}
    except SteamUnreachable as e:
        log.info("steam store: %s/%s not asked (%s)", system, title, e)
        return manifest
    if reqs:
        meta["requirements"] = reqs
    manifest["steam"] = {"appid": appid,
                         "checked_at": datetime.now(timezone.utc).isoformat()}
    write_json(entry_dir(system, manifest["filename"]) / MANIFEST,
               {**manifest, "cached": False})
    return manifest
