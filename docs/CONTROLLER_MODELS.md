# Making any controller work in any emulator

Two distinct, complementary mechanisms. The guiding rule: **no player slot is
ever wired to a particular brand.** The first pad to connect becomes Player 1
whatever it is, the next one Player 2, and so on — like a real console.

## 1. GameCore itself (the TV menu) and the "SDL-native" emulators

`backend/data/gamecontrollerdb.txt` (the community
[SDL_GameControllerDB](https://github.com/mdqinc/SDL_GameControllerDB)) is
exported to the emulators through `SDL_GAMECONTROLLERCONFIG_FILE`
(`process_manager.py`) — that is *the* variable SDL actually reads (2.0.10+ and
SDL3 alike). An earlier revision exported `SDL_GAMECONTROLLERDB`, which is not a
variable SDL has ever read, and the database was silently ignored.

SDL merges it at init, so any emulator that speaks the SDL_GameController
**role** vocabulary rather than raw indices works with **any pad listed in the
database**, with no manual configuration at all. That covers **PCSX2,
DuckStation and gopher64** — verified by reading their live bindings:
`SDL-0/FaceEast`, `SDL-0/A` and so on, role names, never a button index.
Nothing to do, ever, whatever the pad (as long as it is in the database).

## 2. Dolphin, RPCS3, Cemu, Ryujinx, azahar, mgba — live per-slot profiling

Ground-truthed by reading their actual configs on the box:

- **Dolphin and RPCS3** also use semantic SDL roles (`Button S/E/W/N`,
  `West/South/East/North`…) — but they pick *which physical device* feeds that
  role by a literal **name** (`Device = SDL/0/PS4 Controller`,
  `Device: PS4 Controller 1`). Two traps, both found live (RPCS3 log:
  `SDL: Adding empty device` = a pad that is dead in game):

  1. Both bundle **SDL3**, whose names differ from the SDL2-era community
     database: a DualSense is "DualSense Wireless Controller", not
     "PS5 Controller". The name is therefore resolved by asking the **system's
     libSDL3** with the pads actually connected
     (`controller_profiles.resolve_name`); the database is only a last resort.
  2. The number is **not** the player slot. RPCS3 appends a 1-based counter
     **per name** (`sdl_pad_handler.cpp`), Dolphin a 0-based counter **per
     name** (`SDL/<k>/<name>`, ciface DeviceContainer). A lone DualSense is
     "DualSense Wireless Controller 1" / `SDL/0/…` even as Player 2.

- **Ryujinx** binds by a device **GUID** (`button:1,guid:0500…cc09…`). Verified
  in the open on this box: DualShock 4 and DualSense share the **same kernel
  driver** and report **identical raw indices** — only the GUID differs
  (vendor/product bytes at a fixed offset, whatever the SDL GUID format
  revision). Retargeting a slot is therefore *only* a substitution of those
  bytes, never of the indices the owner has already validated. But the
  accompanying index counts **per GUID**, not per player: the `<dup>-<GUID>`
  prefix of `id` in `Config.json` is 0 for a lone pad of its model whatever slot
  it occupies (a dup that does not exist binds a phantom device → a dead
  entry). Ryujinx slots are objects in the `input_config` list, keyed by
  `player_index` (`Player1`…).

- **azahar, mgba, Cemu**: **snapshot restore**, *not* GUID substitution. Their
  bindings cannot be synthesised from a VID:PID alone. The real model is:

  1. the owner maps the pad once, inside the emulator, via **"Scan mapping"**;
  2. `snapshot_save()` stores that config block, indexed by `vendor:product`;
  3. `snapshot_restore()` puts it back when a pad of the same model reconnects.

  GUID-substituting versions of `_mgba()` and `_cemu()` used to exist in
  `controller_profiles.py`. They were never called by `apply_profile()` and have
  been removed — dead code that looks like the mechanism is worse than no code,
  and this page described the box on the strength of them. The module docstring
  is the authority.

The counter common to both the by-name and by-GUID schemes is `dup_index`: how
many pads of the same vendor:product are already connected in a *lower* player
slot. `gamepad_monitor.py` computes it from its roster and passes it to
`apply_profile()`; 0 is always correct for the first pad of a given model.

### The live mechanism: `backend/services/controller_profiles.py`

`gamepad_monitor.py` drives all of it, continuously, inside the already-running
backend — **this is not a script you re-run by hand**. Every time a pad takes a
NEW player slot (including pads already plugged in when the backend starts), the
module:

1. reads its USB vendor:product (evdev),
2. resolves its canonical SDL name,
3. writes or retargets each emulator's native config for THAT slot, with the
   right pad — live, without restarting or relaunching anything.

The slot itself is assigned by `controller_registry.py` (already in place for
battery levels and TV labels): first pad connected = Player 1, next = Player 2,
up to 4. The *type* of pad occupying a slot can therefore change from one
session to the next without ever breaking anything.

- `azahar` (3DS), `mgba` (GBA), `Cemu` (Wii U): single-player hardware here, so
  only Player 1 is ever touched — and by snapshot restore (see above), not GUID
  substitution.
- `melonDS` (DS): **profiled**, contrary to what this page used to claim. A
  saved snapshot wins; otherwise `_melonds()` synthesises the config from the
  connected pad. Face buttons are consistent across pads — only the D-pad
  differs (hat vs buttons), and that is the only thing adapted
  (`_pad_has_hat`). Single-player, slot 1.
- `ppsspp`: no existing config found on this box (never launched) → skipped
  cleanly. Launch it once, map the buttons by hand, and profiling covers it
  from then on.
- Non-Sony pads (Xbox, 8BitDo, generics): GUID substitution (Ryujinx) assumes
  indices identical to the reference pad (the already-configured Player 1),
  which is only guaranteed within one driver family (as with DS4/DualSense). A
  different family needs one "Scan mapping", which then becomes the snapshot
  reused afterwards.

> ⚠️ **An emulator already running when its config changes does not re-read the
> file.** Quit and relaunch the game for the new mapping to apply to that
> session. Subsequent launches are transparent.

### A pad with no Home button still gets a slot

`_find_gamepad_devices()` used to keep a device only if it declared `BTN_MODE`
or `KEY_HOMEPAGE`. A pad without a Home button — a generic USB pad, an arcade
stick, a SNES or N64 clone, an 8BitDo in DInput — never entered the dictionary
at all: never watched, never registered, no player slot, and `apply_profile()`
never called for it. It still worked in emulators that read SDL themselves,
which is what made the whole pipeline described above look like it was running
when it was not.

A device is kept if it declares `BTN_SOUTH` too. Such pads simply never reach
`_on_guide_pressed`, which is correct. A keyboard still cannot take a slot:
`is_pad` is `BTN_SOUTH`, and no keyboard declares it. Pads kept without a Guide
button say so once, at INFO.

### One pad, several device nodes

`controller_registry.key_for()` returns the pad's MAC, so a DualShock 4 paired
over Bluetooth that is then plugged in to charge maps **two** `/dev/input/event*`
paths to a single registry key. Unplugging the cable killed that path's watcher
and used to release the slot outright — `gp:disconnected` broadcast,
`release_profile()` putting `Wiimote1` back on the virtual pointer — while the
pad was still connected over Bluetooth and still in the player's hands. The slot
is released only once no live path maps to that key.

## `install/apply-controller-model.sh` — rescue tool only

```
install/apply-controller-model.sh                    # auto-detect, up to 4
install/apply-controller-model.sh 054c:0ce6          # forced VID:PID (Player 1)
install/apply-controller-model.sh 054c:0ce6 "PS5 Controller"
```

Calls `controller_profiles.py` directly. Useful only for retargeting pads that
are ALREADY connected without unplugging them (right after installing this
feature, for instance). Day to day the normal mechanism is fully automatic via
`gamepad_monitor.py`.

Complementary to `apply-multi-ds4.sh`, which clones Player 1 into slots 2-4 for
several pads of the SAME model, once, at install time.
