"""One mouse per player during melonDS local multiplayer.

Mice are only watched until a second one is really used: one mouse keeps
the plain shared X pointer. From then on, each mouse belongs to the player
it was first used for (first used = player 1), is grabbed away from X,
moves that player's own arrow inside that player's column, and its left
button touches through that player's virtual touchscreen.

Why touch and not clicks: every melonDS instance lives in one Qt process,
and Qt sends all mouse motion to the window a button went down in, whatever
the device. Two players dragging at once then drew on one DS (measured on
the box). Touch points from separate devices stay separate.

    mouse_touch.py --cleanup-after PID    park the arrows once PID is gone
"""
from __future__ import annotations

import logging
import select
import time

import inputdev
import windows
from arrows import Arrows

log = logging.getLogger("melonds-multiplayer")

# Screen pixels per mouse count, constant like X's "flat" profile (the box's
# own setting). Calibration knob.
MOUSE_GAIN = 1.0
# Arrows are windows the compositor redraws: moved once per frame at most,
# raised above the game once a second.
FRAME_SECONDS = 1 / 60
RAISE_SECONDS = 1.0
# Counts of movement (or one click) before a mouse is taken as used: a
# keyboard's built-in pointer node never moves, and a desk bump stays under.
ACTIVITY_THRESHOLD = 40
RESCAN_SECONDS = 3.0


class Pointer:
    """One player's arrow, kept inside that player's column."""

    def __init__(self, rect: tuple[int, int, int, int], gain: float = MOUSE_GAIN):
        self.left, self.top, self.width, self.height = rect
        self.x = self.left + self.width / 2
        self.y = self.top + self.height / 2
        self.gain = gain
        self.pressed = False
        self._dx = self._dy = 0

    @property
    def position(self) -> tuple[int, int]:
        return int(self.x), int(self.y)

    def feed(self, events: list[tuple[int, int, int]]) -> list[tuple]:
        """evdev events → [("move", x, y) | ("down", x, y) | ("drag", x, y) | ("up",)]."""
        actions: list[tuple] = []
        for kind, code, value in events:
            if kind == inputdev.EV_REL and code == inputdev.REL_X:
                self._dx += value
            elif kind == inputdev.EV_REL and code == inputdev.REL_Y:
                self._dy += value
            elif kind == inputdev.EV_KEY and code == inputdev.BTN_LEFT and value in (0, 1):
                actions += self._flush_motion()
                if value and not self.pressed:
                    actions.append(("down", *self.position))
                elif not value and self.pressed:
                    actions.append(("up",))
                self.pressed = bool(value)
            elif kind == inputdev.EV_SYN:
                actions += self._flush_motion()
        return actions

    def _flush_motion(self) -> list[tuple]:
        if not (self._dx or self._dy):
            return []
        self.x = min(max(self.x + self._dx * self.gain, self.left), self.left + self.width - 1)
        self.y = min(max(self.y + self._dy * self.gain, self.top), self.top + self.height - 1)
        self._dx = self._dy = 0
        moved = [("move", *self.position)]
        return moved + ([("drag", *self.position)] if self.pressed else [])


def activity(events: list[tuple[int, int, int]]) -> int:
    """How much these events count toward a mouse being used."""
    total = 0
    for kind, code, value in events:
        if kind == inputdev.EV_REL and code in (inputdev.REL_X, inputdev.REL_Y):
            total += abs(value)
        elif kind == inputdev.EV_KEY and code == inputdev.BTN_LEFT and value == 1:
            total += ACTIVITY_THRESHOLD
    return total


class Assigner:
    """Mouse → player, in the order mice are first really used."""

    def __init__(self, players: int):
        self.players = players
        self.owner: dict[str, int] = {}
        self._score: dict[str, int] = {}

    def note(self, path: str, events: list[tuple[int, int, int]]) -> int | None:
        """Count activity; returns the player `path` was just given, if any."""
        if path in self.owner:
            return None
        self._score[path] = self._score.get(path, 0) + activity(events)
        free = [p for p in range(1, self.players + 1) if p not in self.owner.values()]
        if self._score[path] >= ACTIVITY_THRESHOLD and free:
            self.owner[path] = free[0]
            return free[0]
        return None

    def release(self, path: str) -> int | None:
        """A mouse was unplugged: its player waits for the next mouse used."""
        self._score.pop(path, None)
        return self.owner.pop(path, None)

    @property
    def routed(self) -> bool:
        return len(self.owner) >= 2


class MouseRouter:
    """The loop: watch mice, switch to one arrow per player, route events."""

    def __init__(self, players: int):
        self.players = players
        self.assigner = Assigner(players)
        self.mice: dict[str, inputdev.Mouse] = {}
        self.pointers: dict[int, Pointer] = {}
        self.touches: dict[int, inputdev.Touchscreen] = {}
        self.x11 = self.arrows = None
        self.routed = False
        self._last_scan = 0.0
        self._arrow_due: dict[int, tuple[int, int]] = {}
        self._last_frame = self._last_raise = 0.0
        # X's arrow is left where a touch ended: send it back to the corner,
        # checked until it is there (the touch's own motion may land after).
        self._park_due = False

    def run(self, keep_going) -> None:
        self.x11 = windows.X11()
        self.arrows = Arrows(self.x11)
        try:
            while keep_going():
                self._rescan()
                wait = FRAME_SECONDS if self._arrow_due or self._park_due else 0.5
                ready, _, _ = select.select(list(self.mice.values()), [], [], wait)
                for mouse in ready:
                    self._handle(mouse)
                self._draw_arrows()
                self._park_pointer()
        finally:
            self.close()

    def _rescan(self) -> None:
        if time.monotonic() - self._last_scan < RESCAN_SECONDS:
            return
        self._last_scan = time.monotonic()
        for _number, path, name in inputdev.find_mice():
            if path not in self.mice:
                try:
                    self.mice[path] = inputdev.Mouse(path, name)
                except OSError:
                    continue
                if self.routed:                   # a new mouse never reaches X
                    self._grab(self.mice[path])

    def _handle(self, mouse: inputdev.Mouse) -> None:
        try:
            events = mouse.read()
        except OSError:
            self._drop(mouse)
            return
        player = self.assigner.note(mouse.path, events)
        if player is not None:
            log.info("mouse %s (%s) is player %d's", mouse.path, mouse.name, player)
            if self.assigner.routed or self.routed:
                self._route_all()
            return
        owner = self.assigner.owner.get(mouse.path)
        if owner in self.pointers:
            self._apply(owner, self.pointers[owner].feed(events))

    def _draw_arrows(self) -> None:
        """Move each arrow to its latest position, at most once per frame."""
        now = time.monotonic()
        if not self._arrow_due or now - self._last_frame < FRAME_SECONDS:
            return
        for player, (x, y) in self._arrow_due.items():
            self.arrows.move(player, x, y)
        if now - self._last_raise >= RAISE_SECONDS:
            self.arrows.raise_all()
            self._last_raise = now
        self.arrows.flush()
        self._arrow_due.clear()
        self._last_frame = now

    def _apply(self, player: int, actions: list[tuple]) -> None:
        touch = self.touches[player]
        for action in actions:
            if action[0] == "move":
                self._arrow_due[player] = (action[1], action[2])
            elif action[0] == "down":
                touch.down(0, action[1], action[2])
            elif action[0] == "drag":
                touch.move(0, action[1], action[2])
            elif action[0] == "up":
                touch.up(0)
                self._park_due = True

    def _route_all(self) -> None:
        """Second mouse used: every mouse leaves X, every owner gets an arrow."""
        screen = self.x11.screen_size()
        if not self.routed:
            log.info("one arrow per player from now on")
            self.routed = True
            self._park_due = True
        for mouse in self.mice.values():
            self._grab(mouse)
        cols = windows.columns(self.players, *screen)
        for player in self.assigner.owner.values():
            if player not in self.pointers:
                self.touches[player] = inputdev.Touchscreen(
                    inputdev.TOUCH_NAME.format(player), *screen, 1)
                self.pointers[player] = Pointer(cols[player - 1])
                self.arrows.show(player, *self.pointers[player].position)

    def _park_pointer(self) -> None:
        """Never mid-touch: a drag drives the core pointer, and it sits under
        that player's arrow, which wears the same cursor image."""
        if not self._park_due or any(p.pressed for p in self.pointers.values()):
            return
        self._park_due = not self.arrows.park_system_pointer(*self.x11.screen_size())

    def _grab(self, mouse: inputdev.Mouse) -> None:
        try:
            mouse.grab()
        except OSError:
            log.warning("could not grab %s", mouse.path)

    def _drop(self, mouse: inputdev.Mouse) -> None:
        mouse.close()
        self.mice.pop(mouse.path, None)
        player = self.assigner.release(mouse.path)
        pointer = self.pointers.get(player)
        if pointer is not None and pointer.pressed:
            self._apply(player, [("up",)])
            pointer.pressed = False
        log.info("mouse %s unplugged (player %s)", mouse.path, player)

    def close(self) -> None:
        for touch in self.touches.values():
            touch.close()
        for mouse in self.mice.values():
            mouse.close()
        if self.arrows is not None:
            self.arrows.close()
        if self.x11 is not None:
            self.x11.close()
