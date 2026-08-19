# Refactoring — diagnostic and decisions (2026-08-19)

Branch `factorisation`, based on `installer` (both since merged). Method:
every "dead" claim proven by searching for callers (scripts, docs, CI, tests,
units, sudoers); every factoring justified by a **lived** double-edit, not by
resemblance; every decision NOT to factor written here, so a future pass does
not undo what is duplicated on purpose.

## Removed (proven dead)

| what | proof |
|---|---|
| `scripts/revert-migration.sh` | zero callers anywhere; restores snapshots of an earlier migration mechanism that no longer exist; the living way back is the epilogue `migrate-userdata.py` prints |
| `emu/**/.gitkeep` (12 files) + `.gitignore` rules | a hand-kept skeleton of ROM directories, already stale (no shadps4, no xenia); the installer creates these directories from the catalogue (`catalog-query rom-dirs`), `provision_userdata` creates `emu/`, `rom_scanner` treats absence as empty |
| `verify_emulators.py` (repo root) | moved to `scripts/verify-emulators.py` — same naming as the other eleven tools; 2 callers updated (CI `verify-catalog.yml`, `test_catalog_consumers`) |

## Factored (one fact, one place)

| fact | before | after |
|---|---|---|
| Flatpak sandbox policy | `providers.sandbox_flags()` **and** a copy in `catalog-query.py` — both edited in the same commit on Aug 18 (when the data root joined the flags) | the script imports the real one; import chain verified stdlib on the system python3, which is `arch.sh`'s constraint |
| atomic write (power-cut safety) | **six** copies: configgen `helpers/base.py`, `pergame._atomic_write`, inline in `bezels` (×2), `bezel_capture`, `merge` (×2), `ota` (×2) | `backend/utils.atomic_write` (+ `atomic_write_json`, dumps kwargs passed through — not one byte of output changes); `base.py` delegates keeping its name |
| system-id boundary | the same regex in `routers/overlays.py` and `routers/pergame.py` | `backend/utils.SYSTEM_ID_RE` |
| the 10 MB bezel cap | `_MAX_BEZEL_BYTES` (bezels) + `_MAX_OVERLAY_BYTES` (router) | `bezels.MAX_BEZEL_BYTES`, the router refers to it |

## Examined and left alone — the false positives

These duplications **are intended**. Merging them would break a contract.

- **`install/bin/gamecore-addon` is self-contained.** Copied to
  `/usr/local/bin` by the installer: it can import nothing from the repo. Its
  python-heredoc helpers that resemble the backend stay its own.
- **`_data_root_from_backend_unit` duplicated** (CLI + `update/linux.sh`).
  The updater must not depend on the CLI's presence or version.
- **rom-manager (addons repo) mirrors `fmt_size`/`clean_name`/
  `iter_rom_files`.** Self-contained addon contract — stated in its source; a
  core import would tie the addon to the install tree.
- **`arch.sh` stays monolithic.** Documented decision
  (`11-install-script-seams.md`); no phase extraction here.
- **`make-console-bezel.py`'s PNG encoder vs `test_bezels`'s `_encode`.** Two
  needs (rendering a real bezel vs per-filter fixtures); merging would couple
  tool to tests.
- **`_human` (migrate-userdata) vs `utils.fmt_size`.** Different formats, and
  the migration script reads standalone, outside the venv.
- **`_FreshStatic` (addons) vs `_NoCacheStatic` (core).** Two repositories,
  two release cycles.
- **`data_path_problem` (GUI, Python) vs `_conf_path` (arch.sh).** The same
  rule at both boundaries, each in its own language; a bridge would be more
  fragile than the duplication.
- **The overlay upload route's `mkstemp`.** Not the same problem as
  `atomic_write`: **concurrent** writers — the unique name is the protection,
  and the call-site comment records the failure that demanded it.

## Seen, not handled (out of scope, to decide later)

- `docs/reports/*.md`: the session records (this one included) — useful as
  project memory; prune someday if the folder swells.
- `backend/utils.fmt_size` labelled KB/MB while dividing by 1024 — cosmetic.
  (Fixed in v1.2.15: binary labels, both repos.)

## The one-hour review pass (same day)

Hunk-by-hunk reread of the whole diff, plus running every consumer for real.
Two real finds, two tightenings:

1. **Caught regression: `scripts/verify-emulators.py` no longer ran.** Moved
   one directory deeper, its `sys.path.insert(...parent)` pointed at
   `scripts/` instead of the repo root — `ModuleNotFoundError: backend` when
   executed. The test still passed: it imports the file with `sys.path`
   already set up. The Monday CI job would have broken silently. Fixed
   (`parents[1]`, like the other ten tools), proven by running the Monday job
   end to end — green, network included. Lesson recorded: a test that imports
   a script does not prove the script launches.
2. **`atomic_write` now writes `encoding="utf-8"` explicitly.** `merge.py` and
   `ota.py` did (JSON with `ensure_ascii=False`); inheriting the locale put
   that choice back at the mercy of a unit's environment. (PEP 540 covers the
   `C` locale — verified — not an arbitrary non-UTF-8 one.)
3. `base.py`: relative import like everywhere else; `.gitignore`: an orphan
   comment from the old `.gitkeep` scheme removed.
4. **Unified semantics said out loud**: the helper does `mkdir(parents=True)`
   where the original `base.py` did not. Verified call site by call site: all
   five configgen callers write next to a file they just read, or after their
   own `mkdir` — the unification is a no-op, not a gamble.

Counter-checks replayed: output bytes identical to the historical shape
(`merge_file` on an accented label, binary comparison); all nine
`catalog-query` subcommands and `gamecore-provider --dry-run` on the system
python3; no reader globs an orphan `.gamecore-tmp`; no test pins the old
constants; `merge-tree` simulation against main: zero conflicts. Full suite:
1707 green, the 2 failures being the `test_launch_reconcile` flake reproduced
identically on the base branch in the same environment (control experiment in
a worktree: same totals, same two failures, and the single diverging skip
traced to the line — `test_electron_cache.py:70`, "no frontend build on
disk", the worktree having none: environmental, not branch).

## The `test_launch_reconcile` flake — killed during the review

Halving bisection over the 93 test files: reproducible behind
`test_gamemedia.py` **or** `test_http_cache.py` alone (four "innocent"
predecessors, routers included, stay green). The excess release calls carried
`pack_ids=None` — the signature of the monitor's sweep
(`gamepad_monitor._reconcile`, l.564), not the launch's. `release_profile`
being one shared module object, the recorder a test installs is reachable by
any monitor pass alive in the process — including one belonging to a previous
test's app. The fixture, which already blinded the monitor's input, now also
no-ops `_reconcile` (exact signature): the recorder becomes unreachable from
everywhere. Result: the project's first fully green complete suites (1709/0,
twice in a row); the old "red baseline with a controller" note is retired.
