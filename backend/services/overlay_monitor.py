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
import os
import sys
import time
import threading
import platform
from pathlib import Path

OS = platform.system()  # "Linux" | "Windows" | "Darwin"

# The rules about what a screen measurement has to look like to be believed
# live in `bezel_capture`, so the backend and this process cannot drift apart
# about them. Imported by path because this file is spawned as a script, not
# as part of the package — and guarded, because an import failure here must
# cost the measurement and not the overlay.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
try:
    from backend.services import bezel_capture as _measurement
except Exception as _e:                                       # pragma: no cover
    print(f"[overlay-monitor] no capture support: {_e}", file=sys.stderr)
    _measurement = None

# On Wayland sessions, X11 window detection won't work unless the app runs under XWayland.
# The overlay feature is fully functional on X11/kiosk environments (openbox, etc.).
_WAYLAND_SESSION = OS == "Linux" and bool(os.environ.get("WAYLAND_DISPLAY"))

# ── Platform imports ──────────────────────────────────────────────────────────
if OS == "Linux":
    try:
        from Xlib import display as xdisplay, X, protocol
        _XLIB_OK = True
    except ImportError:
        _XLIB_OK = False

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
            except Exception as e:
                print(f"[overlay-monitor] dump_windows: {e}", file=sys.stderr)
        return out

    def force_rect(self, wid: int, x: int, y: int, w: int, h: int) -> None:
        win = self._display.create_resource_object("window", wid)
        # Leave fullscreen the way EWMH asks a client to: a ClientMessage on
        # the root. The old path wrote _NET_WM_STATE onto the window itself,
        # which does drop fullscreen on KWin — but only by clearing every
        # state at once, _NET_WM_STATE_ABOVE included, and it leaves the WM's
        # own bookkeeping out of step (further state requests on that window
        # are then ignored). Nothing obliges a WM to honour a direct write at
        # all, the property belonging to the WM once the window is mapped.
        net_wm_state      = self._display.intern_atom("_NET_WM_STATE")
        net_wm_fullscreen = self._display.intern_atom("_NET_WM_STATE_FULLSCREEN")
        self._root.send_event(
            protocol.event.ClientMessage(
                window=win, client_type=net_wm_state,
                #     0 = _NET_WM_STATE_REMOVE, then the state to drop,
                #     0 = no second state, 1 = request comes from an application
                data=(32, [0, net_wm_fullscreen, 0, 1, 0]),
            ),
            event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask,
        )
        self._display.sync()
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

    def capture(self, wid: int, w: int, h: int) -> tuple[bytes, int] | None:
        """(raw pixels, bytes per row) of the window's current contents.

        Read in horizontal bands rather than in one call: a 1920x1080 window
        is about 8 MB, and an X reply that large exceeds what some servers will
        return in a single GetImage — the request fails outright rather than
        being split for us. Bands also mean a failure late in the read costs
        the bands already gathered and nothing more.
        """
        try:
            win = self._display.create_resource_object("window", wid)
            rows_per_band = max(1, 262144 // max(1, w * 4))
            data = bytearray()
            y = 0
            while y < h:
                band = min(rows_per_band, h - y)
                img = win.get_image(0, y, w, band, X.ZPixmap, 0xFFFFFFFF)
                raw = img.data
                if isinstance(raw, str):          # python-xlib < 0.30
                    raw = raw.encode("latin-1")
                data += raw
                y += band
            if not data:
                return None
            # Derived, not assumed: the depth-32 visual an emulator gets is not
            # guaranteed, and a stride computed from the wrong one measures a
            # skewed picture rather than failing.
            return bytes(data), len(data) // h
        except Exception as e:
            print(f"[overlay-monitor] capture: {e}", file=sys.stderr)
            return None


# ── Monitor logic ─────────────────────────────────────────────────────────────
class OverlayMonitor:
    def __init__(self):
        self._stop   = threading.Event()
        self._thread: threading.Thread | None = None

        if _WAYLAND_SESSION:
            self._mgr = None  # overlay unsupported on Wayland-native sessions
        elif OS == "Linux" and _XLIB_OK:
            self._mgr = X11Manager()
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
            if _WAYLAND_SESSION:
                # Silently skip on Wayland — overlay works on X11/kiosk sessions only
                emit({"event": "window:closed", "system_id": system_id,
                      "reason": "wayland-unsupported"})
            else:
                emit_error(f"Window manager unavailable on {OS}")
            return

        rect    = cfg["window_rect"]
        timeout = cfg.get("watch_timeout_s", 30)
        classes = cfg["wm_class"].get("linux", [])

        emit({"event": "window:waiting", "system_id": system_id})

        # Give the Flatpak process time to start before we begin polling
        time.sleep(2)

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
            except Exception as e:
                print(f"[overlay-monitor] dump on timeout: {e}", file=sys.stderr)
            emit({"event": "window:closed", "system_id": system_id,
                  "reason": "timeout"})
            return

        # ── Force position and decorations ────────────────────────────────────
        # Give emulator 0.5s to finish drawing before we force the rect
        time.sleep(0.5)
        try:
            before = self._mgr.get_rect(wid)
            emit({"event": "debug", "msg": f"before force_rect: {before}"})
            self._mgr.force_rect(wid, rect["x"], rect["y"], rect["w"], rect["h"])
            time.sleep(0.2)
            after = self._mgr.get_rect(wid)
            emit({"event": "debug", "msg": f"after force_rect: {after}"})
        except Exception as e:
            emit_error(f"force_rect failed: {e}")

        # Send the hole dimensions (game display area), not the window rect.
        # The overlay uses this to punch the transparent hole at the right position.
        hole = cfg.get("hole", rect)
        emit({"event": "window:ready", "system_id": system_id,
              "rect": {"x": hole["x"], "y": hole["y"],
                       "w": hole["w"], "h": hole["h"]}})

        # ── Does the emulator draw where the hole says it does? ───────────────
        # Only when the backend asked: once an answer is cached for this
        # system and ratio there is nothing left to learn, and reading 8 MB
        # off the X server twice per launch for it would be pure cost.
        if cfg.get("measure"):
            self._measure(system_id, wid, rect, cfg.get("announced") or hole)

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
            except Exception as e:
                print(f"[overlay-monitor] maintenance loop: {e}", file=sys.stderr)

            time.sleep(0.1)

    # ── Capture ──────────────────────────────────────────────────────────────

    def _measure(self, system_id: str, wid: int, rect: dict, announced: dict) -> None:
        """Two samples of what is really on screen, reported if they agree.

        Runs after `window:ready`, so the overlay is already up and nothing
        here is in front of the player. Every failure path is silent for the
        same reason: a capture that does not work must cost a log line, never
        a launch.

        Two samples because a second into a game is very often a loading
        screen — see `bezel_capture`, which owns every rule about what a
        measurement has to look like to be believed. This function only holds
        the X11 half, which is the half that cannot be tested without a screen.
        """
        if _measurement is None:
            return
        try:
            samples = []
            for delay in (1.0, 2.5):
                if self._stop.wait(delay):
                    return                        # game already over
                if not self._mgr.window_exists(wid):
                    return
                shot = self._mgr.capture(wid, rect["w"], rect["h"])
                if not shot:
                    return
                pixels, stride = shot
                samples.append(_measurement.content_bbox(
                    pixels, rect["w"], rect["h"], stride))

            box = _measurement.agree(*samples)
            if box is None:
                emit({"event": "debug",
                      "msg": f"measure: samples disagree — {samples}"})
                return
            if not _measurement.is_plausible(box, rect["w"], rect["h"]):
                emit({"event": "debug", "msg": f"measure: implausible — {box}"})
                return

            x, y, w, h = box
            emit({"event": "window:measured", "system_id": system_id,
                  "announced": announced, "window": {"w": rect["w"], "h": rect["h"]},
                  "measured": {"x": x, "y": y, "w": w, "h": h}})
        except Exception as e:
            print(f"[overlay-monitor] measure: {e}", file=sys.stderr)


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
