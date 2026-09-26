"""Shared RetroArch controller generator used by GameCore legacy packs.

The important boundary is deliberate: SDL discovery goes through
``controllers.sdl2_probe``.  That is GameCore's cached, test-substitutable SDL2
seam; pack generators must never spawn their own SDL process.

GameCore's player roster owns the RetroArch joypad slot.  Player 1 is SDL slot
0, Player 2 is slot 1, and so on.  Device *shape* still comes from SDL/GameCore,
but slot assignment is not re-discovered behind the roster's back.
"""
from __future__ import annotations

from collections.abc import Collection
from pathlib import Path
import re

from backend.services.configgen import controllers, inputs, snapshots
from backend.services.configgen.helpers.base import Skip, atomic_write, backup

SEMANTIC = {
    "b": "a", "a": "b", "y": "x", "x": "y",
    "select": "back", "start": "start",
    "l": "leftshoulder", "r": "rightshoulder",
    "l2": "lefttrigger", "r2": "righttrigger",
    "l3": "leftstick", "r3": "rightstick",
    "up": "dpup", "down": "dpdown", "left": "dpleft", "right": "dpright",
}

_GC_BUTTON = {
    "a": 0, "b": 1, "x": 2, "y": 3,
    "back": 4, "guide": 5, "start": 6,
    "leftstick": 7, "rightstick": 8,
    "leftshoulder": 9, "rightshoulder": 10,
    "dpup": 11, "dpdown": 12, "dpleft": 13, "dpright": 14,
}
_GC_AXIS = {
    "leftx": 0, "lefty": 1, "rightx": 2, "righty": 3,
    "lefttrigger": 4, "righttrigger": 5,
}


def _owned_re(player: int) -> re.Pattern[str]:
    return re.compile(
        rf"^input_player{player}_(?:"
        r"joypad_index|"
        r"(?:b|a|y|x|select|start|l|r|l2|r2|l3|r3|up|down|left|right)_(?:btn|axis)|"
        r"(?:l|r)_(?:x|y)_(?:plus|minus)_axis"
        r")\s*=.*(?:\n|$)",
        re.M,
    )


def remove_owned(text: str, player: int) -> str:
    return _owned_re(player).sub("", text)


def set_lines(text: str, player: int, lines: list[str]) -> str:
    """Replace only GameCore-owned player lines before RetroArch includes."""
    base = remove_owned(text, player)
    block = "\n".join(lines).rstrip()
    if not block:
        return base
    include = re.search(r"(?m)^\s*#include\s+.+$", base)
    if include is None:
        return base.rstrip() + ("\n\n" if base.strip() else "") + block + "\n"
    before = base[:include.start()].rstrip()
    after = base[include.start():].lstrip("\n")
    return ((before + "\n\n") if before else "") + block + "\n\n" + after


def _input_to_binding(inp: inputs.Input | None) -> tuple[str, str] | None:
    if inp is None:
        return None
    if inp.kind == "button":
        return "btn", str(inp.index)
    if inp.kind == "hat":
        return "btn", f"h{inp.index}{inp.direction}"
    if inp.kind == "axis":
        sign = inp.direction if inp.direction in ("+", "-") else "+"
        return "axis", f"{sign}{inp.index}"
    return None


def _axis_pair(inp: inputs.Input | None) -> tuple[str, str] | None:
    if inp is None or inp.kind != "axis":
        return None
    pos = inp.direction if inp.direction in ("+", "-") else "+"
    neg = "-" if pos == "+" else "+"
    return f"{pos}{inp.index}", f"{neg}{inp.index}"


def gamecontroller_lines(player: int, device: int) -> list[str]:
    """RetroPad bindings for SDL GameController semantic mode."""
    lines = [f'input_player{player}_joypad_index = "{device}"']
    for retro, semantic in SEMANTIC.items():
        if semantic in _GC_BUTTON:
            lines.append(
                f'input_player{player}_{retro}_btn = "{_GC_BUTTON[semantic]}"'
            )
        elif semantic in _GC_AXIS:
            lines.append(
                f'input_player{player}_{retro}_axis = "+{_GC_AXIS[semantic]}"'
            )
    for prefix, semantic in (("l_x", "leftx"), ("l_y", "lefty"),
                             ("r_x", "rightx"), ("r_y", "righty")):
        axis = _GC_AXIS[semantic]
        lines.append(f'input_player{player}_{prefix}_plus_axis = "+{axis}"')
        lines.append(f'input_player{player}_{prefix}_minus_axis = "-{axis}"')
    return lines


def raw_lines(player: int, device: int, model: inputs.PadInputs) -> list[str]:
    """Raw SDL_Joystick bindings, used only when GameCore has a raw model."""
    lines = [f'input_player{player}_joypad_index = "{device}"']
    for retro, semantic in SEMANTIC.items():
        inp = model.get(semantic)
        if inp is None and retro in ("up", "down", "left", "right"):
            stick = model.get("lefty" if retro in ("up", "down") else "leftx")
            if stick is not None and stick.kind == "axis":
                inp = inputs.Input(
                    "axis", stick.index,
                    "-" if retro in ("up", "left") else "+",
                )
        got = _input_to_binding(inp)
        if got:
            suffix, value = got
            lines.append(f'input_player{player}_{retro}_{suffix} = "{value}"')
    for prefix, semantic in (("l_x", "leftx"), ("l_y", "lefty"),
                             ("r_x", "rightx"), ("r_y", "righty")):
        pair = _axis_pair(model.get(semantic))
        if pair:
            plus, minus = pair
            lines.append(f'input_player{player}_{prefix}_plus_axis = "{plus}"')
            lines.append(f'input_player{player}_{prefix}_minus_axis = "{minus}"')
    return lines


def extract(text: str) -> str:
    return "".join(m.group(0) for m in _owned_re(1).finditer(text))


def _retarget_block(block: str, player: int, device: int) -> str:
    out = re.sub(r"^input_player1_", f"input_player{player}_", block, flags=re.M)
    out = re.sub(
        rf'^input_player{player}_joypad_index\s*=.*$',
        f'input_player{player}_joypad_index = "{device}"', out, flags=re.M,
    )
    return out


def replace(text: str, block: str) -> str:
    return set_lines(text, 1, _retarget_block(block, 1, 0).splitlines())


def _probe(pad, opts: dict) -> dict[str, str]:
    """Ask GameCore's official SDL2 seam, never a pack-owned subprocess."""
    app_id = opts.get("app_id") or ""
    lib = controllers.bundled_sdl2(app_id) if app_id else ""
    return controllers.sdl2_probe(pad.vendor, pad.product, lib)


def generate(emu_id: str, ports: int, player_index: int, pad, opts: dict):
    if player_index < 1 or player_index > ports:
        return None
    path = Path(opts["target"])
    if not path.is_file():
        # Stable fixture/toast text: never leak a tmp/home absolute path.
        return Skip(f"{emu_id}: controller config is missing")

    answer = _probe(pad, opts)
    if answer.get("error"):
        return Skip(
            f"{emu_id}: SDL2 probe unavailable for {pad.vendor}:{pad.product}"
        )

    # Assumes slot N is SDL device N-1: controller_registry.compact() closes
    # gaps on the monitor's scan when no game runs, so this holds unless a pad
    # left less than one scan (3 s) before the launch. No private SDL
    # enumeration here.
    device = player_index - 1

    if snapshots.exists(opts["snap_dir"], emu_id, pad.vendor, pad.product):
        snap = snapshots.snap_path(opts["snap_dir"], emu_id, pad.vendor, pad.product)
        block = snap.read_text(encoding="utf-8")
        text = path.read_text(encoding="utf-8")
        new = set_lines(
            text, player_index,
            _retarget_block(block, player_index, device).splitlines(),
        )
        if new != text:
            backup(path)
            atomic_write(path, new)
            return f"{emu_id}: restored saved mapping P{player_index}"
        return None

    # A built-in SDL mapping means RetroArch uses SDL_GameController semantics.
    if answer.get("map"):
        lines = gamecontroller_lines(player_index, device)
    else:
        model = inputs.for_pad(pad, opts.get("app_id", ""))
        if model is None:
            return Skip(
                f"{emu_id}: no trustworthy SDL mapping for "
                f"{pad.vendor}:{pad.product}"
            )
        # A wizard capture is served to launched emulators as a controller DB,
        # so RetroArch will open it through SDL_GameController too.
        lines = (gamecontroller_lines(player_index, device)
                 if model.source == "wizard"
                 else raw_lines(player_index, device, model))

    text = path.read_text(encoding="utf-8")
    new = set_lines(text, player_index, lines)
    if new != text:
        backup(path)
        atomic_write(path, new)
        return f"{emu_id}: configured P{player_index}"
    return None


def release(emu_id: str, ports: int, player_index: int, opts: dict,
            occupied: Collection[int] = ()) -> list[str]:
    """A list, like every other generator's release: configgen extends its
    results with it, and a None raised TypeError on every unplug."""
    del occupied  # roster state is irrelevant when clearing one RetroArch slot
    if player_index < 1 or player_index > ports:
        return []
    path = Path(opts["target"])
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    new = remove_owned(text, player_index)
    if new != text:
        backup(path)
        atomic_write(path, new)
        return [f"{emu_id}: released P{player_index}"]
    return []
