# Azahar and melonDS packs with their layout daemon

Base: GamecoreRenew `de53579f6802a229dbea3d5edcf3ca4eaab3a300`.

Each pack ships its daemon, its systemd user unit and its seed settings.
Installing from GameCore (`gamecore-emu install`) or from the main installer
deploys the daemon with the emulator. Files go to the player's home even when
the install runs under sudo. Services are enabled and started after the
configs; with no open session they start at the next login.

Service names stay `azahar-layout-toggle.service` and
`melonds-layout-toggle.service`, as in the standalone projects. Installing the
pack replaces the unit of the same name instead of adding a second daemon.

## Contents

- `catalog/azahar/`: L3 → F10, layouts 0/1, top screen stretched.
- `catalog/melonds/`: L3 → memory settings → F12, joystick hotkey disabled,
  no cheats installed or enabled.
- `backend/services/installer/host_access.py` + schema: declarative
  prerequisites `hostAccess.uinput` and `hostAccess.ptrace`, for trusted packs
  only.
- Shared install: correct home, correct seed paths, emulator services
  collected and started, failures reported to the GameCore flow.
- Uninstall: stops the units the packs installed, removes the shipped
  scripts, restores the prerequisites the install recorded, and keeps system
  files the operator changed afterwards.

Both pack directories AND the shared files are required: the manifests use
the new `hostAccess` field, so copying only the two folders onto an older
version does not work.

## Installing on an existing box

Close the emulators, then install the packs from the UI or with:

```bash
sudo gamecore-emu install azahar melonds
```

This keeps the existing seed redeploy behaviour (`.bak-preinstall` backup):
it is not a targeted migration of the layout keys only. Updating the
repository alone does not copy the daemons into the home, and `reconfigure`
alone does not install them.

## Validation

263 tests passed, 5 skipped. Targeted coverage: pack install, both flows
simulated, user services, permissions and restore, catalogue and OTA
restriction, Azahar config, melonDS native/Flatpak path, controller profiles
and existing fixtures. Catalogue: 17 valid packs. Ruff, Bash syntax of the
changed scripts and `git diff --check`: OK.

No daemon or emulator was run; system commands were simulated in tests and
files written to temporary directories.

## To check on the box

- First launch, two L3 presses, quit, new game.
- Bluetooth disconnect/reconnect and controller change.
- Back to the UI: the daemons detect processes, not focus.
- Bezels are not synchronised. Disable the DS/3DS bezel to show the whole
  game in single-screen mode.

melonDS reads its own memory and needs `ptrace_scope=0` on the host. The
dynamic offset search is not guaranteed for future melonDS versions. See each
pack's README.
