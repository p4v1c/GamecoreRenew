# Testing

```bash
pip install -r backend/requirements.txt pytest
pytest backend/tests -q                     # everything
pytest backend/tests -q -m "not network"    # offline subset — what CI runs
```

147 tests, 143 of which need no network.

## The suite used to be decorative

Every test file kept its whole body inside a `main()` behind
`if __name__ == "__main__"`. `pytest backend/tests/` answered **"no tests ran"** —
green, having executed nothing. A CI job built on it reported success on any
change whatsoever.

The assertions were fine and were kept as they were; only the structure changed:
`check(name, cond)` became `assert cond, name`, `setup_root()` and `reset()`
became fixtures, and the `__main__` blocks stayed, because running a file
directly is documented in its own docstring:

```bash
python backend/tests/test_covers.py         # still works, per-file
```

## `conftest.py` — read this before adding a test

`backend/config` reads `GAMECORE_PATH` **at import time**, and every path in the
application is derived from it. Whichever test module pytest imported first would
therefore decide where the whole suite wrote — and the cover tests would drop
their `.miss` markers into the real checkout, or worse into whatever
`GAMECORE_PATH` the shell already exported.

`conftest.py` is imported before any test module, which makes it the only place
the override is guaranteed to land in time. It points `GAMECORE_PATH` at a fresh
temp directory and publishes it as `GAMECORE_TEST_ROOT`.

It **sets** rather than defaults the variable: inheriting a `GAMECORE_PATH` from
the environment would aim the suite at a real installation.

If you add a module that touches the filesystem, take the root from
`GAMECORE_TEST_ROOT` (or a `tmp_path` fixture) — never from `Path.home()` or a
hardcoded path.

## The `network` marker

```ini
# pytest.ini
markers =
    network: hits an external service (GameTDB, xlenore)
```

Four tests carry it: the GameTDB disc-ID lookup, the two xlenore serial lookups,
and the negative-cache test.

That last one is marked for a reason worth knowing: after the `.miss` fix, a
marker is only written when a lookup actually came back **empty**. A failed
request no longer produces one, so "an unknown game gets negatively cached" is
only true with a working network.

CI runs `-m "not network"` — a release must not be blocked because GameTDB is
down. Verify the offline subset really is offline by blackholing HTTP:

```bash
HTTP_PROXY=http://127.0.0.1:1 HTTPS_PROXY=http://127.0.0.1:1 \
  pytest backend/tests -q -m "not network"
```

## What each file covers

| File | Subject |
|---|---|
| `test_auth.py` | password round-trip, per-IP backoff, and that the **global breaker does not lock out an innocent IP** |
| `test_battery.py` | the low-battery threshold logic: one toast per threshold, rearming, hysteresis |
| `test_controller_profiles.py` | `_dolphin()`'s "is this section already a real pad config?" decision, and that the shipped `GCPadNew.ini` has no keyboard bindings left |
| `test_controller_registry.py` | player-slot assignment, MAC normalisation, battery→slot join |
| `test_covers.py` | the cover pipeline end to end against synthetic dumps; path containment; `.miss` written only for a genuine miss |
| `test_cross_origin.py` | the core's origin guard and `/ws` — including that a LAN client through Caddy is still allowed |
| `test_gamepad_monitor.py` | detection of pads with no Home button; one pad owning several device nodes |
| `test_session_robustness.py` | standby wake, display-probe memoisation, adopting an orphaned game, 503 on a missing emulator |
| `test_systems_extensions.py` | `systems.json.dist` ↔ `config/systems.json` ↔ the README table stay in agreement |
| `test_themes.py` | manifest validation, the completeness rule, theme-id safety |
| `test_update.py` | one update at a time (409), the timeout killing the whole process group, `VERSION` written last |

`test_covers.py` builds real binary fixtures rather than mocking: a PARAM.SFO, an
ISO9660 image (2048-byte and raw 2352-byte layouts), a PS1 `.bin` with a
`SYSTEM.CNF`, a GameCube ID6 header. That is why it catches parser regressions
that a mocked test would not.

## Tests that pin a *document*

`test_systems_extensions.py` parses the "Supported formats per system" table out
of `README.md` and compares it to `install/systems.json.dist`. The table gained
an `emu/<id>/` folder column specifically so the pairing is unambiguous enough to
check mechanically.

It exists because that table had drifted: `.cue` was documented and not declared,
so a standard multi-track PS1 dump showed twelve `.bin` entries and hid the one
file that is meant to be launched. A doc-parsing test has one classic failure
mode — matching nothing and passing — so `test_readme_lists_every_system` asserts
the row count too.

## The other repos

```bash
# gamecore-addons
cd addons/save-manager
PYTHONPATH=../../shared/py python tests/test_api.py      # needs fastapi + httpx
PYTHONPATH=../../shared/py python tests/test_memcard.py  # stdlib only

# gamepad-tv-bridge
python -m pytest tests/
```

`shared/py` is on `PYTHONPATH` because `install.sh` copies `sfo.py` into the
addon directory at install time; from a checkout it has not been copied yet.

## Running a backend by hand

Never against the real install directory:

```bash
GAMECORE_PATH=~/scratch/gc GAMECORE_BACKEND_PORT=8899 \
  python -m uvicorn backend.main:app --host 127.0.0.1 --port 8899
```

`GAMECORE_BACKEND_PORT` matters as well as `--port`: the cross-origin guard
accepts a loopback `Origin` on the backend's **configured** port, so with only
`--port` set an `Origin: http://localhost:8899` would be refused.

Ports 8765, 8443, 8770-8799 and 8097 belong to a running installation. Use
something above 8800 for anything disposable.
