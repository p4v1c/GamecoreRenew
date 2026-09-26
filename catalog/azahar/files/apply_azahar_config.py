#!/usr/bin/env python3
"""Set the two Azahar settings the L3 toggle needs.

  [Layout]
  layouts_to_cycle   = 0, 1   → F10 switches Default <-> SingleScreen
                                (instead of cycling all 7 layouts)
  screen_top_stretch = true   → in SingleScreen the top screen fills the
                                whole window (16:9 full frame)

Azahar rewrites its whole qt-config.ini from memory on exit, so editing it
while it runs is lost: this refuses to write while Azahar runs, and can wait.

  --wait [SECONDS]   wait for Azahar to exit (default 2 h), then apply
  --check            write nothing, show the state

`aspect_ratio` (AspectRatio::R16_9) is neither read nor written by the Qt
config in 2125.1.1, hence `screen_top_stretch`, which is persisted and only
acts in SingleFrameLayout.
"""

import os
import glob
import time
import shutil
import argparse

INI = os.path.expanduser(
    "~/.var/app/org.azahar_emu.Azahar/config/azahar-emu/qt-config.ini")
SECTION = "[Layout]"
WANT = {                       # key -> (wanted value, wanted \default flag)
    "layouts_to_cycle":   ("0, 1", "false"),
    "screen_top_stretch": ("true", "false"),
}


def azahar_running():
    for p in glob.glob("/proc/[0-9]*"):
        try:
            if open(p + "/comm").read().strip() == "azahar":
                return int(os.path.basename(p))
        except OSError:
            pass
    return None


def read_state(path):
    """Current values of the watched keys in [Layout]."""
    cur, insec = {}, False
    for ln in open(path, encoding="utf-8"):
        s = ln.strip()
        if s.startswith("["):
            insec = (s == SECTION)
        elif insec and "=" in s:
            k, _, v = s.partition("=")
            if k in WANT:
                cur[k] = v
    return cur


def apply(path):
    out, insec, changed, seen = [], False, [], set()
    wanted = {key + suffix: value for key, values in WANT.items()
              for suffix, value in zip(("", "\\default"), values)}

    def finish_section():
        for key, value in wanted.items():
            if key not in seen:
                out.append("%s=%s" % (key, value))
                changed.append("%s: missing -> %s" % (key, value))
                seen.add(key)

    found_section = False
    original = open(path, encoding="utf-8").read()
    for ln in original.splitlines():
        s = ln.strip()
        if s.startswith("["):
            if insec:
                finish_section()
            insec = (s == SECTION)
            found_section |= insec
        if insec and "=" in s:
            k, _, v = s.partition("=")
            k, v = k.strip(), v.strip()
            if k in wanted:
                seen.add(k)
                want = wanted[k]
                if v != want:
                    changed.append("%s: %s -> %s" % (k, v, want))
                    out.append("%s=%s" % (k, want))
                    continue
        out.append(ln)
    if not found_section:
        out.extend(["", SECTION])
    finish_section()
    if changed:
        shutil.copy2(path, path + ".bak-" + time.strftime("%Y%m%d-%H%M%S"))
        staged = path + ".layout-tmp"
        with open(staged, "w", encoding="utf-8") as f:
            f.write("\n".join(out) + "\n")
        os.replace(staged, path)
    return changed


def main():
    ap = argparse.ArgumentParser(description="configure Azahar for the L3 toggle")
    ap.add_argument("--wait", nargs="?", type=int, const=7200, metavar="SECONDS",
                    help="wait for Azahar to exit (default 7200 s), then apply")
    ap.add_argument("--check", action="store_true", help="write nothing, show the state")
    a = ap.parse_args()

    if not os.path.isfile(INI):
        print("Azahar config not found: %s" % INI); return 1

    if a.check:
        cur = read_state(INI)
        pid = azahar_running()
        print("Azahar: %s" % ("running (pid %d)" % pid if pid else "closed"))
        for k, (want, _) in WANT.items():
            got = cur.get(k, "(missing)")
            print("  %-20s = %-8s  %s" % (k, got, "OK" if got == want else "-> %s" % want))
        return 0

    if a.wait is not None:
        deadline = time.time() + a.wait
        if azahar_running():
            print("Azahar is running: it rewrites its .ini on exit. Waiting…",
                  flush=True)
        while azahar_running() and time.time() < deadline:
            time.sleep(3)
        if azahar_running():
            print("Still running after %d s — nothing done." % a.wait); return 1
        time.sleep(2)          # let Azahar finish writing its file

    pid = azahar_running()
    if pid:
        print("Azahar is running (pid %d): it would overwrite the change on exit." % pid)
        print("Close it, then run this again (or pass --wait).")
        return 1

    changed = apply(INI)
    if changed:
        print("Applied in %s:" % SECTION)
        for c in changed:
            print("   " + c)
        print("Previous file backed up next to it (.bak-*).")
    else:
        print("Nothing to do: both settings are already right.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
