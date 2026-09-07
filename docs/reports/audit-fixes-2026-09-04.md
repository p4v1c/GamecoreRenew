# The nineteen audit subjects, corrected — session report

> Relecture ultérieure : [corrections du 2026-09-07](review-fixes-2026-09-07.md), notamment migration, mapping et démarrage.

**Session:** 2026-09-06. **Base:** `de53579` (the commit the audit examined).
**Branch:** `feat/packs-layout-et-corrections-audit`.

Two audit reports were delivered on 2026-09-04 — nine subjects in the first,
ten plus one conditional in the second — with reproductions that failed on
purpose. This session integrated the Azahar and melonDS layout packs and
corrected all nineteen, plus the conditional one, which turned out not to be
conditional on this box.

Nothing was installed, deployed or restarted. `/opt/GameCore`, `/userdata` and
the running services were not the target of any change — with one exception,
recorded below, which is the most useful paragraph in this file.

## What was changed, and what proves it

Every subject has a test that fails on the code as it was. That is the standard
applied throughout: a fix whose test passes before the fix is not evidence of
anything, so each one was run against `git show HEAD:<file>` before being kept.

| # | subject | where | test |
|---|---|---|---|
| 1, 6, 7 | stale library reply, non-atomic launch, re-sort on every step | `frontend/src/components/LibraryScreen/index.tsx` | `libraryRaces.test.tsx` (5) |
| 2 | a session left running after a reconnection | `backend/ws.py`, `frontend/src/hooks/useWebSocket.ts` | `sessionSync.test.tsx` (5), `test_session_ownership.py` |
| 3 | an old watcher clearing the new session | `backend/services/process_manager.py` | `test_session_ownership.py` |
| 4, 5 | the box travelling without turning; a second press deleting it | `config/themes/shelf/views/library.js` | `shelfSwap.test.tsx` (5) |
| 8 | a temporary media failure cached for ever | `config/themes/shelf/lib/dossier.js` | `shelfDossier.test.tsx` (3) |
| 9 | two consoles sharing one playtime row | `backend/db.py`, `process_manager.py`, `playtime_repair.py`, `routers/playtime.py` | `test_session_ownership.py` |
| 10 | Summer crashing on a cleared selection | `config/themes/summer/views/library.js` | `screensAfterChange.test.tsx` |
| 11 | removing a profile deleting later settings | `backend/services/pergame.py` | `test_pergame.py` (existing suite) |
| 12 | the CLI writing to the wrong root | `install/bin/gamecore-emu` | `test_emu_cli_data_root.py` (6) |
| 13 | a refused second mode losing the first rollback | `backend/routers/settings/display.py` | `test_display_router.py` (+3) |
| 14 | the dashboard not seeing an installed pack | `frontend/src/components/HomeScreen/index.tsx` | `screensAfterChange.test.tsx` |
| 15 | a loaded bezel hidden by a new measurement | `frontend/src/components/OverlayScreen/index.tsx` | `screensAfterChange.test.tsx` |
| 16, 17 | a cancelled overlay start; a window pinned to 1080p | `electron/main.js` | `electron/test/overlay-lifecycle.test.cjs` (4) |
| 18 | the mapping wizard waiting for an unplugged pad | `backend/services/controller_capture.py` | `test_controller_capture.py` (+3) |
| 19 | a failed sandbox override reported as installed | `backend/services/installer/providers.py` | `test_installer_providers.py` (+2) |
| — | the microphone offered as an audio output | `backend/routers/settings/audio.py` | `test_audio_outputs.py` (4) |

Gate at the end of the session: `ruff` clean, `check-catalog` 17 packs,
`gen-catalog --check` in sync, **1723 backend tests**, **313 frontend tests**,
4 Electron bench tests, `npm run build` green. `shellcheck` was NOT run — it is
not installed on this machine; CI runs it.

## The audio point was not conditional here

The complementary audit kept the `wpctl status` parser out of its count,
because the machine it examined printed the `Sink endpoints:` heading the
parser relies on to leave the sinks section.

This box does not print it. Measured directly:

```
$ wpctl status          # PipeWire / WirePlumber 1.6.7
Audio
 ├─ Sinks:
 │  *   52. Ryzen HD Audio Controller Analog Stereo [vol: 1.18]
 ├─ Sources:
 │  *   53. Ryzen HD Audio Controller Analog Stereo [vol: 1.00]
```

Replaying the shipped parser over that output returns node 53 — the microphone
— as an audio output, and would have reached Video's own `Sinks:` as well. The
tree is now read as a tree.

## The one thing that touched the box, and what was done about it

While writing the tests for subject 12, one of them ran the real
`gamecore-emu remove azahar` **without** `GAMECORE_DATA` in its environment.
That is the fallback path the same subject had just added: with no variable,
the CLI asks `systemctl show gamecore-backend.service` for the data root — and
on this machine that answers `/userdata`, the live box.

It did exactly what it is supposed to do, to the real installation:

* `/userdata/config/systems.json` — the `azahar` tile removed;
* `/userdata/config/catalog-removed.json` — `azahar` added to the declined list.

Repaired within the minute, from `/userdata/config/systems.json.bak-merge`
(2026-08-18): the `azahar` entry was restored at its original position — it was
the last one in the file, and every other entry except `mgba` was byte-identical
to the backup, so nothing else was reconstructed — and `azahar` was taken back
out of the declined list, leaving `["cemu", "xenia"]`. The state before the
repair was copied aside first. No emulator was uninstalled and no ROM, save or
setting was touched: `gamecore-emu remove` only edits those two JSON files.

Two guards were added so it cannot recur:

* `backend/tests/conftest.py` exports `GAMECORE_DATA` at the throwaway root, so
  no test in the suite can reach a real box even by omission;
* the CLI tests put a stub `systemctl` on `PATH`, the way
  `test_addon_contract.py` has done for `gamecore-addon` since that CLI grew
  the same fallback.

The general rule this is downstream of: **a CLI that resolves a real path from
the system is a CLI a test must never run with a bare environment.**

## Decisions taken alone

* **The playtime migration does not split what was already merged.** A row that
  accumulated two consoles under one filename keeps the console it is labelled
  with. Nothing recorded which session belonged to where, and inventing a
  division would be worse than a wrong total. Only what happens after the
  migration is kept apart.
* **A second press during the Shelf swap is a step, not a burst.** Once the
  jacket is out of the row, a press puts it away and takes the next one out.
  The cost is stated in the code: a press landing while the pull is still
  running mounts the outgoing jacket at its opening pose, so the box jumps to
  face-on before folding away. Continuity of presence over continuity of pose;
  the exact hand-off needs a negative `animation-delay` computed from how far
  the pull got, and that is worth doing only in front of a television.
* **`/api/playtime/game/<key>` sums across consoles when no `system_id` is
  given.** A filename is no longer an identity, and summing is at least true
  where returning whichever row came first was not.
* **The overlay's stand-in bars are expressed in fractions**, not in pixels of a
  screen assumed to be 1080p, using the window rectangle the hole was measured
  in (it now travels with the event). The full conversion between the reference
  image, the emulator's pixels and Electron's logical units is not attempted
  here — see below.

## What still needs the box

None of the following can be settled from a workstation, and none of it is
claimed:

* **Subject 17 (the bezel window).** The window now takes the bounds of the
  display carrying the interface and follows mode and hot-plug changes. That
  the frame lands correctly on a 4K panel, on a scaled panel, or on a second
  output has been tested only against a simulated `screen` module.
* **Subjects 4 and 5 (the Shelf gesture).** jsdom runs no animations. What is
  asserted is the structure they run on — which node draws what, and how many
  solids are on the stage. Whether the box now reads as one movement, and
  whether the pose jump on an interrupted pull is visible from a sofa, is the
  owner's to judge. Worth walking the shelf fast, reversing direction at 100,
  250, 500 and 800 ms, and holding a direction down.
* **Subject 18 (the mapping wizard).** The stream ends and says so when the
  last node disappears; unplugging a real pad mid-wizard is the check.
* **Subject 12 (`gamecore-emu`).** Exercised against temporary trees. Install,
  remove and re-install on the box itself — where `GAMECORE_DATA=/userdata` —
  is what proves the grid follows.
* **Subject 9 (the playtime migration).** It runs at the next backend start,
  against the box's real `playtime.db`. Copy that file aside before the first
  start on this branch.
* **Subject 13 (resolution).** The rollback path can only be judged on a screen
  that actually refuses a mode.
* **The layout packs themselves** — L3, the screen swap, the exact Azahar and
  melonDS versions, the pads and the decorative frames — as
  `docs/LAYOUT_PACKS.md` already states.

## How to undo any of it

Each subject is one commit, and the commits are small on purpose:

```
git log --oneline de53579..HEAD
```

`git revert <sha>` takes back one subject with its tests, except for one:

**Reverting the playtime commit alone is not enough.** The table is widened at
the first start on this branch and stays widened. The old code's write is
`INSERT … ON CONFLICT(game_key)`, and SQLite refuses a conflict target that is
not a unique index — checked here:

```
sqlite3.OperationalError: ON CONFLICT clause does not match any PRIMARY KEY
or UNIQUE constraint
```

`_watch()` catches that and logs it, so the failure is silent from the sofa:
every session played afterwards is simply not recorded. So a revert of that
commit has to be accompanied by putting the table back — either from the copy
of `playtime.db` taken before the first start (see *What still needs the box*)
or with `CREATE TABLE … game_key TEXT PRIMARY KEY` and an `INSERT … SELECT`,
which forces a choice about any filename two consoles have since written.
