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

Milestone 1 (backend + system pieces) committed. Next: frontend menu, resume
replay, Electron window, docs, screenshots.

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

## Verified (and how)

- `pytest backend/tests/test_rest_mode.py test_resume.py test_bt_wake.py
  test_display_restore.py test_wake_setup_helper.py test_rest_mode_install.py`:
  fakes for processes, signals, suspend, gdbus, busctl and sysfs.
- Install step run with `DESTDIR` twice (second run changes nothing) and
  through the session step (the OTA path).

## Not verified

- Real suspend/resume: this VM cannot sleep. Everything around it is faked.
