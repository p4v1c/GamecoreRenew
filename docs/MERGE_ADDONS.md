# Runbook — merging the addon system into `main`

One-time procedure to ship the addon system (branch `feat/addons`) to
production and migrate the living-room box, **without ever losing ROM
upload**.

> Read this whole page before starting. Nothing here runs automatically.

## What ships

6 commits on `feat/addons` above `main`:

| commit | what |
|--------|------|
| `c8b21c8` | addon system core — `gamecore-addon` CLI, registry, `/api/addons` |
| `a0cc27c` | **BREAKING** — ROM Manager extracted to the `rom-manager` addon (core drops `/roms`) |
| `b3d7bc9` | review fix — `list` resilience, deprecated asyncio call |
| `2f839e2` | native graphical installer (Qt binary) + `arch.sh --unattended` |
| `c076408` | review fix — core-port plumbing, installer robustness |
| `0735da2` | CI — installer binary build is non-blocking |

Addons live in a **separate repo** `p4v1c/gamecore-addons` — they are not
shipped by this merge and never installed by the OTA. GameCore runs fine
without any addon.

## THE ONE HARD RULE — order

The new core **removes `/roms`** from port 8765. So the `rom-manager`
addon must be **serving on the box before the new core is deployed**,
otherwise ROM upload has a gap.

Correct order → **install the addon first, deploy the core second.**

---

## Pre-flight

- [ ] Box safety snapshot exists: branch `box-state` in `/opt/GameCore` ✓ (created 2026-07-04).
- [ ] Box is on `main`, clean except the intentional `config/systems.json` divergence — the OTA rsync **excludes** `config/`, so it is never overwritten.
- [ ] Do the GitHub merge from the **sandbox** (`~/gamecore-test/GamecoreRenew`) or via a PR — **never** from `/opt/GameCore` (it sits on old `main` with a modified `systems.json`; a `git pull` there would conflict). The box only ever updates through the OTA, not through git.

## Step 1 — merge `feat/addons` → `main` (triggers CI)

Via a PR (reviewable) or directly:

```bash
cd ~/gamecore-test/GamecoreRenew
git checkout main && git pull
git merge --no-ff feat/addons
git push origin main
```

The CI then: auto-bumps the patch tag → builds `gamecore-ota.tar.gz` +
`gamecore-full.tar.gz` → tries to build the installer binary
(non-blocking) → publishes the release. Wait for the release to appear
before touching the box.

## Step 2 — bootstrap the addon system on the box (manual, one-time)

The OTA does **not** install the CLI. Do it by hand — and do it **now**,
before the OTA, so `rom-manager` can be installed while the old core still
serves `/roms`:

```bash
# on the box
sudo install -m755 ~/gamecore-test/GamecoreRenew/install/gamecore-addon /usr/local/bin/
sudo install -d -o "$USER" -g "$USER" /opt/gamecore-addons
```

(If the sandbox checkout is gone, grab the script from the release's
`gamecore-full.tar.gz` under `install/gamecore-addon`.)

## Step 3 — install `rom-manager` (box still on the old core)

```bash
gamecore-addon install rom-manager
```

Now **both** are live: old `/roms` on 8765 **and** the addon on 8770.
Verify the addon:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8770/api/emulators   # → 200
```

Optional at this point:

```bash
gamecore-addon install rpcs3-manager   # PS3 config/patches on 8771
```

## Step 4 — deploy the new core (OTA)

From GameCore → Settings → Update → **Check / Apply** (or run
`update/linux.sh`). This rsyncs the new core (excluding `config/`,
`emu/`, …), sets the new VERSION, and restarts via
`gamecore-restart.service`.

After the restart: `/roms` on 8765 is gone (expected), `rom-manager` on
8770 has been serving continuously → **zero gap**.

## Step 5 — verify

```bash
curl -s -o /dev/null -w 'core /roms (should be 404): %{http_code}\n'  http://localhost:8765/roms
curl -s -o /dev/null -w 'rom-manager (should be 200): %{http_code}\n' http://localhost:8770/api/emulators
curl -s http://localhost:8765/api/addons        # registry lists installed addons
gamecore-addon list                             # available vs installed
```

- [ ] Upload a ROM via `http://<box-ip>:8770` → it lands in `emu/<system>/` and the TV home refreshes (the `rom_uploaded` event still fires, now via `/api/addons/notify`).
- [ ] Update any bookmark/QR from `:8765/roms` to `:8770`.

---

## Rollback

**Addon only** (core untouched):
```bash
gamecore-addon remove rom-manager      # stops + disables its service, cleans the registry
```

**Whole core** — the addon migration was pushed but you want the old core
back: re-deploy the previous release. The box's `box-state` branch is the
pre-migration snapshot of `/opt/GameCore`; the previous GitHub release
tag is the pre-merge core. Reinstalling the old `gamecore-ota.tar.gz`
(or `git checkout box-state` + restart) restores `/roms`.

Because ROMs (`emu/`), configs (`config/`) and covers are excluded from
every rsync, **no user data is at risk** in either direction.

## Notes

- `config/addons.json` (the registry) lives under `config/` → survives every OTA.
- `/opt/gamecore-addons` is outside `GAMECORE_PATH` → the OTA never touches it; `gamecore-addon update` manages it independently.
- The installer binary is a release convenience for **fresh** installs; it is irrelevant to this in-place migration.
