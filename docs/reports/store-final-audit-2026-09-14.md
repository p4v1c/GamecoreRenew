# Store final audit — 2026-09-14

## Decision

**Do not release phase 1 in its present state.**  The branch has a real Store,
the catalogue port, persistent jobs, the four post-download stages, installer
and OTA integration, and a large test corpus.  It nevertheless misses two
of the owner's explicit exit criteria and contains two release-blocking seams
which that suite does not exercise:

1. the shipped acquisition/materialisation path can materialise only one file,
   so class E (descriptor plus tracks) and class F (directory tree) cannot be
   produced end to end; an archive containing a descriptor and tracks can
   instead be accepted while silently dropping the tracks;
2. credentials can cross the provider boundary in a Prowlarr GUID, URL
   user-info, or a Real-Debrid error body, then reach an API response, the job
   database, or the journal.

There are also no Store-specific theme adaptations, and four effective
`(system, format)` pairs have no row in the matrix's section 5.1.  Thus the
criteria “themes adapted” and “every console has a validated ingestion
strategy” are not met.  The expected count of 2,697 backend/catalogue tests is
an unverified hypothesis in this environment: two complete runs reached their
1,200-second guard without a pytest summary.  The 612 frontend tests and the
catalogue subset which did finish are useful evidence about the behaviours
they name, but not evidence about these missing compositions.

All audit observations were read-only; the only authorised repository writes
are this report and its index row.  No installer, uninstaller, updater,
emulator, workflow, paid service, or real credential was invoked.

## Scope and baseline

The preflight commands established the requested immutable baseline before any
audit work:

```text
$ git rev-parse --show-toplevel
/home/pavic/gamecore-dev/gamecore-store
$ git branch --show-current
feature/gamecore-store
$ git status --short
<empty>
$ git rev-parse HEAD
0fddd32b...
$ git rev-parse main
59ea18d61...
$ git rev-list --count main..HEAD
22
```

`git log --oneline main..HEAD` names one ALL-PACKS port, the matrix and audit
input, Store shell/search/jobs/acquisition/resolution/materialisation/
inspection/transformation/validation/import, two classification fixes, the
installer manifest, and OTA/rollback work.  The range is exactly the 22 commits
from `c1a4df6` through `0fddd32`; `main` was not checked out or modified.

The required sources were read in the requested order:
`docs/architecture/14-store-ingestion-matrix.md`,
`docs/reports/store-installer-audit-2026-09-12.md`,
`docs/architecture/13-release-and-ota.md`, `docs/SECURITY.md`, then the commit
log.  All code references below are at `0fddd32`.

## Phase-1 exit criteria

| criterion | verdict | evidence |
|---|---|---|
| ALL-PACKS ported | **PASS** | Commit `c1a4df6`; `scripts/check-catalog.py` reports 35 valid packs, of which inspection of `catalog/*/pack.json` finds 31 emulators and four apps.  The port report identifies the 18 imported emulator packs. |
| Catalogue tests green | **PASS** | `.venv/bin/python -m pytest catalog -q -m "not network"` passed 113 tests in 1.24 s; `scripts/check-catalog.py` passed all 35 packs. |
| Matrix covers every effective pack | **PASS, narrow** | Comparing the 31 `kind=emulator` pack IDs to sections 4.1–4.6 of `14-store-ingestion-matrix.md` leaves no pack ID absent.  This is pack coverage, not format-pair coverage; the latter fails below. |
| Store exists | **PASS** | `backend/routers/store.py`, `backend/services/store/`, and `frontend/src/components/StoreScreen/`; router and frontend tests exercise search, jobs, download, cancellation, and rendering. |
| Themes adapted | **FAIL** | `git diff main..HEAD -- frontend/src/themes` changes theme versions and moves Settings' `catalog` page to `apps`; it adds no Store-specific theme layout or styling.  The default shell makes the route reachable, but the explicitly deferred visual adaptation was not performed or accepted on a TV. |
| Console installation moved out of Settings | **PASS** | Commit `906b11f`; `frontend/src/components/SettingsScreen/AppsSettings.tsx` handles apps while emulator management is reached through Store.  Frontend tests cover both destinations. |
| Apps remain managed | **PASS** | Four catalogue packs remain `kind=app`, the Settings apps page still renders and its tests pass. |
| Prowlarr implemented and fake-tested | **PASS, with security failures** | `backend/services/store/prowlarr.py` plus `test_store_prowlarr.py` use mocked HTTP.  No live reconfiguration was made.  The credential tests are incomplete; see Security. |
| Real-Debrid implemented and fake-tested | **PASS, with security and composition failures** | `backend/services/store/realdebrid.py` plus `test_store_realdebrid.py` use fake transports.  No paid call was made. |
| Jobs persist | **PASS** | `store_jobs` is created in `backend/db.py`; `backend/services/store/jobs.py` persists transitions and has restart/recovery tests. |
| Every console has a validated ingestion strategy | **FAIL** | Section 5.1 omits effective pairs `cemu/.rpx`, `dolphin/.wad`, `mame/.cmd`, and `xenia/.xex`; the classifier produces B, B, B, and A respectively.  The matrix test contains seven examples, not the catalogue cross-product.  Moreover classes E and F cannot be formed by the shipped acquisition seam. |
| Materializer, Transformer, Validator, Importer exist | **PASS individually** | `materializer.py`, `transformer.py`, `validator.py`, and `importer.py`, with focused tests for each.  Individual existence does not cure the broken acquisition-to-materializer composition. |
| Library sees imported games | **PASS for synthetic inputs** | `test_store_importer.py::test_imported_game_is_visible_to_library` imports a staged fixture and scans it.  No real acquisition is involved. |
| Installer and uninstaller changed and simulation-tested only | **PASS** | Commit `7da38ae`; manifest/addon fixtures and shell tests cover both directions.  `bash -n install/arch.sh install/uninstall.sh` passed.  Neither script was executed. |
| OTA and rollback covered | **PASS at fixture level** | Commit `0fddd32`, updater tests, rollback tests, and `bash -n update/linux.sh install/steps/install-ota-prerequisites.sh install/steps/setup-gamecore-session.sh` passed.  No updater was executed and no fleet measurement was made. |
| Relevant suite green | **NOT ESTABLISHED in this environment** | Two real runs of `.venv/bin/python -m pytest backend/tests catalog -q -m "not network"` each reached `timeout 1200` with code 124 and no final pytest summary.  This is not a product failure and was not replaced by `collect-only`.  Frontend: 57 files / 612 tests passed. Catalogue: 113 pytest cases and 35 pack checks passed. Docs: 15 documents, all links resolved. Shell syntax: no error for the named installation/update scripts. |
| No real secret used | **PASS for this audit and repository tests** | Provider tests use conspicuously fake values and mocked transports; the adversarial probes below used only `FAKE_*` strings.  No paid endpoint was called.  Git cannot prove what was used outside this audit. |
| No production path modified | **PASS for this audit** | No command wrote `/opt`, `/userdata`, `/var/lib/gamecore`, `/etc`, `/usr/local/bin`, or `~/.var`; no production script ran.  No file under `/userdata` or `~/gamecore-store-sandbox` was read.  The branch diff is repository content only. |

Phase 1 therefore has **15 passes, two failures, and one result not established
in this environment**.  Several qualified passes also carry release blockers;
an exit checklist is not a substitute for the findings below.

## Release blockers, in priority order

### 1. Multi-file ingestion does not exist end to end

`RealDebridAcquisition._choose_file()` chooses exactly one `(file_id, name,
size)`; `_select()` sends exactly that ID; `_wait_for_link()` returns the first
download link.  `AcquiredTarget` is singular and
`Materializer.materialize()` creates one final file.  Those facts are visible
at `backend/services/store/realdebrid.py:503-599`,
`backend/services/store/jobs.py` (`AcquiredTarget`), and
`backend/services/store/materializer.py:91-206`.

Classes E and F require, respectively, a descriptor plus companion tracks and
a preserved top-level directory.  Their transformer/validator tests begin
with those shapes already staged; no test asks acquisition and the
materializer to create them.  Consequently the green component tests cannot
demonstrate a working Dreamcast/PS2 descriptor set or RPCS3 directory.

There is a more damaging accepted path.  A synthetic ZIP containing
`Game.cue` referencing `Game.bin`, run through the real inspector,
transformer, and validator for Dreamcast, produced:

```text
inspection Inspection(ingestion_class='A', complete=True, reason='')
shape A ('Game.cue',)
validation unverified ('Game.cue',)
```

The inspector calls an archive A when it contains a declared playable member
(`inspector.py:238-269`).  The class-A transformer extracts only pack-declared
extensions (`transformer.py:445-483`); Dreamcast declares the descriptor, not
the `.bin` track.  The persisted A classification then selects plain-file
validation (`validator.py:456-482,690-711`).  The result is an importable,
unplayable descriptor with its data silently discarded.  The probe used only
a temporary directory and invented bytes.

Release requires an explicit acquisition representation for all selected
files/directories, a materializer which preserves it, and an end-to-end test
through import and library discovery for every ingestion class.  Archive
classification must not permit a descriptor to shed its companions.

### 2. Credentials can escape all three claimed barriers

The intended barriers are useful but incomplete:

* Prowlarr redaction replaces named credential query parameters only
  (`prowlarr.py:168-174,395-396`).  A fake Prowlarr row whose `guid` contained
  `/download/FAKE_PRIVATE_PASSKEY/9` produced a `SearchResult.source` retaining
  that path (`prowlarr.py:646-688`).  `SearchResult.to_json()` sends `source` to
  the browser, and enqueue persists it as `store_jobs.source`
  (`search.py:196-209`, `db.py:56-78`).  The existing test covers `rss_key` in
  a query string, not path tokens or URL user-info.
* Both provider URL cleaners preserve `urlsplit(...).netloc`.  Synthetic
  `https://FAKE_USERINFO@...` configuration survived in both `_where()` values
  (`prowlarr.py:255-268,399-407` and
  `realdebrid.py:220-233,333-342`), hence in diagnostic text.
* Real-Debrid `_detail()` normalises and truncates the response body but does
  not redact it (`realdebrid.py:703-722`).  A synthetic 500 JSON body containing
  `FAKE_REALDEBRID_TOKEN` retained the token in the exception.  Job settlement
  writes exception text to `reason`, logs it, and `Job.to_json()` exposes it
  (`jobs.py:247-268,994-1015`).  The Store router's generic 502 protects search
  exceptions only (`backend/routers/store.py:123-143`), not asynchronous job
  errors.
* Real-Debrid configuration accepts `http://` (`realdebrid.py:220-233`) while
  every request receives an Authorization bearer header
  (`realdebrid.py:409-417`).  A non-default endpoint can therefore transmit the
  token without transport encryption.

The clear-link refusal in `resolve.torrent_token_of()` correctly rejects a
base64url token which decodes to text containing `://`
(`resolve.py:409-457`).  It does not cover arbitrary Prowlarr GUIDs, URL
user-info, HTTP endpoint configuration, or provider error bodies.  A generic
502 is similarly not a journal/database redaction policy.

Release requires taint-style tests which place a fake sentinel in every input
field and provider response, then assert it is absent from logs, database rows,
and every API response.  Reject URL user-info and non-HTTPS Real-Debrid
endpoints; never retain arbitrary remote error bodies or opaque source URLs.

### 3. The matrix is not executable and misses four real pairs

Section 5.1 lists members while section 5.2 describes a predicate over all
declared formats.  Enumerating every current pack format against the actual
classifier exposes four pairs not named in 5.1:

| pair | actual class |
|---|---|
| `cemu/.rpx` | B |
| `dolphin/.wad` | B |
| `mame/.cmd` | B |
| `xenia/.xex` | A |

`test_store_inspector.py`'s matrix table has only seven examples (NES ZIP,
SNES SFC, MAME ZIP, DuckStation CHD/CUE, Ryujinx XCI, RPCS3 directory).  It
does not compare every effective pair to the contract.  This is the same class
of blind spot that allowed two of six classes to remain wrong while 2,565
tests were green.

The `.cmd` case is not merely documentary.  Search declares `cmd` as
never-offered evidence, but a synthetic Prowlarr result named
`Some Game.cmd` with a MAME-bearing release title was admitted by system-name
evidence.  The existing test uses a title with no MAME evidence and therefore
does not exercise the bypass.  Inspection then classifies the file B.  Until
the product decides what `.cmd` means, it must not be offered or imported.

Release requires one machine-readable source for classification and a
generated, exhaustive catalogue cross-product test.  The decision for each of
the four pairs must be written into that source rather than inferred from
fallback code.

### 4. Switch updates and DLC are deliberately importable as games

The matrix's section 4.5 records that `.nsp` cannot distinguish a base game
from update/DLC by suffix.  `importer.py:183-188` nevertheless imports any
validated `.nsp` and returns only a warning; its test at
`test_store_importer.py:161-170` asserts that behaviour.  The library then
shows the package as a game tile.

This is not a harmless metadata imperfection: an accepted Store result can
produce a tile that cannot launch as a base game.  Release needs content-aware
classification or trustworthy acquisition metadata.  In their absence, NSP
must be refused rather than knowingly published.

### 5. Cancellation can outlive import and race cleanup

The worker awaits `asyncio.to_thread(import_shape, ...)`
(`jobs.py:975-979`).  Cancellation marks the database row cancelled, cancels
and awaits the asyncio task, then cleans the job (`jobs.py:767-803`).
Cancelling the await does not stop the worker thread.  Import can therefore
continue publishing after the row says cancelled or race the cleanup.  No test
cancels during import.

Importer rollback removes its recorded published names
(`importer.py:119-127,159-181`).  If another local actor replaces one of those
paths before rollback, deletion is by pathname rather than by proven object.
The normal path has useful root, symlink, collision, and no-overwrite guards,
but they do not close these races.  Release needs controlled cancellation at
every await boundary, an import transaction which cannot outlive ownership,
and adversarial replacement tests.

### 6. The 17 new RetroArch packs inherit unresolved window ownership

The matrix's D1 remains open: the 17 RetroArch packs share one `wmClass`.
With two games in the same core family, focus/session tracking can attach to
the wrong window.  This is directly in the path of the newly ported catalogue
and GameCore's background-session behaviour, so it is a phase-1 blocker unless
the release explicitly disables concurrent RetroArch sessions.  Closing it
costs a D1 ownership design plus launch/focus/return regression tests on a
real compositor, not more catalogue unit tests.

### 7. The owner's configured indexer cannot complete the owner journey

BlueRoms searches but its Prowlarr definition cannot download.  This is an
upstream operational blocker rather than evidence that the repository's
generic Prowlarr client is wrong.  It still prevents the promised owner flow
from search through import on the deployed configuration.  Release needs a
fixed definition or a different working indexer and one legal, non-paid,
end-to-end acceptance sample.

## Findings that may wait until after release blockers

These are not reasons, by themselves, to hold a release candidate once the
blockers above are closed:

1. Prowlarr deliberately recognises `.rar` as an offered archive
   (`prowlarr.py:148-149`), while inspection recognises only `.zip` and `.7z`
   (`inspector.py:20`).  Such a result can consume acquisition time only to be
   treated as a plain file and rejected downstream.  Either stop offering RAR
   or support and adversarially test it; this is a bounded availability defect,
   not a path-escape route.
2. DuckStation's missing `*.m3u`, PCSX2's track-without-descriptor declarations,
   and the unanchored `example` substring are safe refusals or degraded library
   behaviour under the present contract.  They may wait if the limitations are
   made explicit; changing them requires pack, scanner, import and UI tests
   together.
3. The stale Store comments and theme documentation mislead maintainers but do
   not alter runtime behaviour.  They should be corrected only after the code
   decisions settle, with a semantic gate that can catch the next drift.
4. Addon-data removal may wait only if the configured roots are contractually
   exclusive to GameCore and the operator accepts the scope.  A shared real
   root would promote it to a destructive release blocker.

## Security review

### One LAN port

Static review found no added listening daemon, socket unit, Caddy listener, or
Store `bind`/`listen` call in `main..HEAD`.  Store routes are mounted in the
existing backend.  The only new service-shaped items are one-shot migration or
sync work, not listeners.  This preserves the design which followed the
documented EmberTV failure: a second LAN port created an unauthenticated path
around the single proxy/authentication boundary (`docs/SECURITY.md:7` and its
history).

The runtime corroboration could not be made: `ss -tlnp` returned “Cannot open
netlink socket: Operation not permitted” in this audit sandbox.  This is an
environmental limitation, not a claim that the box is blocked or that the
invariant has failed.  A release-candidate box should capture `ss -tlnp` and
map every listener to its unit.

### Decompression closure

The path traversal closure held under independent synthetic probes.  A raw ZIP
entry `../../escaped.nes` was flattened to `escaped.nes` and remained inside
the staging root.  Calling the explicit escape guard on the same name refused
it.  Calling the final containment guard on an outside target also refused it.
Thus name flattening and explicit/containment validation each stop that path
even if the other policy changes.

Existing real-archive tests add traversal names, absolute names, archive
symlinks, and a class-F symlink to `/etc/passwd`
(`test_store_transformer.py:295-391`); all passed.  The 7z path streams named
members rather than asking 7z to choose filesystem destinations.  This is a
pass for pathname escape.  It is not a proof against every decompressor parser
bug or resource-exhaustion archive; those need bounded-output tests and a
patched system decompressor.

### OTA package authority

`install/steps/install-ota-prerequisites.sh:27-49` contains a fixed
`REQUIRED=(p7zip)`, checks with `pacman -Qq`, and installs with
`pacman -S --noconfirm --needed`.  It does not consume caller-supplied package
arguments and contains no `-Syu`.  `update/linux.sh` does not call pacman.  The
root migration service invokes the release-owned migration helper without
arguments; that helper selects its manifest and setup step from the installed
release (`install/system/gamecore-session-migrate.service:25-30`,
`install/bin/gamecore-session-migrate:11-98`).  Shell syntax and fixture tests
passed.  This is a code-level pass; pacman/systemd were not exercised.

### Destructive paths

Transformation has job-root containment, rejects symlinks and archive escape,
and cleans only its derived staging paths.  Import uses pack-derived library
roots, rejects symlinked destinations, uses no-replace publication, and rolls
back its own recorded names.  The uninstaller's `safe_rm` applies a depth guard
and deletes only configured GameCore data roots.  These controls stop ordinary
path injection; the import cancellation/replacement race above prevents an
unqualified pass for concurrent destruction.

The updated uninstaller intentionally deletes addon data as well as catalogue
data, including when addon data lives on a separate configured root.  That is
acceptable only if that root is exclusively GameCore-owned and the destructive
scope is explicit to the operator.  The fixture proves expansion of the named
root, not absence of unrelated user material in a reused real directory.

## Drift and dead-contract review

The prior `assets-installed` failure—declared and documented for months but
never written—has been removed by `7da38ae`, and a test asserts its absence.
No comparably certain runtime-orphan export was proven in this pass; the broad
`backend.services.store` public exports are heavily test-used and may be an
intentional package API.  Calling them dead solely because the present router
does not import each name would be speculation.

Several current comments/documents do contradict the implementation:

* `docs/themes/README.md:552` says only the demo provider exists, while
  Prowlarr is shipped.
* The same file at line 556 says `gamesDownloadReady` is false and there is no
  queue, while `/jobs` returns true and the frontend consumes it
  (`backend/routers/store.py:196-213`, `StoreScreen/index.tsx:626-629`).
* Lines 566–584 first state games are ready, then state search/download are
  still future work.
* `frontend/src/components/StoreScreen/index.tsx:33-37` says there is no worker,
  every job fails, and download readiness is false; all three are stale.
* `backend/services/store/__init__.py:3-8` says byte-to-playable work is outside
  this package, while lines 10–20 describe and export the full ingestion chain.
* The matrix header pins its snapshot to `c1a4df6`; later classification fixes
  mean it is historical unless continuously checked.

`scripts/check-docs.py` passed all 15 documents because it validates paths and
links, not semantic assertions.  These contradictions are direct evidence
that documentation truth can drift while the docs gate remains green.

## Known open points: ship decision and cost

| known point | ship decision | closure cost |
|---|---|---|
| Section 5.1 list versus section 5.2 predicate; four missing pairs | **Blocker** | Make the contract executable, decide all four pairs, generate exhaustive tests. |
| NSP base/update/DLC ambiguity and Ryujinx routing | **Blocker** | Inspect package metadata or require trustworthy type metadata; add base/update/DLC fixtures and refuse unknowns. |
| DuckStation omits `*.m3u` | **May wait** if degraded multi-disc support is explicit | Pack declaration, scanner/import behaviour, multi-disc fixtures and UI expectations. |
| PCSX2 declares track extensions without a descriptor | **May wait** because the Store currently refuses the incomplete shape | Decide CUE support, then change pack, ingestion, scanner and tests together. |
| Format detection uses an unanchored `example` substring | **May wait**: current consequence is a safe availability false-negative | Anchor the predicate and add negative/positive catalogue tests. |
| D1 shared RetroArch `wmClass` | **Blocker** for concurrent sessions | Stable per-launch ownership and real compositor/session regression tests. |
| Uninstaller removes addon data on separate roots | **May wait only with explicit exclusive-root contract** | Operator-facing destructive scope, ownership proof, and a disposable multi-root uninstall exercise. |
| BlueRoms searches but cannot download | **Operational blocker** for the owner's acceptance path | Repair the upstream definition or choose a working indexer; run one legal non-paid acceptance download. |

## Owner decisions taken after this audit

The audit is a finding, not a verdict on what to build. These were decided by
the owner once the findings were on the table, and are recorded here so that a
later reader does not mistake a choice for an oversight.

### Blocker 2, credential escape — **accepted, not fixed** (2026-09-14)

The three paths are real and were reproduced twice, once by the audit and once
independently: a private-tracker passkey inside a `guid` **path** reaches
`SearchResult.source`, `to_json()` and `store_jobs.source`; URL user-info
survives both `_clean_url`s into every `_where()` diagnostic; and a remote error
body is copied verbatim into a job's `reason`, which is logged and exposed.

The owner's judgement, and it is sound on severity: none of this is reachable
from the network. `/api/*` is 403 through Caddy, so the Store's API and screen
are loopback-only; there is no privilege escalation and no remote exposure.
The exposure is to whoever already has the box.

What remains true, and was said before the decision rather than after: **logs
get pasted.** During this chantier the owner pasted terminal output into a chat
a dozen times, and a real Real-Debrid key was offered and declined for exactly
that reason. A tracker passkey in a journal line would travel the same way.
There is also a non-security cost: a `source` carrying a full tracker URL is no
longer opaque, and opacity is the property the whole resolution redesign was
built on — `(indexerId, guid)` was rejected precisely to obtain a clean,
durable locator.

Cost of closing it later: four small changes — redact URL paths, refuse
user-info, refuse a non-HTTPS Real-Debrid endpoint, stop retaining remote error
bodies — plus the taint test that keeps the class of bug from returning. The
taint test is the expensive half and the only part that prevents recurrence.

**This is a decision, not a gap.** It should be revisited before the box is
ever used by someone other than its owner, and before any log from it is shared.

## What step 21 must close

Step 21 should not be “add more coverage.”  It should add these named
observations:

1. Generate every `(pack, declared extension/container)` row and compare its
   classification with one machine-readable ingestion contract; fail on any
   unlisted row.
2. Exercise search/resolution/acquisition/materialisation/inspection/
   transformation/validation/import/library as one chain for A–F, including a
   genuinely multi-file E and directory F.  Do not inject the post-materializer
   shape.
3. Feed an archive-wrapped CUE plus track through that chain and assert that
   every referenced companion survives; repeat for applicable disc systems.
4. Prove `.cmd` remains unavailable even when system-name evidence says MAME,
   until its semantics are decided.
5. Put one fake credential sentinel in query values, URL paths, URL user-info,
   GUIDs, redirect/download links, and success/error bodies; assert the sentinel
   is absent from logs, API payloads, exceptions, and database rows.  Assert
   Real-Debrid rejects HTTP and user-info endpoints.
6. Cancel at each job await boundary, especially during the importer thread;
   prove no publication continues after cancellation and cleanup cannot remove
   a replacement object.
7. Distinguish Switch base games, updates, and DLC with fixtures, or assert all
   unproven NSPs are refused before import.
8. Render and navigate Store with a gamepad in every shipped theme at the TV
   viewport, with visual baselines for focus, overflow, keyboard and job states.
9. Run concurrent games for the 17 shared-wmClass RetroArch packs and prove
   focus, stop, and return target the originating process/window.
10. Statistically scan release units and capture live listeners on a disposable
    release candidate; assert the documented single LAN entry point.
11. Exercise the root OTA helper and rollback on a disposable old-layout image;
    assert the release manifest alone selects packages, no arguments reach
    pacman, and no sync/full-upgrade flag appears.
12. Run provider protocol tests against local fake HTTP servers, plus one legal
    working-indexer acceptance run; include redirects, multiple torrent files,
    multiple unrestricted links, timeouts, malformed bodies and echoed secrets.
13. Decide whether RAR is supported or never offered, then test that decision;
    add bounded-output/archive-count/time cases, including adversarial 7z
    fixtures, rather than treating path containment as resource safety.
14. Give the stale Store documentation assertions a semantic/versioned gate or
    remove them as executable claims.

## Measurements not made

* A completed backend result: two full runs reached the requested 1,200-second
  guard, and a Store-only run reached a 600-second guard, all after printing
  progress dots but without a final pytest summary.  Catalogue tests completed
  normally.  Needed: rerun the exact full command on the known reference
  environment and retain its terminal summary.  This audit does not infer an
  `aiosqlite`, Python, or product defect from the sandbox-specific observation.
* Live socket inventory: netlink access was denied.  Needed: `ss -tlnp` on a
  disposable or production-equivalent candidate, with permission to inspect
  owning processes.
* Actual install/uninstall/update/rollback: expressly forbidden, including
  dry-run.  Needed: a disposable Manjaro/GameCore image with representative
  split roots and an old release, never the owner's live data.
* Real emulator launch, TV theme, gamepad, compositor and D1 behaviour: no
  emulator was run.  Needed: staging hardware, legal tiny fixtures for all 18
  ported packs, and an explicit concurrent-session protocol.
* Paid Real-Debrid and live Prowlarr acquisition: no paid service was called and
  loopback Prowlarr was not reconfigured or queried.  Needed: local protocol
  fakes for deterministic security tests, then an owner-authorised legal
  acceptance sample through a working indexer.
* Real external/cross-filesystem import and destructive rollback races: needed
  on disposable mounted filesystems with controlled cancellation and pathname
  replacement.
* The 8 GiB download and its backup in `~/gamecore-store-sandbox`: not read;
  the code questions were answered by minimal invented fixtures.  `/userdata`
  was likewise not read at all.

## Commands and production ledger

Read-only gates executed:

```text
timeout 1200 .venv/bin/python -m pytest backend/tests catalog -q -m "not network"
# first run: exit 124, no final pytest summary
# second run: exit 124, no final pytest summary

timeout 600 .venv/bin/python -m pytest catalog -q -m "not network"
# 113 passed in 1.24 s

timeout 600 .venv/bin/python -m pytest backend/tests/test_store_*.py -q \
  -m "not network"
# exit 124, no final pytest summary

cd frontend && npm run test:run
# 57 files, 612 tests passed

bash -n install/arch.sh install/uninstall.sh update/linux.sh \
  install/steps/install-ota-prerequisites.sh \
  install/steps/setup-gamecore-session.sh
# no output, exit 0

.venv/bin/python scripts/check-catalog.py
# 35 packs OK

.venv/bin/python scripts/check-docs.py
# 15 documents; all referenced paths and links resolve
```

The independent classifier, archive, and credential probes imported repository
modules against temporary invented data under `/tmp`; they made no network
request and touched no production path.

Production touched: **NO**.  Worked on `main`/`master`: **NO**.  Worktree writes
outside `docs/reports/`: **NO**.  Reads under `/userdata`: **none**.  Reads under
`~/gamecore-store-sandbox`: **none**.

The rule “do not add a second LAN port” names EmberTV's authentication bypass;
“do not infer coverage from a green count” names the prior 2,565-green/
two-wrong-classes failure; and “do not run lifecycle scripts against the box”
names their authority to install packages and remove catalogue/addon data.
