---
name: gamecore-file-size
description: Prevent giant files in GameCore (GamecoreRenew). Use before adding code to any file, when creating a module, when a file passes ~400 lines, and in every review. Gives the line budgets, the exemption list, and how to split Python services, React screens, Electron main, theme CSS and shell installers.
---

# GameCore file size

Big files are where bugs hide and where two features collide. Budget:

| Lines (code files) | Status | Action |
|---|---|---|
| ≤ 400 | target | — |
| 401–600 | warn | new code goes in a new module if it is a new concern |
| 601–800 | too big | extract **before** adding |
| > 800 | hard limit | no net growth; the PR that touches it must shrink it or explain why not |

Functions: ≤ ~50 lines. Components: one component per file (tiny private
helpers allowed).

## Run the check

```bash
bash .claude/skills/gamecore-file-size/scripts/check-file-size.sh          # whole repo
bash .claude/skills/gamecore-file-size/scripts/check-file-size.sh --diff   # files changed vs origin/main
```

In `--diff` mode a FAIL on a file that was already over budget means: check
`git diff --stat` — it must not have grown.

## Exempt (with reason)

- Generated: `install/generated/*`, `install/installer-gui/catalog_data.py`
- Data / vendored: `backend/data/gamecontrollerdb.txt`, `backend/services/gamemedia/` vendored parts, seeds, fixtures (`**/tests/fixtures/**`, `catalog/*/seed/**`)
- Lockfiles, `LICENSE`, `CHANGELOG.md`
- `install/arch.sh` / `uninstall.sh`: monolithic **by decision**
  (`docs/architecture/11-install-script-seams.md`) — still no net growth
  without a pack-model reason.
- Tests: budget ×1.5; split by behaviour when over (`test_<module>_<behaviour>.py`).

## How to split

- **Python service** → package: `services/<name>/__init__.py` re-exports the
  public API, one file per concern (see `services/configgen/`,
  `services/gamemedia/`). Callers do not change.
- **Router** → move logic to a service first; then split by resource
  (`routers/settings/` is the model).
- **React screen** → decisions stay in `index.tsx`, markup in
  `Default*View.tsx`, pure helpers in `lib/`, state logic in a `use*` hook.
- **`frontend/src/api/index.ts`** → one file per group (`api/games.ts`,
  `api/settings.ts`…) re-exported from `api/index.ts`.
- **`electron/main.js`** → one module per window/IPC domain, `main.js` wires.
- **Theme CSS** → one stylesheet per view (`views/library.css`…) imported by the theme.
- **Pack daemon** (`catalog/*/files/*.py`) → split parsing/offsets from the
  event loop; keep stdlib-only.
- Keep the old import path working (re-export) so the split is a no-op for
  callers, and snapshot behaviour first (`backend/tests/characterisation.py`).

## Never

- Split by line number ("part1/part2"). Split by concern.
- Create `utils2.py` / `helpers_misc.py` dumping grounds.
