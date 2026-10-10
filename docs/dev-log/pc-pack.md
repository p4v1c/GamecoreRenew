# PC games (Lutris pack): dev log

## Status

Pack written (`catalog/lutris/`), on branch `claude/modest-noether-4ipr9j`, not
merged. Install, library, launch, media and the host extension rule are done,
unit-tested, and checked against the real Flathub Lutris (0.5.22) on an Ubuntu
VM with Xvfb: install through the provider, Lutris reading our config and our
GE-Proton folder, and a full launch of a native test game through the session
wrapper. Not exercised: a Wine game, a real GPU, gamemode on Arch, the GE-Proton
download (GitHub releases unreachable from here). See "Not verified".

## What was built

| Piece | Files |
|---|---|
| pack | `catalog/lutris/pack.json`, `logo.png` (the monitor icon from `pc-pack-tools/logo.png`) |
| GE-Proton + Lutris defaults | `files/lutris_setup.py` (CLI), `files/lutris_proton.py`, `files/lutris_defaults.py`, `files/lutris_paths.py`, `files/gamecore-lutris-setup.{service,timer}` |
| library | `generator.py` (`sync_library` hook), `files/lutris_library.py`, `backend/services/pack_library.py`, `backend/routers/games.py` |
| launch | `files/lutris_session.py` |
| media | `scraper.mediaAlias: ["pc windows"]`; `.lutris` never hashed (`backend/services/gamemedia/ss_client.py`) |
| host UI | `roms.showExtension` (schema) → `ext: ""`; `DefaultLibraryView.tsx` and Summer `views/library.js` print nothing for an empty ext |
| pack model | `roms.showExtension`, `hostAccess.gamemode` (`backend/services/installer/host_access.py`), generator hook `sync_library` |
| docs | `docs/architecture/10-catalog-and-install.md` "PC games (Lutris)", `04-backend-services.md` `pack_library.py`, README "PC games (Lutris)", CHANGELOG |

## What was verified, and how

Sources read, not guessed (clones under `/home/user/research`, `/home/user/lutris`,
`/home/user/flathub` in the session that wrote this):

- **Flatpak target**: Flathub **stable** (what `flatpak install flathub
  net.lutris.Lutris` gets; branch `master` at `5a74a8b`) builds Lutris
  `159d7a21` = **0.5.22**, GNOME 49, base `org.winehq.Wine` stable-25.08. The
  `beta` branch (`067090ef`) builds **0.5.23** on GNOME 51 / Wine 26.08. Every
  fact below was read in both versions and holds in both. finish-args already give `--filesystem=home`,
  `~/Games`, `--device=all`, x11 + wayland, `xdg-data/umu:create`.
- **32-bit / Vulkan**: the manifest declares `org.freedesktop.Platform.GL32`
  (`download-if: active-gl-driver`, so the right one for the host driver is
  pulled with the app, NVIDIA included) and `org.freedesktop.Platform.Compat.i386`
  (auto-downloaded). No host lib32 package is needed for the Flatpak.
  If Compat.i386 is missing, the Flatpak's own wrapper (`lutris_wrapper.py`)
  opens a GTK window instead of starting Lutris: worth checking with
  `flatpak list` on the box if a launch shows a window.
- **Config location** (`lutris/settings.py`): `CONFIG_DIR = ~/.config/lutris`
  only if it exists, else `DATA_DIR = ~/.local/share/lutris`. In the Flatpak
  that is `~/.var/app/net.lutris.Lutris/data/lutris` on a fresh box. Files:
  `runners/wine.yml` = `{wine: {...}, system: {...}}`, `system.yml` =
  `{system: {...}}` (`lutris/config.py`). `runner_dir`, `pga_path` in
  `lutris.conf` [lutris] override the runner and DB paths; both honoured.
- **Where GE-Proton goes** (`lutris/util/wine/proton.py`): Proton builds are
  listed from `settings.WINE_DIR` = `<runners>/wine/` (any folder holding a
  `proton` script; key = folder name) and Steam's folders. `runners/proton/` is
  legacy: migration `migrate_proton_to_wine_dir` moves it into `runners/wine/`.
  A Proton version is run through umu (`PROTONPATH=<that folder>`).
- **Lutris's own default** is the sentinel `ge-proton` (umu downloads the latest
  GE-Proton at the first game start, then checks for updates at each start).
  Decision: pin our pre-fetched build instead. The first game would otherwise
  sit on a black screen during a ~500 MB download, and every start would ask
  GitHub. Owner choices are kept: `version` is written only when absent, or
  when it still names a build this pack installed (state file).
- **GE-Proton release assets** (`proton-ge-custom` `Makefile.in` `redist`,
  `.github/workflows/release.yml`): `<tag>.tar.gz` with one top folder `<tag>/`,
  and `<tag>.sha512sum` (`sha512sum` output). Latest tag via the
  `/releases/latest` redirect, API as fallback. Latest tag at writing: GE-Proton11-7
  (`git ls-remote`). Wine-GE is discontinued; nothing uses it.
- **umu needs Lutris's GUI once**: `get_umu_path()` finds umu in `/app/share`
  (not built in the Flatpak) or Lutris's runtime dir, which the runtime updater
  fills only when the main window opens (`application.py`: `start_runtime_updates`
  is on the window path, never on `lutris:rungameid`). Without umu no Proton
  version is listed. The owner opens Lutris to install games anyway, so this is
  met in practice; the README says to let that first download finish.
- **Runner options** (`lutris/runners/wine.py`, `lutris/sysoptions.py`):
  `dxvk`, `vkd3d`, `esync` default true, `fsync` default = kernel support,
  `gamemode` default = `gamemoderun` on PATH (it is, `/app/bin`). Written
  explicitly anyway (only where absent): intent visible, and survives a failed
  detection in the sandbox. `game_path` (default install folder) set to
  `<data>/emu/lutris-games` (big data disk, inside the default sandbox grant;
  `emu/` is outside the OTA rsync).
- **gamemode**: the Flatpak builds gamemode 1.8.2 (64 and 32-bit client) and
  reaches the host daemon through xdg-desktop-portal (a dependency of the Arch
  `flatpak` package). Host needs `gamemode` (daemon, D-Bus activated).
  `lib32-gamemode` is NOT added: only host 32-bit programs use it, and it lives
  in [multilib], which `arch.sh` does not guarantee; one `pacman -S` with it
  would fail the whole `packages` line on such a box. gamemode's polkit policy
  (`com.feralinteractive.GameMode.policy`: `allow_active no`) lets only the
  `gamemode` group change the governor, hence `hostAccess.gamemode`.
- **Winetricks** is bundled in the Flatpak; nothing added.
- **Library**: `pga.db` table `games` (`id, name, slug, runner, service,
  installed`) and the `.hidden` category (`lutris/database/schema.py`,
  `categories.py`). Covers `<data>/coverart/<slug>.jpg`.
- **Launch** (`lutris/gui/application.py`): `lutris:rungameid/<id>` with no
  visible window and no tray icon sets `quit_on_game_exit`, launches with the
  window-less delegate (primary launch config, no dialog) and quits when the
  game stops. It is a `Gtk.Application`: a second start while one runs is
  forwarded over D-Bus and returns at once. Every game runs under
  `share/lutris/bin/lutris-wrapper`, retitled `lutris-wrapper: <name>`
  (setproctitle is in the Flatpak), a subreaper that waits for the game's
  whole tree. No `setsid` anywhere on that path.
- **ScreenScraper**: systems 135 PC Dos (recalbox/retropie "pc"), 136 Win3.xx,
  137 Win9X, **138 PC Windows** (LaunchBox "Windows"), from the
  `screenscraper_platforms.json` Skyscraper ships (same data as
  `systemesListe.php`). So the alias is `pc windows`, never `pc` (= DOS).
  Test: `backend/tests/test_pack_library.py`.

## Checked against the real Flatpak (Ubuntu 24.04 VM, flatpak 1.14.6, Xvfb)

Scripts in `pc-pack-tools/real-lutris/`; the test user was `gcplayer`.

| Check | Result |
|---|---|
| `gamecore-provider.py install lutris --user gcplayer` | `net.lutris.Lutris` installed (stable, 0.5.22) with `Platform.Compat.i386`, `GL.default`, `GL32.default` 25.08 pulled automatically; `flatpak override` applied (filesystem = install root, devices all, x11); `gamecore-lutris-setup.{service,timer}` written with tokens expanded and the timer enabled. pacman and `hostAccess.gamemode` failed as expected on Ubuntu (no pacman, no `gamemode` group) and were reported, not raised |
| `lutris_setup.py` as the player | GitHub answered 403 (this sandbox's proxy): logged, exit 1, defaults still written to `data/lutris/runners/wine.yml` and `system.yml`, no `config/lutris` created |
| Lutris starting on that home | used `data/lutris` (no `config/lutris`), kept our `system.yml`/`wine.yml`, created `pga.db` with the columns and the `categories`/`games_categories` tables the sync reads |
| Lutris's own view (in the sandbox, `lutris.util.wine.proton`) | a `GE-Proton11-7/` folder (with `proton`, `files/bin/wine`) in `runners/wine/` is listed as a Proton version once umu exists; with `version: GE-Proton11-7` written by `lutris_defaults.apply`, the wine runner resolves that version; `dxvk`, `vkd3d`, `esync`, `fsync`, `gamemode`, `game_path` read back as written |
| launch premise | with Lutris's window open, a bare `flatpak run net.lutris.Lutris lutris:rungameid/1` returned after **0.8 s** (forwarded over D-Bus) |
| `lutris_session.py` on a native test game (`linux` runner, `/usr/bin/sleep 6`) | `exit=0 elapsed=9.6` s: Lutris without a window, the game followed through `lutris-wrapper`, Lutris quit on its own after it |
| same, Lutris window already open | "closing an idle Lutris first", then the same 9.6 s session, no instance left |
| GameCore's kill (SIGKILL to the session's process group) | `lutris-wrapper` and the game ran **in the session's group**; after the kill no game process and no Flatpak instance were left |
| real `lutris-wrapper` cmdline | not retitled in the sandbox (`python3 /app/share/lutris/bin/lutris-wrapper Sleeper 0 0 gamemoderun ./sleep 6`): the script-path match in `is_game_cmdline` is the one that fires. `gamemoderun` is there: our `gamemode: true` reached the launch |

No container test: Docker Hub answered 429 to the Arch image pull, and a
privileged container (needed for bwrap) was refused in this session.

## Decisions

- **Library = stubs** in `emu/lutris/` (`<Title>.lutris`, JSON with the Lutris
  id), refreshed by a generic pack hook before each listing. Everything keyed
  by file name (covers, playtime, favourites, media, themes, launch path
  check) then works unchanged. The name is chosen once per Lutris id and kept,
  so a rename in Lutris keeps its hours; a reinstall (new id, same title)
  takes its old stub back. Stubs are removed only when the DB was read.
  Lutris covers are copied into GameCore's cover cache when it has none.
- **Launch = a wrapper session** (`lutris_session.py`) rather than bare
  `flatpak run`: closes an idle Lutris first (forwarding), follows the game by
  its `lutris-wrapper` process, closes a Lutris lingering 10 s after the game.
  The tile is `python3 lutris_session.py --app-id @APPID@`, so the app id is
  still resolved at launch; GameCore kills the wrapper's process group, which
  holds flatpak/bwrap and so the sandbox.
- **GE-Proton by a user timer** (like RPCS3's), not `postInstall`: postInstall
  is capped at 300 s and a ~500 MB download does not fit on a slow line. The
  timer retries daily and picks up new releases; two of our builds are kept,
  plus any a game config names.
- `perGame` / `profileSaves`: `supported: false`, reasons in pack.json.

## Pack-model gaps found

- None needing `arch.sh`. Two small extensions instead, with tests and docs:
  `roms.showExtension` and `hostAccess.gamemode`; one generator hook,
  `sync_library`.
- Opening Lutris's window from the couch: no tile does it. Installing games
  is done from the desktop (Settings → Desktop). Launching the tile with no
  ROM would open it (`lutris_session.py` without a stub), but no UI sends that.

## Not verified (cannot run here)

- A Wine/Proton game (no GPU, no umu runtime download here), DXVK/VKD3D at
  work, umu's first-run download of the Steam runtime.
- GE-Proton's real download and unpack: github.com release URLs are blocked
  from this sandbox. The redirect parsing, checksum and unpack are unit-tested
  on a tarball built like GE's.
- gamemode on Arch: the `gamemode` group, polkit, the portal path from the
  Flatpak to gamemoded. Group membership takes effect at the next login.
- Suspend (SIGSTOP to the group) during a Wine game; the group was verified
  for a native game only.
- A Lutris lingering after its game (the 10 s close path) was not reproduced;
  it is unit-tested.

## How to test

```bash
python3 -m pytest catalog/lutris backend/tests/test_pack_library.py \
  backend/tests/test_host_access_gamemode.py -q
cd frontend && npx vitest run src/components/LibraryScreen/libraryExtension.test.tsx
```

On a box: install PC, wait a minute after login, then
`systemctl --user status gamecore-lutris-setup.service`,
`ls ~/.var/app/net.lutris.Lutris/data/lutris/runners/wine/`,
`cat ~/.var/app/net.lutris.Lutris/data/lutris/runners/wine.yml`,
`groups` (gamemode, after re-login). Install a game in Lutris, open PC in
GameCore, start it; `logs/launch/lutris/` has the wrapper's lines
(`[gamecore-lutris]`). `gamemoded -s` while the game runs says active.

## Screenshots

`pc-pack-tools/shots/`, taken with `pc-library-shots.cjs` against devserve with
a fake Lutris home (`pc-fixture.py`): the stubs and covers in them were
written by the real sync, not mocked. Covers are drawn placeholders.

| File | What it shows |
|---|---|
| `default-library.png` | default UI: PC library, no extension line, no chip |
| `summer-library.png` | Summer: same, cover from Lutris's coverart |
| `shelf-home.png`, `shelf-library.png`, `shelf-reverse.png` | Shelf: PC on the console row (the monitor logo, no hardware photo), the PC case with the disc, the printed reverse with no media |
| `orbit-home.png`, `jelly-home.png` | PC games among the others on Orbit and Jelly homes |

## Next

- Jelly drawn 3D box fallback (optional, not started).
