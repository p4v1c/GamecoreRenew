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

- **Stremio launches windowed until its tile is patched.** The `fullscreen` and
  `gamepadTrigger` blocks were lost when the tile moved to a wrapper script, and
  an OTA cannot deliver them: `update/linux.sh` excludes `config/` wholesale and
  only merges `systems.json`, never `apps.json`. A fresh install, or re-running
  `install/arch.sh`, regenerates `config/apps.json` from the shipped catalogue
  and fixes it. Otherwise patch the `stremio` entry by hand.

### Changed

- **The power menu offers "Return to desktop".** Leaving the front end is the
  third way a session ends and it was reachable only from Settings → Desktop —
  four rows into a menu nobody opens in order to quit, while the button that
  means "I am done with this box" opened a screen that could reboot it and shut
  it down but not step out of it. Same two-press confirmation and the same
  failsafe as the other two. Every theme gets it; the settings page stays for
  the sentence of explanation the row has no room for.
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
