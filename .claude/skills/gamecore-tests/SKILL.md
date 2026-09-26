---
name: gamecore-tests
description: Testing rules for GameCore (GamecoreRenew) — pytest backend and pack tests, vitest frontend, Electron bench, network marker, characterisation before refactor. Use whenever adding logic, fixing a bug, refactoring, or before a PR.
---

# GameCore tests

## Where

| Code | Test |
|---|---|
| `backend/**` | `backend/tests/test_<module>.py` |
| `catalog/<id>/**` | `catalog/<id>/tests/test_*.py` (travels with the pack) |
| `frontend/src/**` | `<file>.test.ts(x)` next to the file |
| `config/themes/<name>/**` | `frontend/src/lib/<name>*.test.tsx` (current layout) |
| `electron/**` | `electron` bench (`npm test`) |

## Rules

1. **A bug fix starts with a test that fails on the old code.**
2. Filesystem: take the root from `GAMECORE_TEST_ROOT` or `tmp_path` —
   never `Path.home()`, never `/opt`, never `/userdata`.
3. Internet → `@pytest.mark.network`. CI runs `-m "not network"`.
4. **Refactor = characterisation first**: snapshot the old output
   (`backend/tests/characterisation.py`), replay against the new code.
5. A test that imports a script does not prove the script runs — also run it.
6. Test names say the behaviour, in English:
   `test_unplug_during_launch_releases_slot`, not `test_case_3`.
7. No sleeps for sync; wait on the condition. Flaky = bug, find the shared state.
8. Test files follow the size budget ×1.5 (`gamecore-file-size`).

## Run (what CI runs)

```bash
ruff check .
python3 -m pytest backend/tests catalog -m "not network"
cd frontend && npm run test:run && npm run build
cd electron && npm test
```

Full list: `CONTRIBUTING.md` "Before you open a pull request", `docs/TESTING.md`.
