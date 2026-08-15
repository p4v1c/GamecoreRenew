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
database**, with no manual configuration at all. That covers **PCSX2 and
DuckStation** — verified by reading their live bindings: `SDL-0/FaceEast`,
`SDL-0/A` and so on, role names, never a button index. Nothing to do, ever,
whatever the pad (as long as it is in the database).

The N64 pack (`gopher64`, running Rosalie's Mupen GUI) used to be listed here
and does **not** belong: see §4 below. Its button profile is device-agnostic,
but nothing binds a pad to an N64 port, so "nothing to do, ever" is false for
it in the way that matters.

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

- **Ryujinx** binds by a device **GUID**, and it resolves that GUID by string
  equality: `DriverConfigurationUpdate` → `GetGamepad(id)` →
  `_gamepadsIds.IndexOf(id)`. No match is −1, and −1 disposes the slot in
  silence — no log, no "already assigned" mark in Input Settings.

  The GUID must therefore be the exact one Ryujinx's own SDL2 computes, and it
  carries **bus type, version and driver signature** on top of vendor/product:
  the same DualShock 4 has different GUIDs over USB and over Bluetooth. It is
  never derived from a vendor:product. Ryujinx renders SDL2's 16 raw GUID bytes
  through .NET's `System.Guid`, which reverses the first three fields and
  leaves the rest alone, so the conversion is exact:

  ```
  030000004c050000cc09000000006800  ->  00000003-054c-0000-cc09-000000006800
  050000005e040000fd02000003090000  ->  00000005-045e-0000-fd02-000003090000
  ```

  `ryu_guid_from_sdl2()` does that, on the GUID read live from SDL2. When SDL2
  cannot be asked, the slot is left alone and a `Skip` says so — an id that
  matches no device is worse than an unchanged one.

  An earlier version copied the GUID from any entry sharing a vendor:product,
  or else substituted vendor/product into a reference GUID. The first breaks
  whenever a pad changes transport; the second produces strings no device has
  ever had, and since they parse back to the right vendor:product, the next
  pass adopted them as "a GUID Ryujinx wrote" and reported a match. Once wrong,
  always wrong, always reported as a success.

  The accompanying index counts **per GUID**, not per player
  (`SDL2GamepadDriver.GenerateGamepadId` walks `guidIndex` up while the id is
  taken): the `<dup>-<GUID>` prefix of `id` in `Config.json` is 0 for a lone pad
  of its model whatever slot it occupies. Ryujinx slots are objects in the
  `input_config` list, keyed by `player_index` (`Player1`…).

- **azahar, mgba, Cemu**: **snapshot restore**, *not* GUID substitution. A
  vendor:product alone still says nothing about a raw button index. The model is:

  1. the owner maps the pad once, inside the emulator, via **"Scan mapping"**;
  2. `snapshots.capture()` stores that config block, indexed by `vendor:product`
     — refusing it when the block's own GUID names another controller;
  3. `snapshots.restore()` puts it back when a pad of the same model reconnects.

  **A saved snapshot still always wins. What changed is what happens when there
  is none.** azahar and mgba are now built from the abstract input model
  (`configgen/inputs.py`), which asks *that emulator's own SDL* for the pad's
  indices — the question nobody was asking, and the reason this page could say
  they were unsynthesisable. Cemu is not: its `<uuid>` is an identity no SDL on
  the box computes and its `<button>` encoding is undocumented, both recorded in
  `derive.cemu_is_not_derivable`.

  GUID-substituting versions of `_mgba()` and `_cemu()` used to exist in
  `controller_profiles.py`. They were never called by `apply_profile()` and have
  been removed — dead code that looks like the mechanism is worse than no code,
  and this page described the box on the strength of them. The module docstring
  is the authority.

The counter common to both the by-name and by-GUID schemes is `dup_index`: how
many pads with the same **resolved name** are already connected in a *lower*
player slot. `gamepad_monitor.py` computes it from its roster and passes it to
`apply_profile()`; 0 is always correct for the first pad of a given model.

### The live mechanism: `backend/services/controller_profiles.py`

`gamepad_monitor.py` drives all of it, continuously, inside the already-running
backend — **this is not a script you re-run by hand**. Whenever the set of
connected pads changes, `_reconcile()` runs and the module:

1. builds the roster — one entry per PHYSICAL pad, since a DualShock 4 owns
   three `/dev/input/event*` nodes and `key_for()` collapses them onto its MAC,
2. releases the slots of pads that have left, and gives arrivals theirs,
3. recomputes every `dup` index and re-profiles **each** slot whose
   `(vendor, product, resolved name, dup)` footprint moved — live, without
   restarting or relaunching anything.

Step 3 is the part that is easy to get wrong. Only the arriving pad used to be
profiled, and only the leaving pad's slot released. But `SDL/<dup>/<name>`,
`<name> <dup+1>` and `<dup>-<GUID>` all describe the *roster*, not one
controller: player 1's pad running out of battery mid-session left player 2
holding a `dup` that no longer meant anything. Reconciling the whole roster
fixes that class of bug rather than its instances, and it is the only way a
slot ever gets a second chance — the old code profiled a pad exactly once.

The slot itself is assigned by `controller_registry.py` (already in place for
battery levels and TV labels): first pad connected = Player 1, next = Player 2,
up to 4. The *type* of pad occupying a slot can therefore change from one
session to the next without ever breaking anything.

`dup` is counted by **resolved name**, not by vendor:product. Every consumer
counts by name, and `SDL3_FALLBACK_NAMES` alone maps `054c:05c4`, `054c:09cc`
and `054c:0ba0` onto "PS4 Controller" — counting by vendor:product gave two
DualShock 4 revisions `dup 0` each, so one pad drove two ports and the other
was dead.

- `azahar` (3DS), `mgba` (GBA), `Cemu` (Wii U): single-player hardware here, so
  only Player 1 is ever touched — and by snapshot restore (see above), not GUID
  substitution.
- `melonDS` (DS): **profiled**, contrary to what this page used to claim. A
  saved snapshot wins; otherwise `_melonds()` synthesises the config from the
  connected pad. Face buttons are consistent across pads — only the D-pad
  differs (hat vs buttons), and that is the only thing adapted
  (`_pad_has_hat`). Single-player, slot 1.
- `ppsspp`: **deliberately not profiled, and that is the right answer** — not
  "never launched", which this page used to say and which was already false.
  `controls.ini` binds `NKCODE` role names under `DEVICE_ID_PAD_0` and carries
  no device identity at all, so one shipped file fits every pad. It is a
  static config to get right once, in `catalog/ppsspp/seed/`, not something to
  write per controller.
- `gopher64` — the pack id; the emulator is **Rosalie's Mupen GUI**, a front end
  over the Mupen64Plus core, which is why its config file is `mupen64plus.cfg`:
  **not profiled either, and this page used to imply otherwise** by listing it
  with PCSX2 and DuckStation under "nothing to do, ever". Its button
  profile is genuinely device-agnostic (`SDL_GamepadButton` enum ids), but
  binding a pad to an N64 *port* is a separate step nothing performs:
  `controller_assignment` sits at `[null, null, null, null]` and the N64 has no
  controller at all. Out of scope here; it needs its own step.
- Non-Sony pads (Xbox, 8BitDo, generics): nothing special. Ryujinx reads the
  real GUID from SDL2 rather than assuming a driver family, PCSX2 and
  DuckStation bind by SDL role, and Dolphin/RPCS3 by SDL name. Only azahar, mgba
  and Cemu — which store raw button indices — need one "Scan mapping" per
  model, which then becomes the snapshot reused afterwards.

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

## `install/steps/apply-controller-model.sh` — rescue tool only

```
install/steps/apply-controller-model.sh                    # auto-detect, up to 4
install/steps/apply-controller-model.sh 054c:0ce6          # forced VID:PID (Player 1)
install/steps/apply-controller-model.sh 054c:0ce6 "PS5 Controller"
```

Calls `controller_profiles.py` directly. Useful only for retargeting pads that
are ALREADY connected without unplugging them (right after installing this
feature, for instance). Day to day the normal mechanism is fully automatic via
`gamepad_monitor.py`.

Complementary to `apply-multi-ds4.sh`, which clones Player 1 into slots 2-4 for
several pads of the SAME model, once, at install time.
