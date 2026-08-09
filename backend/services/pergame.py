"""One game's settings: kept in `<DATA>`, materialised into the emulator's tree.

The shape of this module is one decision, and everything else follows from it.

**The emulator's file is DERIVED; `<DATA>` holds the original.** A per-game
setting placed by the player is written to
`<DATA>/config/per-game/<system>/<game id>.json`, and the file the emulator
actually reads is produced from it at launch. The alternative — write straight
into `~/.var/app/…` and call that the record — loses everything the day
somebody runs `flatpak uninstall --delete-data`, which is a thing people do
when an emulator is misbehaving, which is exactly when they have per-game
settings in the first place.

**Nothing here knows what a setting MEANS.** No table maps "internal
resolution" onto thirteen vocabularies. That translation layer is what makes
Batocera's configgen impossible to port and impossible to keep current: every
emulator release moves an option and the map has to be chased. GameCore writes
the section and key it is given, verbatim, and the button next to it opens the
emulator's own settings window. A shipped profile names RPCS3's spelling of
RPCS3's option because it IS an RPCS3 profile.

**`own-keys`, and what it costs to honour.** Merging means reading the file the
emulator wrote, changing the keys GameCore was asked to change, and leaving
every other byte exactly as it was — the same divergence from Batocera the
controller generators make. Here it protects settings the player made in the
emulator's own window, which is the one place they are most likely to have
made them.

It also makes removal possible, and removal is the part that is easy to get
wrong. "Undo" cannot mean "delete the file": the file may hold the player's own
settings alongside ours. So every write records what was displaced — the
previous value, or a marker saying the key was absent — and removal puts that
back, key by key, deleting the file only if GameCore is the one that created
it. Without that record, "the player can remove it" is a button that lies.

Nothing here is on the critical path of a launch in the sense that matters: a
failure is a log line and a game that starts anyway. A per-game config is an
improvement on a working system, never a precondition of it.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
from pathlib import Path

from . import gameid
from .catalog import load_catalog
from .configgen.helpers.ini import section as ini_section
from .configgen.helpers.ini import set_key as ini_set_key
from .configgen.helpers.ini import set_section as ini_set_section
from .paths import pergame_dir

log = logging.getLogger(__name__)

# `.bak-pergame`, and only ever the first time. A second write must not
# overwrite the backup with a file this module has already touched — that turns
# the safety net into a copy of the damage.
_BAK_SUFFIX = ".bak-pergame"

# A game id becomes a path component. Every reader in `gameid` already produces
# something alphanumeric, so this rejects nothing today — which is the point of
# having it: the id is derived from a file the player downloaded, and the reader
# that eventually forgets to constrain its output must not be the one that gets
# to name a path. A PARAM.SFO is a container, and a container holds whatever it
# was built to hold.
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

# What "there was no key here before" looks like in the restore record. A JSON
# null, because the record is JSON and because a legitimate value of None is
# not expressible in any of the file formats this writes.
ABSENT = None


# ── the pack's answer ────────────────────────────────────────────────────────

def block(system_id: str) -> dict | None:
    """The `perGame` block for a system, or None if it has none.

    Read from the catalogue each time rather than cached at import: this is
    the block a signed OTA correction changes, and the whole argument for
    putting per-game support in the pack was that shadPS4 growing per-title
    configs should reach a box without a release. A table built at import would
    hold yesterday's answer until someone rebooted the backend.
    """
    try:
        pack = load_catalog().get(system_id.lower())
    except Exception:
        log.warning("pergame: catalogue unreadable — no system gets per-game "
                    "settings this pass", exc_info=True)
        return None
    return (pack.data.get("perGame") or None) if pack else None


def supported(system_id: str) -> bool:
    return bool((block(system_id) or {}).get("supported"))


def unsupported_reason(system_id: str) -> str | None:
    """The pack's own sentence, for the screen that has to explain the absence.

    An empty options panel and an emulator that genuinely cannot do this look
    identical from a sofa, and the second is not a fault anybody should go
    hunting for.
    """
    b = block(system_id) or {}
    return None if b.get("supported") else b.get("why")


def identify(system_id: str, rom: Path | str) -> str | None:
    """This game's id under the strategy its pack declares.

    None when the system declares no per-game support, when the dump carries no
    identity, or when the id is not something that may name a file.
    """
    b = block(system_id)
    if not b or not b.get("supported"):
        return None
    value = gameid.identify(b["key"], Path(rom))
    if value and not _SAFE_ID_RE.fullmatch(value):
        log.warning("pergame: %s produced game id %r, which is not a name a "
                    "file may have — refusing to use it", b["key"], value)
        return None
    return value


def target(system_id: str, game_id: str, home: Path) -> Path | None:
    """Where the emulator reads this game's settings from, on THIS box.

    `@FLATPAK_CONFIG@` and `@FLATPAK_DATA@` expand from the `install.appIds`
    entry the box actually has installed — the same expander `bios.dir` and
    `config.dest` use — so a per-game directory under an app id nobody has is
    unexpressible rather than merely wrong.
    """
    b = block(system_id)
    if not b or not b.get("supported"):
        return None
    try:
        pack = load_catalog()[system_id.lower()]
    except (KeyError, Exception):
        return None
    return pack.expand(b["path"].replace("@GAMEID@", game_id), home)


# ── the record in <DATA> ─────────────────────────────────────────────────────

def record_path(system_id: str, game_id: str) -> Path:
    return pergame_dir() / system_id.lower() / f"{game_id}.json"


def record(system_id: str, game_id: str) -> dict:
    """What GameCore owns for this game. `{}` when it owns nothing.

    Never raises on a damaged file. A record that cannot be parsed is a game
    with no GameCore settings, which is a state the whole system already
    handles; refusing to launch over it would be this module deciding that its
    own bookkeeping matters more than the game.
    """
    try:
        loaded = json.loads(record_path(system_id, game_id).read_text())
        return loaded if isinstance(loaded, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_record(system_id: str, game_id: str, data: dict) -> None:
    p = record_path(system_id, game_id)
    if not data.get("settings") and not data.get("dismissed"):
        # Nothing owned and nothing refused: remove the file rather than leave
        # an empty one. An empty record and an absent one mean the same thing,
        # and only one of them can also mean "a write failed halfway".
        p.unlink(missing_ok=True)
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
    tmp.replace(p)


# ── the two file formats ─────────────────────────────────────────────────────
#
# Surgical, both of them: read what is there, change the named key, leave every
# other byte alone. Neither reformats, neither reorders, and neither is a
# general parser for its format — they only have to handle the shape the
# emulator itself writes, which is what makes them short enough to be right.

def _render(value) -> str:
    """A Python value as the emulators spell it.

    `True` is `true` in both an RPCS3 YAML and a Dolphin INI, and `str(True)`
    is `True` — a value neither of them recognises, written into a real config
    file, producing a setting that reads as present and does nothing.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _yaml_get(text: str, sect: str, key: str) -> str | None:
    m = re.search(rf"^{re.escape(sect)}:\n((?:[ \t]+.*\n|\n)*)", text, re.M)
    if not m:
        return None
    line = re.search(rf"^[ \t]+{re.escape(key)}:[ \t]*(.*)$", m.group(1), re.M)
    return line.group(1).strip() if line else None


def _yaml_set(text: str, sect: str, key: str, value: str | None) -> str:
    """Set or remove `key` inside a top-level `sect:` mapping.

    RPCS3's own file is two levels deep and 288 lines long, written by RPCS3.
    Re-emitting it from a parsed structure would reformat every one of those
    lines and lose the ordering the emulator wrote — which is not a
    correctness problem right up until the day it is, and it is impossible to
    review a diff of.
    """
    m = re.search(rf"^{re.escape(sect)}:\n((?:[ \t]+.*\n|\n)*)", text, re.M)
    if not m:
        if value is None:
            return text
        prefix = text if not text or text.endswith("\n") else text + "\n"
        return f"{prefix}{sect}:\n  {key}: {value}\n"
    body = m.group(1)
    line_re = rf"^[ \t]+{re.escape(key)}:[ \t]*.*\n"
    if re.search(line_re, body, re.M):
        new_body = (re.sub(line_re, "", body, count=1, flags=re.M) if value is None
                    else re.sub(line_re, lambda _: f"  {key}: {value}\n",
                                body, count=1, flags=re.M))
    elif value is None:
        return text
    else:
        new_body = body + f"  {key}: {value}\n"
    return text[:m.start(1)] + new_body + text[m.end(1):]


def _ini_get(text: str, sect: str, key: str) -> str | None:
    body = ini_section(text, sect)
    if body is None:
        return None
    m = re.search(rf"^{re.escape(key)}\s*=\s*(.*)$", body, re.M)
    return m.group(1).strip() if m else None


def _ini_set(text: str, sect: str, key: str, value: str | None) -> str:
    if value is None:
        body = ini_section(text, sect)
        if body is None:
            return text
        stripped = re.sub(rf"^{re.escape(key)}\s*=\s*.*\n?", "", body, count=1, flags=re.M)
        return ini_set_section(text, sect, stripped)
    if ini_section(text, sect) is None:
        # `set_key` refuses a section that is not there — it was written for
        # generators editing a seed, where every section already exists. A
        # per-game file is usually empty or absent, so the section has to be
        # created or the very first setting would silently write nothing.
        text = ini_set_section(text, sect, "")
    return ini_set_key(text, sect, key, value)[0]


_FORMATS = {
    "ini":  (_ini_get, _ini_set),
    "yaml": (_yaml_get, _yaml_set),
}


# ── writing, and un-writing ──────────────────────────────────────────────────

def _backup(p: Path) -> None:
    b = p.with_name(p.name + _BAK_SUFFIX)
    if p.is_file() and not b.exists():
        shutil.copy2(p, b)


def _atomic_write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".gamecore-tmp")
    try:
        tmp.write_text(text)
        tmp.replace(p)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def set_settings(system_id: str, game_id: str, settings: dict,
                 source: str = "player") -> None:
    """Record what GameCore should place on this game. Does not write the
    emulator's file — `materialise()` does, on the next launch.

    Split in two because the emulator reads its config once, at startup: a
    setting changed while a game is running takes effect next time whatever we
    do, and pretending otherwise on screen is worse than saying so.
    """
    data = record(system_id, game_id)
    merged = {s: dict(k) for s, k in (data.get("settings") or {}).items()}
    for sect, keys in settings.items():
        merged.setdefault(sect, {}).update(keys)
        for key, value in list(keys.items()):
            if value is None:
                merged[sect].pop(key, None)
        if not merged[sect]:
            merged.pop(sect)
    data["settings"] = merged
    data["source"] = source
    _write_record(system_id, game_id, data)


def materialise(system_id: str, rom: Path | str, home: Path) -> str | None:
    """Write this game's settings into the file the emulator reads.

    The launch-path entry point: it is handed a ROM because that is what a
    launch has. Identifying the game is the part that opens a dump, so it is
    kept out of `materialise_id` — everything the UI and the tests do already
    knows the id and must not pay for a second read of the container.
    """
    game_id = identify(system_id, rom)
    if not game_id:
        return None
    adopt_profile(system_id, game_id)
    return materialise_id(system_id, game_id, home)


def materialise_id(system_id: str, game_id: str, home: Path) -> str | None:
    """As `materialise`, for a game already identified.

    Returns a line describing what happened, or None when there was nothing to
    do. Never raises: this runs in front of a game starting.
    """
    wanted = record(system_id, game_id).get("settings") or {}
    if not wanted:
        return None
    return _apply(system_id, game_id, wanted, home)


def _apply(system_id: str, game_id: str, wanted: dict, home: Path) -> str | None:
    b = block(system_id) or {}
    get, put = _FORMATS.get(b.get("format"), (None, None))
    if put is None:
        log.warning("pergame: %s declares format %r, which this backend cannot "
                    "write — the settings stay in <DATA> and nothing is lost",
                    system_id, b.get("format"))
        return None
    path = target(system_id, game_id, home)
    if path is None:
        return None

    existed = path.is_file()
    try:
        text = path.read_text() if existed else ""
    except OSError as e:
        log.warning("pergame: cannot read %s — %s", path, e)
        return None

    data = record(system_id, game_id)
    restore = {s: dict(k) for s, k in (data.get("restore") or {}).items()}
    changed = 0
    for sect, keys in wanted.items():
        for key, value in keys.items():
            rendered = _render(value)
            current = get(text, sect, key)
            if current == rendered:
                continue
            # Recorded ONCE, on the first write. A second pass must not record
            # our own value as "what was there before" — that is how an undo
            # restores the thing it was undoing.
            if key not in restore.get(sect, {}):
                restore.setdefault(sect, {})[key] = current if current is not None else ABSENT
            text = put(text, sect, key, rendered)
            changed += 1
    if not changed:
        return None

    if existed:
        _backup(path)
    try:
        _atomic_write(path, text)
    except OSError as e:
        log.warning("pergame: cannot write %s — %s", path, e)
        return None

    data["restore"] = restore
    data.setdefault("createdFile", not existed)
    _write_record(system_id, game_id, data)
    return f"{system_id}: {changed} setting(s) written for {game_id}"


def release(system_id: str, game_id: str, home: Path) -> str | None:
    """Put the emulator's file back the way GameCore found it.

    Key by key, from the record made when each was written: the previous value,
    or removal when there was none. The file itself goes only if GameCore
    created it — otherwise it holds settings the player made in the emulator's
    own window, and deleting those to undo ours would be a far larger act than
    the one they asked for.
    """
    data = record(system_id, game_id)
    restore = data.get("restore") or {}
    b = block(system_id) or {}
    _get, put = _FORMATS.get(b.get("format"), (None, None))
    path = target(system_id, game_id, home) if put else None

    if path is not None and path.is_file():
        if data.get("createdFile"):
            path.unlink(missing_ok=True)
        else:
            try:
                text = path.read_text()
                for sect, keys in restore.items():
                    for key, previous in keys.items():
                        text = put(text, sect, key, previous)
                _atomic_write(path, text)
            except OSError as e:
                log.warning("pergame: cannot un-write %s — %s", path, e)

    data.pop("settings", None)
    data.pop("restore", None)
    data.pop("createdFile", None)
    data.pop("source", None)
    _write_record(system_id, game_id, data)
    return f"{system_id}: settings removed for {game_id}"


# ── shared profiles ──────────────────────────────────────────────────────────
#
# The "it just works" half: a game with a known-good setting starts, and the
# player never learns that anything was placed. Everything below exists to keep
# that from also meaning "and can never be undone".
#
# Distributed as DATA in the pack, which is what makes them reach a box down
# the signed catalogue channel. A profile is a fact about a game, not code, and
# a fix for a title somebody discovers on a Tuesday should not need a release.

# `flatpak info` per app id, once per process. The version only changes when
# something updates the emulator, and that does not happen while the backend is
# up: a box that updated mid-session gets the old answer until it restarts,
# which costs at most one launch with a profile that was correct yesterday.
_version_memo: dict[str, str | None] = {}

# Long enough for a cold flatpak metadata read, short enough that it cannot be
# what makes a game feel slow to start. A timeout answers "unknown", and
# unknown applies the profile — see `_version_allows`.
_VERSION_TIMEOUT = 2.0


def _version_tuple(raw: str) -> tuple[int, ...]:
    """The leading dotted-numeric part of a version, and nothing else.

    RPCS3 reports `0.0.41-19497-c0598f61`. The build counter and the commit are
    real information and completely useless for ordering, so they are dropped
    rather than parsed into something that would compare `c0598f61` against
    `a1b2c3d4` and produce an answer.
    """
    lead = re.match(r"\d+(?:\.\d+)*", raw.strip())
    return tuple(int(n) for n in lead.group(0).split(".")) if lead else ()


def _at_least(have: tuple[int, ...], want: tuple[int, ...]) -> bool:
    width = max(len(have), len(want))
    return have + (0,) * (width - len(have)) >= want + (0,) * (width - len(want))


def emulator_version(system_id: str) -> str | None:
    """What version of this emulator the box has, or None if it cannot tell.

    Only Flatpak is asked, because only Flatpak can be asked cheaply and
    uniformly. An emulator installed from a GitHub asset has its version in the
    pack's `install.version`, which is what the catalogue THOUGHT it installed
    rather than what is on the disk — close enough to mislead, so it is not
    used here.
    """
    import subprocess

    try:
        pack = load_catalog()[system_id.lower()]
    except Exception:
        return None
    if (pack.data.get("install") or {}).get("provider") != "flatpak":
        return None
    app_id = pack.app_id
    if app_id in _version_memo:
        return _version_memo[app_id]

    found = None
    try:
        r = subprocess.run(["flatpak", "info", app_id], capture_output=True,
                           text=True, timeout=_VERSION_TIMEOUT)
        m = re.search(r"^\s*Version:\s*(\S+)", r.stdout, re.M)
        found = m.group(1) if m and r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        found = None
    _version_memo[app_id] = found
    return found


def _version_allows(spec: str, version: str | None) -> bool:
    """Does the installed emulator fall inside a profile's declared range?

    UNKNOWN counts as yes, and that is a judgement rather than an oversight.
    The range exists so a profile can be retired the day an emulator renames
    the option it sets — a case somebody has to notice and push. Refusing on
    "cannot tell" would instead switch the whole feature off on any box where
    `flatpak info` is slow, unavailable, or the emulator is not a Flatpak, and
    a feature that silently does nothing is worse than one that occasionally
    writes a key an old build ignores.
    """
    if version is None:
        return True
    have = _version_tuple(version)
    if not have:
        return True
    for clause in spec.split(","):
        clause = clause.strip()
        op = clause[:2] if clause[:2] in (">=", "<=") else clause[:1]
        want = _version_tuple(clause[len(op):])
        if not want:
            continue
        if op == ">=" and not _at_least(have, want):
            return False
        if op == ">" and (_at_least(want, have)):
            return False
        if op == "<=" and not _at_least(want, have):
            return False
        if op == "<" and _at_least(have, want):
            return False
    return True


def profile_for(system_id: str, game_id: str) -> dict | None:
    """The shipped profile for this exact game, or None.

    Matched on the id and never on the title: two dumps of one game agree on
    their Title ID and disagree about their file name, their region tag and
    their revision. A profile keyed by anything else would apply to one
    player's copy and not the next one's, which reads as the profile being
    broken rather than as the match being wrong.
    """
    for profile in (block(system_id) or {}).get("profiles", []):
        if profile["gameId"] == game_id:
            return profile
    return None


def profile_state(system_id: str, game_id: str) -> dict:
    """Everything the options screen needs to say about the shipped profile.

    Assembled here rather than in the router because "applied", "refused" and
    "exists but this emulator is too old for it" are three different sentences
    and the difference between them is entirely this module's business.
    """
    profile = profile_for(system_id, game_id)
    if profile is None:
        return {"available": False}
    data = record(system_id, game_id)
    version = emulator_version(system_id)
    return {
        "available": True,
        "label": profile["label"],
        "why": profile["why"],
        "emulator": profile["emulator"],
        "emulatorVersion": version,
        "inRange": _version_allows(profile["emulator"], version),
        "applied": data.get("profileApplied") == game_id,
        "dismissed": bool(data.get("dismissed")),
    }


def adopt_profile(system_id: str, game_id: str) -> bool:
    """Take the shipped profile's settings as this game's, once.

    Once, and the marker is what makes it once. Re-adopting on every launch
    would undo a player who had changed one of the profile's keys in the
    emulator's own window — they would fix it, play, quit, and find it back the
    way it was, with nothing on screen connecting the two.

    Returns True when something was newly adopted.
    """
    profile = profile_for(system_id, game_id)
    if profile is None:
        return False
    data = record(system_id, game_id)
    if data.get("dismissed") or data.get("profileApplied") == game_id:
        return False
    if not _version_allows(profile["emulator"], emulator_version(system_id)):
        log.info("pergame: %s has a profile for %s but it declares %s and this "
                 "box runs %s — offering it rather than placing it",
                 system_id, game_id, profile["emulator"],
                 emulator_version(system_id))
        return False
    set_settings(system_id, game_id, profile["settings"], source="profile")
    data = record(system_id, game_id)
    data["profileApplied"] = game_id
    _write_record(system_id, game_id, data)
    return True


def dismiss_profile(system_id: str, game_id: str, home: Path) -> str | None:
    """Take the profile back off, and remember that the player said so.

    Both halves are needed. Un-writing without the flag means the next launch
    puts it straight back — a setting the player cannot remove, only postpone,
    which is the trust bug this feature would be judged on. The flag without
    the un-write is a screen that says "removed" over a file that still holds
    it.
    """
    message = release(system_id, game_id, home)
    data = record(system_id, game_id)
    data["dismissed"] = True
    data.pop("profileApplied", None)
    _write_record(system_id, game_id, data)
    return message


def restore_profile(system_id: str, game_id: str, home: Path) -> str | None:
    """Put a dismissed profile back. The inverse has to exist, or "remove" is
    a one-way door and nobody can safely try it."""
    data = record(system_id, game_id)
    data.pop("dismissed", None)
    _write_record(system_id, game_id, data)
    adopt_profile(system_id, game_id)
    return materialise_id(system_id, game_id, home)


# ── the emulator's own screen ────────────────────────────────────────────────

def settings_launcher(system_id: str) -> tuple[str, str] | None:
    """`(path, args)` that open this emulator's own settings window, or None.

    GameCore builds no unified settings screen, and this function is where that
    decision is spent. Translating "internal resolution" into thirteen
    vocabularies and then chasing it across every emulator release is what
    makes Batocera's configgen impossible to port; opening the real window
    costs one field in the pack and never goes out of date.

    The args are DECLARED by the pack rather than derived from `launch.args` by
    stripping `--fullscreen --no-gui`. That shortcut is a hardcoded list of
    other people's command-line flags living in the backend: correct for the
    three emulators somebody checked, and for the fourth it opens a fullscreen
    game with no window and no way back.
    """
    b = block(system_id) or {}
    args = b.get("settingsArgs")
    if not args or not b.get("supported"):
        return None
    try:
        pack = load_catalog()[system_id.lower()]
    except Exception:
        return None
    return pack.launcher(prefer_existing=True)[0], args
