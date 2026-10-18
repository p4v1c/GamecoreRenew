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
5. `systemd-inhibit --list` shows GameCore's `sleep` delay lock; a game
   running, then `systemctl suspend` from SSH: the game is gone after the wake.
6. In the GameCore session, `systemd-inhibit --list` shows nobody holding
   `handle-power-key`; a short press of the case button sleeps (games closed).
7. `systemd-analyze cat-config systemd/logind.conf` shows `90-gamecore.conf`.

## Follow-up: every sleep closes the games, and the power key

The owner asked for games to be killed on every way the box sleeps (power
button, KDE menu, idle, `systemctl suspend` from anywhere), and for a short
press of the case button to be Rest mode.

| Question | Choice | Why |
|---|---|---|
| Hook | logind delay lock for `sleep`, held by `systemd-inhibit --what=sleep --mode=delay … cat` (`services/sleep_guard.py`) | The lock is an fd; `cat` keeps `systemd-inhibit` alive until its stdin closes, so releasing is closing a pipe, and a dead backend releases it too. No D-Bus binding needed, same subprocess style as `resume.py`. Delay locks for sleep need no privilege. |
| When | Taken while the gdbus monitor runs (released if it dies, so sleeps are never delayed for nobody); on `PrepareForSleep(true)`: gate, Rest mode's sweep with 6 s + SIGKILL + 2 s, bounded at 12 s, release in `finally`; on the wake: sweep again, take it back | A sleep that outran the lock (logind's own limit) or a launch that slipped in is closed before the UI comes back, so the wake never lands in a game. |
| Budget | `InhibitDelayMaxSec=15` in `/etc/systemd/logind.conf.d/90-gamecore.conf` | logind's default 5 s is shorter than one Flatpak's `flatpak kill` plus a grace. 15 s is the most a sleep waits, normally well under 1 s (SIGKILL is immediate). |
| Rest button | Unchanged path: it sweeps with its long waits, then `systemctl suspend`; logind's `PrepareForSleep(true)` makes sleep_guard sweep an empty box and release | No double kill (nothing left), no deadlock (the sweep never waits on systemctl). Tested with both in one run. |
| Power key | `HandlePowerKey=suspend` in the same drop-in | In GameCore's session the compositor is a bare `kwin_x11` (`install/bin/gamecore-session`) and nothing starts PowerDevil (see `services/desktop_power.py`), so nobody takes the `handle-power-key` lock and logind acts: a sleep, with games closed by the lock. In a Plasma desktop session PowerDevil holds the key and its own setting applies. `HandlePowerKeyLongPress` is left alone; the 4 s hold is the firmware's force-off anyway. |
| Applying it | `systemctl reload systemd-logind` only if the unit says `CanReload=yes` (systemd 254+, SIGHUP); otherwise at the next boot. Never a restart | Restarting logind ends every session, the TV's included. On a logind that does not handle SIGHUP, the signal would kill it, hence the check instead of a bare `systemctl kill -s HUP`. |

Verified with fakes: `test_sleep_guard.py` (lock held and released by EOF,
sweep then release, release even on a slow or failing sweep, wake sweeps
again and re-locks, button + lock together kill once), `test_resume.py` (lock
while listening, sweep on the sleep line before the wake's steps),
`test_rest_mode_install.py` (drop-in installed, idempotent, exact keys, logind
reloaded only when it can be, never restarted). Not verified: a real logind
holding a real sleep for the lock, the real power key, PowerDevil in the
desktop session, `systemctl reload systemd-logind` on Manjaro's systemd.

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
- A sleep started outside GameCore now closes games through the lock (see the
  follow-up), verified with fakes only.

## Follow-up 2: the TV misses the start of the animation (`claude/wake-display`)

Rest mode works on the box (PR #149: PS wakes it, games closed). On wake the
splash started at once while the TV was still re-syncing HDMI, so the owner
saw only its end. Branch `claude/wake-display`, from `origin/main` at `7a44855`.

| Question | Choice | Why |
|---|---|---|
| Stale frame | A plain black layer in `App.tsx` (z 9600, over the splash) from the sleep to the wake. Set by Rest mode's second press locally, and by `power:sleeping`, which `resume.py` sends on `PrepareForSleep(true)` for every sleep path | The TV must never show the menu from before the sleep, and games close behind black. |
| When is the screen back | `/sys/class/drm/card*-*`: `status` connected, `enabled` enabled, `dpms` On, polled every 200 ms (`services/display_ready.py`), at most 10 s, then on anyway | amdgpu updates these as soon as it re-senses the TV and a mode is set. No X connection or privilege needed (X is the slowest thing to come back, and the backend's X access is a guess at that moment), and nothing to subscribe to. xrandr would need DISPLAY and can block; a udev monitor would need a second subprocess for a 10 s window. |
| After the link | Display mode restored (needs the output re-sensed), then `wake_settle_secs` (default 2.5 s) | A TV shows "no signal" a moment after the link is up; the sysfs files can also still read "lit" from before the sleep for an instant. The delay covers both. |
| Setting | `standby.json` `wake_settle_secs`, 0-8 s, clamped in `save_config`; Settings → System row "Wait for the TV after waking" (`frontend/src/settings/system.js`, steps 0, 1, 1.5, 2, 2.5, 3, 4, 5, 6, 8 s) | Every TV differs. The shared settings page is what all five themes draw, so one row reaches every theme. The legacy `SettingsModal`/`StandbyPage` is not used by any shipped theme and was left alone. |
| Announce | The wake count grows and `power:resumed` goes out only after the settle delay; `GET /api/power/state` adds `sleeping` | A client reconnecting mid-wake must not start the splash early, and must drop a black layer the backend no longer stands behind (`syncWake`). |

Verified, with fakes: `test_display_ready.py` (connector rule, waits for a
fake sysfs to come back, gives up at the bound and wakes anyway, no DRM means
no wait, setting clamped 0-8 and saved), `test_resume.py` (order: sweep, gate,
screen, link, mode, settle, then `power:resumed`; count and `sleeping` move
only after the wait; the settle is waited before the announcement;
`power:sleeping` before the sweep), `wake.test.tsx` (layer up on
`power:sleeping`, down with the wake; kept while the backend still waits;
dropped when the backend no longer sleeps), `PowerModal.test.tsx` (Rest mode
sets the layer, a refusal drops it), `settings/wakeSettle.test.tsx` (row
reached and changed with the pad, saves `wake_settle_secs`).

Screens (`rest-mode-tools/wake-shots.cjs`, devserve): `shots/wake-setting-<theme>.png`
for all five themes, the row focused at 2.5 s; `shots/wake-black-default.png`
(every theme's frame measured all pixels 0); `shots/wake-splash-start-orbit.png`
and `-jelly.png`, the splash's first frames after `power:resumed`. Reviewed:
the row matches its neighbours in every theme (it is the same row type as
"Screen off after"); the first draft's description was two lines long in Orbit
and was shortened. A legibility audit was not run on this row (the audit tool
cannot reach the System page by itself); it reuses the row style the audit
passed before.

Not verified: what amdgpu's sysfs reports during a real resume on the 680M
(whether `enabled`/`dpms` go through a not-ready state, or whether only the
settle delay does the work); the right default for the owner's TV; the boot
sound after a real wake.

Found on the way: the full suite hung in a `TestClient` teardown, about one
run in two. The logind monitor loop (`resume.run`, from PR #149) could lose
its cancellation inside `sleep_guard.release()` (Python 3.11 `wait_for`
swallows a cancel that lands as it completes), then slept 30 s and restarted,
so the lifespan waited forever. The loop now re-raises a pending cancel and
every wait on the lock's helper process is bounded; `test_resume.py` has a
test that fails without the fix. On the box this would have shown as a
backend that does not stop on `systemctl stop`/OTA restart until systemd's
timeout.

## Follow-up 3: wakes by itself, picture before the splash (`fix/rest-mode-wake`)

Owner, TCL TV, 16/10: Rest mode woke at once, five times in a row; the
picture came back (Home with black polygons) before the animation.

| Finding | Evidence |
|---|---|
| A Bluetooth device paging the box wakes it | Each immediate wake: bluetoothd `Authorization request for non-connected device!?` as user space freezes, then the Xbox Wireless Controller (045e:02fd) back 40-60 ms after the resume. Same line on 15/10 13:44: the Bluetooth mouse woke the box. DS4-only sleeps on 14/10: no such line, they held for hours. |
| The kernel's disconnect is not a console's | Kernel 6.12 `hci_suspend_sync` disconnects every link with "power off" (0x15) before arming the wake filter (the `ACL packet for unknown connection handle` lines); the Xbox pad pages straight back, the DS4 does not. BlueZ `Device1.Disconnect` ends the link with 0x13 "remote user terminated" (source: BlueZ 5.87 `disconnect_all()` → `MGMT_OP_DISCONNECT`, kernel `disconnect_sync()` → `hci_abort_conn(conn, HCI_ERROR_REMOTE_USER_TERM)`; the L2CAP idle drop uses the same `disc_reason`). An earlier draft of this log said a GameCore disconnect would repeat the kernel's: wrong, the reason differs. Built: `bt_wake.turn_off_pads()` in `sleep_guard.before_sleep()`. |
| The mouse has `WakeAllowed` | BlueZ's default for HID devices, not `bt_wake.py`. |
| The menu came back as the box fell asleep | `POST /api/power/rest` is in no access log, ever: Chromium drops every socket as NetworkManager sleeps (WebSocket 1006 in the same millisecond). The fetch error was taken for a refusal, the black layer lifted, and that frame went to sleep with the box. |

Fixes: `services/wake_source.py` logs the wakeup sources whose `event_count`
moved across the sleep; a `TypeError` from Rest mode's POST keeps the black;
`syncWake()` puts it back while the backend says `sleeping`/`resting`; the
shell relays `powerMonitor` `resume` (`onResume`, black at once) and calls
`webContents.invalidate()`; `hooks/useWakeSplash.ts` derives "splash done"
per wake so the splash renders in the frame the black goes.

Screens (headless Chromium, devserve, a script that kills the POST like the
box does): every theme, before and after, in the owner's
`~/Downloads/rest-mode-wake/shots`. Before: the menu is back after the
press on all five themes. After: 0.0 % lit pixels after the press and after
the shell's resume, the theme's splash from its first frame 50 ms after
`power:resumed`.

Not verified: a real suspend (not run on the box). That 0x13 turns the Xbox
pad off is its firmware's behaviour, not readable in any source: the
`wake_source` line after the owner's test says whether it held.
