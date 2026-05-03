"""
Overlay monitor — spawned by Electron main process.

Protocol (stdio JSON-lines):
  stdin  ← {"cmd": "watch",  "system_id": "dolphin", "config": {...}}
  stdin  ← {"cmd": "stop"}
  stdout → {"event": "window:ready",  "system_id": "...", "rect": {x,y,w,h}}
  stdout → {"event": "window:waiting","system_id": "..."}
  stdout → {"event": "window:closed", "system_id": "..."}
  stdout → {"event": "error",         "message": "..."}
"""
import json
import sys
import time
import threading
import platform

OS = platform.system()  # "Linux" | "Windows" | "Darwin"

# ── Platform imports ──────────────────────────────────────────────────────────
if OS == "Linux":
    try:
        from Xlib import display as xdisplay, X, Xatom
        _XLIB_OK = True
    except ImportError:
        _XLIB_OK = False

elif OS == "Windows":
    try:
        import win32gui
        import win32con
        import win32process
        _WIN32_OK = True
    except ImportError:
        _WIN32_OK = False


# ── Output helpers ────────────────────────────────────────────────────────────
def emit(obj: dict) -> None:
    print(json.dumps(obj), flush=True)


def emit_error(msg: str) -> None:
    emit({"event": "error", "message": msg})


# ── Linux / X11 ───────────────────────────────────────────────────────────────
class X11Manager:
    def __init__(self):
        self._display = xdisplay.Display()
        self._screen  = self._display.screen()
        self._root    = self._screen.root

    def _client_windows(self):
        """Yield top-level client windows via _NET_CLIENT_LIST (EWMH).
        Falls back to recursive scan if the atom is unavailable."""
        atom = self._display.intern_atom('_NET_CLIENT_LIST')
        prop = self._root.get_full_property(atom, 0)
        if prop and prop.value:
            for wid in prop.value:
                try:
                    yield self._display.create_resource_object('window', wid)
                except Exception:
                    pass
            return
        # Fallback: recursive scan
        def _recurse(win):
            yield win
            try:
                for child in win.query_tree().children:
                    yield from _recurse(child)
            except Exception:
                pass
        yield from _recurse(self._root)

    def find_window(self, wm_classes: list[str]) -> int | None:
        """Return window id matching any of the given WM_CLASS names."""
        targets = {c.lower() for c in wm_classes}
        for win in self._client_windows():
            try:
                cls = win.get_wm_class()
                if cls and any(c.lower() in targets for c in cls):
                    return win.id
            except Exception:
                continue
        return None

    def dump_windows(self) -> list[dict]:
        """Debug helper — return WM_CLASS of all client windows."""
        out = []
        for win in self._client_windows():
            try:
                cls  = win.get_wm_class()
                name = win.get_wm_name()
                if cls:
                    out.append({"wm_class": list(cls), "title": name, "id": win.id})
            except Exception:
                pass
        return out

    def force_rect(self, wid: int, x: int, y: int, w: int, h: int) -> None:
        win = self._display.create_resource_object("window", wid)
        # Remove fullscreen state
        net_wm_state      = self._display.intern_atom("_NET_WM_STATE")
        net_wm_fullscreen = self._display.intern_atom("_NET_WM_STATE_FULLSCREEN")
        win.change_property(net_wm_state, Xatom.ATOM, 32, [])
        # Remove window decorations via Motif hints
        motif_atom = self._display.intern_atom("_MOTIF_WM_HINTS")
        win.change_property(motif_atom, motif_atom, 32, [2, 0, 0, 0, 0])
        # Move and resize
        win.configure(x=x, y=y, width=w, height=h)
        self._display.sync()

    def get_rect(self, wid: int) -> dict:
        win  = self._display.create_resource_object("window", wid)
        geom = win.get_geometry()
        # Translate to root coordinates
        translated = win.translate_coords(self._root, geom.x, geom.y)
        return {"x": translated.x, "y": translated.y,
                "w": geom.width,   "h": geom.height}

    def window_exists(self, wid: int) -> bool:
        try:
            win = self._display.create_resource_object("window", wid)
            win.get_geometry()
            return True
        except Exception:
            return False


# ── Windows / Win32 ───────────────────────────────────────────────────────────
class Win32Manager:
    def find_window(self, wm_classes: list[str]) -> int | None:
        """Return HWND matching any of the given window class names."""
        targets = {c.lower() for c in wm_classes}
        result  = []

        def _cb(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                cls = win32gui.GetClassName(hwnd).lower()
                if cls in targets or any(t in cls for t in targets):
                    result.append(hwnd)
            return True

        win32gui.EnumWindows(_cb, None)
        return result[0] if result else None

    def force_rect(self, hwnd: int, x: int, y: int, w: int, h: int) -> None:
        # Remove title bar and borders
        style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
        style &= ~(win32con.WS_CAPTION | win32con.WS_THICKFRAME |
                   win32con.WS_MINIMIZEBOX | win32con.WS_MAXIMIZEBOX |
                   win32con.WS_SYSMENU)
        win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)
        # Move + resize + force on top
        win32gui.SetWindowPos(
            hwnd, win32con.HWND_TOP,
            x, y, w, h,
            win32con.SWP_SHOWWINDOW | win32con.SWP_FRAMECHANGED
        )

    def get_rect(self, hwnd: int) -> dict:
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        return {"x": left, "y": top, "w": right - left, "h": bottom - top}

    def window_exists(self, hwnd: int) -> bool:
        return win32gui.IsWindow(hwnd)


# ── Monitor logic ─────────────────────────────────────────────────────────────
class OverlayMonitor:
    def __init__(self):
        self._stop   = threading.Event()
        self._thread: threading.Thread | None = None

        if OS == "Linux" and _XLIB_OK:
            self._mgr = X11Manager()
        elif OS == "Windows" and _WIN32_OK:
            self._mgr = Win32Manager()
        else:
            self._mgr = None

    def watch(self, system_id: str, cfg: dict) -> None:
        """Start watching in a background thread."""
        if self._thread and self._thread.is_alive():
            self.stop()

        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, args=(system_id, cfg), daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        self._thread = None

    def _run(self, system_id: str, cfg: dict) -> None:
        if not self._mgr:
            emit_error(f"Window manager unavailable on {OS}")
            return

        rect    = cfg["window_rect"]
        timeout = cfg.get("watch_timeout_s", 30)
        classes = cfg["wm_class"].get("windows" if OS == "Windows" else "linux", [])

        emit({"event": "window:waiting", "system_id": system_id})

        # ── Wait for window to appear ─────────────────────────────────────────
        wid     = None
        deadline = time.time() + timeout
        while not self._stop.is_set() and time.time() < deadline:
            wid = self._mgr.find_window(classes)
            if wid:
                break
            time.sleep(0.5)

        if not wid:
            # Dump visible windows to help diagnose wrong WM_CLASS
            try:
                visible = self._mgr.dump_windows()
                emit({"event": "error",
                      "message": f"timeout — visible windows: {visible}"})
            except Exception:
                pass
            emit({"event": "window:closed", "system_id": system_id,
                  "reason": "timeout"})
            return

        # ── Force position and decorations ────────────────────────────────────
        # Give emulator 0.5s to finish drawing before we force the rect
        time.sleep(0.5)
        try:
            self._mgr.force_rect(wid, rect["x"], rect["y"], rect["w"], rect["h"])
        except Exception as e:
            emit_error(f"force_rect failed: {e}")

        emit({"event": "window:ready", "system_id": system_id,
              "rect": {"x": rect["x"], "y": rect["y"],
                       "w": rect["w"], "h": rect["h"]}})

        # ── Maintenance loop — reforce if window moves/resizes ────────────────
        while not self._stop.is_set():
            if not self._mgr.window_exists(wid):
                emit({"event": "window:closed", "system_id": system_id})
                return

            try:
                current = self._mgr.get_rect(wid)
                if (current["x"] != rect["x"] or current["y"] != rect["y"] or
                        current["w"] != rect["w"] or current["h"] != rect["h"]):
                    self._mgr.force_rect(
                        wid, rect["x"], rect["y"], rect["w"], rect["h"]
                    )
            except Exception:
                pass

            time.sleep(0.1)


# ── Main stdin loop ───────────────────────────────────────────────────────────
def main():
    monitor = OverlayMonitor()

    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            continue

        cmd = msg.get("cmd")
        if cmd == "watch":
            monitor.watch(msg["system_id"], msg["config"])
        elif cmd == "stop":
            monitor.stop()
            emit({"event": "window:closed", "system_id": msg.get("system_id", "")})
        elif cmd == "quit":
            monitor.stop()
            break

    monitor.stop()


if __name__ == "__main__":
    main()
