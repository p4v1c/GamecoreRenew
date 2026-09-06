# The console boot — session report

**Session:** 2026-09-06. **Branch:** `feat/boot-console`, out of
`feat/packs-layout-et-corrections-audit` (the nineteen audit fixes).
**Nothing was installed, armed or restarted on any box.**

The complaint this answers, in the owner's words: the television shows the
desktop for several seconds, then GameCore, and how long varies by screen. The
requirement that shaped every decision below: *the move to the dashboard must
depend on the real state of the system and the application, never on an
arbitrary wait.*

## The rule

**No timer promotes anything.** Every transition is a fact — the backend
answered `/api/ready`, the interface said `boot:ready`. Durations survive in
exactly one role: bounding a failure so it can be *reported*. There is
deliberately no deadline that gives up and shows the dashboard anyway, because
a dashboard built from nothing is, from a sofa, indistinguishable from a box
that has lost its games.

## What was wrong, measured against the code

| | Before |
|---|---|
| What covered the screen during the wait | Nothing. `createWindow()` ran *after* `startBackend()`, so the desktop, its panel and its wallpaper were the boot screen. |
| How "the backend is up" was decided | `GET /api/sysinfo` — which opens a UDP socket towards 8.8.8.8 to find the box's address, walks the disk, reads controller batteries and lists BIOS files. Polled, on the boot path, on a box that may have no network. Any response counted, including one from a backend still opening its database. |
| What the backend did before answering | `init_db`, then a playtime repair that **walks every system's ROM directory**, then standby resume and desktop-power arbitration (both of which talk to X, the one thing that may not exist yet at cold boot), then the orphan adoption. |
| Who owned the backend process | Both. Electron spawned a second uvicorn whenever nothing answered within 1.5 s — which is true of a backend that is merely still starting. |
| When the dashboard appeared | When the boot animation ended, plus a fixed 4 s Electron added whenever uptime was under 180 s (`?splashHold=4000`). Neither shipped theme read that value. |
| The player's chosen resolution | Not written down anywhere. `gamecore-xsetup` forced 1080p at every boot, so a confirmed choice was silently undone. |
| Mode changes per boot | Two: SDDM's `DisplayCommand`, then `start-ui.sh` again inside the session to beat KScreen. Each one is a television resynchronising. |

## What it is now

**A readiness protocol.** `GET /api/ready` — a dict lookup and a subtraction,
no socket, no subprocess, no scan; **200 ready, 503 with the outstanding step**.
`backend/services/boot.py` holds the rule that decides what blocks: *a step is
required when answering without it would make the front end say something
false.* Required: the database, and the adoption of a game left running by a
previous backend — answering before it means telling the player nothing is
running while an emulator is on screen. Not required, and now running beside
the server: the playtime repair (its cost belongs to the size of the shelf, not
to the boot; it announces itself when it moves rows, and the screens re-read
them), the standby resume and the screen-timeout arbitration.

**One owner for the backend.** `INVOCATION_ID` — set by systemd in every
service it runs, inherited through `start-ui.sh` — is how the shell knows it is
managed. Managed, it waits; it never competes for the port.

**The window comes first.** `electron/boot/boot.html` is loaded from disk, with
no backend, no network and no bundle, before anything is waited for. The window
is created `show: false` and presented on `ready-to-show`, and the interface is
loaded into the *same* window: the frame between two documents is painted with
the window's own background, whereas two windows would leave the compositor to
decide which is on top and which has the pad.

**The host decides when the interface is worth showing.**
`frontend/src/lib/boot.ts`: theme resolved (or its fallback — either is an
answer), the dashboard's own data settled (an empty list is a valid success),
and a frame actually painted (two `requestAnimationFrame`, because the first
runs before the paint that follows the commit). Not waited for: the network,
the cover art, the scraper, a ROM scan, a connected pad.

**A versioned splash contract (SDK 4).** The splash receives `bootReady`, ends
on a *held* frame, and leaves when the host allows it. `bootReady !== false`,
never `bootReady`: an older host passes nothing, and a splash waiting for a
prop that never arrives is a box that never boots. A theme at `api ≤ 3` keeps
working — the host holds an opaque curtain under it instead.

**A session of its own.** `gamecore.desktop` + `install/bin/gamecore-session`
start KWin (X11) and the GameCore user units, and nothing else: no plasmashell,
no panel, no wallpaper, no session restore. The environment is handed over
rather than guessed — imported into the user manager for the session's units,
and written to `$XDG_RUNTIME_DIR/gamecore/session.env` for the backend, which
is a system unit and can see none of it.

**Recovery.** A renderer that dies puts the boot screen back and starts the
sequence again, bounded by the same rebuild budget as the window. A compositor
that keeps crashing is retried three times a minute and then given up on — the
session *continues* without one, because a session that exits returns to SDDM,
which auto-logs straight back in: a login loop on a television with no
keyboard. Leaving for the desktop points the auto-login at the desktop first
and only then ends the session.

## Decisions taken alone

* **Installing is not arming.** `setup-gamecore-session.sh` installs the
  session and leaves the box booting exactly as it did; `gamecore-session-select
  gamecore` is a separate command with a separate rollback. Changing how
  somebody's console starts, unattended, from an update, is not a decision an
  update gets to take.
* **The migration is applied, not announced.** A line in an update log saying
  "run this" is not a migration: every box whose log nobody reads stays on the
  old shape for ever, and both shapes then have to be supported indefinitely.
  It runs through a one-shot unit whose arguments come from the root-owned
  manifest, started through a sudoers rule naming exactly that unit — the
  updater stays unprivileged — and the result is verified on disk rather than
  from an exit code.
* **The system-wide `gamecore-ui.service` is masked, not merely disabled.**
  `gamecore-launcher` and years of habit call `systemctl start gamecore-ui`; on
  a migrated box that would be a second Electron over the session's own.
* **Only a *confirmed* display mode is remembered.** Persisting an unconfirmed
  one would persist exactly the black screens the automatic revert exists to
  undo.
* **Plymouth is out of scope**, at the owner's decision and for a good reason:
  it is `mkinitcpio` on Arch, dracut elsewhere, and the result depends on the
  graphics driver. What it would cover — the kernel's text before X — is two or
  three seconds that read as a machine starting, not as an application broken.

## What is proven, and how

`ruff`, `check-catalog`, `gen-catalog --check`, **1756 backend tests**, **325
frontend tests**, **14 Electron bench tests**, `npm run build`. The Electron
bench runs the real `electron/main.js` in a VM with Electron, the child
processes and the network replaced; the session script and the installer step
run for real against staging trees (`DESTDIR`, `SDDM_CONF_DIR`,
`XSESSIONS_DIR`), so no test touches `/etc`, `/usr` or the systemd of the
machine running it.

Two defects were found by the tests written for this work, and both are in the
commits that introduced them: Summer's splash cancelled the exit timer it had
just armed (an effect re-running on its own state change), and
`gamecore-session-select desktop` offered the GameCore session itself as the
desktop to return to on a box that had only ever had it.

## What still needs the box

Nothing below can be settled from a workstation, and none of it is claimed:

* **The visual continuity itself.** jsdom runs no compositor. What is asserted
  here is the order of events and which document is in the window — that the
  television never shows a desktop, a white flash or a gap is the owner's to
  judge, on the screen it is about.
* **Stacking and focus under KWin**, with the bezel window and an emulator —
  §4 of the brief asks for it explicitly and it has no substitute.
* **The session without Plasma**: whether the Flatpak emulators, the portals,
  the audio and the packs' layout daemons (Azahar, melonDS, L3) behave with no
  desktop session behind them. Their units are `WantedBy=default.target` and
  survive by design; that is a design, not a measurement.
* **The migration on a real box**: `setup-gamecore-session.sh`, then
  `gamecore-session-select gamecore`, then a reboot — with `gamecore-session-select
  desktop` over SSH proven to work *first*.
* **`scripts/boot-timeline.sh`** on the box, before and after. It reads the
  journal and writes nothing; it exists to say which step costs the seconds on
  *that* machine, because it is a different step on different machines. It is
  never a source for a delay: nothing in the code reads a duration any more.

## How to undo it

Each piece is one commit; `git log --oneline feat/packs-layout-et-corrections-audit..HEAD`.

On a box, in order and each one sufficient on its own:

1. **Boot the desktop again:** `sudo gamecore-session-select desktop` — SSH is
   enough, and this is the escape hatch to prove before arming anything.
2. **Put the old shape back:** `sudo mv
   /etc/systemd/system/gamecore-ui.service.pre-session
   /etc/systemd/system/gamecore-ui.service && sudo systemctl unmask
   gamecore-ui.service && sudo systemctl enable --now gamecore-ui.service`.
   The step moves the old unit aside rather than deleting it, for exactly this.
3. **Remove the session:** `sudo rm /usr/share/xsessions/gamecore.desktop
   /usr/local/bin/gamecore-session` and the two user units under
   `~/.config/systemd/user/`.

The display preference (`<DATA>/config/display.json`) is the only new state on
disk. Deleting it restores the previous behaviour exactly: 1080p at every boot.
