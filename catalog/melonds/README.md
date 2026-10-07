# melonDS — L3 layout toggle built into the pack

Installing this pack installs melonDS, then the Python daemon and the user
service `melonds-layout-toggle.service`, from GameCore or from the main
installer. The service starts after the config; with no open user session it
starts at the next login.

L3 switches between both screens and top screen only in 16:9. The daemon
changes the layout settings in memory, then injects F12 so melonDS recomputes
the display. The seed binds F12 to `HK_SwapScreenEmphasis` and unbinds the
matching joystick hotkey. Restoring an old controller profile keeps that
unbinding when F12 is selected. The daemon also repairs the binding when
melonDS closes.

The pack declares two prerequisites applied by the install engine:

- `hostAccess.uinput`: module, virtual keyboard permissions, `input` group.
- `hostAccess.ptrace`: `kernel.yama.ptrace_scope=0`, needed for the daemon to
  read another process of the same user. Host-wide setting. The previous value
  and replaced files are kept in `/var/lib/gamecore/layout-access.json` for
  uninstall.

Python 3 stdlib only. Installed under
`~/.local/share/gamecore/layout-toggle/melonds/`. The service keeps the
standalone project's name to avoid two daemons at once.

Changes from the standalone copy:

- run with `--recalc uinput --no-widescreen`: no cheat code installed and no
  automatic `EnableCheats`; 16:9 is a stretch;
- no toggle write until the virtual keyboard exists;
- exits with failure when inputs are unreadable, so systemd retries;
- picks the config from the GameCore launcher, supports the optional native
  binary `lib/melon`; `MELONDS_CONFIG` can force a path;
- offsets and caches stay per daemon and per melonDS version;
- split into modules (`melonds_common`, `melonds_config`, `melonds_memory`,
  `melonds_input`) installed next to `melonds_layout_toggle.py`.

On a box that already has the pack: `sudo gamecore-emu install melonds` adds
the daemon. It reapplies the seed with a backup, as before; close the emulator
first. A code update alone does not deploy the daemon into the home.

Diagnostics: `systemctl --user status melonds-layout-toggle` and
`journalctl --user -u melonds-layout-toggle -f`.

Reading melonDS internals depends on its version; the dynamic search does not
guarantee future versions. The daemon checks the process, not focus, and does
not drive GameCore's bezels — disable the bezel for full screen. Automated
tests do not replace an L3/Bluetooth check on the box.

## Local multiplayer (2-4 controllers)

With two to four pads connected, `generator.launch_command` replaces the
launch with `multiplayer/launcher.py` around melonDS (no fullscreen). One pad:
the solo launch, unchanged. Architecture and the reasons:
`docs/architecture/10-catalog-and-install.md`, "melonDS local multiplayer".

- One melonDS process, one instance per player, opened through melonDS's own
  menus over AT-SPI (`gdbus`). Every instance boots its firmware with the cart
  in: the DS menu offers the game and DS Download Play.
- Each instance reads `[InstanceN] JoystickID`, written by the launcher from
  an SDL probe run inside the flatpak, before melonDS starts (too slow for
  the backend's 3 s launch budget: overrunning it started melonDS solo).
- Each player is a full-height column of two windows, top screen above
  touch screen, no decorations, no menu bar (hidden through melonDS's own
  fullscreen hotkey, F11 in multiplayer). 3-4 players stretch the image
  vertically to fill the screen. L3 does nothing in multiplayer: the
  launcher sets `GAMECORE_MELONDS_PLAYERS` on melonDS and the daemon skips
  any process with more than one player (its A/B layout broke the screen
  windows).
- Two mice or more: once a second mouse is used, each mouse belongs to one
  player (order of first use), with its own arrow (the box's cursor theme, same for all) kept in that
  player's column; its click is that player's stylus, so two players can
  drag at once. X's own arrow, moved by every touch, goes back to the
  off-screen corner when the touch ends.
  One mouse keeps the normal pointer.
- Saves: player 1 keeps `<rom>.sav`; players 2-4 get their own `<rom>.sav.N`,
  blank the first time (a new game), never a copy of player 1's.
- Diagnostics: `melonds-multiplayer.log` in `$GAMECORE_LOG_DIR` (`<data>/logs/packs/melonds/` when GameCore launches it), else in `~/.cache/gamecore/`.

## Saves per profile

`"profileSaves": "per-instance"` in `pack.json`: the save follows the profile
playing. `place_saves` in `generator.py` runs before every launch, solo or
multiplayer, and writes `[Instance0] SaveFilePath` and `SavestatePath`:

- the primary profile (the first one, named in Settings → Profiles): left as they are, empty =
  next to the ROM, where every save from before profiles lives. A path under
  `emu/profile-saves/` left by another profile's launch is emptied (melonDS
  writes its config back on exit); a path you set yourself stays;
- any other profile: `<data>/emu/profile-saves/<profile id>/melonds/`, created
  if missing. The first launch finds no save and the game offers a new one.
  The ROM-side save is never read, copied or touched.

Players 2-4 in local multiplayer keep `<rom>.sav.N` beside the ROM until pads
carry profiles. The flatpak sees the folder because it has `/userdata` and
the install directory. A non-primary launch with no `melonDS.toml` yet is
refused rather than saving into the primary's file, and so is one while a
path you set yourself is in place: nothing remembers it, so it would be lost. When the game ends both
paths go back to the defaults (`profile_saves.release`), so melonDS started
from Desktop Mode saves beside the ROM.
