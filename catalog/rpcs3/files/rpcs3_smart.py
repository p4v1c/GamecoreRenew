#!/usr/bin/env python3
"""RPCS3 Smart Pack: the settings a PS3 game should start with.

What RPCS3 already does, and what this adds
-------------------------------------------
Read from RPCS3's own source (v0.0.41, `Emu/System.cpp`) rather than assumed:
a `--no-gui` boot in the default config mode reads
`GuiConfigs/config_database.dat` and applies the official recommendation for
the serial — *unless* `custom_configs/config_<SERIAL>.yml` exists, in which
case the log says "Found custom config. Ignoring database config" and the
recommendation is dropped entirely. Both are layered over `config.yml`, and
only the keys present in the file change anything.

So on a game with no custom config RPCS3 is already right and nothing is
written. On a game WITH one — every hand-tuned game on a real box — the
official recommendation is silently lost. That is the gap this closes: the
recommendation, and the pack's own profile, are merged into the custom config
key by key, never over a value the player chose.

Precedence, per key: RPCS3 default < `config.yml` < official recommendation <
pack profile < the player's own value. "The player's own value" is a key in
the custom config that differs from `config.yml` and that GameCore did not
write — RPCS3's settings window saves a custom config as a full dump, so
presence alone says nothing about intent. Which keys exist at all is read from
the "Used configuration" RPCS3 prints at every boot.

Written once: a second launch finds every key in place and writes nothing.
Everything written is recorded with what it displaced, so `undo` puts it back
key by key.

Patches: the timer keeps RPCS3's official patch catalogue (patches/patch.yml)
fresh, so every official patch is already there to tick. Which ones are
enabled stays the player's call, made in RPCS3's patch manager or
rpcs3-manager: patch_config.yml and imported_patch.yml are never written.
"""
from __future__ import annotations

import argparse
import contextlib
import dataclasses
import errno
import fcntl
import hashlib
import json
import os
import re
import struct
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterator

try:
    import yaml
except ImportError:  # pragma: no cover - both interpreters that run this have it
    yaml = None

DEFAULT_APP_ID = "net.rpcs3.RPCS3"
CONFIG_DB_URL = "https://api.rpcs3.net/config/?api=v1"
PATCH_DB_URL_TEMPLATE = "https://rpcs3.net/compatibility?patch&api=v1&v={version}"
PATCH_ENGINE_VERSION = "1.2"
HERE = Path(__file__).resolve().parent

_APP_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")
SERIAL_RE = re.compile(r"^[A-Z]{4}[0-9]{5}$")
APP_VER_RE = re.compile(r"^[0-9]{2}\.[0-9]{2}$")

# The third letter of a PS3 serial is the territory it was released in.
_REGIONS = {"E": "Europe", "U": "USA", "J": "Japan", "A": "Asia", "K": "Korea",
            "H": "Hong Kong", "T": "Japan"}

ABSENT = None


def _log(message: str) -> None:
    print(f"[gamecore-rpcs3-smart] {message}", flush=True)


# ── YAML, the way yaml-cpp reads it ──────────────────────────────────────────
#
# Two differences from PyYAML's defaults, both of which silently produce a
# wrong answer rather than an error:
#   · every scalar stays a string. `01.10` is an app version, and SafeLoader
#     turns it into the float 1.1 — which then matches nothing, ever.
#   · an anchor may be defined twice. RPCS3's own patch.yml does it (yaml-cpp
#     keeps the latest), and PyYAML refuses the whole 900 KB file over it.

if yaml is not None:
    class _Loader(yaml.BaseLoader):
        pass

    def _compose_node(self, parent, index):
        if self.check_event(yaml.events.AliasEvent):
            event = self.get_event()
            if event.anchor not in self.anchors:
                raise yaml.composer.ComposerError(
                    None, None, f"found undefined alias {event.anchor!r}", event.start_mark)
            return self.anchors[event.anchor]
        anchor = self.peek_event().anchor
        self.descend_resolver(parent, index)
        if self.check_event(yaml.events.ScalarEvent):
            node = self.compose_scalar_node(anchor)
        elif self.check_event(yaml.events.SequenceStartEvent):
            node = self.compose_sequence_node(anchor)
        else:
            node = self.compose_mapping_node(anchor)
        self.ascend_resolver()
        return node

    _Loader.compose_node = _compose_node


def yload(text: str) -> Any:
    if yaml is None:
        raise RuntimeError("PyYAML is not available")
    return yaml.load(text, Loader=_Loader)


def flatten(tree: Any, prefix: tuple[str, ...] = ()) -> dict[tuple[str, ...], Any]:
    """Every leaf of a nested mapping, keyed by its path. Lists are leaves."""
    out: dict[tuple[str, ...], Any] = {}
    if isinstance(tree, dict):
        for key, value in tree.items():
            out.update(flatten(value, prefix + (str(key),)))
    elif prefix:
        out[prefix] = tree
    return out


def norm(value: Any) -> Any:
    """A setting value as RPCS3 compares it: `True`, `true` and `"true"` agree."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str) and value.lower() in ("true", "false"):
        return value.lower()
    return value


def keyname(path: tuple[str, ...] | list[str]) -> str:
    return "/".join(path)


# ── files ────────────────────────────────────────────────────────────────────

def atomic_write(path: Path, payload: bytes | str) -> None:
    """Replace `path` whole or not at all, keeping its mode."""
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        mode = path.stat().st_mode & 0o7777
    except OSError:
        mode = None
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".gcsmart", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def write_json(path: Path, data: Any) -> None:
    atomic_write(path, json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


BACKUP_SUFFIX = ".bak-gamecore-smart"


def backup_once(path: Path) -> None:
    """The file as it was before GameCore first touched it — and only then.
    A second backup would be a copy of GameCore's own edit."""
    target = path.with_name(path.name + BACKUP_SUFFIX)
    if path.is_file() and not target.exists():
        target.write_bytes(path.read_bytes())
        with contextlib.suppress(OSError):
            os.chmod(target, path.stat().st_mode & 0o7777)


def state_dir(home: Path) -> Path:
    return home / ".local/share/gamecore/rpcs3-smart"


@contextlib.contextmanager
def locked(home: Path, *, timeout: float) -> Iterator[bool]:
    """One writer at a time between the timer and a launch.

    Yields False when the lock could not be had in time: the caller then does
    nothing rather than write beside another writer.
    """
    path = state_dir(home) / "lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    got = False
    try:
        end = time.monotonic() + max(0.0, timeout)
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                got = True
                break
            except OSError as exc:
                if exc.errno not in (errno.EAGAIN, errno.EACCES) or time.monotonic() >= end:
                    break
                time.sleep(0.05)
        yield got
    finally:
        if got:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def rpcs3_running(proc: Path = Path("/proc")) -> bool:
    """Is an RPCS3 of this user alive? It rewrites its own files while it runs.

    The Flatpak's process is still called `rpcs3` in the host's /proc.
    """
    uid = os.getuid()
    try:
        entries = list(proc.iterdir())
    except OSError:
        return False
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            if entry.stat().st_uid != uid:
                continue
            comm = (entry / "comm").read_text().strip()
        except OSError:
            continue
        if comm.lower() == "rpcs3":
            return True
    return False


# ── where RPCS3 keeps things ─────────────────────────────────────────────────

def validate_app_id(app_id: str) -> str:
    if not _APP_ID_RE.fullmatch(app_id):
        raise ValueError(f"invalid Flatpak app id: {app_id!r}")
    return app_id


@dataclasses.dataclass(frozen=True)
class Runtime:
    kind: str           # "flatpak" | "native"
    config: Path        # the directory holding config.yml
    cache: Path         # the directory holding RPCS3.log
    app_id: str = DEFAULT_APP_ID


def flatpak_runtime(home: Path, app_id: str = DEFAULT_APP_ID) -> Runtime:
    validate_app_id(app_id)
    base = home / ".var/app" / app_id
    return Runtime("flatpak", base / "config/rpcs3", base / "cache/rpcs3", app_id)


def native_runtime(home: Path) -> Runtime:
    return Runtime("native", home / ".config/rpcs3", home / ".cache/rpcs3")


def runtime_for_launch(exec_path: str, exec_args: str, home: Path,
                       app_id: str = DEFAULT_APP_ID) -> Runtime:
    """The tree of the binary the launch is ACTUALLY about to run.

    Taken from the launch's own exec path rather than re-derived: GameCore's
    `preferIfPresent` can put `lib/rpcs3` in front of the Flatpak, and a guess
    that disagrees with the launcher writes into a tree nobody will read.
    """
    if Path(exec_path).name == "flatpak":
        m = re.search(r"\brun\s+(\S+)", exec_args or "")
        wanted = m.group(1) if m and _APP_ID_RE.fullmatch(m.group(1)) else app_id
        return flatpak_runtime(home, wanted)
    return native_runtime(home)


def runtimes_for_sync(home: Path, gamecore_path: Path, app_id: str) -> list[Runtime]:
    found = []
    fp = flatpak_runtime(home, app_id)
    if fp.config.parent.is_dir():
        found.append(fp)
    if (gamecore_path / "lib/rpcs3").is_file():
        found.append(native_runtime(home))
    return found


def hdd0_dir(root: Path) -> Path:
    """dev_hdd0 as RPCS3 resolves it: vfs.yml when present, else beside config."""
    default = root / "dev_hdd0"
    try:
        doc = yload((root / "vfs.yml").read_text(encoding="utf-8"))
    except (OSError, RuntimeError, Exception):
        return default
    value = doc.get("/dev_hdd0/") if isinstance(doc, dict) else None
    if not isinstance(value, str) or not value:
        return default
    value = value.replace("$(EmulatorDir)", str(root) + "/")
    return Path(value)


# ── PARAM.SFO ────────────────────────────────────────────────────────────────

def read_sfo(path: Path) -> dict[str, Any]:
    """PARAM.SFO's key/value table. `{}` for anything that is not one."""
    try:
        data = path.read_bytes()
    except OSError:
        return {}
    if len(data) < 20 or data[:4] != b"\0PSF":
        return {}
    _, key_start, data_start, count = struct.unpack_from("<IIII", data, 4)
    out: dict[str, Any] = {}
    for i in range(min(count, 256)):
        off = 20 + i * 16
        if off + 16 > len(data):
            break
        key_off, fmt, length, _max_len, data_off = struct.unpack_from("<HHIII", data, off)
        k0 = key_start + key_off
        k1 = data.find(b"\0", k0)
        if k1 < 0:
            break
        key = data[k0:k1].decode("ascii", "replace")
        v0 = data_start + data_off
        raw = data[v0:v0 + length]
        if fmt == 0x0404 and len(raw) >= 4:
            out[key] = struct.unpack_from("<I", raw)[0]
        else:
            out[key] = raw.split(b"\0", 1)[0].decode("utf-8", "replace")
    return out


@dataclasses.dataclass
class Game:
    serial: str
    region: str
    title: str
    category: str
    disc_app_ver: str
    disc_version: str
    update_app_ver: str | None
    app_version: str
    executable_dir: str

    def label(self) -> str:
        return f"{self.title} ({self.serial} v{self.app_version})"


class NotIdentified(Exception):
    pass


def identify(rom: Path, root: Path) -> Game:
    """Serial, region and the app version RPCS3 will report for this dump.

    Mirrors `Emulator::Load`: a disc game whose serial has a CATEGORY=GD update
    with an EBOOT.BIN in dev_hdd0/game/ boots that update, and the version the
    patch engine matches against is the update's APP_VER, not the disc's.
    """
    rom = Path(rom)
    sfo_path = next((p for p in (rom / "PS3_GAME/PARAM.SFO", rom / "PARAM.SFO")
                     if p.is_file()), None)
    if sfo_path is None:
        raise NotIdentified(f"no PARAM.SFO under {rom}")
    sfo = read_sfo(sfo_path)
    serial = str(sfo.get("TITLE_ID", "")).strip()
    if not SERIAL_RE.fullmatch(serial):
        raise NotIdentified(f"PARAM.SFO carries no valid serial ({serial!r})")
    category = str(sfo.get("CATEGORY", "")).strip()
    app_ver = str(sfo.get("APP_VER", "")).strip()
    version = str(sfo.get("VERSION", "")).strip()
    title = str(sfo.get("TITLE", "")).replace("\n", " ").strip() or serial

    update_ver = None
    exe_dir = sfo_path.parent / "USRDIR"
    if category == "DG":
        upd = hdd0_dir(root) / "game" / serial
        usfo = read_sfo(upd / "PARAM.SFO")
        if (usfo.get("TITLE_ID") == serial and usfo.get("CATEGORY") == "GD"
                and (upd / "USRDIR/EBOOT.BIN").is_file()):
            update_ver = str(usfo.get("APP_VER", "")).strip() or None
            exe_dir = upd / "USRDIR"

    effective = update_ver or app_ver or version
    if not APP_VER_RE.fullmatch(effective or ""):
        raise NotIdentified(f"{serial}: no usable app version ({effective!r})")
    return Game(serial=serial, region=_REGIONS.get(serial[2], "unknown"), title=title,
                category=category, disc_app_ver=app_ver, disc_version=version,
                update_app_ver=update_ver, app_version=effective,
                executable_dir=str(exe_dir))


def rpcs3_version(runtime: Runtime, timeout: float = 2.0) -> str | None:
    if runtime.kind == "flatpak":
        try:
            r = subprocess.run(["flatpak", "info", runtime.app_id], capture_output=True,
                               text=True, timeout=timeout)
        except (OSError, subprocess.SubprocessError):
            return None
        m = re.search(r"^\s*Version:\s*(\S+)", r.stdout, re.M)
        return m.group(1) if m and r.returncode == 0 else None
    first = _read_log_head(runtime)
    m = re.search(r"RPCS3 v(\S+)", first or "")
    return m.group(1) if m else None


def _version_tuple(raw: str | None) -> tuple[int, ...]:
    lead = re.match(r"\d+(?:\.\d+)*", (raw or "").strip())
    return tuple(int(n) for n in lead.group(0).split(".")) if lead else ()


def version_allows(spec: str | None, version: str | None) -> bool:
    """`>=0.0.41,<0.0.50` against `0.0.41-19497-c0598f61`. Unknown → False:
    a patch whose RPCS3 range cannot be checked is not enabled."""
    if not spec:
        return True
    have = _version_tuple(version)
    if not have:
        return False
    for clause in spec.split(","):
        clause = clause.strip()
        op = clause[:2] if clause[:2] in (">=", "<=", "==") else clause[:1]
        want = _version_tuple(clause[len(op):])
        if not want:
            continue
        w = max(len(have), len(want))
        a, b = have + (0,) * (w - len(have)), want + (0,) * (w - len(want))
        if ((op == ">=" and a < b) or (op == ">" and a <= b) or (op == "<=" and a > b)
                or (op == "<" and a >= b) or (op == "==" and a != b)):
            return False
    return True


# ── RPCS3's log: what actually happened ──────────────────────────────────────

_LOG_APPLIED = re.compile(
    r"Applied patch \(hash='([^']+)', description='(.*?)', author='.*?', "
    r"patch_version='([^']*)', file_version='[^']*'\) \(<- (\d+)\)")


def log_path(runtime: Runtime) -> Path:
    return runtime.cache / "RPCS3.log"


def _read_log_head(runtime: Runtime) -> str | None:
    try:
        with open(log_path(runtime), encoding="utf-8-sig", errors="replace") as fh:
            return fh.readline()
    except OSError:
        return None


def parse_log(text: str) -> dict[str, Any]:
    """The facts of one RPCS3 run that matter here, read from its log."""
    obs: dict[str, Any] = {"exeHashes": [], "applied": [], "configSources": []}
    m = re.search(r"RPCS3 v(\S+)", text[:400])
    obs["rpcs3"] = m.group(1) if m else None
    m = re.search(r"Booting application from command line: (.*)", text)
    obs["bootPath"] = m.group(1).strip() if m else None
    serials = re.findall(r"SYS: Serial: (\S+)", text)
    versions = re.findall(r"SYS: Version: APP_VER=(\S+) VERSION=(\S+)", text)
    obs["serial"] = serials[-1] if serials else None
    obs["appVersion"] = versions[-1][0] if versions else None
    obs["update"] = bool(re.search(r"Updates found at /dev_hdd0/game/", text))
    for line in text.splitlines():
        if "SYS: Applying custom config: " in line:
            obs["configSources"].append({"custom": line.split("Applying custom config: ", 1)[1].strip()})
        elif "SYS: Applying database config" in line:
            obs["configSources"].append({"database": True})
        elif "Found custom config. Ignoring database config" in line:
            obs["configSources"].append({"databaseIgnored": True})
        elif "PPU executable hash: " in line or "SPU executable hash: " in line:
            h = re.search(r"((?:PPU|SPU)-[0-9a-f]{40})", line)
            if h and h.group(1) not in obs["exeHashes"]:
                obs["exeHashes"].append(h.group(1))
        else:
            a = _LOG_APPLIED.search(line)
            if a:
                # {PPU Exec Worker} is RPCS3 precompiling every executable of
                # the game in one process. A patch applied there proves nothing
                # about the run — and one using a fixed `alloc` silently fails
                # there for the second executable while it applies at boot.
                obs["applied"].append({"hash": a.group(1), "description": a.group(2),
                                       "patchVersion": a.group(3), "changes": int(a.group(4)),
                                       "precompile": "{PPU Exec Worker}" in line})
    obs["fatal"] = [ln.strip()[:300] for ln in text.splitlines() if "·F " in ln][:10]
    obs["usedConfigKeys"] = used_config_keys(text)
    return obs


def used_config_keys(text: str) -> list[str]:
    """Every setting key of the running build, from the "Used configuration"
    dump RPCS3 writes at boot — its own g_cfg, so its own schema."""
    m = re.search(r"SYS: Used configuration:\n((?:[^·\n][^\n]*\n|\n)+)", text)
    if not m:
        return []
    try:
        return sorted(keyname(k) for k in flatten(yload(m.group(1))))
    except Exception:
        return []


def ingest_log(home: Path, runtime: Runtime) -> dict[str, Any] | None:
    """Record the last run before the next one overwrites the log. Idempotent."""
    path = log_path(runtime)
    try:
        st = path.stat()
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return None
    key = f"{runtime.kind}:{int(st.st_mtime)}:{st.st_size}"
    store = state_dir(home) / "observations.json"
    data = read_json(store, {"version": 1, "runs": []})
    runs = data.get("runs") if isinstance(data.get("runs"), list) else []
    for run in runs:
        if run.get("key") == key:
            return run
    obs = parse_log(text)
    obs.update({"key": key, "runtime": runtime.kind, "logMtime": int(st.st_mtime)})
    keys = obs.pop("usedConfigKeys", [])
    if keys and obs.get("rpcs3"):
        write_json(state_dir(home) / f"schema-{runtime.kind}.json",
                   {"rpcs3": obs["rpcs3"], "keys": keys, "from": key})
    if not obs.get("serial"):
        return None
    runs.append(obs)
    data["runs"] = runs[-40:]
    write_json(store, data)
    return obs


def observations(home: Path) -> list[dict[str, Any]]:
    data = read_json(state_dir(home) / "observations.json", {})
    return data.get("runs", []) if isinstance(data, dict) else []


# ── settings ─────────────────────────────────────────────────────────────────

_PLAIN = re.compile(r"^[A-Za-z0-9_(][A-Za-z0-9_ .()%&!+,/\[\]-]*$")
_AMBIGUOUS = re.compile(r"^(?:true|false|yes|no|on|off|null|~|y|n|[-+]?[0-9][0-9._]*(?:e[-+]?[0-9]+)?)$",
                        re.I)


def yaml_scalar(value: str, *, bare_bool: bool = False) -> str:
    """A string as RPCS3's emitter would write it, quoted only when it must be."""
    if bare_bool and value in ("true", "false"):
        return value
    if value and _PLAIN.fullmatch(value) and not _AMBIGUOUS.fullmatch(value) \
            and not value.endswith(" "):
        return value
    return "'" + value.replace("'", "''") + "'"


def setting_scalar(value: str) -> str:
    """A config.yml VALUE. RPCS3 writes numbers and booleans bare, and its
    own parser reads a quoted "60" and a bare 60 identically — but bare is what
    its settings window would write, so the file stays reviewable."""
    if value in ("true", "false") or re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", value or ""):
        return value
    if value == "":
        return '""'
    return yaml_scalar(value)


def _key_re(key: str) -> str:
    return rf"(?:{re.escape(key)}|\"{re.escape(key)}\"|'{re.escape(key)}')"


def yaml_set_path(text: str, path: tuple[str, ...], value: str) -> str:
    """Set one leaf of RPCS3's two-space block YAML, leaving every other line.

    Creates missing parents at the end of their block. Refuses (ValueError)
    rather than guess on a shape RPCS3 does not write.
    """
    if text and not text.endswith("\n"):
        # RPCS3 writes its files without a final newline; keep it that way.
        return yaml_set_path(text + "\n", path, value)[:-1]
    lines = text.splitlines(keepends=True)
    start, end = 0, len(lines)
    for depth, key in enumerate(path):
        indent = "  " * depth
        pat = re.compile(rf"^{indent}{_key_re(key)}:(?:[ \t]+(.*))?$")
        found = None
        for i in range(start, end):
            line = lines[i].rstrip("\n")
            if pat.match(line):
                found = i
                break
        last = depth == len(path) - 1
        if found is None:
            # insert the rest of the path after the last non-blank line in range
            at = end
            while at > start and not lines[at - 1].strip():
                at -= 1
            new = [f"{'  ' * d}{yaml_scalar(k)}:\n" for d, k in enumerate(path[depth:-1], depth)]
            new.append(f"{'  ' * (len(path) - 1)}{yaml_scalar(path[-1])}: {setting_scalar(value)}\n")
            lines[at:at] = new
            return "".join(lines)
        if last:
            m = re.match(rf"^({indent}{_key_re(key)}):", lines[found])
            lines[found] = f"{m.group(1)}: {setting_scalar(value)}\n"
            return "".join(lines)
        m = pat.match(lines[found].rstrip("\n"))
        if m and m.group(1) and m.group(1).strip() not in ("", "{}"):
            raise ValueError(f"{keyname(path[:depth + 1])} is a value, not a section")
        start = found + 1
        stop = start
        child = "  " * (depth + 1)
        while stop < end and (not lines[stop].strip() or lines[stop].startswith(child)):
            stop += 1
        end = stop
    raise ValueError("empty path")


def db_recommendation(root: Path, serial: str) -> tuple[dict[tuple[str, ...], str], str]:
    """The official per-game settings from RPCS3's config database, if any."""
    try:
        doc = json.loads((root / "GuiConfigs/config_database.dat").read_text(encoding="utf-8"))
    except OSError:
        return {}, "database absent"
    except ValueError:
        return {}, "database unreadable"
    entry = (doc.get("games") or {}).get(serial) if isinstance(doc, dict) else None
    if not isinstance(entry, dict) or not isinstance(entry.get("config"), str):
        return {}, "no official recommendation for this serial"
    try:
        tree = yload(entry["config"])
    except Exception:
        return {}, "official recommendation is not valid YAML"
    flat = {k: norm(v) for k, v in flatten(tree).items() if isinstance(v, str)}
    return flat, "official recommendation"


def pack_profile(pack: dict, serial: str, version: str | None) -> tuple[dict, str | None]:
    for profile in ((pack.get("perGame") or {}).get("profiles") or []):
        if profile.get("gameId") != serial:
            continue
        if not version_allows(profile.get("emulator"), version) and version is not None:
            return {}, None
        flat = {k: norm(v) for k, v in flatten(profile.get("settings") or {}).items()}
        return flat, profile.get("label")
    return {}, None


def logged_schema(home: Path, runtime: Runtime, version: str | None) -> set | None:
    """The schema RPCS3 itself printed, if it was printed by this very build."""
    doc = read_json(state_dir(home) / f"schema-{runtime.kind}.json", {})
    if not isinstance(doc, dict) or not doc.get("keys") or not version or doc.get("rpcs3") != version:
        return None
    return {tuple(k.split("/")) for k in doc["keys"]}


def settings_schema(root: Path, base: dict | None) -> set | None:
    """The setting keys this RPCS3 build knows.

    RPCS3 writes config.yml and every custom config as a FULL dump of its
    settings, so the most recently written full dump is this build's schema.
    config.yml alone is not enough: it is only rewritten when the global
    settings are saved, and on the reference box it predates the installed
    build by weeks — keys the emulator reads today were missing from it.
    """
    keys = set(base or ())
    newest: tuple[float, Path] | None = None
    for p in (root / "custom_configs").glob("config_*.yml"):
        try:
            m = p.stat().st_mtime
        except OSError:
            continue
        if newest is None or m > newest[0]:
            newest = (m, p)
    for _m, p in ([newest] if newest else []):
        try:
            flat = flatten(yload(p.read_text(encoding="utf-8")))
        except Exception:
            continue
        if len(flat) >= 150:           # a full dump, not a hand-written fragment
            keys |= set(flat)
    return keys or None


def plan_config(*, custom: dict | None, base: dict | None, owned: dict,
                layers: list[tuple[str, dict]],
                schema: set | None = None) -> tuple[dict, list[dict]]:
    """What to write into the custom config, and why each key was or was not.

    `layers` is lowest priority first: [("official", …), ("profile", …),
    ("prerequisite:<patch>", …)]. A later layer overrides an earlier one on the
    same key. `custom` is the flattened custom config (None: no file),
    `base` the flattened config.yml (None: unknown), `owned` what GameCore wrote
    before: {keyname: {"written": v, "restore": v|None}}.
    """
    if schema is None and base is not None:
        schema = set(base)
    targets: dict[tuple[str, ...], tuple[str, str]] = {}
    for source, layer in layers:
        for key, value in layer.items():
            targets[key] = (norm(value), source)

    writes: dict[tuple[str, ...], str] = {}
    decisions: list[dict] = []
    for key, (target, source) in sorted(targets.items()):
        name = keyname(key)
        d = {"key": name, "target": target, "source": source}
        if schema is not None and key not in schema:
            decisions.append({**d, "action": "skipped",
                              "reason": "not a setting of this RPCS3 build"})
            continue
        inherited = norm(base.get(key)) if base is not None and key in base else None
        mine = owned.get(name)
        if custom is None or key not in custom:
            current, where = inherited, "config.yml"
        else:
            current, where = norm(custom[key]), "custom config"
        d["current"] = current
        if custom is not None and key in custom:
            if mine is not None and norm(mine.get("written")) != current:
                decisions.append({**d, "action": "kept-personal",
                                  "reason": "changed by you after GameCore set it"})
                continue
            if mine is None and current != target and inherited is None:
                # config.yml predates this setting, so nothing says whether the
                # custom config's value is a choice or a default. Kept.
                decisions.append({**d, "action": "kept-personal",
                                  "reason": "cannot tell whether this value is yours "
                                            "(config.yml has no such key); kept"})
                continue
            if mine is None and inherited is not None and current != inherited:
                decisions.append({**d, "action": "kept-personal" if current != target else "already",
                                  "reason": "your own value in the custom config"
                                  if current != target else "already set"})
                continue
        if current == target:
            decisions.append({**d, "action": "already", "reason": f"already {target} ({where})"})
            continue
        writes[key] = target
        decisions.append({**d, "action": "write"})
    return writes, decisions


# ── the launch ───────────────────────────────────────────────────────────────

def _owned(home: Path) -> dict:
    data = read_json(state_dir(home) / "owned.json", {})
    if not isinstance(data, dict) or data.get("version") != 1:
        data = {"version": 1, "config": {}}
    data.setdefault("config", {})
    return data


def prepare(*, rom: Path, home: Path, exec_path: str, exec_args: str,
            pack_dir: Path = HERE.parent, deadline: float | None = None,
            app_id: str = DEFAULT_APP_ID, proc: Path = Path("/proc"),
            version: str | None = "auto") -> dict[str, Any]:
    """The settings this game should start with, in the file RPCS3 will read.

    Never raises. Writes nothing it cannot finish before `deadline`
    (time.monotonic()), and nothing while an RPCS3 is running. Patches are
    the player's business (RPCS3's patch manager, rpcs3-manager) and are not
    touched here.
    """
    started = time.time()
    deadline = deadline if deadline is not None else time.monotonic() + 5.0
    report: dict[str, Any] = {"version": 2, "at": int(started), "rom": str(rom),
                              "errors": [], "settings": [], "written": []}
    try:
        runtime = runtime_for_launch(exec_path, exec_args, home, app_id)
    except ValueError as exc:
        report["errors"].append(str(exc))
        return _finish(home, report, None)
    report["runtime"] = {"kind": runtime.kind, "config": str(runtime.config),
                         "exec": exec_path, "args": exec_args}
    budget = max(0.0, deadline - time.monotonic() - 0.2)
    with locked(home, timeout=min(1.0, budget)) as got:
        if not got:
            report["errors"].append("another GameCore RPCS3 task holds the lock; nothing written")
            return _finish(home, report, None)
        try:
            ingest_log(home, runtime)
        except Exception as exc:  # the diagnosis must not cost the launch
            report["errors"].append(f"previous log not recorded: {exc}")
        try:
            game = identify(Path(rom), runtime.config)
        except NotIdentified as exc:
            report["errors"].append(str(exc))
            return _finish(home, report, None)
        report["game"] = dataclasses.asdict(game)
        ver = rpcs3_version(runtime) if version == "auto" else version
        report["rpcs3"] = ver
        if rpcs3_running(proc):
            report["errors"].append("RPCS3 is already running; its files were not modified")
            return _finish(home, report, game)

        root = runtime.config
        pack = read_json(pack_dir / "pack.json", {})
        owned = _owned(home)
        rkey = str(root)
        owned_cfg = owned["config"].setdefault(rkey, {}).get(game.serial, {"keys": {}})

        custom_path = root / "custom_configs" / f"config_{game.serial}.yml"
        try:
            custom_text = custom_path.read_text(encoding="utf-8") if custom_path.is_file() else None
            custom = flatten(yload(custom_text)) if custom_text is not None else None
        except Exception as exc:
            report["errors"].append(f"custom config unreadable ({exc}); settings not touched")
            return _finish(home, report, game)
        try:
            base = flatten(yload((root / "config.yml").read_text(encoding="utf-8")))
        except Exception:
            base = None
        schema = logged_schema(home, runtime, ver)
        report["schemaSource"] = "RPCS3's own configuration dump" if schema else "config files (fallback)"
        if schema is None:
            schema = settings_schema(root, base)
        rec, rec_status = db_recommendation(root, game.serial)
        profile, profile_label = pack_profile(pack, game.serial, ver)
        report["configSource"] = {
            "customConfig": str(custom_path) if custom_text is not None else None,
            "official": rec_status, "packProfile": profile_label,
        }

        writes: dict = {}
        if custom is None and not profile:
            # RPCS3 applies the official recommendation itself when there is
            # no custom config. Creating one here would switch that OFF.
            report["configSource"]["effective"] = ("RPCS3 applies the official recommendation natively"
                                                   if rec else "config.yml only")
            report["settings"] = [{"key": keyname(k), "target": v, "source": "official",
                                   "action": "native",
                                   "reason": "applied by RPCS3 at boot (no custom config)"}
                                  for k, v in sorted(rec.items())]
        else:
            writes, decisions = plan_config(custom=custom, base=base, schema=schema,
                                            owned=owned_cfg.get("keys", {}),
                                            layers=[("official", rec), ("profile", profile)])
            report["configSource"]["effective"] = "custom config (GameCore-merged)"
            if custom is None:
                # The file is about to exist, which stops RPCS3 applying the
                # official recommendation — so it has to carry it itself.
                for k, val in rec.items():
                    if (schema is None or k in schema) and k not in writes:
                        writes[k] = val
                        for d in decisions:
                            if d["key"] == keyname(k) and d["action"] == "already":
                                d.update(action="write", reason="carried into the new custom config, "
                                         "whose existence stops RPCS3 applying the recommendation itself")
            report["settings"] = decisions

        if writes and time.monotonic() >= deadline:
            report["errors"].append("out of time before writing; nothing written")
            return _finish(home, report, game)

        if writes:
            try:
                text = custom_text if custom_text is not None else ""
                for key in sorted(writes):
                    text = yaml_set_path(text, key, writes[key])
                after = flatten(yload(text))
                before = custom or {}
                expected = {**before, **writes}
                if {k: norm(v) for k, v in after.items()} != {k: norm(v) for k, v in expected.items()}:
                    raise ValueError("re-read custom config does not match the intended edit")
                if custom_text is not None:
                    backup_once(custom_path)
                atomic_write(custom_path, text)
                entry = owned["config"][rkey].setdefault(
                    game.serial, {"file": str(custom_path), "created": custom_text is None, "keys": {}})
                for key, value in writes.items():
                    name = keyname(key)
                    prev = entry["keys"].get(name, {}).get("restore", "__unset__")
                    restore = (before.get(key, ABSENT) if prev == "__unset__" else prev)
                    entry["keys"][name] = {"written": value, "restore": restore, "at": int(time.time())}
                report["written"].append({"file": str(custom_path), "keys": sorted(keyname(k) for k in writes),
                                          "created": custom_text is None})
                write_json(state_dir(home) / "owned.json", owned)
            except Exception as exc:
                report["errors"].append(f"settings not written: {exc}")
        return _finish(home, report, game)


def notice(report: dict) -> str | None:
    """One line for the screen, only when there is something to say.
    English, like the rest of GameCore's UI."""
    game = report.get("game")
    if not game:
        return None
    parts = []
    written = [d for d in report.get("settings", []) if d["action"] == "write"]
    if written:
        parts.append(f"{len(written)} recommended setting(s) applied")
    kept = [d for d in report.get("settings", []) if d["action"] == "kept-personal"]
    if kept:
        parts.append(f"kept your value for {', '.join(d['key'].split('/')[-1] for d in kept[:3])}"
                     + (" …" if len(kept) > 3 else "") + " (RPCS3 recommends otherwise)")
    if report.get("errors"):
        parts.append(report["errors"][0])
    if not parts:
        return None
    return f"PS3 · {game['title']} ({game['serial']} v{game['app_version']}): " + "; ".join(parts)


def _finish(home: Path, report: dict, game: Game | None) -> dict:
    report["notice"] = notice(report)
    sd = state_dir(home)
    with contextlib.suppress(OSError):
        write_json(sd / "last-launch.json", report)
        if game is not None:
            write_json(sd / "games" / f"{game.serial}.json", report)
        with open(sd / "history.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps({k: report.get(k) for k in
                                 ("at", "rom", "coverage", "errors", "written")},
                                ensure_ascii=False) + "\n")
    return report


def undo(home: Path, root: Path, serial: str | None = None) -> list[str]:
    """Put back what GameCore wrote, key by key. Values the player changed
    since are left alone."""
    done = []
    owned = _owned(home)
    rkey = str(root)
    for s, entry in list(owned["config"].get(rkey, {}).items()):
        if serial and s != serial:
            continue
        path = Path(entry["file"])
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            cur = flatten(yload(text))
            removals = []
            for name, rec in entry["keys"].items():
                key = tuple(name.split("/"))
                if norm(cur.get(key)) != norm(rec["written"]):
                    continue
                if rec["restore"] is ABSENT:
                    removals.append(key)
                else:
                    text = yaml_set_path(text, key, rec["restore"])
            for key in removals:
                text = _yaml_remove(text, key)
            if entry.get("created") and not _has_settings(text):
                path.unlink()
            else:
                atomic_write(path, text)
            done.append(f"{s}: settings restored in {path}")
        owned["config"][rkey].pop(s, None)
    write_json(state_dir(home) / "owned.json", owned)
    return done


def _has_settings(text: str) -> bool:
    """Anything left but empty section headers?"""
    return any(re.match(r"^\s*[^#\s].*?:[ \t]+\S", line) for line in text.splitlines())


def _yaml_remove(text: str, path: tuple[str, ...]) -> str:
    lines = text.splitlines(keepends=True)
    start, end = 0, len(lines)
    for depth, key in enumerate(path):
        pat = re.compile(rf"^{'  ' * depth}{_key_re(key)}:")
        idx = next((i for i in range(start, end) if pat.match(lines[i])), None)
        if idx is None:
            return text
        if depth == len(path) - 1:
            del lines[idx]
            return "".join(lines)
        start = idx + 1
        stop = start
        while stop < end and (not lines[stop].strip() or lines[stop].startswith("  " * (depth + 1))):
            stop += 1
        end = stop
    return text


# ── the timer: database synchronisation ──────────────────────────────────────

DEFAULT_POLICY: dict[str, Any] = {
    "version": 1, "syncConfigDatabase": True, "syncPatchDatabase": True,
    "syncHours": 6, "networkTimeoutSeconds": 10, "patchEngineVersion": PATCH_ENGINE_VERSION,
}


def load_policy(path: Path | None) -> dict[str, Any]:
    policy = dict(DEFAULT_POLICY)
    if path is None:
        return policy
    incoming = read_json(path, None)
    if not isinstance(incoming, dict) or incoming.get("version") != 1:
        _log("policy unreadable or unsupported; safe defaults used")
        return policy
    for key in DEFAULT_POLICY:
        if key in incoming and key != "version":
            policy[key] = incoming[key]
    try:
        policy["syncHours"] = max(1, min(24 * 30, int(policy["syncHours"])))
    except (TypeError, ValueError):
        policy["syncHours"] = 6
    try:
        policy["networkTimeoutSeconds"] = max(2, min(30, int(policy["networkTimeoutSeconds"])))
    except (TypeError, ValueError):
        policy["networkTimeoutSeconds"] = 10
    if policy["patchEngineVersion"] != PATCH_ENGINE_VERSION:
        policy["patchEngineVersion"] = PATCH_ENGINE_VERSION
    return policy


class HTTPSOnlyRedirectHandler(urllib.request.HTTPRedirectHandler):
    """urllib follows a redirect to plain HTTP by default; content RPCS3 later
    parses must not cross that boundary."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme.lower() != "https":
            raise urllib.error.HTTPError(newurl, code, "refusing non-HTTPS redirect", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url: str, timeout: int) -> bytes:
    request = urllib.request.Request(url, headers={
        "User-Agent": "GameCore-RPCS3-SmartPack/4",
        "Accept": "application/json,text/plain;q=0.9,*/*;q=0.1"}, method="GET")
    opener = urllib.request.build_opener(HTTPSOnlyRedirectHandler())
    with opener.open(request, timeout=timeout) as response:
        if getattr(response, "status", 200) != 200:
            raise OSError(f"HTTP status {response.status}")
        data = response.read(64 * 1024 * 1024 + 1)
    if len(data) > 64 * 1024 * 1024:
        raise ValueError("download exceeds 64 MiB safety limit")
    return data


def validate_config_database(payload: bytes) -> dict[str, int]:
    try:
        doc = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"config DB is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(doc, dict):
        raise ValueError("config DB root is not an object")
    code = doc.get("return_code")
    if not isinstance(code, int) or code < 0:
        raise ValueError(f"config DB return_code is invalid: {code!r}")
    games = doc.get("games")
    if not isinstance(games, dict) or not games:
        raise ValueError("config DB has no games object")
    usable = sum(1 for s, e in games.items()
                 if isinstance(s, str) and isinstance(e, dict) and isinstance(e.get("config"), str))
    if usable < 100:
        raise ValueError(f"config DB has only {usable} usable entries")
    return {"games": len(games), "usable": usable}


def decode_patch_database_response(payload: bytes, engine_version: str) -> bytes | None:
    """The envelope RPCS3's patch manager downloads, checked the way it checks it
    (`patch_manager_dialog::handle_json`), plus a full parse of the YAML."""
    try:
        doc = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"patch response is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(doc, dict):
        raise ValueError("patch response root is not an object")
    code = doc.get("return_code")
    if code == 1:
        return None
    if code != 0:
        raise ValueError(f"patch endpoint return_code is invalid: {code!r}")
    if doc.get("version") != engine_version:
        raise ValueError(f"patch version {doc.get('version')!r} does not match {engine_version!r}")
    patch, checksum = doc.get("patch"), doc.get("sha256")
    if not isinstance(patch, str) or not patch:
        raise ValueError("patch response has no patch content")
    if not isinstance(checksum, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", checksum):
        raise ValueError("patch response has no valid sha256")
    content = patch.encode("utf-8")
    if hashlib.sha256(content).hexdigest().lower() != checksum.lower():
        raise ValueError("patch response checksum mismatch")
    if not re.search(rf"(?m)^\s*Version:\s*[\"']?{re.escape(engine_version)}[\"']?\s*$", patch):
        raise ValueError("patch YAML is missing the expected Version header")
    try:
        tree = yload(patch)
    except Exception as exc:
        raise ValueError(f"patch YAML does not parse: {type(exc).__name__}") from exc
    if not isinstance(tree, dict) or len(tree) < 50:
        raise ValueError("patch YAML has implausibly few entries")
    return content


def _fresh(path: Path, hours: int) -> bool:
    try:
        st = path.stat()
    except OSError:
        return False
    return st.st_size > 0 and (time.time() - st.st_mtime) < hours * 3600


def sync_runtime(home: Path, runtime: Runtime, policy: dict, *, offline: bool, force: bool,
                 fetcher=None, proc: Path = Path("/proc")) -> dict[str, str]:
    """Refresh both databases for one RPCS3 tree. Downloads outside the lock,
    replaces inside it, never while RPCS3 runs, never with invalid data."""
    fetcher = fetcher or fetch
    result = {}
    with contextlib.suppress(Exception):
        ingest_log(home, runtime)
    jobs = [
        ("configDatabase", policy["syncConfigDatabase"], runtime.config / "GuiConfigs/config_database.dat",
         CONFIG_DB_URL, lambda b: (validate_config_database(b), b)[1]),
        ("patchDatabase", policy["syncPatchDatabase"], runtime.config / "patches/patch.yml",
         PATCH_DB_URL_TEMPLATE.format(version=policy["patchEngineVersion"]),
         lambda b: decode_patch_database_response(b, policy["patchEngineVersion"])),
    ]
    for name, enabled, target, url, decode in jobs:
        if not enabled:
            result[name] = "disabled"
            continue
        if not force and _fresh(target, int(policy["syncHours"])):
            result[name] = "fresh"
            continue
        if offline:
            result[name] = "offline" + (":cache-kept" if target.is_file() else ":no-cache")
            continue
        try:
            content = decode(fetcher(url, int(policy["networkTimeoutSeconds"])))
        except Exception as exc:
            result[name] = f"error:{type(exc).__name__}:{str(exc)[:120]}"
            _log(f"{runtime.kind} {name}: {exc}; existing data kept")
            continue
        if content is None:
            result[name] = "current"
            with contextlib.suppress(OSError):
                os.utime(target)
            continue
        with locked(home, timeout=30) as got:
            if not got:
                result[name] = "deferred:lock-busy"
            elif rpcs3_running(proc):
                result[name] = "deferred:rpcs3-running"
            else:
                atomic_write(target, content)
                result[name] = "updated"
    return result


def sync_main(args: argparse.Namespace) -> int:
    home = (args.home or Path.home()).expanduser()
    try:
        validate_app_id(args.app_id)
    except ValueError as exc:
        _log(str(exc))
        return 2
    policy = load_policy(args.policy)
    offline = args.offline or os.environ.get("GAMECORE_RPCS3_OFFLINE") == "1"
    runtimes = runtimes_for_sync(home, args.gamecore_path, args.app_id)
    state: dict[str, Any] = {"version": 2, "timestamp": int(time.time()), "runtimes": {}}
    failed = not runtimes
    if not runtimes:
        state["error"] = "no RPCS3 installation found"
    for rt in runtimes:
        res = sync_runtime(home, rt, policy, offline=offline, force=args.force)
        state["runtimes"][rt.kind] = {"config": str(rt.config), **res}
        failed |= any(v.startswith("error") or v.endswith(":no-cache") for v in res.values())
    state["ok"] = not failed
    with contextlib.suppress(OSError):
        write_json(state_dir(home) / "state.json", state)
    _log(json.dumps(state, sort_keys=True))
    return 1 if failed else 0


# ── command line ─────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="GameCore RPCS3 Smart Pack")
    sub = p.add_subparsers(dest="cmd")
    s = sub.add_parser("sync", help="refresh RPCS3's config and patch databases")
    s.add_argument("--gamecore-path", type=Path, required=True)
    s.add_argument("--app-id", default=DEFAULT_APP_ID)
    s.add_argument("--policy", type=Path)
    s.add_argument("--offline", action="store_true")
    s.add_argument("--force", action="store_true")
    s.add_argument("--home", type=Path, help=argparse.SUPPRESS)
    pr = sub.add_parser("prepare", help="what a launch does, for a ROM, without launching")
    pr.add_argument("rom", type=Path)
    pr.add_argument("--exec-path", default="flatpak")
    pr.add_argument("--exec-args", default=f"run {DEFAULT_APP_ID} --fullscreen --no-gui")
    pr.add_argument("--home", type=Path, help=argparse.SUPPRESS)
    st = sub.add_parser("status", help="last launch report, and what RPCS3's log proves")
    st.add_argument("--home", type=Path, help=argparse.SUPPRESS)
    st.add_argument("--app-id", default=DEFAULT_APP_ID)
    un = sub.add_parser("undo", help="put back what GameCore wrote")
    un.add_argument("--serial")
    un.add_argument("--home", type=Path, help=argparse.SUPPRESS)
    un.add_argument("--app-id", default=DEFAULT_APP_ID)
    args = p.parse_args(argv)
    home = (getattr(args, "home", None) or Path.home()).expanduser()
    if args.cmd == "sync":
        return sync_main(args)
    if args.cmd == "prepare":
        r = prepare(rom=args.rom, home=home, exec_path=args.exec_path, exec_args=args.exec_args)
        print(json.dumps(r, indent=2, ensure_ascii=False))
        return 1 if r.get("errors") else 0
    if args.cmd == "status":
        rt = flatpak_runtime(home, args.app_id)
        obs = ingest_log(home, rt)
        last = read_json(state_dir(home) / "last-launch.json", {})
        print(json.dumps({"lastLaunch": last, "lastRun": obs}, indent=2, ensure_ascii=False))
        return 0
    if args.cmd == "undo":
        rt = flatpak_runtime(home, args.app_id)
        with locked(home, timeout=5) as got:
            if not got or rpcs3_running():
                print("busy: RPCS3 running or lock held")
                return 1
            for line in undo(home, rt.config, args.serial):
                print(line)
        return 0
    p.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
