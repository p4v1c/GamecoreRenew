"""melonDS config file (hotkey binding) and process discovery."""

import glob
import json
import os
import re
import shutil
import time

from melonds_common import (BINDING, MELONDS_TOMLS, QT_KEYS, SCAN_IDLE_S,
                            keyname, log)


def melonds_toml():
    override = os.environ.get("MELONDS_CONFIG")
    if override:
        return override if os.path.isfile(override) else None
    root = os.environ.get("GAMECORE_PATH")
    if root:
        # Match GameCore's launcher choice, not a stale Flatpak config left on
        # disk after switching to its optional lib/melon native executable.
        native = os.path.isfile(os.path.join(root, "lib", "melon"))
        data = os.environ.get("GAMECORE_DATA", root)
        try:
            systems = json.load(open(os.path.join(data, "config", "systems.json")))
            system = next(s for s in systems if s.get("id") == "melonds")
            native = os.path.basename(system["path"]) != "flatpak"
        except (OSError, ValueError, KeyError, StopIteration, TypeError):
            pass
        path = MELONDS_TOMLS[1 if native else 0]
        return path if os.path.isfile(path) else None
    return next((p for p in MELONDS_TOMLS if os.path.isfile(p)), None)


def is_melonds_binary(path):
    path = path.removesuffix(" (deleted)")
    if os.path.basename(path) == "melonDS":
        return True
    root = os.environ.get("GAMECORE_PATH")
    return bool(root and path == os.path.realpath(os.path.join(root, "lib", "melon")))


def read_binding(path=None):
    """(keyboard value, joystick value) of HK_SwapScreenEmphasis, or (None, None)."""
    path = path or melonds_toml()
    if not path:
        return None, None
    vals, sec = {}, None
    try:
        for ln in open(path, encoding="utf-8", errors="replace"):
            t = ln.strip()
            if t.startswith("["):
                sec = t
            elif sec in ("[Instance0.Keyboard]", "[Instance0.Joystick]") and "=" in t:
                k, _, v = t.partition("=")
                if k.strip() == BINDING:
                    vals[sec] = v.strip()
    except OSError:
        return None, None
    return vals.get("[Instance0.Keyboard]"), vals.get("[Instance0.Joystick]")


def ensure_binding(hkcode, verbose=True, cheats=True):
    """Bind 'Swap screen emphasis' to the expected KEYBOARD key in melonDS's
    .toml and clear its JOYSTICK binding.

    Automatic because the binding once vanished on its own (melonDS rewrote
    its config with -1 everywhere). The joystick binding is an SDL index that
    breaks on a pad change, so it is removed for good.

    NEVER writes while melonDS runs: it rewrites the whole file on exit.
    """
    path = melonds_toml()
    if not path:
        return False
    if find_pid(force=True) is not None:
        return False
    want_kb = str(QT_KEYS.get(hkcode))
    if hkcode not in QT_KEYS:
        return False
    kb, joy = read_binding(path)
    txt = open(path, encoding="utf-8", errors="replace").read()
    # With EnableCheats false melonDS loads NO cheat, so our flag would be moot.
    need_cheats = cheats and re.search(r"^EnableCheats = false$", txt, re.M) is not None
    if kb == want_kb and joy in ("-1", None) and not need_cheats:
        return False                     # already right
    out, sec, done = [], None, []
    for ln in open(path, encoding="utf-8", errors="replace").read().splitlines():
        t = ln.strip()
        if t.startswith("["):
            sec = t
        elif need_cheats and t == "EnableCheats = false":
            out.append("EnableCheats = true")
            done.append("EnableCheats -> true (otherwise no cheat is loaded)")
            continue
        elif "=" in t and t.partition("=")[0].strip() == BINDING:
            if sec == "[Instance0.Keyboard]" and t.partition("=")[2].strip() != want_kb:
                out.append("%s = %s" % (BINDING, want_kb))
                done.append("keyboard -> %s (%s)" % (want_kb, keyname(hkcode)))
                continue
            if sec == "[Instance0.Joystick]" and t.partition("=")[2].strip() != "-1":
                out.append("%s = -1" % BINDING)
                done.append("joystick -> -1 (SDL binding removed)")
                continue
        out.append(ln)
    if not done:
        return False
    try:
        shutil.copy2(path, path + ".bak-mlt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(out) + "\n")
    except OSError as e:
        if verbose:
            log("melonDS binding: cannot write (%s)" % e)
        return False
    if verbose:
        log("melonDS binding set in %s: %s" % (os.path.basename(path), "; ".join(done)))
    return True


# ---------- process ---------------------------------------------------------
SCAN_FULL_S = 10.0       # "has a newer instance appeared?" check
_pid_cache = {"pid": None, "next_scan": 0.0, "next_full": 0.0, "warned": None}


def _starttime(pid):
    """Field 22 of /proc/<pid>/stat: start time, in ticks since boot."""
    try:
        d = open("/proc/%d/stat" % pid).read()
        return int(d[d.rindex(")") + 2:].split()[19])
    except (OSError, ValueError, IndexError):
        return 0


def _all_melonds():
    out = []
    for p in glob.glob("/proc/[0-9]*"):
        try:
            if is_melonds_binary(os.readlink(p + "/exe")):
                out.append(int(os.path.basename(p)))
        except OSError:
            pass
    return out


def find_pid(force=False):
    """melonDS pid — the NEWEST one when several run.

    The synthetic key goes to the foreground window, i.e. the instance just
    opened; writing another instance's config does nothing, silently (a
    forgotten test instance once captured the daemon). While the known pid
    answers only /proc/<pid>/exe is read; the full /proc scan runs every
    SCAN_FULL_S.
    """
    c = _pid_cache
    now = time.time()

    fast = None
    if c["pid"] is not None:
        try:
            if is_melonds_binary(os.readlink("/proc/%d/exe" % c["pid"])):
                fast = c["pid"]
            else:
                c["pid"] = None
        except OSError:
            c["pid"] = None

    if fast is not None and not force and now < c["next_full"]:
        return fast
    if fast is None and not force and now < c["next_scan"]:
        return None

    c["next_scan"] = now + SCAN_IDLE_S
    c["next_full"] = now + SCAN_FULL_S
    pids = _all_melonds()
    if not pids:
        c["pid"] = None
        return None
    best = max(pids, key=_starttime)
    if len(pids) > 1 and c["warned"] != best:
        c["warned"] = best
        log("%d melonDS instances (%s) -> using the newest: %d"
            % (len(pids), ",".join(str(x) for x in sorted(pids)), best))
    elif len(pids) == 1:
        c["warned"] = None
    c["pid"] = best
    return best
