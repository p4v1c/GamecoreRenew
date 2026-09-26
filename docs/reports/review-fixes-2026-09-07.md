# Fixes for the eight review points — 2026-09-07

Base: `ff1e352`, branch `feat/boot-console`. No merge, push, deploy, session
change or box reboot. This report refines and corrects the two previous ones.

| # | Fixed behaviour | Verification |
|---|---|---|
| 1 | Installing the session leaves the kiosk system service intact. The selector disables and masks it only when a session is explicitly chosen, keeping the current process until it exits. The launcher also recognises an already-running system kiosk. | install into a temp tree; arming with mocked systemctl; file backup and restore |
| 2 | The playtime migration uses a SAVEPOINT and individual statements. An error or rollback returns to the previous schema. | SQLite refuses INSERT, DROP, ALTER in turn; reopen, check data, migrate again |
| 3 | The mapping wizard handles `ended` and socket close during capture/replay, shows an error and leaves the waiting step. | frontend tests with an end event and a close without event |
| 4 | One admin preparation installs the full OTA chain and helper copies. The new updater checks prerequisites before download and writes, then refreshes the session on every OTA, even if already installed. | tests for missing/present prerequisites and preparation in DESTDIR |
| 5 | The restart helper restarts the system backend, then the UI through its owner: user manager for the console, system for the active kiosk. A desktop without UI stays without UI. | three scenarios with a systemctl command log |
| 6 | `start-ui.sh` alone calls `gamecore-xsetup --session`, after resolving X and its cookie. The helper waits for a connected output and applies the preference, or 1080p. The backend no longer changes the mode; SDDM's no-arg call is a no-op. | 720p preference, mode already right, output initially disconnected, legacy SDDM call |
| 7 | The synchronous ROM scan runs in `asyncio.to_thread`. | a blocked scan does not stall another coroutine |
| 8 | Only a successful systems response validates boot, empty list included. An error keeps the gate shut; BootRecovery offers a reload after its existing error delay. | HTTP failure then empty success; boot gate tests |

## First update of an old install

The old updater (from `main`) cannot gain new sudo rights or run the check
added here retroactively. No sudoers workaround is added. Run this preparation
before the first update, **from the new files**. It does not arm the console
and restarts no GameCore service.

```bash
# From the checkout carrying these fixes, not the old /opt/GameCore.
sudo bash install/steps/setup-gamecore-session.sh "$USER" /opt/GameCore /userdata 8765
```

Later updates use the allowed unit `gamecore-session-migrate.service`. A
missing preparation makes the **new** updater fail before replacing code, and
it prints the command to run. The preparation also installs
`gamecore-session-select`, `gamecore-emu`, `gamecore-xsetup`, the
migrate/restart helpers, the units and sudoers. Migration arguments come from
the installed manifest — no complex shell interpolation in ExecStart and no
caller-supplied parameters.

Back up playtime **before the first update** (it may restart the backend and
migrate the DB). Use a consistent SQLite backup, safe while the DB is open,
not a copy that ignores the WAL:

```bash
mkdir -p "$HOME/verif-avant"
sqlite3 /userdata/config/playtime.db ".backup '$HOME/verif-avant/playtime-before-console.db'"
```

The migration is atomic, but the new schema is incompatible with the old code:
a code rollback needs that backup. Restore with the backend stopped; games
counted since the backup are lost. Never overwrite an open DB.

## Rollback

The preparation keeps the first state of every replaced file in
`<player-home>/verif-avant/gamecore-session/`, with exact `restore.sh`
commands; a second preparation does not overwrite them. Each later selection
creates its own `gamecore-session-switch.*` directory (SDDM config, previous
unit and its enablement), path printed at run time. Backups survive
uninstall.

- Undo one selection: run its `restore.sh` as admin.
- Back to the original kiosk: leave the console session, restore the
  selections' snapshots in reverse order, run the preparation's `restore.sh`,
  then `sudo systemctl daemon-reload` and `systemctl --user daemon-reload`.
  Empty unit directories may remain; they enable nothing. The historical copy
  `gamecore-ui.service.pre-session` stays. Linger is not touched.

None of these rollbacks was run on the real box; restore was tested in a temp
tree only.

## Hardware limits

To validate with the owner: visual continuity, KWin/Flatpak, emulator focus,
session switch and return to desktop, real screen, physical pads and hotplug.
A saved resolution the screen refuses keeps the current mode and logs it; no
unconfirmed mode is persisted. The mode is restored when the UI starts, not on
a lone backend restart.

Controllers: always diff configs before/after. melonDS declares
`maxPlayers: 1`; test its player and the L3 toggle separately from Dolphin and
DuckStation P1/P2. Layout packs are not redeployed into the home by a code
OTA alone.

## Results

- Ruff, ShellCheck 0.11.0, `check-catalog`, `gen-catalog --check`,
  `git diff --check`: OK.
- Python suite: **1770 passed**, 5 skipped, 4 deselected (`network`).
- Frontend: **328 passed**, TypeScript and Vite build OK.
- Electron: both bench files, **14 cases**, pass.
- Backup adjustments: **33 targeted tests passed**.
- Isolated SQLite counter-test: injecting an error before ALTER fails on
  `ff1e352`'s function and passes on the fixed one. The mapping failure was
  also reproduced during review, then passed with the new tests.

The Python suite uses temp data roots and HOME and stubs power commands. It
ran outside the sandbox (which blocks TestClient/aiosqlite thread exchange).
ShellCheck was downloaded to `/tmp/gamecore-shellcheck-review`; logs and
counter-tests under `/tmp/gamecore-*`.
