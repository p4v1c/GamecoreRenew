# Rest mode (dev log)

Branch: `claude/rest-mode`, from `origin/main` at `05bef90`. Never pushed to
`main`, no PR: a push to `main` publishes an OTA release. The owner merges.

## Goal

PS5-style sleep. The power menu leads with **Rest mode**: close every game and
app (suspended ones too), check nothing is left, suspend (deep sleep), wake on
the pad's PS button over Bluetooth, replay the theme's boot animation with its
sound, land on Home. **Turn off**, **Restart** and **Return to desktop** stay
as they were.

Owner's box: GMKtec, Ryzen 6000 / 680M, Manjaro, kernel 6.12, Plasma X11,
`mem_sleep` = `s2idle [deep]`, Intel AX200 (8087:0029). Wake measured by hand
with `power/wakeup=enabled` on the adapter's USB device + BlueZ
`WakeAllowed=true` on the pad + `systemctl suspend`.

## Where I stopped

**Done, pending the owner's test on the box.** Backend, system pieces, menu in
all five themes, wake replay, Electron window, docs, screenshots: committed
and pushed. Next step is the owner's: update the box from this branch's
release once merged, open the Power menu, Rest mode, press PS.

What the owner should check on the box (cannot be done here):
1. `systemctl status gamecore-wake.service` ran at boot; `journalctl -u
   gamecore-wake` names the AX200 (8087:0029) as "wake enabled".
2. `cat /sys/class/bluetooth/hci0/device/../power/wakeup` says `enabled`.
3. `busctl get-property org.bluez /org/bluez/hci0/dev_XX… org.bluez.Device1
   WakeAllowed` says `b true` (set by the backend, `journalctl -u
   gamecore-backend | grep bt_wake`).
4. A game running, Rest mode: the game closes, the box sleeps, PS wakes it, the
   theme's boot plays with sound, Home is shown, the pad works.

## Decisions

| Question | Choice | Why |
|---|---|---|
| Who suspends | The backend (`services/rest_mode.py`), `sudo -n systemctl suspend` | It owns the sessions: kill, verify and suspend in one place, no renderer round trip between "nothing is running" and "sleep". |
| Kill | `process_manager.kill()` per session (group SIGKILL, `flatpak kill`, SIGCONT first for frozen ones), then poll each process group; SIGKILL again after 8 s, sleep after 2 s more | Same kill as the session bar; the group covers Lutris/Steam children that share it. |
| Launch race | `launch.close_gate()` from the first step until the wake; a launch already preparing gets 15 s to spawn so the sweep sees it | A launch pressed just before the menu must not start a game after the sweep. |
| Resume signal | logind `PrepareForSleep(false)` via `gdbus monitor --system` in the backend (`services/resume.py`) | Sent for every suspend (menu, power button, desktop); unprivileged; the backend has to act anyway (screen, pads, gate). The UI follows over WS (`power:resumed`) and re-checks `GET /api/power/state` on reconnect. Electron's `powerMonitor` only re-asserts its own window. |
| sysfs wake | Root helper `gamecore-wake-setup` (bash), boot unit `gamecore-wake.service`, udev rule for hotplug | `power/wakeup` is root-only and resets at boot/replug. Pads are told apart with the backend's rule (BTN_SOUTH, not a keyboard), mirrored in bash and pinned by a test that runs both. |
| BlueZ wake | Backend `services/bt_wake.py`, `busctl set-property … WakeAllowed b true` | Any user may set it on the system bus. Runs at start and whenever a pad not seen before joins the roster, which covers pads paired later. Pads = paired with `Icon` input-gaming, or MAC on GameCore's roster; keyboards/mice never. |
| Install path | `install/steps/setup-rest-mode.sh`, called from `setup-gamecore-session.sh` | arch.sh runs that step, and every OTA runs it through `gamecore-session-migrate.service`. The old installed migrate helper execs the step from the freshly rsynced tree, so the first update lands everything. |
| Menu | `rest` row first in `PowerModal.OPTIONS`, cursor opens on it (also when "In the background" leads); "Shut down" renamed "Turn off" as the owner listed it; two presses like every row | Every theme draws the host's rows (`createPowerView`), so each theme dresses it in its own CSS with no theme code. No SDK surface added, so no SDK bump. |
| Refusal | 503 sentence shown in the Rest row's subtitle | No new view prop: every theme already draws `desc`. |
| Wake replay | `store.wake()` bumps `wakeCount`; `App.tsx` re-keys the splash, `DefaultShell` closes its modals | Themes' splashes play `sdk.system.playSound('boot')` on mount, so a remount replays the sound. |
| Jelly | confirm row ink, icon and pad glyphs white (1.6.2) | Rest mode made the confirm row the common case; it measured 1.2-2.5:1. |

## Verified (and how)

- Backend: `test_rest_mode.py` (every session gone before suspend, frozen ones
  thawed then killed, lingering group forced, in-flight launch waited for and
  killed, launches refused until the wake, refused suspend reopens, router),
  `test_resume.py` (gdbus lines, wake steps in order, one failing step does not
  stop the others, fake `gdbus` process), `test_bt_wake.py` (pads only, never
  keyboard/mouse, roster MACs, busctl calls, new pad triggers a pass),
  `test_display_restore.py`, `test_wake_setup_helper.py` (the bash helper on a
  fake sysfs: adapter + pads armed, keyboard/mouse/virtual not, idempotent,
  udev mode, agrees with `is_pad_keys`), `test_rest_mode_install.py` (DESTDIR,
  idempotent, sudoers exact line and mode 440, OTA path through the session
  step, rollback records the new files).
- Frontend: `PowerModal.test.tsx`, `lib/wake.test.tsx`, shelf/ui tests.
- Electron: `electron/test/power.test.cjs` (commands, resume re-fullscreen and
  focus, nothing when a session owns the screen).
- Screens: `rest-mode-tools/power-shots.cjs` on devserve, all five themes,
  reviewed twice (Jelly's confirm row fixed after pass 1). Legibility audit,
  power menu open / confirm / with a suspended game: 0 FAIL in all five.
- Pre-push list (ruff, shellcheck, gen-catalog, check-catalog, pytest, tsc,
  vitest, electron bench, check-theme jelly, theme versions, check-docs,
  file size): see the commit; pytest fails only the 4 known tests on `main`.

Shots (960x540): `rest-mode-tools/shots/<theme>-power.png`, `-power-confirm`,
`-power-bg` (a suspended game: the session row leads, the cursor is on Rest
mode), `-wake-splash` (the boot replaying after `power:resumed`),
`default-power-refused.png`, `default-wake-home.png`.

## Not verified

- Real suspend and resume: this VM cannot sleep. Process kills, suspend, gdbus,
  busctl, sysfs and powerMonitor are all fakes in the tests.
- That the PS button wakes the box with these settings: measured by the owner
  by hand with the same two settings, not with this code.
- Boot sound after a real wake (AudioContext after resume), display mode and
  window focus after a real resume, NetworkManager reconnecting (GameCore does
  nothing for it; the settings pages refetch when opened).
- `systemctl suspend` through the new sudoers rule; `visudo` on the real file.
- A sleep started outside GameCore (power button, KDE) leaves games running;
  the wake still lands on Home, the game stays in the session bar.
