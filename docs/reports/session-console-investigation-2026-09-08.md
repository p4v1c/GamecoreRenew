# Leaving to the desktop — investigation state, 2026-09-08 08:45

Written when the box was switched off. Everything below was measured on the
reference box, not inferred.

## Box state

- Deployed **v1.2.31**, autologin **armed on `gamecore`**.
- SDDM not restarted since, so Plasma was still running at shutdown. **Next
  boot opens the console session** with `gamecore-session` v1.2.31 — the one
  that switches in its teardown. The intended test state.
- `/var/lib/gamecore/previous-session` = `plasma`, so "Desktop mode" must
  return to Plasma, not openbox.

## Fixed and proven

### 1. SDDM precedence (v1.2.29)
SDDM reads **every** file in `/etc/sddm.conf.d` whatever its extension; the
last `[Autologin]` by name wins. Our own backup
`zz-gamecore-autologin.conf.pre-session` sorted after the file it backed up,
and a leftover `zz-gamecore-openbox.conf` (Session=plasma, 10 July, not from
this repo) beat both. Both now live in `/var/lib/gamecore/retired-sddm/`, the
backup leaves the directory, and arming verifies its own effect before
reporting success.

### 2. Writing is not applying (v1.2.30)
SDDM reads its config **when the daemon starts**. Ending a session only makes
it build a new display and, with `Relogin=true`, reopen what it was told at
*its* start. Verified: `NRestarts=0`, `ActiveEnterTimestamp=07:45:02` after
three session cycles. Hence `gamecore-session-select desktop --restart-dm`.

### 3. `systemctl stop` did not stop the UI (fix in progress)
**This is the error seen on screen.** Journal:

    08:34:04  Stopping GameCore — Electron UI…      (end of the update)
    08:34:04  gamecore-backend.service: Deactivated successfully
    08:35:35  State 'stop-sigterm' timed out. Killing.
    08:35:35  Killing process 25837 (node-MainThread) with signal SIGKILL

**1 min 45 s** of live UI on the TV with its backend already stopped.
`window-all-closed` cannot tell a stop from a crash: windows closing during a
shutdown that skipped `before-quit` look like a failure, so it rebuilds one.
Fixed with an explicit `SIGTERM`/`SIGINT`/`SIGHUP` handler in `main.js` +
`TimeoutStopSec=10`.

It happens **on every update**, not only on the button — very likely the
"javascript error" the user saw.

## NOT solved

**"Desktop mode" called from the UI does not write the file.**

Five calls in the journal, all accepted by sudo, all exit 0 in ~32 ms:

    02:08:57  gamecore-session-select desktop
    02:09:11  desktop
    02:23:22  desktop
    02:32:48  desktop
    08:09:38  desktop --restart-dm

`/etc/sddm.conf.d/zz-gamecore-autologin.conf` unchanged: mtime `02:07:55`,
`Session=gamecore`. No error, no line in the unit's journal. The backup dir
`verif-avant/…` IS created each time, so the script reaches `backup_switch`,
four lines before the write.

The same command writes the file **every time** from: a plain SSH shell;
`systemd-run --user --wait` (same user manager, no tty); a reduced env copying
the service's (`env -i` + the unit's six variables); `/opt/GameCore` as the
unit's `WorkingDirectory`. Six reproductions, six successes. A successful run
takes 30–55 ms, so 32 ms proves nothing either way.

**Only common point of the five failures:** they run in the
`gamecore-ui.service` cgroup, which systemd tears down as soon as Electron
exits — the next line. Could not prove this race over SSH.

### Done instead of a sixth theory (v1.2.31)

The privileged work moved out of there. The UI drops
`$XDG_RUNTIME_DIR/gamecore/leave-to-desktop` and quits; the `gamecore-session`
teardown — in the session process, outside the torn-down cgroup, after the
units stop — does the switch and the display-manager restart, and copies its
output line by line to the journal.

**This is what remains to validate at next boot.**

### Nothing is invisible any more

`gamecore-session-select` and `gamecore-session` log under their own tag. The
session script's `echo` went to SDDM's session log, which is **zero bytes** on
this box — hence `journalctl -t gamecore-session` answering "No entries" for a
session started four times. At the next button press:

    journalctl -t gamecore-session -t gamecore-session-select --since "-10 min"

## A diagnosis mistake not to repeat

I claimed the case of `XDG_SESSION_DESKTOP` (`GameCore` vs `gamecore`) was the
cause. **Wrong.** I had read the env of the bash script SDDM starts; Electron's,
under `gamecore-ui.service`, carries lowercase `gamecore` (the session script
writes it), so the old comparison passed. The fix stays useful (both spellings
exist depending on who asks) but unblocked nothing.

Lesson: read the environment of the **process concerned**, not its ancestor's.

## Debt left behind

- The test suite writes to the machine's journal: `test_session_install` runs
  the real `gamecore-session-select`, which now calls `logger` (~20 lines at
  08:24:17). Harmless but dirty — stub `logger` under test (env var or PATH
  stub in the fixture).
- `gamecore-ui.service:26: Unknown key 'StartLimitIntervalSec' in section
  [Service]` at every boot: the key belongs to `[Unit]`, so `StartLimitBurst`
  bounds nothing today.
