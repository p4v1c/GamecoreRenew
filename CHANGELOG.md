# Changelog

**This is not the release log.** Every push to `main` is tagged and published
automatically with generated notes — read those for "what changed":
<https://github.com/p4v1c/GamecoreRenew/releases>. Duplicating them here would
produce a second source of truth that goes stale on the next push, which is the
failure mode this project keeps paying for.

What this file records is the short list the generated notes cannot: **changes
that need something from the operator**, and changes to how the project is put
together. If updating a box requires you to do anything, it is written here.

The format is loosely [Keep a Changelog](https://keepachangelog.com); versions
are the auto-incremented tags.

---

## Unreleased

### Needs action on an already-installed box

- **`/usr/local/bin/gamecore-addon` is a copy only the installer writes, and
  it is stale on every box installed before 9 August.** The OTA cannot replace
  it (root) and now says so with the command; the copy that runs today does
  not know `GAMECORE_DATA` at all. Harmless while the data still lives inside
  the install, and the thing that would split the box the day it does not — a
  `gamecore-addon update` from the old CLI would bake the old root into every
  addon's unit. Refresh it once:
  `sudo install -m 755 /opt/GameCore/install/bin/gamecore-addon /usr/local/bin/gamecore-addon`.
  The CLI now also finds the data root on its own, from the backend's unit,
  when the shell that runs it has none — see `docs/architecture/07-config-and-data.md`,
  *Moving the data out*.

- **A bezel per console is now possible, and no bezel is supplied.** One
  emulator is sometimes several machines: mGBA runs Game Boy and Game Boy Color
  in 10:9 and Game Boy Advance in 3:2 behind one system id, so a single frame
  bit into one of them — and the drift correction, keyed by the announced ratio,
  was learned from whichever console was played first and then frozen for all
  three (`for_launch` sets `measure: false` once an answer exists). Measured on
  the reference box: one `mgba@1:1` entry of `1234x1080`, a Game Boy rectangle,
  cutting 193 px off each side of every GBA game.

  **Nothing is required.** `config/systems.json` gains `consoles` through the
  `merge_file()` call the OTA already makes, and the old console-blind
  corrections simply become unreachable, so each console re-measures itself —
  which already makes the *hole* right per console even with the old artwork.
  What no update can deliver is the artwork: `assets/overlays/` is excluded from
  the rsync. To get a frame that actually fits, drop a PNG named
  `<system>.<console>.png` beside the system one — `mgba.gba.png`,
  `dolphin.wii.png`. `docs/reports/bezels-per-console-phase3.md` has the
  verification steps, the backup and the way back.

- **An overlay upload with no transparent area is now refused (422).** A valid
  image with no hole is a rectangle painted over the whole game; every previous
  check passed it. This applies to the existing per-system upload too, which in
  practice means JPEG is no longer usable as a bezel — it cannot carry an alpha
  channel. A PNG copied in by hand is still not validated: the guard is on the
  route, not the filesystem.

- **Stremio launches windowed until its tile is patched.** The `fullscreen` and
  `gamepadTrigger` blocks were lost when the tile moved to a wrapper script, and
  an OTA cannot deliver them: `update/linux.sh` excludes `config/` wholesale and
  only merges `systems.json`, never `apps.json`. A fresh install, or re-running
  `install/arch.sh`, regenerates `config/apps.json` from the shipped catalogue
  and fixes it. Otherwise patch the `stremio` entry by hand.

### Changed

- **A fresh install with its data outside the install now starts with its
  bezels.** `install/arch.sh` seeded the player's starting tree — the shipped
  bezels, `config/overlays.json`, the bundled themes — into the install "when
  absent there"; on a split install (`GAMECORE_DATA=/userdata`, which is what
  the ISO produces) the data directories already existed, empty, so nothing was
  seeded and no game got a frame. Seeding now targets the data root and fills a
  directory that is absent or empty; a populated one is left alone. Same
  decision, three consequences: the addons checkout is pre-created in
  `/opt/gamecore-addons` only on the old layout, the desktop shortcut carries
  the GameCore logo instead of the theme's generic gamepad, and the graphical
  installer asks for the data path (default `/userdata`) when it is not the ISO.
  Boxes already installed are not affected — nothing here runs at OTA time.

- **The power menu offers "Return to desktop".** Leaving the front end is the
  third way a session ends and it was reachable only from Settings → Desktop —
  four rows into a menu nobody opens in order to quit, while the button that
  means "I am done with this box" opened a screen that could reboot it and shut
  it down but not step out of it. Same two-press confirmation and the same
  failsafe as the other two. Every theme gets it; the settings page stays for
  the sentence of explanation the row has no room for.
- **A theme can now set the player's sound and haptics settings, and drop the
  mapping utilities from the power menu.** `sdk.system.sound` and
  `sdk.input.haptics` were read-only, so a theme rendering its own
  Settings → Audio silently removed three controls from the console; they take
  values now. `DefaultShell` also accepts `powerOmit`, letting a theme that
  gives "Scan mapping" and "Forget mapping" a proper home stop showing them in
  the power menu — `restart`, `shutdown` and `desktop` can never be dropped.
  Nothing changes for a theme that asks for neither.
- **Shelf's settings screen is a numbered rail, and Shelf v1 ships beside it.**
  The previous drawer menu is installed unchanged as the separate theme
  **Shelf v1**, selectable from Settings → Themes. It is the fallback if the
  new screen turns out to be awkward on a pad — nothing to restore by hand.

- **The kiosk is hosted on the machine's own X11 desktop session.** openbox is
  no longer installed and is no longer the auto-login target. Closing GameCore
  now reveals a usable desktop instead of an empty root window. Boxes installed
  before this keep their openbox session until `arch.sh` is re-run.
- **`gamecore-session-select` is a kiosk toggle, not a session switcher.** There
  is one session now, so it enables or disables `gamecore-ui.service` and
  touches no SDDM configuration. `gamecore` / `desktop` / `status` unchanged.
- **`install/` is grouped by role** — `bin/`, `system/`, `steps/`, `generated/`.
  After an OTA the old flat copies stay behind in `/opt/GameCore/install/`,
  inert; a clean reinstall avoids them.
- **Emulators and applications install from their pack**, through
  `gamecore-provider.py`. `install/arch.sh` no longer contains a list of
  emulator ids, a Flatpak loop, or the EmberTV/Stremio blocks.

### Fixed

- **The installation ISO booted on nothing — no machine, no firmware, neither
  bootloader.** BIOS showed the syslinux menu, counted down and started over,
  for ever; UEFI said `Error preparing initrd: Not found`. One cause under both:
  every boot entry asked for `intel-ucode.img` and `amd-ucode.img` beside the
  kernel, and archiso stopped putting them there (upstream
  [archiso#226](https://gitlab.archlinux.org/archlinux/archiso/-/issues/226)) —
  the microcode belongs inside the initramfs now, via mkinitcpio's `microcode`
  hook, which this profile did not have either. The boot configs name one initrd
  each and the hook is in place. `intel-ucode` and `amd-ucode` stay in
  `packages.x86_64`: the hook builds the early cpio *from* them.
- **The ISO's initramfs was never built from the ISO's own hook list.** Its
  preset set `ALL_config=/etc/mkinitcpio.conf`, mkinitcpio turns the
  `/etc/mkinitcpio.conf.d/` drop-in off whenever it is given a config file by
  name, and so `archiso.conf` — `archiso`, `archiso_loop_mnt`, `memdisk` — was
  read by nothing. The preset now names the drop-in, as releng's does. This was
  hidden behind the boot failure above and would have surfaced as an emergency
  shell the moment it was fixed alone.
- The graphical installer segfaulted on the first key typed into any field —
  PyInstaller bundled the runner's `libxkbcommon` next to the host's
  `libxkbcommon-x11`. Fixed by a `.spec` that keeps host-provided libraries out
  of the bundle, and by pinning the build's PySide6 and PyInstaller.
- A fresh install died at 4 % (`tar: /opt/GameCore: Cannot open`) and, once past
  that, at 66 % (Firefox kiosk profiles deleted by the catalogue refactor while
  `arch.sh` still read the old path). Only fresh installs were affected, which
  is why neither showed up for months.

### Added

- `ruff` and `shellcheck` in CI, and a single tile builder
  (`backend/services/catalog/tiles.py`) replacing the two that had drifted.
- `docs/architecture/10-catalog-and-install.md` — the catalogue and the install
  pipeline, which the documentation did not cover at all.
- GPL-3.0 licence, `CONTRIBUTING.md`, `.editorconfig`.
