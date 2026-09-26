#!/usr/bin/env python3
"""melonDS layout toggle — L3 switches the display live, no window resize.

   A = normal DS (two screens, 4:3)
   B = top screen only, 16:9

The daemon reads the pad's L3 over evdev (kernel code, same on every pad),
writes the target layout into melonDS's memory, then sends a synthetic
KEYBOARD key over /dev/uinput bound to melonDS's "Swap screen emphasis" hotkey
so it recomputes its geometry. A keycode never changes with the number or
order of pads; an SDL joystick binding does.

Modules (same directory, stdlib only):
  melonds_common.py   constants, log
  melonds_config.py   melonDS .toml binding, process discovery
  melonds_memory.py   memory access, locating config nodes / ScreenPanel
  melonds_input.py    uinput key, evdev pads

Usage:
  melonds_layout_toggle.py --diag       full diagnosis (run first)
  melonds_layout_toggle.py --watch      raw input events
  melonds_layout_toggle.py              daemon
  melonds_layout_toggle.py --mode blob --calibrate   fallback (v1 method)

Needs the same uid as melonDS and /proc/sys/kernel/yama/ptrace_scope = 0.
After a melonDS update the worst case is `--derive`, which re-derives and
caches the ScreenPanel offsets for the new binary; toggling works without them.
"""

import argparse
import glob
import json
import os
import select
import struct
import time

from melonds_common import (BLOB_HI, BLOB_LO, CACHE_PATH, CALIB_PATH, DEBOUNCE_S,
                            EV_KEY, HOTKEY_CODE, IEV, KEY_NAMES, OBJ_WIN, QT_KEYS,
                            SETTLE_S, STATE_A, STATE_B, TRIGGER_KEYCODES,
                            UINPUT_KEYS, expected_numscreens, keyname, log)
from melonds_config import ensure_binding, find_pid, melonds_toml, read_binding
from melonds_input import (Inputs, KeyEmitter, declares, dev_keybits, dev_name,
                           uinput_status)
from melonds_memory import (Mem, Target, build_fingerprint, load_cache,
                            module_span, save_cache, scan_regions)


# ===========================================================================
# TOGGLE
# ===========================================================================
def toggle(tgt, emitter, use_cheat=True):
    """Write the target state into the config, then ask melonDS to recompute.

    uinput mode: WE fire the hotkey (no race, no pad dependency in melonDS).
    hotkey mode (v1): relies on melonDS seeing the same physical press.
    Returns (label, verified); label None = melonDS did not follow.
    """
    cur_s, cur_a = tgt.cfg()
    to_B = (cur_s, cur_a) != (STATE_B["sizing"], STATE_B["aspect"])
    want = STATE_B if to_B else STATE_A
    label = "B (top only 16:9)" if to_B else "A (normal DS)"

    tgt.write_cfg(want["sizing"], want["aspect"])
    # Widescreen only makes sense in 16:9: on in B, off in A.
    if use_cheat and tgt.cheat_ready():
        tgt.set_cheat(to_B)
    if emitter is not None:
        emitter.tap()

    time.sleep(SETTLE_S)
    st = tgt.panel_state()
    if st is None:
        tgt.refresh()                    # nodes may have been created since
        return label, False              # no panel: nothing to verify
    if (st[0], st[1]) == (want["sizing"], want["aspect"]):
        return label, True

    # melonDS did not recompute: put the config back in phase with the screen
    # so the next press starts from a consistent state.
    try:
        tgt.write_cfg(cur_s, cur_a)
    except Exception:
        pass
    tgt.locate_toml()
    return None, True


# ===========================================================================
# RE-DERIVING THE OFFSETS  (surviving melonDS updates)
#
# Force melonDS from the current state to the other one and diff memory. The
# wanted fields are the only ones following EXACTLY the expected transition
#     sizing s0 -> s1, aspect a0 -> a1, numScreens expected(s0) -> expected(s1)
# inside one object whose first qword (vtable) points into the module and does
# not change between the two snapshots. No build constant involved.
# ===========================================================================
def snapshot(pid, mem):
    out = []
    for r in scan_regions(pid):
        data = mem.rd_soft(r["lo"], r["hi"] - r["lo"])
        if data is not None:
            out.append((r["lo"], data))
    return out


def derive(tgt, emitter, verbose=True):
    base, mlo, mhi = tgt.span
    s0, a0 = tgt.cfg()
    n0 = expected_numscreens(s0)
    other = STATE_B if (s0, a0) != (STATE_B["sizing"], STATE_B["aspect"]) else STATE_A
    s1, a1 = other["sizing"], other["aspect"]
    n1 = expected_numscreens(s1)
    if s0 == s1 or a0 == a1 or n0 == n1:
        if verbose:
            print("  starting state unusable for a diff (sizing=%d aspect=%d)" % (s0, a0))
        return None
    if verbose:
        print("  deriving: state %d/%d -> %d/%d" % (s0, a0, s1, a1))

    snap0 = snapshot(tgt.pid, tgt.mem)
    tgt.write_cfg(s1, a1)
    if emitter is not None:
        emitter.tap()
    time.sleep(max(SETTLE_S, 0.4))
    snap1 = snapshot(tgt.pid, tgt.mem)

    hits = []
    for (lo0, d0), (lo1, d1) in zip(snap0, snap1):
        if lo0 != lo1 or len(d0) != len(d1):
            continue                      # the mapping moved: ignore it
        end = len(d0) - OBJ_WIN
        for i in range(0, max(0, end), 8):
            p = struct.unpack_from("<Q", d0, i)[0]
            if not (mlo <= p < mhi):
                continue
            if struct.unpack_from("<Q", d1, i)[0] != p:
                continue
            so = ao = no = None
            for k in range(0, OBJ_WIN - 3, 4):
                v0 = struct.unpack_from("<i", d0, i + k)[0]
                v1 = struct.unpack_from("<i", d1, i + k)[0]
                if v0 == v1:
                    continue
                if   (v0, v1) == (s0, s1) and so is None: so = k
                elif (v0, v1) == (a0, a1) and ao is None: ao = k
                elif (v0, v1) == (n0, n1) and no is None: no = k
            if so is not None and ao is not None and no is not None:
                hits.append({"vtable": p - base, "sizing": so, "aspect": ao,
                             "numscr": no, "obj": lo0 + i})

    try:                                   # restore the starting state
        tgt.write_cfg(s0, a0)
        if emitter is not None:
            emitter.tap()
    except Exception:
        pass

    if not hits:
        return None
    if verbose and len(hits) > 1:
        print("  %d candidate objects, keeping the first" % len(hits))
    h = hits[0]
    offs = {k: h[k] for k in ("vtable", "sizing", "aspect", "numscr")}
    save_cache(tgt.fp, offs)
    tgt.obj, tgt.offs = h["obj"], dict(offs)
    if verbose:
        print("  object @ 0x%x" % h["obj"])
        print("  VTABLE_OFF = 0x%x   OFF_SIZING = 0x%x   OFF_ASPECT = 0x%x   "
              "OFF_NUMSCR = 0x%x" % (offs["vtable"], offs["sizing"],
                                     offs["aspect"], offs["numscr"]))
        print("  saved to %s (build %s)" % (CACHE_PATH, tgt.fp))
    return offs


# ===========================================================================
# DAEMON
# ===========================================================================
def load_calib():
    try:
        calib = json.load(open(CALIB_PATH))
    except (OSError, ValueError) as e:
        log("calibration unreadable: %s" % e); return None
    if (calib.get("blob_lo"), calib.get("blob_hi")) != (BLOB_LO, BLOB_HI):
        log("calibration incompatible with this version -> recalibrate."); return None
    return calib


def make_emitter(recalc, code, quiet=False):
    """(emitter, effective_mode).

    `quiet` is for the repeated attempts: at boot /dev/uinput has no session
    ACL yet (the user service starts before the session), and staying in the
    'hotkey' fallback forever would run the very mode this avoids."""
    if recalc == "hotkey":
        return None, "hotkey"
    ok, why = uinput_status()
    if not ok:
        if not quiet:
            log("uinput unavailable: %s" % why)
            log("   -> 'hotkey' mode meanwhile; retrying in a loop.")
        return None, "hotkey"
    try:
        return KeyEmitter(code), "uinput"
    except OSError as e:
        if not quiet:
            log("virtual keyboard failed (%s) -> 'hotkey' mode meanwhile" % e)
        return None, "hotkey"


def do_daemon(mode, recalc, hkcode, use_cheat=True):
    emitter, eff = make_emitter(recalc, hkcode) if mode == "native" else (None, "n/a")
    devs = Inputs()
    if not devs.readable:
        print("No readable /dev/input/event*. The 'input' group is required "
              "(sudo usermod -aG input $USER, then log in again).")
        return 1

    keylabel = ",".join(sorted(k for k, v in KEY_NAMES.items() if v in TRIGGER_KEYCODES)) \
               or ",".join(str(c) for c in sorted(TRIGGER_KEYCODES))
    log("daemon ready [mode %s / recalc %s]. %d input(s) with the button, of %d. key=%s"
        % (mode, eff, len(devs.devs), devs.readable, keylabel))
    if not devs.devs:
        log("no pad with this button yet - waiting for one (hotplug)")
    if eff == "uinput":
        kb, joy = read_binding()
        want = str(QT_KEYS.get(hkcode))
        if kb == want:
            log("melonDS: 'Swap screen emphasis' bound to KEYBOARD key %s  OK"
                % keyname(hkcode))
        else:
            log("melonDS: 'Swap screen emphasis' not on %s yet (read: %s)"
                % (keyname(hkcode), kb))
            log("   -> will set it as soon as melonDS is closed.")
    elif eff == "hotkey":
        log("melonDS must have 'Swap screen emphasis' on the same PAD button.")
        log("   That binding is an SDL index: it breaks when the pad order")
        log("   changes. Prefer --recalc uinput.")

    calib, calib_mtime = None, None
    tgt = None
    last_fail = None
    last_toggle = last_check = last_emit_try = last_refresh = 0.0
    refresh_wait = 3.0          # backs off rescans when the panel never shows up
    melonds_seen = find_pid() is not None
    if not melonds_seen and eff == "uinput":
        ensure_binding(hkcode, cheats=use_cheat)   # melonDS closed: good moment

    def toml_mtime():
        tp = melonds_toml()
        try:
            return os.path.getmtime(tp) if tp else None
        except OSError:
            return None
    cfg_mtime = toml_mtime()
    try:
        while True:
            events = devs.wait(1000)
            now = time.time()

            if now - last_check > 1.0:
                last_check = now
                devs.rescan()

                # uinput not accessible yet at boot: retry instead of staying
                # stuck in the 'hotkey' fallback.
                if emitter is None and recalc != "hotkey" and mode == "native" \
                        and now - last_emit_try > 5.0:
                    last_emit_try = now
                    emitter, eff2 = make_emitter(recalc, hkcode, quiet=True)
                    if emitter is not None:
                        eff = eff2
                        log("virtual keyboard available -> recalc uinput (key %s)"
                            % keyname(hkcode))
                        ensure_binding(hkcode, cheats=use_cheat)
                if mode == "blob":
                    try:
                        mtime = os.path.getmtime(CALIB_PATH)
                    except OSError:
                        mtime = None
                    if mtime != calib_mtime:
                        calib_mtime = mtime
                        calib = load_calib() if mtime is not None else None
                        if calib:
                            log("calibration loaded (%s)" % CALIB_PATH)

                # No panel = attached before melonDS built its window: the
                # config nodes seen are dead and a toggle would do nothing.
                # Rescan until it shows up.
                if tgt is not None and tgt.obj is None and now - last_refresh > refresh_wait:
                    last_refresh = now
                    if tgt.refresh():
                        refresh_wait = 3.0
                        log("panel found later: 0x%x  (%dx sizing/%dx aspect)"
                            % (tgt.obj, len(tgt.toml_s_all), len(tgt.toml_a_all)))
                    else:
                        refresh_wait = min(refresh_wait * 2, 30.0)

                pid = find_pid()
                if pid is None:
                    if tgt:
                        log("melonDS closed."); tgt.close(); tgt = None
                    if melonds_seen and eff == "uinput":
                        melonds_seen = False
                        ensure_binding(hkcode, cheats=use_cheat)  # it just rewrote it
                        cfg_mtime = toml_mtime()
                elif not melonds_seen:
                    melonds_seen = True

                # melonDS.toml changed by someone else (pad autoconfig,
                # reinstall, manual edit): check again.
                if eff == "uinput" and pid is None:
                    mt = toml_mtime()
                    if mt != cfg_mtime:
                        cfg_mtime = mt
                        ensure_binding(hkcode, cheats=use_cheat)
                elif tgt is None or tgt.pid != pid:
                    if tgt:
                        tgt.close()
                    try:
                        tgt = Target(pid); last_fail = None; refresh_wait = 3.0
                    except Exception as e:
                        tgt = None
                        if last_fail != (pid, str(e)):     # one line per cause
                            last_fail = (pid, str(e))
                            log("cannot attach (pid %d): %s" % (pid, e))
                            if isinstance(e, OSError):
                                log("   -> ptrace_scope=%s; it must be 0"
                                    % open("/proc/sys/kernel/yama/ptrace_scope").read().strip())

            who = devs.pressed(events)
            if not who:
                continue
            if recalc == "uinput" and emitter is None:
                # The pack disables the joystick hotkey. Do not write memory
                # until we can actually ask the emulator to redraw.
                continue
            if now - last_toggle < DEBOUNCE_S:
                continue
            last_toggle = now
            if tgt is None and find_pid(force=True) is None:
                log("button from [%s] but melonDS is not attached." % who)
                continue
            if tgt is None:
                continue        # melonDS just started: attach on the next pass

            try:
                if mode == "native":
                    label, verified = toggle(tgt, emitter, use_cheat)
                    if label is None:
                        log("melonDS did not react to the trigger.")
                        if eff == "uinput":
                            log("   -> is 'Swap screen emphasis' bound to the expected")
                            log("      KEYBOARD key (Config -> Input -> Hotkeys)?")
                        else:
                            log("   -> stale pad binding (pad changed?).")
                            log("      Use --recalc uinput, or redo the binding.")
                    else:
                        ws = ""
                        if use_cheat and tgt.cheat_flags:
                            ws = "  widescreen %s" % ("ON" if label.startswith("B") else "off")
                        log("toggle -> %s   [%s]%s%s"
                            % (label, who, "" if verified else "  (unverified)", ws))
                else:
                    if calib is None:
                        log("button received but no calibration (--calibrate)."); continue
                    if tgt.obj is None:
                        log("blob mode: ScreenPanel object not found (--derive)."); continue
                    A, B = calib["A"], calib["B"]
                    in_B = tgt.cfg() == (B["sizing"], B["aspect"])
                    snap, label = (A, "A (normal DS)") if in_B else (B, "B (top only 16:9)")
                    tgt.restore(snap)
                    time.sleep(0.05)
                    log("toggle -> %s   (numScreens=%d) [%s]" % (label, tgt.numscr(), who))
            except Exception as e:
                log("failed: %s" % e)
                try: tgt.close()
                except Exception: pass
                tgt = None
    finally:
        devs.close()
        if emitter:
            emitter.close()


# ===========================================================================
# TOOLS
# ===========================================================================
def do_watch():
    """Print EVERYTHING the input devices send: answers "does the daemon see
    my pad?" in 5 seconds."""
    print("Input devices (all, not only those declaring %s):"
          % ",".join(hex(c) for c in sorted(TRIGGER_KEYCODES)))
    fds, poller = {}, select.poll()
    for path in sorted(glob.glob("/dev/input/event*")):
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        except OSError as e:
            print("  %-22s  NOT READABLE (%s)" % (path, e.strerror))
            continue
        bits = dev_keybits(fd)
        mark = "   <-- declares the trigger" if bits and declares(bits, TRIGGER_KEYCODES) else ""
        print("  %-22s  %s%s" % (path, dev_name(fd), mark))
        fds[fd] = path
        poller.register(fd, select.POLLIN)
    if not fds:
        print("\nNo readable device: 'input' group missing.")
        return
    print("\nPress some buttons (Ctrl-C to quit).")
    while True:
        for fd, ev in poller.poll(1000):
            if ev & (select.POLLHUP | select.POLLERR | select.POLLNVAL):
                poller.unregister(fd); os.close(fd)
                print("  %s disconnected" % fds.pop(fd, "?"))
                continue
            try:
                buf = os.read(fd, IEV.size * 64)
            except OSError:
                continue
            for off in range(0, len(buf) - IEV.size + 1, IEV.size):
                _, _, et, code, val = IEV.unpack_from(buf, off)
                if et == EV_KEY and val in (0, 1):
                    name = next((k for k, v in KEY_NAMES.items() if v == code), "")
                    print("  %-22s code=%d (0x%x) %-3s %-8s%s"
                          % (fds.get(fd, "?"), code, code, name,
                             "PRESS" if val else "release",
                             "   <== TRIGGER" if (val and code in TRIGGER_KEYCODES) else ""))


def do_diag(hkcode):
    print("=== melonds-layout-toggle: diagnosis ===\n")

    print("-- system")
    try:
        ps = open("/proc/sys/kernel/yama/ptrace_scope").read().strip()
    except OSError:
        ps = "?"
    print("   ptrace_scope        : %s%s" % (ps, "   OK" if ps == "0" else "   (must be 0)"))
    ok, why = uinput_status()
    print("   /dev/uinput         : %s" % why)
    ev = sorted(glob.glob("/dev/input/event*"))
    readable = sum(1 for p in ev if os.access(p, os.R_OK))
    print("   /dev/input/event*   : %d present, %d readable%s"
          % (len(ev), readable, "   (input group?)" if readable < len(ev) else ""))

    print("\n-- inputs declaring %s"
          % (",".join(sorted(k for k, v in KEY_NAMES.items() if v in TRIGGER_KEYCODES))
             or ",".join(str(c) for c in sorted(TRIGGER_KEYCODES))))
    found = 0
    for path in ev:
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        except OSError:
            continue
        bits = dev_keybits(fd)
        if bits and declares(bits, TRIGGER_KEYCODES):
            print("   %-22s %s" % (path, dev_name(fd)))
            found += 1
        os.close(fd)
    if not found:
        print("   NONE. Is the pad on? (--watch shows the real codes)")

    print("\n-- 'Swap screen emphasis' binding in the melonDS config")
    tp = melonds_toml()
    if not tp:
        print("   melonDS config not found.")
    else:
        kb, joy = read_binding(tp)
        want = str(QT_KEYS.get(hkcode))
        print("   file                : %s" % tp)
        print("   keyboard key        : %s   %s"
              % (kb, "OK (%s)" % keyname(hkcode) if kb == want
                 else "-> expected %s for %s" % (want, keyname(hkcode))))
        print("   pad button          : %s   %s"
              % (joy, "OK (removed)" if joy in ("-1", None)
                 else "to remove: SDL index, breaks when the pad changes"))
        if kb != want or joy not in ("-1", None):
            print("   -> the daemon sets it by itself once melonDS is closed")

    print("\n-- melonDS")
    pid = find_pid(force=True)
    if not pid:
        print("   not running.")
        return
    try:
        mem = Mem(pid)
    except OSError as e:
        print("   pid=%d but /proc/%d/mem unreadable: %s" % (pid, pid, e))
        print("   -> ptrace_scope must be 0 (hostAccess.ptrace)")
        return
    span = module_span(pid)
    print("   pid=%d  module=0x%x" % (pid, span[0] if span else 0))
    print("   build               : %s" % (build_fingerprint(mem, *span) if span else "?"))
    print("   cached offsets      : %s" % (load_cache(build_fingerprint(mem, *span))
                                           if span else None))
    mem.close()
    try:
        tgt = Target(pid)
    except Exception as e:
        print("   cannot attach: %s" % e)
        return
    s, a = tgt.cfg()
    print("   config in memory    : ScreenSizing=%d  ScreenAspectTop=%d  (@0x%x, @0x%x)"
          % (s, a, tgt.toml_s, tgt.toml_a))
    if tgt.obj:
        st = tgt.panel_state()
        print("   ScreenPanel         : 0x%x   vtable+0x%x sizing+0x%x aspect+0x%x numscr+0x%x"
              % (tgt.obj, tgt.offs["vtable"], tgt.offs["sizing"],
                 tgt.offs["aspect"], tgt.offs["numscr"]))
        print("   displayed state     : sizing=%d aspect=%d numScreens=%d%s"
              % (st[0], st[1], st[2],
                 "" if st[2] == expected_numscreens(st[0]) else "   (inconsistent!)"))
    else:
        print("   ScreenPanel         : NOT FOUND  -> run --derive")

    print("\n   (the keyboard binding %s is set by the daemon itself,"
          % keyname(hkcode))
    print("    while melonDS is closed: see the binding section above.)")
    tgt.close()


def do_derive(recalc, hkcode):
    pid = find_pid(force=True)
    if not pid:
        print("melonDS is not running."); return
    tgt = Target(pid)
    emitter, eff = make_emitter(recalc, hkcode)
    if eff != "uinput":
        print("Without uinput I cannot trigger the recompute myself.")
        print("Run again with --recalc uinput (see --diag).")
        tgt.close(); return
    print("Deriving offsets for this build (the screen toggles twice)...")
    if derive(tgt, emitter) is None:
        print("  failed: melonDS did not recompute, or the class changed too much.")
        print("  First check that toggling itself works (--diag).")
    emitter.close()
    tgt.close()


def do_calibrate():
    pid = find_pid(force=True)
    if not pid:
        print("melonDS is not running."); return
    tgt = Target(pid)
    if tgt.obj is None:
        print("ScreenPanel object not found -> --derive first."); return
    print("\n  CALIBRATION (blob mode, fallback) - set through melonDS's MENU.")
    print("  Same session, window at game size, do not resize it.\n")

    def wait_state(want):
        shown = stable = None
        while True:
            if find_pid() != tgt.pid:
                raise RuntimeError("melonDS closed during calibration")
            cur = tgt.cfg()
            if cur != shown:
                shown = cur
                print("       (current sizing=%d aspect=%d - expected %d/%d)"
                      % (cur[0], cur[1], want[0], want[1]))
            if cur == want:
                if stable is None:
                    stable = time.time()
                elif time.time() - stable >= 0.4:
                    return
            else:
                stable = None
            time.sleep(0.1)

    try:
        print("  1/2  View -> Screen sizing = Even, Aspect ratio (top) = 4:3")
        wait_state((STATE_A["sizing"], STATE_A["aspect"]))
        A = tgt.capture()
        print("       capture A OK\n")
        print("  2/2  View -> Screen sizing = Top only, Aspect ratio (top) = 16:9")
        wait_state((STATE_B["sizing"], STATE_B["aspect"]))
        B = tgt.capture()
        print("       capture B OK")
    except (RuntimeError, OSError) as e:
        print("\n  !! %s -- nothing saved." % e); return
    if A["blob"] == B["blob"]:
        print("\n  !! A and B are identical. Start again."); return
    os.makedirs(os.path.dirname(CALIB_PATH), exist_ok=True)
    json.dump({"version": 2, "blob_lo": BLOB_LO, "blob_hi": BLOB_HI, "A": A, "B": B},
              open(CALIB_PATH, "w"), indent=1)
    print("\n  Calibration saved: %s" % CALIB_PATH)
    tgt.close()


# ---------- main -----------------------------------------------------
def keyarg(v):
    """Accepts "L3" / "r3" / "F" (see KEY_NAMES) or a numeric evdev code."""
    k = KEY_NAMES.get(v.strip().upper())
    if k is not None:
        return k
    try:
        return int(v, 0)
    except ValueError:
        raise argparse.ArgumentTypeError(
            "unknown key %r (names: %s, or an evdev code)" % (v, ", ".join(KEY_NAMES)))


def hkarg(v):
    k = UINPUT_KEYS.get(v.strip().upper())
    if k is not None:
        return k
    try:
        return int(v, 0)
    except ValueError:
        raise argparse.ArgumentTypeError(
            "unknown key %r (names: %s, or an evdev code)" % (v, ", ".join(UINPUT_KEYS)))


def main():
    global CALIB_PATH
    ap = argparse.ArgumentParser(description="melonDS layout toggle (memory, no resize)")
    ap.add_argument("--diag", "--scan", dest="diag", action="store_true",
                    help="full diagnosis (system, inputs, melonDS), then exit")
    ap.add_argument("--watch", action="store_true",
                    help="print raw input events from every device")
    ap.add_argument("--derive", action="store_true",
                    help="re-derive the memory offsets for this melonDS build")
    ap.add_argument("--calibrate", action="store_true", help="(blob mode) capture states A/B")
    ap.add_argument("--key", type=keyarg, action="append",
                    help="trigger button: L3 (default), R3, L1, R1, PS, F, or an evdev code")
    ap.add_argument("--mode", choices=("native", "blob"), default="native",
                    help="native (default): melonDS recomputes itself; "
                         "blob: replay a calibration")
    ap.add_argument("--recalc", choices=("auto", "uinput", "hotkey"), default="auto",
                    help="how to ask melonDS to recompute. uinput = synthetic keyboard "
                         "key, immune to pad changes (default when /dev/uinput is "
                         "accessible); hotkey = v1 behaviour")
    ap.add_argument("--hotkey-key", type=hkarg, default=HOTKEY_CODE, metavar="KEY",
                    help="keyboard key sent to melonDS (default F12)")
    ap.add_argument("--no-widescreen", action="store_true",
                    help="leave the widescreen cheat alone")
    ap.add_argument("--calib", metavar="FILE", help="calibration file path")
    a = ap.parse_args()

    if a.key:
        TRIGGER_KEYCODES.clear(); TRIGGER_KEYCODES.update(a.key)
    if a.calib:
        CALIB_PATH = os.path.expanduser(a.calib)

    if a.watch:     return do_watch()
    if a.diag:      return do_diag(a.hotkey_key)
    if a.derive:    return do_derive(a.recalc, a.hotkey_key)
    if a.calibrate: return do_calibrate()
    return do_daemon(a.mode, a.recalc, a.hotkey_key, not a.no_widescreen)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        pass
