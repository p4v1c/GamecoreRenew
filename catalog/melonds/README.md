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
