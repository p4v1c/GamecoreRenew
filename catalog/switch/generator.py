"""Switch (Eden) — a saved snapshot first, otherwise built from Eden's own SDL.

Eden binds a pad by `guid` + `port` and RAW SDL indices (`button:1`, `hat:0`,
`axis:4`), written by `src/input_common/drivers/sdl_driver.cpp`:

  · `guid` is SDL_JoystickGetGUID with bytes 2-3 (the name CRC) zeroed;
  · `port` is the pad's rank among connected pads of that same GUID, which is
    what `Pad.dup_index` counts;
  · the indices come from `SDL_GameControllerGetBindForButton`, so they must be
    asked of the SDL Eden links (the KDE runtime's), never the host's — the
    same two-SDLs trap azahar documents.

Eden sets `SDL_JOYSTICK_HIDAPI_XBOX=0` and the probe does not. The Xbox pad
measured on the reference box has no HIDAPI marker in its GUID, so SDL was not
using that driver for it anyway; an Xbox pad SDL would drive through HIDAPI is
the unverified case (its GUID and indices could differ inside Eden).

Positional layout, as the Ryujinx seed had it: Switch A is the EAST button.

Players are Eden's `player_0` .. `player_3`. A released player keeps its
bindings and is only disconnected, so a returning pad of the same model gets
its slot back as it was.
"""
from __future__ import annotations

import re

from backend.services.configgen import inputs, snapshots
from backend.services.configgen.helpers.base import Skip, atomic_write, backup

EMU_ID = "switch"
MAX_PLAYERS = 4

# Switch control → the SDL control it is read from.
_FROM_SDL = {
    "button_a": "b", "button_b": "a", "button_x": "y", "button_y": "x",
    "button_lstick": "leftstick", "button_rstick": "rightstick",
    "button_l": "leftshoulder", "button_r": "rightshoulder",
    "button_zl": "lefttrigger", "button_zr": "righttrigger",
    "button_plus": "start", "button_minus": "back", "button_home": "guide",
    "button_dup": "dpup", "button_ddown": "dpdown",
    "button_dleft": "dpleft", "button_dright": "dpright",
}
_STICKS = {"lstick": ("leftx", "lefty"), "rstick": ("rightx", "righty")}



def eden_guid(sdl_guid: str) -> str:
    """Eden's device id: SDL's GUID with the name CRC cleared."""
    return sdl_guid[:4] + "0000" + sdl_guid[8:]


def _binding(inp: inputs.Input, guid: str, port: int) -> str:
    head = f"engine:sdl,port:{port},guid:{guid}"
    if inp.kind == "button":
        return f"{head},button:{inp.index}"
    if inp.kind == "hat":
        return f"{head},hat:{inp.index},direction:{inp.direction}"
    # A trigger read as an axis: Eden's own mapping writes threshold 0.5.
    return f"{head},axis:{inp.index},threshold:0.5,invert:{inp.direction}"


def _stick(x: inputs.Input | None, y: inputs.Input | None, guid: str, port: int) -> str | None:
    if x is None or y is None or x.kind != "axis" or y.kind != "axis":
        return None
    return (f"engine:sdl,port:{port},guid:{guid},axis_x:{x.index},axis_y:{y.index},"
            "offset_x:0,offset_y:0,invert_x:+,invert_y:+")


def derive_keys(model: inputs.PadInputs, player: int, port: int) -> dict[str, str]:
    """Every `player_<n>_*` value this pack owns, for one pad."""
    guid = eden_guid(model.guid)
    keys: dict[str, str] = {}
    for control, field in _FROM_SDL.items():
        inp = model.get(field)
        if inp is not None:
            keys[f"player_{player}_{control}"] = f'"{_binding(inp, guid, port)}"'
    for stick, (fx, fy) in _STICKS.items():
        value = _stick(model.get(fx), model.get(fy), guid, port)
        if value:
            keys[f"player_{player}_{stick}"] = f'"{value}"'
    if keys:
        keys[f"player_{player}_connected"] = "true"
    return keys


def _set_lines(text: str, lines: dict[str, str]) -> str:
    """Replace each `key=` line in place; a key Eden did not write is skipped."""
    for key, value in lines.items():
        text = re.sub(rf"^{re.escape(key)}=.*$", lambda _, k=key, v=value: f"{k}={v}",
                      text, flags=re.M)
    return text


def set_keys(text: str, keys: dict[str, str]) -> str:
    """Set each key and mark it changed (`\\default=false`), as Eden's UI does.

    Eden writes every key of every player, so a key missing here means the file
    is not Eden's; it is left alone rather than appended in the wrong section.
    """
    return _set_lines(text, {**{f"{k}\\default": "false" for k in keys}, **keys})


def _player_lines(text: str, player: int) -> str:
    prefix = f"player_{player}_"
    return "".join(l for l in text.splitlines(keepends=True) if l.startswith(prefix))


def _extract(player: int):
    return lambda text: _player_lines(text, player)


def _replace(player: int, port: int):
    """Replay a snapshot into `player`, on the port this pad holds now."""
    def replace(text: str, block: str) -> str:
        lines = {}
        for line in block.splitlines():
            key, sep, value = line.partition("=")
            if sep:
                key = re.sub(r"^player_\d+_", f"player_{player}_", key)
                lines[key] = re.sub(r"port:\d+", f"port:{port}", value)
        return _set_lines(text, lines)
    return replace


# What snapshot capture reads off the module: a snapshot is stored as player 1,
# port 0, and `generate` re-keys it to the slot and port of the pad at hand.
extract = _extract(0)
replace = _replace(0, 0)


def generate(player_index: int, pad, opts: dict) -> str | Skip | None:
    if not 1 <= player_index <= MAX_PLAYERS:
        return None
    player, port = player_index - 1, pad.dup_index
    snap_dir, target = opts["snap_dir"], opts["target"]
    if snapshots.exists(snap_dir, EMU_ID, pad.vendor, pad.product):
        return snapshots.restore(snap_dir, EMU_ID, target, _extract(player),
                                 _replace(player, port), pad.vendor, pad.product)
    if not target.is_file():
        return None                      # Eden writes it on first run
    model = inputs.for_pad(pad, opts.get("app_id", ""))
    if model is None:
        return Skip(f"switch: Eden's SDL does not describe {pad.vendor}:{pad.product}, "
                    f"so player {player_index} is left as it is")
    text = target.read_text()
    out = set_keys(text, derive_keys(model, player, port))
    if out == text:
        return None
    backup(target)
    atomic_write(target, out)
    return (f"switch: player {player_index} bound to {pad.vendor}:{pad.product} "
            f"(port {port}, {model.source})")


def release(player_index: int, opts: dict, occupied=()) -> list[str]:
    """Disconnect a player whose pad left, keeping its bindings."""
    if not 1 <= player_index <= MAX_PLAYERS:
        return []
    target = opts["target"]
    if not target.is_file():
        return []
    key = f"player_{player_index - 1}_connected"
    text = target.read_text()
    if not re.search(rf"^{key}=true$", text, flags=re.M):
        return []
    backup(target)
    atomic_write(target, set_keys(text, {key: "false"}))
    return [f"switch: player {player_index} disconnected"]
