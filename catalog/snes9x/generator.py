"""Snes9x GTK controller autoconfig for GameCore.

Snes9x stores every local pad in one INI-like file, one `[Joypad N]` section
per player. GTK Snes9x binds RAW SDL joystick inputs:

    Joystick 1 Button 0
    Joystick 1 Axis 0 - 40%

Two details are important here:

1. GameCore's roster already assigns player slots. Snes9x numbers joystick
   devices from 1, so Player N is written as Joystick N instead of launching a
   second private SDL process to rediscover the same roster.
2. GTK Snes9x converts a hat into synthetic axes placed after the joystick's
   real axes. The physical axis count therefore comes from GameCore's official
   cached ``controllers.sdl2_probe`` seam.

Flatpak app/runtime SDL is still selected through ``controllers.bundled_sdl2``;
a native Snes9x install asks the host SDL.

A hand-made snapshot always wins. "Scan mapping" captures Joypad 0 (the scan
requires one connected pad); on restore the block is retargeted to the player's
Joypad section AND to the pad's current live SDL joystick number.
"""
from __future__ import annotations

from collections.abc import Collection
import re

from backend.services.configgen import controllers, inputs, snapshots
from backend.services.configgen.helpers.base import Skip, atomic_write, backup
from backend.services.configgen.helpers.ini import iter_sections, replace_section

EMU_ID = "snes9x"
PORTS = 2
THRESHOLD = 40
_CANON_PORT = 0

# Face buttons are positional:
# SDL south/east/west/north -> SNES B/A/Y/X.
_BINDINGS = {
    "b_up": "dpup",
    "b_down": "dpdown",
    "b_left": "dpleft",
    "b_right": "dpright",
    "b_start": "start",
    "b_select": "back",
    "b_a": "b",
    "b_b": "a",
    "b_x": "y",
    "b_y": "x",
    "b_l": "leftshoulder",
    "b_r": "rightshoulder",
}

_DPAD_STICK = {
    "dpup": ("lefty", "-"),
    "dpdown": ("lefty", "+"),
    "dpleft": ("leftx", "-"),
    "dpright": ("leftx", "+"),
}

# Mirrors the information Snes9x itself uses in gtk/src/gtk_control.cpp:
# SDL joystick index and SDL_JoystickNumAxes(). Print every matching VID:PID,
# because two identical pads are a normal couch setup.
def _physical_axis_count(answer: dict[str, str]) -> int | None:
    """Axis count reported by GameCore's official SDL2 probe.

    Older probe implementations did not expose it, so a complete SDL mapping
    remains a safe fallback: the highest raw axis token + 1 is the physical
    axis count Snes9x needs to place its synthetic hat axes.
    """
    raw = answer.get("axes")
    if raw is not None:
        try:
            return max(0, int(raw))
        except (TypeError, ValueError):
            return None
    mapping = answer.get("map", "")
    axes = [int(n) for n in re.findall(r":(?:[+-])?a(\d+)(?:~)?(?:,|$)", mapping)]
    return max(axes) + 1 if axes else None


def _header(port: int) -> str:
    return f"Joypad {port}"


def _section_of(text: str, port: int) -> str:
    for header, body in iter_sections(text):
        if header == _header(port):
            return body
    return ""


def _retarget(block: str, port: int, device: int) -> str:
    lines = block.splitlines(keepends=True)
    if lines and lines[0].strip().startswith("["):
        lines[0] = f"[{_header(port)}]\n"
    text = "".join(lines)
    # Only joystick bindings are rewritten; keyboard/custom shortcut lines stay
    # exactly as the owner made them.
    return re.sub(r"\bJoystick\s+\d+\b", f"Joystick {device}", text)


def _extract_port(port: int):
    def f(text: str) -> str:
        return _section_of(text, port)
    return f


def _replace_port(port: int, device: int):
    def f(text: str, block: str) -> str:
        if not block.strip():
            return text
        return replace_section(_header(port))(text, _retarget(block, port, device))
    return f


# Public snapshot contract. It is only a file-to-file default used by contract
# checks; live restores use _replace_port(..., live_device).
extract = _extract_port(_CANON_PORT)
replace = _replace_port(_CANON_PORT, 1)


def _live_joystick(player_index: int, pad, opts: dict) -> tuple[int, int] | None:
    """Return (Snes9x 1-based device slot, physical axis count).

    Discovery stays on GameCore's official, cached ``controllers.sdl2_probe``
    seam.  The roster already assigned the player slot, so this generator does
    not spawn another SDL process to rediscover device order.
    """
    app_id = opts.get("app_id") or ""
    lib = ""
    if app_id:
        lib = controllers.bundled_sdl2(app_id)
        if not lib:
            return None
    answer = controllers.sdl2_probe(pad.vendor, pad.product, lib)
    if answer.get("error"):
        return None
    axes = _physical_axis_count(answer)
    if axes is None:
        return None
    return player_index, axes


def _as_snes9x(inp: inputs.Input, device: int, axis_count: int) -> str | None:
    if inp.kind == "button":
        return f"Joystick {device} Button {inp.index}"
    if inp.kind == "axis":
        sign = inp.direction if inp.direction in ("+", "-") else "+"
        return f"Joystick {device} Axis {inp.index} {sign} {THRESHOLD}%"
    if inp.kind == "hat":
        # Snes9x GTK turns hat N into two axes *after every physical axis*:
        # vertical = axis_count + N*2, horizontal = +1.
        vertical = inp.direction in ("up", "down")
        axis = axis_count + inp.index * 2 + (0 if vertical else 1)
        sign = {"up": "+", "down": "-", "left": "-", "right": "+"}.get(inp.direction)
        if sign:
            return f"Joystick {device} Axis {axis} {sign} {THRESHOLD}%"
    return None


def _input_for(model: inputs.PadInputs, control: str) -> inputs.Input | None:
    inp = model.get(control)
    if inp is not None:
        return inp
    fallback = _DPAD_STICK.get(control)
    if not fallback:
        return None
    field, sign = fallback
    axis = model.get(field)
    if axis is None or axis.kind != "axis":
        return None
    return inputs.Input("axis", axis.index, sign)


def _values_for(model: inputs.PadInputs, device: int,
                axis_count: int) -> dict[str, str]:
    values: dict[str, str] = {}
    for key, control in _BINDINGS.items():
        inp = _input_for(model, control)
        value = _as_snes9x(inp, device, axis_count) if inp is not None else None
        values[key] = value or "Unset"
    return values


def _set_owned(section: str, values: dict[str, str]) -> str:
    """Change only GameCore-owned normal joypad bindings in one section."""
    out: list[str] = []
    seen: set[str] = set()
    for line in section.splitlines(keepends=True):
        key = line.partition("=")[0].strip()
        if "=" in line and key in values:
            out.append(f"{key} = {values[key]}\n")
            seen.add(key)
        else:
            out.append(line)
    missing = [k for k in values if k not in seen]
    if missing:
        at = max((n for n, line in enumerate(out) if line.strip()), default=-1) + 1
        out[at:at] = [f"{k} = {values[k]}\n" for k in missing]
    return "".join(out)


def _unset_values() -> dict[str, str]:
    return {k: "Unset" for k in _BINDINGS}


def _synthesise(player_index: int, pad, opts: dict, live=None):
    target = opts["target"]
    if not target.is_file():
        return None

    live = live or _live_joystick(player_index, pad, opts)
    if live is None:
        return Skip(
            f"{EMU_ID}: Snes9x's SDL2 did not expose {pad.vendor}:{pad.product} "
            f"with a usable joystick index; player {player_index} left untouched"
        )
    device, axis_count = live

    model = inputs.for_pad(pad, opts.get("app_id", ""))
    if model is None:
        return Skip(
            f"{EMU_ID}: Snes9x's SDL2 has no usable GameController mapping for "
            f"{pad.vendor}:{pad.product}; player {player_index} left untouched"
        )

    port = player_index - 1
    text = target.read_text()
    section = _section_of(text, port)
    if not section:
        return Skip(f"{EMU_ID}: {target.name} has no [{_header(port)}] section")

    values = _values_for(model, device, axis_count)
    body = _set_owned(section, values)
    out = replace_section(_header(port))(text, body)
    if out == text:
        return None
    backup(target)
    atomic_write(target, out)
    mapped = sum(v != "Unset" for v in values.values())
    return (f"{EMU_ID}: player {player_index} -> Joystick {device}, "
            f"{mapped} controls mapped ({model.source})")


def generate(player_index: int, pad, opts: dict):
    if not 1 <= player_index <= PORTS:
        return None
    snap_dir, target = opts["snap_dir"], opts["target"]

    live = _live_joystick(player_index, pad, opts)
    if live is None:
        return Skip(
            f"{EMU_ID}: could not resolve Snes9x's live SDL joystick for "
            f"{pad.vendor}:{pad.product}; player {player_index} left untouched"
        )
    device, _axis_count = live

    # A captured hand mapping wins, but is retargeted to this player's section
    # and to the device number Snes9x actually enumerates right now.
    if snapshots.exists(snap_dir, EMU_ID, pad.vendor, pad.product):
        port = player_index - 1
        return snapshots.restore(
            snap_dir, EMU_ID, target,
            _extract_port(port), _replace_port(port, device),
            pad.vendor, pad.product,
        )
    return _synthesise(player_index, pad, opts, live)


def release(player_index: int, opts: dict,
            occupied: Collection[int] = ()) -> list[str]:
    """Clear this departed player's bindings so recycled SDL ids cannot alias."""
    if not 1 <= player_index <= PORTS:
        return []
    target = opts["target"]
    if not target.is_file():
        return []
    port = player_index - 1
    text = target.read_text()
    section = _section_of(text, port)
    if not section:
        return []
    body = _set_owned(section, _unset_values())
    out = replace_section(_header(port))(text, body)
    if out == text:
        return []
    backup(target)
    atomic_write(target, out)
    return [f"{EMU_ID}: player {player_index} released"]
