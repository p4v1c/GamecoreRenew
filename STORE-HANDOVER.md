# The Store chantier — handover

**Branch:** `feature/gamecore-store` · **Base:** `main` at `59ea18d` ·
**27 commits** · 604 files, +43,397 / −996 · 13–14 September 2026.

Written in English like the rest of `docs/`, for the reason
`docs/reports/README.md` gives: so that any developer — or any AI — picking the
work up can replay the reasoning rather than only read the result.

`main` was never checked out, never modified, never merged into. Nothing was
pushed until the owner asked for it. No production path was ever written:
`/opt`, `/userdata`, `/var/lib/gamecore`, `/etc`, `/usr/local/bin` and
`~/.var/app` were read-only throughout, and `install/arch.sh`,
`install/uninstall.sh` and `update/linux.sh` were never executed in any mode,
`--dry-run` included.

---

## 1. What this branch does

A **Store**: from the sofa, on the television, with a gamepad — pick a console,
search it, and watch a game arrive in your library.

The whole chain exists and was proven end to end against the real services on
14 September: a 7.99 GB download, announced and received byte-identical, the
file atomically renamed into the job's work area, `emu/` untouched, production
untouched.

| stage | what it does |
|---|---|
| **search** | Prowlarr, **system first** — the console is chosen before the query |
| **resolve** | by BitTorrent info hash, or by fetching the `.torrent` behind Prowlarr's protected token |
| **acquire** | Real-Debrid turns a torrent into direct HTTPS links — no torrent client, no daemon, no port |
| **materialize** | download into `<DATA>/store/jobs/<job-id>/`, with progress, resume policy and cancellation |
| **inspect** | classify into one of six ingestion classes, from the pack and a listing — never a per-system table |
| **transform** | give the download the shape its class requires; never touch the source |
| **validate** | signatures at three strengths; a missing BIOS warns, never blocks |
| **import** | `renameat2(RENAME_NOREPLACE)` into `emu/<system>/` — atomic, and it can never overwrite |
| **library** | nothing to do: `backend/routers/games.py` — the listing **is** the ROM scan |

It also carries the catalogue from **13 emulators to 31** (35 packs), moves
emulator installation out of Settings into the Store, and updates the
installer, the uninstaller and the OTA for everything above.

---

## 2. Where it stands

**Verified from the main session, not taken on trust** — every sub-task's
numbers were re-measured before acceptance:

- backend + catalogue: **2,706 passed, 22 skipped**, ~6 min 30
- frontend: **57 files / 612 tests**
- `scripts/check-catalog.py`: 35 packs · `scripts/check-docs.py`: 15 documents
- `bash -n` clean on `arch.sh`, `uninstall.sh`, `update/linux.sh` and the new steps

**A final audit exists and says: do not release yet.**
`docs/reports/store-final-audit-2026-09-14.md`. Of the owner's own phase-1 exit
criteria it finds **15 met, 2 not met**, and it names seven release blockers.
Two of those have since been closed and one was deliberately declined; four
remain. Section 5 below is the list.

---

## 3. The decisions that shaped it

These are the ones that are expensive to re-derive. Each was argued at the time
and the reasoning is in the commit message it belongs to.

**The Store is core code — a backend router and a frontend screen.** Not a pack,
not an addon. And it is a **destination**, not a settings page: you go there,
the way you go to the library.

**Themes get a view, never the behaviour.** The core owns navigation, focus and
paging; a theme supplies an optional `storeView` with a host default, so no
theme can break by omission. All three shipped themes compose
`sdk.defaults.Shell`, so they received the Store without being touched.

**Prowlarr and Real-Debrid are external and belong to the owner.** GameCore
never installs, manages, updates or removes either; it knows a URL and a key.
That single choice removed almost all of step 19's debt: no system service to
install, no second LAN port, no managed-versus-external logic in the manifest.
The list of indexers lives in the owner's Prowlarr, not in this repository.

**Search is system-first**, because the ingestion class is a property of the
pair *(system, incoming format)*. Ask for the console first and the target
directory, the class and the validation are all decided; ask afterwards and no
indexer can tell you reliably.

**The write guard.** From the moment the queue existed, one test asserted that
nothing outside `store/jobs/<job-id>/` is ever written. It stayed green through
materialize, inspect, transform and validate, and **the import is the single
place that opens it** — narrowly, to one pack directory, with a test that goes
red if any other stage writes into `emu/` and another if the import writes
outside its system's folder.

**Honest failure at every stage.** A job that cannot finish fails with a
*distinct* reason — `NO_PROVIDER`, `NO_MATERIALIZER`, `NOT_IMPORTED`,
`INSPECTED_NOT_IMPORTED`, `TRANSFORMED_NOT_VALIDATED`, `VALIDATED_NOT_IMPORTED` —
because a player who reads the wrong reason goes and checks the wrong setting.
Nothing ever succeeds by pretending.

**Class C is never unpacked.** For `mame`, `naomi`, `naomigd` and `atomiswave`
the archive **is** the ROM. Unpacking a romset does not degrade it, it deletes
it: measured, `{sf2/, sf2_01.rom} → []`.

**Rollback stays manual.** `${GAMECORE_PATH}.prev`, restored by hand. An
automatic restore has to be right about a machine whose state it does not know,
and that path cannot be exercised in CI.

**The OTA does not get `pacman`.** It needed to deliver `p7zip` to existing
boxes, and it does — through the root-owned unit that **already existed**, whose
step owns a hardcoded package list. The updater passes no package name, no
repository, no pacman argument, and never runs a distribution upgrade.

---

## 4. What measurement found that reading did not

This is the part worth keeping. Every one of these was invisible to a green test
suite and took minutes to find by measuring against reality.

**A console claimed its successors' releases.** `duckstation` is the
PlayStation 1 and its pattern was `playstation`, which is a whole word inside
`PlayStation 3`. Measured against a real indexer: it kept **7 of 7**
`gran turismo` rows, PS3 and PSP among them. A player on the PS1 screen was
being offered games no PS1 emulator can run — the import would have worked, the
tile would have appeared, and the screen would have stayed black. Fixed in
`37fda09`; re-measured at **2 of 7**, and those two are the genuine PS1 discs.

**Two ingestion classes out of six were wrong under 2,565 green tests**, because
no test compared a verdict to the contract's own table. `snes9x` + `.sfc` and
`ryujinx` + `.xci` were being called disc images. Fixed in `6da8666`, and the
missing test — *one case per class, against §5.1* — is now in the suite.

**The 8 GB download the chain fetched is a fake release.** The owner's own
`Super Mario Party.xci` carries `HEAD` at offset 0x100 exactly where switchbrew
puts it; the downloaded file carries nothing there. Ground truth from the
owner's library closed a question the documentation alone could not, and `.xci`
was promoted from *hint* to *proof* in `ba0b500` — so validation would now
refuse that file. The first thing the chain caught on real material.

**An RPCS3 service and timer survived every uninstall.** They arrived with the
ALL-PACKS port and nobody added them to the uninstaller's hand-written lists.
Found by the new guard on its first run, in `7da38ae`.

**A disc set could be imported without its data.** An archive holding
`Game.cue` *and* `Game.bin` for the Dreamcast classified as A — "unpack, keep
declared extensions" — which extracted the descriptor and silently dropped the
track. Loose, those two files would have been class E and the completeness
check would have caught it; inside an archive, that check never ran. Fixed in
`1fcabf8`: it is class E now, complete or refused by name.

**A system prerequisite could never reach an existing box.** `p7zip` was added
to the installer, but the OTA installs no system packages — so every box that
*updates* would have failed archive classification forever, with an error
message that promised "a GameCore update installs it". Fixed in `0fddd32`.

**And the phantom that cost five sessions.** Five sub-tasks in a row reported
that the backend suite hangs under Python 3.14.6 and blamed `aiosqlite`; one of
them shipped a red test without seeing it, having fallen back on
`collect-only`. The suite does not hang: ~20 runs from the main session, always
about 6 min 30. The cause is the **isolation of the sub-task execution
environment**. Outside it, same command, same venv: green.

---

## 5. What is not done

### Declined on purpose

**Credential escape (audit blocker 2)** — decided by the owner on 14 September
and recorded in `d315044` and in the audit's *Owner decisions* section. Three
paths are real and were reproduced twice: a private-tracker passkey inside a
`guid` **path** reaches `SearchResult.source`, the browser and
`store_jobs.source`; URL user-info survives both `_clean_url`s into every
diagnostic; a remote error body is copied verbatim into a job's `reason`, which
is logged and exposed. None is reachable from the network — `/api/*` is 403
through Caddy — so the exposure is to whoever already has the box.

Revisit it before the box is used by anyone else, or before a log from it is
shared: logs get pasted. Closing it costs four small changes plus a taint test,
and the taint test is the only part that prevents the class of bug returning.

### Written, never dispatched

Three complete sub-task briefs exist only in the session that produced them.
Each names its starting commit, its production-safety rules and its expected
tests; they need re-deriving before use.

- **D1 — bezels and window ownership.** All 17 RetroArch packs declare the same
  `wmClass`, so with two RetroArch games alive at once — which background
  sessions allow — the overlay can follow the wrong window. The fix exists in
  the ALL-PACKS bundle (`~/src/gamecore-store-work/all-packs-v7/`) but is
  **broken there**: its own gate fails at its own base commit with three
  regressions, all D1's. Two are one traceback — the inserted
  `"pgid": self.pgid` reads `self.proc.pid` against a `FakeProcess` that has
  none. The third is a real race: `overlay:start` awaits `/api/games/session`
  without re-checking cancellation afterwards. Fix both, then port. Its gate
  also needs a physical test only the owner can run — launch a RetroArch game,
  suspend it, launch a second, check the bezel follows the second, resume the
  first, check again.
- **Audit blocker 3 — the matrix states a rule instead of listing members.**
  §5.2 claims a predicate, §5.1 is a table of members, and they disagree. The
  full cross-product was measured: **100 (system, format) pairs** plus 32
  archive variants. Four pairs have no row — `cemu/.rpx`, `dolphin/.wad`,
  `mame/.cmd` → B and `xenia/.xex` → A — and a fifth divergence was found that
  nobody had seen: a **`mame` archive containing a `.cmd` member classifies as
  B, and B unpacks**. `.cmd` is a declared non-archive extension, so it trips
  the B-versus-C predicate. The table says mame + `.zip` is C unconditionally.
  This is the one divergence that can destroy a game.
- **Step 21 — close what the audit named.** Not "add coverage": the audit lists
  the specific gaps, and §*What step 21 must close* enumerates them.

### Known and open

From the audit's own table, with its ship decisions:

| open point | audit's call |
|---|---|
| NSP base/update/DLC are indistinguishable from the file | blocker |
| D1 shared RetroArch `wmClass` | blocker for concurrent sessions |
| BlueRoms searches but cannot download | operational blocker for acceptance |
| `duckstation` omits `*.m3u` | may wait, if degraded multi-disc is explicit |
| `pcsx2` declares track extensions with no descriptor | may wait |
| the `example` filter is an unanchored substring | may wait |
| the uninstaller now removes addon data on separate roots | may wait, with an explicit contract |

Two exit criteria are **not met**: *themes adapted* — the Store is reachable in
all three but has no Store-specific layout, deliberately deferred — and *every
console has a validated ingestion strategy*, which fails on the four unlisted
pairs above.

---

## 6. How the work was actually run

Worth knowing, because it explains the shape of everything above and it is not
visible in the commits.

One orchestrating session held the architecture and the order of work. It never
wrote the feature code itself: for each step it produced a **written brief** —
objective, decisions already taken and not open for re-litigation, the question
that step had to settle, production-safety rules, files to read first, expected
tests, and the exact report format — and stopped. A fresh session did the work
against that brief and returned a structured report. The orchestrator then
**re-measured the claims itself** before accepting: the suite, the gates, and
whichever specific behaviour the step turned on.

The dispatch is by hand and deliberately so — the owner carries each brief to a
fresh session and carries the report back. No sub-agent tooling was used, which
is what keeps every brief self-contained enough to be replayed by a human, and
what forces each report to state its starting and ending commit, `Production
touched: NO` and `Worked on main/master: NO`.

That last part is not ceremony. Of the reports returned, several carried a
number or a conclusion that did not survive re-measurement — a red test shipped
unseen, a suite declared hung that was not, a class verdict that contradicted
the contract. Every one of the seven findings in section 4 came out of
re-measuring rather than re-reading.

Two rules that earned their place:

- **A guard that cannot fail guards nothing.** Every new guard was proved to go
  red — a fake pack declaring a forgotten service, an archive trying to escape
  its directory, a write outside the job's area. The two wrong ingestion classes
  lived under 2,565 green tests precisely because no test could fail on them.
- **Measure against reality once, early.** The console-claiming defect, the
  fake `.xci`, the 0 %-resolvable indexer and the never-delivered `p7zip` were
  all invisible offline and obvious within minutes of a real measurement.

---

## 7. Where this sits in the 23-step plan

The chantier followed a numbered plan the owner wrote. Steps **1 to 20 are
done**: clone, the ALL-PACKS analysis and port, the catalogue as source of
truth, the ingestion matrix, the Store core and navigation, the migration out
of Settings, the games tab, Prowlarr, persistent jobs, Real-Debrid,
materializer, inspect, transform, validate, import, library rescan — which
needed nothing, the listing already is the scan — installer and manifest, and
OTA with rollback.

**Step 21** (close the gaps the audit named) and **step 22** (the final audit)
were reordered deliberately, and the reason is worth keeping: running the audit
*first* turns step 21 from "add tests until it feels done" into "close these
named holes". The audit is therefore already written —
`docs/reports/store-final-audit-2026-09-14.md` — and step 21 is what remains.

Phase 2, the deployment plan, was never written and must not be started without
the owner saying so.

---

## 8. What lives outside this repository

None of this is versioned; a fresh clone will not have it.

| path | what it is |
|---|---|
| `~/src/gamecore-store-work/all-packs-v7/` | the extracted ALL-PACKS bundle, including the unported D1 patch and its two tests |
| `~/gamecore-store-sandbox/` | an isolated data root, holding the 8 GB fake-release `.xci` and a full copy of it |
| `~/prowlarr-app/`, `~/.config/Prowlarr/` | a hand-installed Prowlarr, loopback-only, with the owner's real key |
| `~/prowlarr-can-download.py` | tests whether an indexer can actually hand over a file — Prowlarr's own Test button only tests *search*, and an indexer can pass it green and fail every grab |

The sandbox is disposable. The Prowlarr install is the owner's to keep or
remove; if it stays, its service and its Caddy route are a production decision
nobody has taken yet.

---

## 9. Picking this up

**Where things are.** Work in a clone, never in `/opt`, which is production.
The backend runs on `.venv/bin/python`; the frontend on `npm` in `frontend/`.

**Run the suite, always, before believing a result.** Five sub-tasks in a row
got this wrong:

```bash
.venv/bin/python -m pytest backend/tests catalog -q -m "not network"
cd frontend && npm run test:run
```

`test_standby_launch.py::test_the_idle_clock_restarts_from_the_launch` fails
when `-k` deselects its neighbours — a known timing artefact, green in the full
suite. Do not fix it.

**Two manual checks live in `scripts/` and need real credentials**, so they are
not gates and the owner runs them:

- `scripts/prowlarr-filter-check.py` — how many rows an indexer returns versus
  how many the console filter keeps, per console. This is what found the
  PlayStation defect.
- `scripts/realdebrid-resolve-check.py` — resolves one source end to end and
  prints every step.

**The traps, in one place.**

- Never trigger `release.yml`: a `workflow_dispatch` from a branch publishes a
  release the whole fleet installs. Pushing a feature branch is safe — it fires
  on `main`, on `v*.*.*` tags and manually, nothing else.
- `docs/architecture/14-store-ingestion-matrix.md` is the contract. Changing it
  is a decision, not an edit.
- `config/` is excluded from the OTA rsync and from the `.prev` snapshot. That
  is what preserves ROMs, settings and credentials across an update — and it is
  also why rolling back does not roll back `systems.json`, `playtime.db` or the
  Store's two credential files.
- Rolling back leaves a box **degraded but sound**: the restore command has no
  `--delete`, so the 18 new packs survive against older code, their generators
  fail to import, the failure is logged, and the console boots.

**The ground truth on this machine**, worth knowing before re-measuring
anything: the owner's Switch library is almost entirely `.nsp`, all of them
starting `PFS0`; their one `.xci` carries `HEAD` at 0x100; and their only
configured indexer, BlueRoms, searches perfectly and cannot download — its
Prowlarr definition selects `a[href^="magnet:?xt="]` while the site now serves
the magnet base64-encoded in `button#magnet-button[data-link]`, and Cardigann
has no base64 filter to express it. That one is upstream and no GameCore change
fixes it.
