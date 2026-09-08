# Orbit, and background sessions — 2026-09-08

Two pieces of work in one branch, because the second is what the first was
pretending to have: install the **Orbit** theme, and give GameCore a real
*background / quit* for games **and** applications.

Nothing here was deployed. `/opt/GameCore`, `/userdata`, `/etc` and every real
systemd unit were untouched; all work happened in a fresh clone at
`~/work/gamecore-orbit`. The one change outside that clone is a repo-local git
identity (`git config user.name/user.email`, no `--global`), which lives inside
the clone and disappears with it.

---

## 1. What was measured before anything was decided

Three questions decide whether suspending a session is a feature or a way to
lose someone's save. None of them are answerable from documentation, so they
were run on this box. The scripts are in the session scratchpad; the commands
and the results are below so they can be re-run.

### 1.1 Does `SIGSTOP` on the process group reach inside a Flatpak sandbox? **Yes**

Launched exactly the way `ProcessManager` launches — `create_subprocess_exec`
with `start_new_session=True` — then `os.killpg(pgid, SIGSTOP)`:

```
flatpak run --command=sleep io.mpv.Mpv 120        (a sandbox whose data dir already existed)

before   22029 Ss  bwrap --args 68 -- sleep 120
         22054 S   bwrap --args 70 -- xdg-dbus-proxy --args=69
         22055 Sl  xdg-dbus-proxy --args=69
         22059 S   bwrap --args 68 -- sleep 120
         22060 S   sleep 120
after    all five in T
SIGCONT  all five back in S
```

**One process group, five processes, no `setsid` anywhere inside bwrap.** So
`killpg` is sufficient and no `flatpak`-specific path is needed to *suspend* —
unlike `kill()`, where SIGTERM to the wrapper never reaches the application.
Signalling the pid instead would have frozen the wrapper and left the game
running underneath the interface.

### 1.2 What does PipeWire do with a frozen client? **Nothing harmful**

`paplay` on a WAV of silence, frozen mid-stream:

- its sink-input stays listed and **uncorked** — PipeWire does not reclaim it,
  cork it, or kill the client;
- a **second** client opens the sink normally while the first is frozen;
- after `SIGCONT` the client is alive and its stream is still there.

Side effect worth knowing: the suspended game keeps a visible stream in the
mixer. It is silent, because it produces nothing.

### 1.3 Does a GPU client survive a long freeze? **Here, yes — and that is not a guarantee**

`vkcube` (a real Vulkan device, a real swapchain, a real present loop) frozen
for 45 s and resumed: alive, context intact, on AMD `radeonsi`, under XWayland.

This is a **signal, not a promise**. RPCS3, Ryujinx and Cemu carry their own
watchdogs and network timeouts, and a signal from `vkcube` says nothing about
what PCSX2 does after ten minutes stopped. Per-emulator behaviour is in the
owner checklist in §6, and the honest position is written into the feature: if
an emulator does not survive a freeze, that is a fact to record and degrade for,
not a thing to promise around.

---

## 2. The backend contract

### 2.1 Two slots, one screen

`MAX_SESSIONS = 2`. At most two launched things are resident at once, at most
one of them is in front of the player. Every other combination is legal: two
suspended, one suspended and one playing, one playing, nothing.

**The cap is memory, not bookkeeping.** A suspended emulator has given back its
CPU and nothing else — RPCS3 holds several gigabytes of RAM and its VRAM for as
long as it is stopped. A third resident emulator on a fixed-memory box is the
OOM killer, and the OOM killer takes whichever process it likes, which is to say
sooner or later the player's suspended game. A feature sold as *"your game is
safe while you do something else"* must not contain a path that ends in the
kernel destroying it.

The question the brief asked to settle explicitly — **refuse, replace, or
stack?** — is answered per operation:

| | |
|---|---|
| Launch with something **on the screen** | **refused**, 409, unchanged |
| Launch with something **suspended** | **allowed.** This is the point of the feature |
| Launch with **two** already resident | **refused**, and the refusal names them so the player knows what to close |
| **Suspending** | **never refused** (§2.2) |
| Resuming while something holds the screen | **swapped** — the outgoing one is suspended, in one operation |

Stacking beyond two was rejected for the OOM reason above. Replace-after-confirm
was rejected because it destroys the suspended game, which is the exact thing the
player suspended it to avoid.

The swap is one operation and not two on purpose: only one thing can own the
screen, so resuming a game while an application is up already *implies*
suspending the application. Making the player close it first would be the
interface asking them to do arithmetic the box can do itself. The resident count
is unchanged either side of it.

### 2.2 The refusal that created a dead end, and was removed

The first draft kept a single background slot and refused a second. That reads
as reasonable until the double-Home gesture meets it: a player inside game B
with game A already suspended presses Home twice to get out, the suspend is
refused, and **the only way off that screen is to abandon the game they are
playing.**

Moving a session from the screen to the background creates no session — the
resident count is identical either side of it — so there was never a memory
argument for that refusal, only a data-structure one. The cap belongs on
launching, which really does create a session. Suspending is now never refused,
and `test_suspending_is_never_refused_while_something_is_on_the_screen` holds it
that way.

### 2.3 The two locks the brief named

**The 409.** `/games/launch` refused every launch while `process_manager.is_running`
was true, and a process frozen by `SIGSTOP` still has `returncode is None` — it
is "running" by that definition for its whole suspension. So backgrounding a game
locked the box out of starting anything else, which is the one thing the player
backgrounded it in order to do.

`is_running` (a session **exists**) and `is_foreground` (a session **owns the
screen**) are now two questions. Every caller was re-read to decide which it was
actually asking:

| caller | asks | why |
|---|---|---|
| `/games/launch` | `is_foreground` | a frozen game must not refuse a launch |
| `/pergame/{id}/open` | `is_foreground` | it takes the screen slot like a game |
| `standby` | `is_foreground` | a frozen game is nobody playing; holding the idle clock for it would be a box that never sleeps again |
| `prefetch` | `is_foreground` | a frozen game reads no disc; waiting on it would silently stop the library filling in |
| `storage_monitor` | residence, via `_resident_games()` | a suspended game is still on that disk, still holding its disc image open |
| `settings/display.py` | `is_running` | a frozen emulator still owns a swapchain a mode change would invalidate |
| `gamepad_monitor` (player renumbering) | `is_running` | see §8: renumbering under a frozen game costs the same thing, on resume |

**The pad guard.** `useGamepad` blocks every press while `sessionGameKey` is set.
That rule is right and stays. The fix was *not* to teach every reader about
background state: `sessionGameKey` keeps meaning **"a game owns the screen"**, and
a suspended session writes `null`. `App.tsx`, `DefaultShell.tsx`, `LibraryScreen`
and `isPlaying()` all ask the same question in different words, and all four
became correct without being touched. The alternative — a state field checked in
each of them — is the same fix written five times, with a sixth reader added later
that nobody remembers to teach.

### 2.4 The API

`GET /api/games/session` **keeps its flat shape**, and that is load-bearing.
The flat fields describe the session *on the screen*, which is what this endpoint
has always returned — so a front end from before this feature reads a box whose
only session is suspended as *"nothing in front of me"*. That is true, and it is
the answer that leaves its pad unblocked rather than frozen over a game nobody
can see. `background` is a new array beside it.

```
POST /api/games/background          suspend what is on the screen
POST /api/games/foreground {session?}   resume one, swapping out whatever holds the screen
POST /api/games/kill       {session?}   unchanged with no body
GET  /api/games/session             flat = foreground, + background[]
```

Two websocket events, `game:backgrounded` and `game:foregrounded`, numbered like
`game:started`. **They carry the whole state as well as the transition**, and
that is not redundancy: a resume moves *both* slots at once, and a client
rebuilding its picture from "run 3 came forward" cannot know what happened to
run 2 — it would drop a session that is still frozen and leave the player with a
game the interface no longer shows.

### 2.5 Playtime

`elapsed` was wall-clock between launch and exit, so a game left suspended
overnight billed the player for the night. Each session accumulates its frozen
seconds and subtracts them. Clamped at zero, because a clock that jumped must
not subtract from someone's hours.

### 2.6 Standby, and a restart

**A suspended game does not hold the box awake.** When the box then sleeps,
nothing happens to that game: `SIGSTOP` is already the state a sleeping process
should be in, and it is still suspended on the way back. It stays in the
background until the player resumes it.

`SIGSTOP` also outlives the backend that sent it, so the session file records
both slots and their suspended state. A backend restarted by an OTA finds a
frozen game again — the session that most needs finding, because a frozen
process cannot exit on its own to clear itself.

### 2.7 Double Home

It killed. It suspends now, and closing is a deliberate second action on the
session bar. The gesture stays the core's — `gp:guide` is in `RESERVED_EVENTS`
precisely so no theme can take the one binding that gets a player out of a game
— and what themes draw is the bar that follows.

Both the backend's evdev monitor and the browser can see the double press
(Chromium exposes the guide button on some pads and not others), so both paths
call it; the second finds nothing on the screen and is refused, harmlessly.

### 2.8 Applications are not a special case

A tile with no ROM launches through the same endpoint with `game_key ==
system_id`, so an application session is an ordinary session and that identity is
the only thing telling the two apart afterwards. It is computed once, in
`Session.is_app`, and travels as `kind` so that every theme says *"Close
application"* rather than calling Stremio a game.

**An application accumulates hours exactly like a game**, and that is left as it
was — deliberately, because the playtime table is keyed `['game_key',
'system_id']` and an app is a row like any other. It is now at least *honest*
hours: time spent suspended is not counted for an app either.

---

## 3. What the Orbit audit found

The README claimed *"12 integration tests passed"* and that the repository's
checker passed. That is an assertion by the author, not a test anyone else can
run. Everything was replayed.

**Held up:**

- **The version gate.** Orbit declared `api: 4` and used exactly SDK 4 surfaces
  (`bootReady`, `s.standby`, `createSettings`/`createPowerView`). Verified by
  having `test_sdk_version_gate` compute the minimum from the *sources* rather
  than trusting the manifest.
- **Declared features present.** All ten declared settings pages are reachable
  (`scripts/check-theme.mjs` confirms). Home, library, power, controllers,
  search, sort, per-game options and a `bootReady`-aware splash are all there;
  sort, search and R2 options are correctly left to the host.
- **The data is real.** No fabricated games, controllers, profiles, or
  "recommendations" section. Every list comes from host props or the real API.
  The one thing masquerading as a feature was the session preview — and the
  README said so plainly.

**Did not hold up:**

1. **A second search keyboard.** Orbit opened its own modal, using the host's
   own keyboard component, styled the same — from a button reachable with a
   pointer and by nothing else. On a console that is a dead control, and two
   modals over one screen if both ever opened. Both shipped themes had already
   settled this and Shelf writes it in a comment: searching is the host's, △
   opens *its* keyboard, and the theme offers a plain field for a mouse. Orbit
   does that now.
2. **`views/controller.js` escaped `test_shipped_theme_views`.** That test
   checks a shipped theme has not lost the mapping wizard — the only way to make
   a pad SDL cannot name usable at all. It looked for `views/gamepad.js` *by
   name*, but the name belongs to the theme: the host takes the view as the
   `gamepadView` prop and never looks at the path. It now finds the file by its
   content, and Orbit is in the shipped list. Orbit already passed both
   assertions; the coverage was what was missing.
3. **29 MB of photographs for 5.1 MB of use.** Eight of the thirteen were
   already 960 px on their long edge; **five** were not — `ps4` at 6000 px,
   `n64` and `gamecube` near 3800, and `ps3` (960×1067) and `xbox360`
   (960×1322), which are 960 px *wide* and taller than the norm. That is four to
   six times more pixel than this theme can draw, since the largest render is
   `.orbit-feature-art`, capped at 450 px and 40vh (864 px even on a 2160p
   panel). All five were resampled and everything was recompressed. **The eight
   that were not resampled are pixel-for-pixel identical**, asserted by hashing
   the decoded image before and after.

   > This paragraph said *ten and three* until an independent review recounted
   > it (§8). The script had always been right — it keys on the long edge — and
   > the prose was counting width, so the two tall images were described as
   > untouched while they had in fact been resized. The claim was checkable and
   > wrong, which is the same fault this report opens by finding in Orbit's own
   > README. Corrected numbers, and the method, above.

**And the preview is gone.** `lib/local-session.js` was a pure in-memory model
with `foreground`, `background`, `askClose` and a session object no process ever
answered to. `lib/session.js` calls the real backend. Nothing in the interface
says "preview" or "UI PREVIEW" any more, because there is nothing left to hedge
about. Orbit moves to `api: 5`, and the gate was checked in both directions —
declaring 4 makes it refuse the theme by name.

---

## 4. What each theme draws

The bar is an **optional surface**: the host supplies the layer (position, and
the z-index themes are forbidden to write) and the theme draws inside it — the
same bargain the themed splash has, and the reason Shelf's stylesheet can keep
its "no z-index anywhere in this file" rule.

| theme | how it reads |
|---|---|
| **Orbit** | a night dock with the orbiting mark, pulsing while the bar holds the pad; L2 opens the full cinematic panel with resume / close / back |
| **Shelf** | the ledge under the shelf — paper, ink, one hairline rule, the seal gold. The seal is filled when ✕ acts on the bar and hollow when it does not. *"Pick it back up"* / *"Put the game away"* |
| **Summer** | a pane of sea glass on the tideline, translucent and blurred like every other panel. What says *paused* is that the ocean behind it is still moving and this is not; the buoy bobs only while the bar has the pad |
| **_skeleton** | the teaching version, with what makes this surface different from the other two spelled out: optional, not in `provides`, and deleting it breaks nothing |

**Shelf and Summer deliberately stay at `api: 4`.** They take their state as
props and call nothing, so a front end without the lifecycle simply never mounts
the bar and the theme keeps working. Declaring 5 would take them off that box for
a surface they do not use. (The gate did flag them at first — it matches raw
substrings including comments, and the comments quoted `sdk.session`. The
comments were reworded: over-triggering is the safe direction for that gate, and
changing the gate to parse JavaScript would be trading a false positive for a
parser.)

---

## 5. Tests

All four gates green: `ruff`, **1813 passed / 5 skipped** (from 1774/6),
**351 frontend** (from 331), **27 electron**, and the production build.

Proven red before green, which is this project's rule:

| test | what it caught |
|---|---|
| `test_a_game_that_has_exited_does_not_hold_a_slot` | a real bug introduced by the slot cap: `_reap()` only dropped adopted orphans, so a child that had already exited kept its slot until its watcher got the event loop back — and the next launch was refused *naming games that no longer existed*. Confirmed red with the exact message. |
| `backgroundSession.test.tsx` — the pad guard | replayed with the naive implementation (a suspended session still filling the flat fields): `isPlaying()` returned `true`, pad frozen. Two tests red. |
| `test_sdk_version_gate[orbit]` | with `api: 4` in the manifest, refused with *"orbit uses an SDK 5 surface but declares api 4"*. |

Six existing suites that stubbed `is_running` now stub `is_foreground`. Their
meaning is unchanged: it is the property carrying *"a game is on the screen"*
that was renamed, and each of those tests was asserting exactly that.

---

## 6. What could not be validated without the hardware

Everything below needs the box, a television, two pads and a real game. None of
it is guessed at in the code — each one degrades to the honest behaviour — but
none of it has been seen working.

1. **A real emulator across a real freeze.** `vkcube` survived 45 s (§1.3);
   RPCS3, PCSX2, Ryujinx, Dolphin and Cemu have not been tried. Suspend a game
   with an actual save at risk **only after** trying one you do not mind losing.
   Watch for: a black window on resume, a hung audio device, a controller the
   emulator no longer sees.
2. **The screen handover.** `window_focus` asks the window manager to drop
   fullscreen from the frozen window and raise the interface, over EWMH, on the
   console's X session. It was written against the same Xlib path the fullscreen
   enforcer already uses successfully, and it fails silently by design — but it
   has not been seen doing it. **If the interface stays behind a frozen picture,
   this is the file.** The Electron window's `WM_CLASS` is pinned to
   `electron/package.json` by a test, so at least a rename cannot break it
   quietly.
3. **Two controllers**, and a pad unplugged and replugged while a game is
   suspended. The roster only renumbers players between games and a frozen
   emulator re-reads nothing until resumed, so the reasoning says it is safe;
   it has not been watched.
4. **Standby with a game suspended.** Reasoned in §2.6 and not observed: let the
   box sleep with a game frozen, wake it, resume.
5. **An OTA with a game suspended** — the adoption path across a backend
   restart. Unit-tested with a synthetic session file; never run against a real
   frozen emulator.
6. **Two suspended sessions at once**, and the third launch being refused by
   name.
7. **The double-Home change on the television.** It no longer kills. Anyone used
   to the old behaviour will press it twice expecting the game to end and find it
   suspended instead.

### The checklist to run on the box

```
1  launch a game you do not mind losing · Home ×2 → the interface comes back,
   pad works, session bar names the game
2  ✕ on the bar → the game comes back fullscreen, with focus
3  Home ×2 again · launch an application (Stremio) → both allowed, bar shows the game
4  resume the game from the bar → the app goes to the background, the game returns
5  Settings → check the game's playtime has NOT grown by the suspended minutes
6  suspend two things · try to launch a third → refused, naming what to close
7  suspend a game · let the box go to standby · wake · resume
8  suspend a game · restart the backend · the bar is still right, resume still works
9  repeat 1–2 on each emulator that matters, worst case first (RPCS3)
10 switch themes with a game suspended — Shelf, Summer, Orbit — the bar is
   always there and always navigable with the pad alone
```

---

## 8. What an independent review found afterwards

The work above was handed to a second reviewer with instructions to treat every
claim in this report as unproven. It found **seven real defects and one false
statement in this document**. They are recorded here rather than quietly fixed,
because the pattern is the point: most of them are places where the code was
*described* correctly and *written* against a slightly older idea of itself.

| | what was wrong | why it mattered |
|---|---|---|
| 1 | `launch()` raises `SessionConflict` for the resident cap, and the router caught only `FileNotFoundError`/`PermissionError` | the refusal left as an unhandled **500**. The player met a crash instead of the sentence naming what to close — a sentence written specifically so they would know. §2.1 claimed this worked at the HTTP level; only the manager had been tested |
| 2 | double Home fell back to `pm.kill()` when suspending failed | `kill()` with no argument means "the one on the screen, **else the suspended one**", and the way a suspend fails is that the foreground has just exited. The fallback reached past the gap and **destroyed a suspended game the player never pointed at**. Nothing is closed on a failed suspend now |
| 3 | `adopt_orphan` dropped sessions past `MAX_SESSIONS` | the cap governs how many sessions may be *created*. Applying it to *recovery* threw away the pgid — the only handle that can ever close that process — turning an over-full session file into an emulator holding its memory until reboot |
| 4 | recovery resolved two recorded foregrounds by writing `state = "background"` and sending no signal | the box reported a freeze it had never performed. The session bar offered to "resume" a game still running at full speed behind the interface. Only a SIGSTOP that landed may be advertised |
| 5 | the Electron bezel was driven off `game:started` / `game:finished` | `overlay:stop` is what tears the bezel down **and brings `mainWindow` back** — the overlay hides it. A suspend never sent it, so the player was left in front of a frozen bezel with the interface invisible behind it, holding a controller that worked and had nothing to point at. **The worst of the eight, and entirely missed.** The overlay follows the reconciled foreground now (`hooks/useEmulatorOverlay.ts`) |
| 6 | a theme's `sessionBar` that *throws* removed the bar | §4 claimed a theme "replaces the picture, never the guarantee". Omitting it was covered; crashing was not, and the outcome is identical. Wrapped in an `ErrorBoundary` falling back to the host's own view |
| 7 | `storage_monitor` asked `current_game`; `settings/display.py` too | both went blind to suspended sessions when `current_game` became foreground-only. A disk pulled from under a frozen game raised no warning, and a display-mode change could invalidate a frozen swapchain. The caller table in §2.3 named `storage_monitor` as already correct — it was not |
| 8 | this report said **ten** images were untouched | eight. The script keys on the long edge and was right; the prose counted width, so `ps3` (960×1067) and `xbox360` (960×1322) were described as untouched while they had been resized |

Two further hardenings came out of the same pass: `Session.pgid` no longer asks
`getpgid()` for a pid that may already have been reaped and recycled (the child
is spawned with `start_new_session=True`, so its pid *is* its group), and
`foreground()` now guards against a launch in flight and describes a failed
rollback truthfully instead of claiming the screen was restored.

And one earlier decision was reversed. The roster stops renumbering players
while a session is merely **suspended**, not only while one is on screen. The
original reasoning — a frozen emulator re-reads no input config — was true and
one step short: nothing goes wrong while it is frozen, it goes wrong on
**resume**, when the emulator comes back holding the binding it read at startup
and the registry has closed the gap underneath it. That is "the remaining player
silently becomes somebody else", arriving a few minutes late.

Six of the eight were reproduced as failing tests before being fixed
(`backend/tests/test_session_audit_findings.py`, plus the crashing-theme case in
`sessionBar.test.tsx`, the bezel in `emulatorOverlay.test.tsx` and the roster in
`test_gamepad_monitor.py`). One reviewer suggestion was **not** taken: adding a
host-drawn management modal and a "Manage suspended sessions" button on top of
every theme's bar. It would have put hardcoded chrome over Shelf's paper and
Summer's sea glass, which is the one thing the brief asked not to do.

## 7. Not done, on purpose

- **Not deployed.** Nothing was merged, tagged, released, or copied to
  `/opt/GameCore`. The branch is `feat/orbit-et-sessions`.
- **Electron was not given a "raise yourself" IPC.** The X11 path covers both
  directions and the shell's window name is pinned by a test; a second mechanism
  for the same job is a second thing to keep in step. If §6.2 fails on the
  television, that IPC is the fix to reach for.
- **The version gate still matches substrings, comments included.** Reworded the
  comments rather than taught it to parse JavaScript: over-triggering is the
  safe direction for a gate whose job is refusing incompatible themes.
- **Applications still accumulate playtime like games.** Called out in §2.8
  rather than changed — it is a product decision, and the hours are at least
  honest now.
