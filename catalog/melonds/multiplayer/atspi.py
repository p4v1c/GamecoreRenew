"""Press melonDS's own menu items over the accessibility bus (AT-SPI).

melonDS has no command line for "Launch new instance" or for loading a ROM
into an instance: the player clicks menus. These are the same QActions,
pressed over D-Bus. Qt exposes them only when started with
QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1. `gdbus` keeps this stdlib-only.
"""
from __future__ import annotations

import ast
import re
import subprocess
from collections.abc import Callable

GDBUS_TIMEOUT = 5.0
REGISTRY = "org.a11y.atspi.Registry"
ROOT = "/org/a11y/atspi/accessible/root"
ACCESSIBLE = "org.a11y.atspi.Accessible"
# Roles a menu path walks through; anything else (the screen widget) is skipped.
MENU_ROLES = {"frame", "menu bar", "menu item", "menu", "popup menu"}


class AtspiError(RuntimeError):
    """The bus or the application did not answer as expected."""


def _gdbus(*args: str) -> str:
    try:
        out = subprocess.run(["gdbus", "call", *args], capture_output=True,
                             text=True, timeout=GDBUS_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise AtspiError(f"gdbus failed: {e}") from e
    if out.returncode != 0:
        raise AtspiError(out.stderr.strip() or "gdbus failed")
    return out.stdout.strip()


def parse_gvariant(text: str):
    """GVariant text from gdbus → Python. Covers what AT-SPI returns here:
    strings, booleans, object paths and arrays of (bus, path) tuples."""
    text = re.sub(r"\bobjectpath (?=')", "", text)
    text = re.sub(r"(?<=[(,\s])<(.*)>(?=,\))", r"\1", text)   # (<'x'>,) → ('x',)
    text = re.sub(r"\btrue\b", "True", re.sub(r"\bfalse\b", "False", text))
    try:
        return ast.literal_eval(text)
    except (ValueError, SyntaxError) as e:
        raise AtspiError(f"unparsable gdbus output: {text[:80]!r}") from e


def bus_address() -> str:
    return parse_gvariant(_gdbus("--session", "-d", "org.a11y.Bus", "-o",
                                 "/org/a11y/bus", "-m", "org.a11y.Bus.GetAddress"))[0]


def strip_mnemonic(text: str) -> str:
    """Qt drops '&' from accessible names; drop it on our side too."""
    return text.replace("&", "")


class Node:
    """One accessible object: (bus name, object path) on the a11y bus."""

    def __init__(self, address: str, bus: str, path: str):
        self.address, self.bus, self.path = address, bus, path

    def _call(self, method: str, *args: str):
        return parse_gvariant(_gdbus("--address", self.address, "-d", self.bus,
                                     "-o", self.path, "-m", method, *args))

    def children(self) -> list[Node]:
        return [Node(self.address, b, p)
                for b, p in self._call(f"{ACCESSIBLE}.GetChildren")[0]]

    def name(self) -> str:
        return self._call("org.freedesktop.DBus.Properties.Get", ACCESSIBLE, "Name")[0]

    def role(self) -> str:
        return self._call(f"{ACCESSIBLE}.GetRoleName")[0]

    def extents(self) -> tuple[int, int, int, int]:
        """(x, y, width, height) on screen."""
        return tuple(self._call("org.a11y.atspi.Component.GetExtents", "0")[0])

    def press(self) -> None:
        if not self._call("org.a11y.atspi.Action.DoAction", "0")[0]:
            raise AtspiError(f"action refused on {self.path}")


def find_app(address: str, name: str = "melonDS") -> Node | None:
    """The newest application registered under `name`, or None."""
    root = Node(address, REGISTRY, ROOT)
    found = None
    for app in root.children():
        try:
            if app.name() == name:
                found = app       # registry order = registration order
        except AtspiError:
            continue              # an app that died while we listed it
    return found


def menu_bar(frame: Node) -> Node | None:
    return next((c for c in frame.children() if c.role() == "menu bar"), None)


def find_menu_item(frame: Node, path: list[str | Callable[[str], bool]]) -> Node | None:
    """Walk `frame`'s menus by item names; the last step may be a predicate."""
    steps = [(lambda n, s=s: n == s) if isinstance(s, str) else s for s in path]
    return _walk(frame, steps, depth=0)


def _walk(node: Node, steps: list[Callable[[str], bool]], depth: int) -> Node | None:
    if depth > 8:
        return None
    for child in node.children():
        role = child.role()
        if role not in MENU_ROLES:
            continue
        if role == "menu item":
            if steps[0](strip_mnemonic(child.name())):
                if len(steps) == 1:
                    return child
                hit = _walk(child, steps[1:], depth + 1)
                if hit:
                    return hit
            continue
        hit = _walk(child, steps, depth + 1)     # menu bar / popup: transparent
        if hit:
            return hit
    return None
