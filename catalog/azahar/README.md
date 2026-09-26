# Azahar — L3 layout toggle built into the pack

Installing this pack installs Azahar, then the Python daemon and the user
service `azahar-layout-toggle.service`, from GameCore's Systems screen or from
the main installer.

- L3 sends F10: both screens → top screen only → both screens.
- The seed selects layouts `0, 1` and stretches the top screen. The config
  script fills missing keys, keeps a backup, and writes only while the
  emulator is closed.
- The pack declares `hostAccess.uinput`: the shared engine sets up the module,
  udev permissions and `input` group membership when needed.
- Python 3 stdlib only; no pip package for the daemon.

Files go to `~/.local/share/gamecore/layout-toggle/azahar/`. The service keeps
the standalone project's name so an install replaces that unit instead of
running two L3 translators.

On a box that already has the pack: `sudo gamecore-emu install azahar` adds
the daemon. It reapplies the seed as this command always does (`.bak-preinstall`
backup). Close the emulator first. A code update alone does not deploy the
services.

Diagnostics: `systemctl --user status azahar-layout-toggle` and
`journalctl --user -u azahar-layout-toggle -f`.

The daemon checks that Azahar is running, not that its window has focus. It
does not drive GameCore's bezels: disable the DS/3DS bezel to see the whole
game in single-screen mode. Validate on the box: L3, Bluetooth, and returning
to the UI.
