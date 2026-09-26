"""Reading and writing melonDS's memory: config nodes, ScreenPanel, cheat flag.

How things are found, cheapest first, so a melonDS update does not break it:
  · toml config nodes: by the text signature "ScreenSizing\\0" (toml11 stores
    the int64 value at key+0x18) — independent of the melonDS build;
  · the ScreenPanel object: offsets cached per build, else the melonDS 1.1
    hints, else any aligned qword pointing into the module. A candidate must
    satisfy obj.sizing == config.sizing, obj.aspect == config.aspect and
    obj.numScreens == expected_numscreens(sizing);
  · if the class itself moved, `--derive` finds the offsets by an A/B diff.
The panel is only used to VERIFY a toggle; without it the toggle still works.
"""

import hashlib
import json
import os
import re
import struct
import time

from melonds_common import (BLOB_HI, BLOB_LO, CACHE_PATH, CHEAT_NAME, HINT,
                            OFF_ENABLED, OFF_NAME, SSO_OFF, expected_numscreens,
                            log)
from melonds_config import is_melonds_binary

MAP_RE = re.compile(r"^([0-9a-f]+)-([0-9a-f]+) (\S{4}) \S+ \S+ \S+\s*(.*?)\s*$")


def regions(pid):
    out = []
    for ln in open("/proc/%d/maps" % pid):
        m = MAP_RE.match(ln)
        if m:
            out.append({"lo": int(m.group(1), 16), "hi": int(m.group(2), 16),
                        "perms": m.group(3), "path": m.group(4)})
    return out


def module_span(pid, regs=None):
    """(base, lo, hi) of the melonDS binary's mappings — /app/bin (Flatpak) or
    /usr/bin (native). None when absent."""
    regs = regs if regs is not None else regions(pid)
    hits = [r for r in regs if is_melonds_binary(r["path"])]
    if not hits:
        return None
    lo = min(r["lo"] for r in hits)
    return lo, lo, max(r["hi"] for r in hits)


def scan_regions(pid, regs=None):
    """rw- regions to search for objects. Skips the 128 MB rwx region
    (emulated DS RAM + JIT): nothing for us and expensive to read."""
    regs = regs if regs is not None else regions(pid)
    out = [r for r in regs
           if r["perms"].startswith("rw") and "x" not in r["perms"]
           and (r["hi"] - r["lo"]) <= (256 << 20)]
    out.sort(key=lambda r: (r["path"] != "[heap]", r["lo"]))   # heap first
    return out


def build_fingerprint(mem, base, lo, hi):
    """Identify the melonDS build without its file path (unreachable from the
    host for a Flatpak): hash of the first mapped bytes + module size."""
    head = mem.rd_soft(base, min(1 << 20, hi - lo))
    if head is None:
        return None
    return "%s-%x" % (hashlib.sha256(head).hexdigest()[:16], hi - lo)


class Mem:
    def __init__(self, pid):
        self.f = open("/proc/%d/mem" % pid, "r+b", 0)

    def close(self):
        try: self.f.close()
        except OSError: pass

    def rd(self, a, n):
        self.f.seek(a)
        b = self.f.read(n)
        if b is None or len(b) != n:
            # /proc/<pid>/mem of a dead process returns 0 bytes without raising
            raise OSError("short read at 0x%x (%d/%d bytes) - melonDS closed?"
                          % (a, 0 if b is None else len(b), n))
        return b

    def rd_soft(self, a, n):
        """Best-effort read: None when the range is unreadable."""
        try:
            self.f.seek(a)
            b = self.f.read(n)
        except OSError:
            return None
        return b if b is not None and len(b) == n else None

    def wr(self, a, b):
        self.f.seek(a); self.f.write(b)

    def ri32(self, a): return struct.unpack("<i", self.rd(a, 4))[0]
    def ri64(self, a): return struct.unpack("<q", self.rd(a, 8))[0]
    def wi32(self, a, v): self.wr(a, struct.pack("<i", int(v)))
    def wi64(self, a, v): self.wr(a, struct.pack("<q", int(v)))


def find_toml_nodes(mem, regs, key, vmax):
    """Every plausible address of the int64 value of toml node `key`.
    The .toml text buffer also holds the string, but with ASCII at +0x18 —
    rejected by 0 <= v <= vmax."""
    needle = key.encode() + b"\x00"
    found = []
    for r in regs:
        data = mem.rd_soft(r["lo"], r["hi"] - r["lo"])
        if data is None:
            continue
        i = data.find(needle)
        while i != -1:
            if i + 0x20 <= len(data):
                v = struct.unpack_from("<q", data, i + 0x18)[0]
                if 0 <= v <= vmax:
                    found.append(r["lo"] + i + 0x18)
            i = data.find(needle, i + 1)
    return found


def find_cheat_flags(mem, regs, name):
    """Address of the `Enabled` bool of every copy of cheat `name`.

    Found by NAME, like the toml nodes. Under 16 chars libstdc++ stores it in
    the object (SSO), so the ARCode starts at (string - 0x18) — verified, not
    assumed: the string's data pointer must point at its own buffer and its
    size must match. Normally TWO copies (ARCodeFile and the one AREngine
    runs); all are kept.
    """
    needle = name.encode() + b"\x00"
    out = []
    for r in regs:
        data = mem.rd_soft(r["lo"], r["hi"] - r["lo"])
        if data is None:
            continue
        i = data.find(needle)
        while i != -1:
            chars = r["lo"] + i
            obj = chars - (OFF_NAME + SSO_OFF)
            try:
                if (mem.ri64(obj + OFF_NAME) == chars
                        and mem.ri64(obj + OFF_NAME + 8) == len(name)
                        and mem.rd(obj + OFF_ENABLED, 1)[0] in (0, 1)):
                    out.append(obj + OFF_ENABLED)
            except OSError:
                pass
            i = data.find(needle, i + 1)
    return out


def _check_obj(buf, off, offs, cfg_s, cfg_a):
    """buf/off = buffer holding the object at offset off."""
    try:
        s = struct.unpack_from("<i", buf, off + offs["sizing"])[0]
        a = struct.unpack_from("<i", buf, off + offs["aspect"])[0]
        n = struct.unpack_from("<i", buf, off + offs["numscr"])[0]
    except struct.error:
        return False
    return s == cfg_s and a == cfg_a and n == expected_numscreens(s)


def scan_panel(mem, pid, span, cfg_s, cfg_a, offs, vtable_off=None):
    """(object address, vtable_off) or (None, None).

    Known vtable_off → search that exact pointer (fast). Unknown → every
    aligned qword pointing into the module is a candidate; the invariants sort
    them out.
    """
    base, mlo, mhi = span
    need = struct.pack("<Q", base + vtable_off) if vtable_off is not None else None
    max_off = max(offs[k] for k in ("sizing", "aspect", "numscr")) + 4

    for r in scan_regions(pid):
        data = mem.rd_soft(r["lo"], r["hi"] - r["lo"])
        if data is None:
            continue
        if need is not None:
            i = data.find(need)
            while i != -1:
                if i % 8 == 0 and i + max_off <= len(data) and \
                   _check_obj(data, i, offs, cfg_s, cfg_a):
                    return r["lo"] + i, vtable_off
                i = data.find(need, i + 1)
            continue
        end = len(data) - max_off
        for i in range(0, max(0, end), 8):
            p = struct.unpack_from("<Q", data, i)[0]
            if mlo <= p < mhi and _check_obj(data, i, offs, cfg_s, cfg_a):
                return r["lo"] + i, p - base
    return None, None


def load_cache(fp):
    if not fp:
        return None
    try:
        return json.load(open(CACHE_PATH)).get(fp)
    except (OSError, ValueError):
        return None


def save_cache(fp, offs):
    if not fp:
        return
    try:
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        try:
            all_ = json.load(open(CACHE_PATH))
        except (OSError, ValueError):
            all_ = {}
        all_[fp] = offs
        json.dump(all_, open(CACHE_PATH, "w"), indent=1)
    except OSError:
        pass


class Target:
    """A session attached to one melonDS process."""

    def __init__(self, pid):
        self.pid  = pid
        self.mem  = Mem(pid)
        self.obj  = None
        self.offs = dict(HINT)
        span = module_span(pid)
        if span is None:
            raise RuntimeError("melonDS module missing from /proc/%d/maps" % pid)
        self.span = span
        self.fp   = build_fingerprint(self.mem, *span)

        self.toml_s = self.toml_a = None
        self.toml_s_all = self.toml_a_all = []
        self.cheat_flags, self.cheat_scan = [], 0.0
        if not self.locate_toml():
            raise RuntimeError("config nodes ScreenSizing/ScreenAspectTop "
                               "not found (melonDS not initialised yet?)")
        self.locate_panel()

        log("attached pid=%d module=0x%x panel=%s toml=%dx sizing/%dx aspect build=%s"
            % (pid, span[0], hex(self.obj) if self.obj else "not-found",
               len(self.toml_s_all), len(self.toml_a_all), self.fp or "?"))
        if self.obj is None:
            log("   panel not found -> toggling without verification.")
            log("   (melonDS may have been updated: '--derive' finds it)")

    # --- config: what melonDS re-reads, so the source of truth --------------
    def locate_toml(self):
        """Keep EVERY candidate, not just the first.

        "ScreenSizing\\0" matches several times in the heap: the live
        [Instance0.Window0] node plus dead copies. Measured on the box: 3
        candidates, ONE re-read by melonDS, in heap-dependent order — so all
        are written and stay in phase.
        """
        regs = scan_regions(self.pid)
        self.toml_s_all = find_toml_nodes(self.mem, regs, "ScreenSizing", 5)
        self.toml_a_all = find_toml_nodes(self.mem, regs, "ScreenAspectTop", 4)
        self.toml_s = self.toml_s_all[0] if self.toml_s_all else None
        self.toml_a = self.toml_a_all[0] if self.toml_a_all else None
        return self.toml_s is not None and self.toml_a is not None

    # --- widescreen cheat (optional: absent for most games) ----------------
    def locate_cheat(self):
        """ARCodes exist only once the ROM is loaded, well after attach:
        searched on demand, rate-limited."""
        self.cheat_flags = find_cheat_flags(self.mem, scan_regions(self.pid), CHEAT_NAME)
        self.cheat_scan = time.time()
        return bool(self.cheat_flags)

    def cheat_ready(self, retry_s=30.0):
        if self.cheat_flags:
            try:                                    # still valid?
                self.mem.rd(self.cheat_flags[0], 1)
                return True
            except OSError:
                self.cheat_flags = []
        if time.time() - self.cheat_scan < retry_s:
            return False
        return self.locate_cheat()

    def set_cheat(self, on):
        """Write the flag in EVERY copy. Returns how many were written."""
        n = 0
        for a in self.cheat_flags:
            try:
                self.mem.wr(a, b"\x01" if on else b"\x00")
                n += 1
            except OSError:
                pass
        return n

    def refresh(self):
        """Re-locate config nodes AND panel.

        The LIVE config node and the ScreenPanel are created late, with the
        window (`ScreenPanel::loadConfig()` materialises the node). Attaching a
        second after launch only sees DEAD nodes; symptom: the toggle is
        announced, nothing moves, and it is '(unverified)'. So while the panel
        is missing, rescan.
        """
        self.locate_toml()
        return self.locate_panel()

    def cfg(self):
        """Current state. The panel wins (it is what is DISPLAYED); config
        nodes are the fallback when it is missing."""
        if self.obj is not None:
            st = self.panel_state()
            if st is not None:
                return st[0], st[1]
        return self.mem.ri64(self.toml_s), self.mem.ri64(self.toml_a)

    def write_cfg(self, sizing, aspect):
        wrote = 0
        for nodes, val, vmax in ((self.toml_s_all, sizing, 5),
                                 (self.toml_a_all, aspect, 4)):
            for n in nodes:
                try:
                    if 0 <= self.mem.ri64(n) <= vmax:   # still a plausible enum
                        self.mem.wi64(n, val)
                        wrote += 1
                except OSError:
                    pass
        if not wrote:
            raise RuntimeError("config nodes invalid -> re-locating")

    # --- ScreenPanel object: optional, used to verify ----------------------
    def locate_panel(self):
        # Candidate nodes may hold different values (dead ones included): try
        # each distinct pair, or one bad candidate fails the whole search.
        pairs, seen = [], set()
        for ns in (self.toml_s_all or [None]):
            for na in (self.toml_a_all or [None]):
                try:
                    v = (self.mem.ri64(ns), self.mem.ri64(na))
                except (OSError, TypeError):
                    continue
                if v not in seen:
                    seen.add(v); pairs.append(v)
        if not pairs:
            pairs = [(0, 0)]
        cached = load_cache(self.fp)
        tries = []
        if cached:
            tries.append((dict(cached), cached.get("vtable")))
        tries.append((dict(HINT), HINT["vtable"]))     # melonDS 1.1 hint
        tries.append((dict(HINT), None))               # same class, other build
        for offs, vt in tries:
            obj = vtable = None
            for cfg_s, cfg_a in pairs:
                obj, vtable = scan_panel(self.mem, self.pid, self.span,
                                         cfg_s, cfg_a, offs, vt)
                if obj is not None:
                    break
            if obj is not None:
                self.obj = obj
                self.offs = dict(offs)
                self.offs["vtable"] = vtable
                if not cached or cached.get("vtable") != vtable:
                    save_cache(self.fp, self.offs)
                return True
        self.obj = None
        return False

    def panel_state(self):
        if self.obj is None:
            return None
        try:
            return (self.mem.ri32(self.obj + self.offs["sizing"]),
                    self.mem.ri32(self.obj + self.offs["aspect"]),
                    self.mem.ri32(self.obj + self.offs["numscr"]))
        except OSError:
            return None

    def numscr(self):
        st = self.panel_state()
        return st[2] if st else -1

    # --- blob mode (fallback) ------------------------------------------------
    def capture(self):
        s, a = self.cfg()
        return {"blob": self.mem.rd(self.obj + BLOB_LO, BLOB_HI - BLOB_LO).hex(),
                "numscreens": self.numscr(), "sizing": s, "aspect": a}

    def restore(self, snap):
        st = self.panel_state()
        if st is None or not (0 <= st[0] <= 5 and 0 <= st[1] <= 4 and 1 <= st[2] <= 4):
            raise RuntimeError("implausible panel state -> refusing to write")
        self.mem.wr(self.obj + BLOB_LO, bytes.fromhex(snap["blob"]))
        self.mem.wi32(self.obj + self.offs["numscr"], snap["numscreens"])
        self.write_cfg(snap["sizing"], snap["aspect"])

    def close(self):
        self.mem.close()
