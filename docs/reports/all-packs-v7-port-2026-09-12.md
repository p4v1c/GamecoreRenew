# Porting the ALL-PACKS v7 payload onto `feature/gamecore-store` — 2026-09-12

The ALL-PACKS v7 CANDIDATE bundle adds 18 emulator packs, rewrites the RPCS3
pack and replaces ~5,100 duplicated generator lines with one shared RetroArch
helper. It was built against a commit six commits behind this branch, and its
own `APPLY-ALL.sh` refuses to run anywhere else. This session treated it as a
patch to port, not a script to obey: it reproduced the bundle's gate at the
bundle's own base, found that gate red, attributed the failure, and then ported
only the part that was proven sound.

The result is the catalogue this branch's Store work will read as its source of
truth: **31 `kind=emulator` packs**, listed in full at the end.

Every claim below names the command or measurement behind it.

---

## 1. What was measured before anything changed

`.venv/bin/python -m pytest backend/tests catalog -q -m "not network"` on
`59ea18d`, untouched:

```
1963 passed, 6 skipped, 4 deselected in 408.17s
```

**Zero failures.** This matters: the bundle's own independent audit recorded a
baseline of "1,943 cases, 3 failures (test_install_media_index / no DNS)"
(`INDEPENDENT-AUDIT-v3-VERDICT.md`). This machine has DNS, so those three pass
here. A fully green baseline means any post-port failure is unambiguously the
port's, with nothing to excuse it away.

pytest is absent from the system `python3`, so the suite runs from a `.venv`
created in the clone (`.venv/` is gitignored — `git check-ignore -v .venv`
returns `.gitignore:5`). `python3` was shimmed to that interpreter through
`PATH` for the bundle's scripts, which hardcode `python3`.

## 2. The bundle's own gate is RED at its own base commit

The bundle declares `baseCommit = 9c5c6d13` (`MANIFEST.json:3`) and
`APPLY-ALL.sh:11` aborts if `HEAD` differs. Two facts about that script decided
how it was run:

- `APPLY-ALL.sh:10` tests `[[ -d .git ]]`. In a git worktree `.git` is a *file*,
  so the gate **structurally cannot run in a worktree** — it exits with
  `ERROR: run from a real GameCoreRenew git checkout root`. It was therefore run
  in a throwaway local clone, `/home/pavic/src/gamecore-store-work/gate-clone`,
  detached at `9c5c6d13`, which is what `CLAUDE-RUN-ME.txt` asks for anyway.
- `APPLY-ALL.sh:145-155` **writes into the bundle directory** (`export-fixtures.py`,
  `write-combined-report.py`, `build-validated-zip.py`). The extracted bundle is
  read-only for this session, so the gate ran against a copy. The pristine
  bundle's checksum was `298e2900543899e3…` before the run and after the port —
  `find … -exec sha256sum {} + | sort | sha256sum`, unchanged. The original
  `~/Downloads/…zip` was never opened for writing.

Result, full `APPLY-ALL.sh` at `9c5c6d13` (`GATE EXIT=1`):

```
baseline: 1943 cases, 0 failing/error
ORDER-A:  2258 cases, 3 failing/error
NEW REGRESSIONS:
  test_electron_overlay::test_the_electron_overlay_bench_passes
  test_session_ownership::test_an_old_watcher_does_not_clear_the_game_that_replaced_it
  test_session_ownership::test_each_launch_is_announced_under_its_own_number
```

The gate aborted there. It never ran the ORDER-B post suite, never compared the
two tree digests, never exported fixtures and never built its "validated"
re-zip — `grep -c "ORDER-B full post suite|tree digest|COMBINED VALIDATION PASS"`
returns 0. **No part of the v7 bundle has ever passed its own combined gate.**

### All three regressions belong to D1, which this port excludes

`patch-d1-overlay-ownership.py` owns exactly five files (`grep -n "ROOT /"` on
it): `backend/services/process_manager.py`, `electron/main.js`,
`backend/services/overlay_monitor.py` and the two
`test_overlay_*_ownership/identity_contract.py` tests.

The two `test_session_ownership` failures are one traceback:

```
process_manager.py:824 launch → :746 _publish → :608 session_state
  → :422 describe → :379 pgid → self.proc.pid
E AttributeError: 'FakeProcess' object has no attribute 'pid'
```

Line 422 is the `"pgid": self.pgid` that D1 inserts into `Session.describe()`,
and `pgid` reads `self.proc.pid`. The suite's `FakeProcess` has no `.pid`, so
every `describe()` under test raises.

The third is D1's `electron/main.js` edit breaking the node bench. The failing
assertion names the bug:

```
✖ a stop cancels a start that is still waiting on the backend
  AssertionError: a cancelled launch was still handed to the monitor
```

D1 makes `overlay:start` `await` `/api/games/session`, and does not re-check
cancellation after that await — so a stop arriving during the await is lost and
a cancelled launch still reaches the monitor. That is a race D1 introduces
itself, not a stale test. **It belongs to the separate D1 subtask, and is the
first thing that subtask should fix.**

## 3. The payload alone passes the same gate

To answer the question the gate exists to answer — is the *payload* sound? — the
gate was re-run with D1 removed and nothing else changed
(`GATE-PAYLOAD-ONLY.sh`: same baseline, same two orders, same single fixture
regeneration point, same catalogue gates, same double characterisation run, same
`compare-junit.py`, same `tree-manifest.py` convergence digest):

```
baseline: 1943 cases, 0 failing/error
ORDER-A:  2244 cases, 0 failing/error   PASS: no new FAIL/ERROR node
ORDER-B:  2244 cases, 0 failing/error   PASS: no new FAIL/ERROR node
ORDER-A tree digest: 44e4139d5b1d44b495f83f55d86178862641da687e5dc8bee08b99b04c15c79d
ORDER-B tree digest: 44e4139d5b1d44b495f83f55d86178862641da687e5dc8bee08b99b04c15c79d
```

Both application orders converge to the same tree, byte and mode
(`tree-manifest.py` hashes every path's mode and SHA-256).

That digest is **character-for-character the one in the bundle's own
`PREVIOUS-v4-COMBINED-VALIDATION-RESULT.txt`**. The bundle's payload claim is
independently reproduced on this machine; only the v7 D1 layer added on top of
it is broken.

## 4. Zero conflict surface on this branch

`git diff --name-only 9c5c6d13 HEAD` — the six intervening commits touched
`backend/services/desktop_power.py`, `backend/services/standby.py`,
`config/themes/orbit/**`, `docs/architecture/04-backend-services.md` and three
test files.

`git diff --stat 9c5c6d13 HEAD --` over every path the port writes
(`controllers.py`, `characterisation.py`, `gen-catalog.py`, `README.md`,
`config/systems.json`, `config/overlays.json`, `catalog/`, `assets/`) prints
**nothing**: all of them are byte-identical between the bundle's base and
`59ea18d`. Every anchor the patchers look for is therefore exactly where they
expect it, and nothing newer can be clobbered. No file was overwritten on the
"it exists in the ZIP" argument alone.

## 5. Classification of every divergence

The applier's own create-vs-overwrite split was read off the live ORDER-A
worktree (`git --no-optional-locks status --porcelain`), then confirmed on this
branch. **30 tracked files modified, 42 paths created**, and — verified
file by file — none of D1's five.

| path | applier action | class | evidence / why it stands |
|---|---|---|---|
| `catalog/{18 new ids}/**` | create | **pack** — still necessary | 18 ids absent upstream; `check-catalog: 35 pack(s) OK` |
| `assets/overlays/{18}.png` | create | **asset** — still necessary | 18 bezels absent upstream; `test_bezels` green, incl. `[snes9x]` |
| `backend/services/configgen/helpers/retroarch.py` | create | **backend partagé** — still necessary | helpers/ held only `base.py`, `ini.py`, `tier0.py`; fixes audit D3 (~5,100 dup lines → 233) |
| `scripts/gamecore-retroarch-launch.py` | create | **backend partagé** — still necessary | fixes R3; `os.execvpe` with an argv list, no shell string. `test_launch_args_roots` green |
| `backend/tests/test_configgen_retroarch_legacy.py`, `test_sdl2_probe_axes_legacy.py` | create | **test only** | cover the new helper and the AXES seam |
| `catalog/rpcs3/files/**`, `catalog/rpcs3/tests/test_smart_launch.py` | create | **pack** — still necessary | Smart-Sync units + its 33 unit tests |
| `catalog/rpcs3/pack.json` | overwrite | **pack** — still necessary | diff is purely additive: `description`, two `services` units, `appIds`/`settings` reformatting. Both schema keys are legal (`pack.schema.json` allows `description`, `services`; `additionalProperties:false`) |
| `catalog/rpcs3/seed/config.yml` | overwrite (1 regex) | **pack** — still necessary | replaces a harvest-box value: `Adapter: AMD Radeon Graphics (RADV REMBRANDT)` → `Adapter: ""`. The committed seed leaked this box's GPU; `check-catalog`'s seed family screens absolute paths, not adapter names |
| `backend/services/configgen/controllers.py` | overwrite (3 anchors) | **backend partagé** — still necessary | +9 lines: SDL2 `NumAxes` probe + `AXES` accepted in `sdl2_probe`. Fixes R1 — packs use the cached, substitutable seam instead of private SDL subprocesses |
| `backend/tests/characterisation.py` | overwrite (anchors) | **test only** | +45 lines: the 18 ids in `WATCHED`/`SEED_DEST`, `axes: "6"` in the stub, and a `launches_flatpak` pin for snes9x. Fixes audit D2/E3 |
| `scripts/gen-catalog.py` | overwrite (1 anchor) | **backend partagé** — still necessary | 1-line guard `if pid not in rows`. Fixes R5: the legacy alias block no longer shadows the real `nes`/`mame` pack colours |
| `catalog/_characterisation/*.messages` (20) | overwrite, then regenerated | **test only** — already upstream in content | the ZIP copies are byte-identical to what `GAMECORE_UPDATE_FIXTURES=1` regenerates here (`sha256sum` on `one-ds4`, `four-mixed`, `unknown-pad`: same). The v4 export did land in the bundle; regeneration confirms rather than corrects. `autoconfig-off.messages` is untouched |
| `config/overlays.json` | merge, then generated | **pack** — still necessary | non-destructive: 6 keys → 24, `LOST keys: none`, `CHANGED pre-existing keys: none` |
| `config/systems.json`, `install/generated/systems.json.dist`, `install/installer-gui/catalog_data.py`, `frontend/src/lib/systemColors.ts` | generated | **derived, not authored** | all written by `scripts/gen-catalog.py`; `gen-catalog.py --check` → `35 pack(s), .dist up to date`. Fixes R2 |
| `README.md` | overwrite (rows appended) | **documentation only** | purely additive: 18 lines added, **0 removed** (`git diff README.md \| grep '^-'` is empty). Fixes R2; `test_systems_extensions` green |
| `backend/services/process_manager.py`, `electron/main.js`, `backend/services/overlay_monitor.py`, `test_overlay_process_ownership.py`, `test_overlay_session_identity_contract.py` | **not run** | **excluded — D1** | all five report clean in `git status`; the three regressions of §2 are theirs |

Nothing was classed obsolete, and nothing was dropped as "already upstream" in
substance — the only already-upstream content is the fixture set, which is
regenerated from code here rather than trusted from the ZIP.

### Audit reservations that this port resolves, measured

| audit item | claim | measured here |
|---|---|---|
| R1 private SDL probe | 19 characterisation tests + stale slots | `test_controller_characterisation` 49 passed, twice, fixture digest `475ba1f9…` unchanged between runs — the `/tmp/pytest-of-…` path no longer leaks into a fixture |
| R2 README / systems.json stale | 20 `test_systems_extensions` | green; `gen-catalog --check` up to date |
| R4 snes9x bezel not opaque | audit: **0** pixels at alpha 255, max 235 | now **518,400** at alpha 255, max 255 — and 518,400 = 1920·1080 − 1440·1080, exactly the declared hole |
| R5 nes/mame colours shadowed | `test_frontend_colours_match_the_catalogue` | green |
| R6 order collisions | `order` 9 melonds/snes9x, `controllers.order` 8 duckstation/snes9x | **0 same-kind collisions** across 35 packs; `controllers.order` has 0 collisions at all. The 4 remaining `order` ties are the legitimate emulator-vs-app pairs (azahar/steam, cemu/youtube, dolphin/twitch, ryujinx/stremio) |
| C1 RPCS3 v2 dropped per-game profiles | 2 collection errors killed the suite | v3 **keeps** both Demon's Souls profiles; `test_pergame` + `test_pergame_router` green |
| C2 RPCS3 v2 dropped `launch.preferIfPresent` | native `lib/rpcs3` path lost | v3 **retains** `preferIfPresent` — verified in the shipped `pack.json` |

### Reservations that remain OPEN after this port

- **D1 / shared `wm_class`.** All 17 RetroArch packs declare
  `"wm_class": ["retroarch", "RetroArch"]`. The overlay monitor locates the
  window by `WM_CLASS`, so with two RetroArch windows alive a Mega Drive game
  can take the NES bezel. Deliberately not addressed here; the v7 attempt at it
  is red (§2).
- **C3 RPCS3 Smart-Sync trust anchor.** `rpcs3-smart-sync.py` takes the patch
  database's SHA-256 from the *same* JSON response as the content it certifies,
  so it detects transport corruption, not a compromised upstream. The only real
  anchor is TLS. `VERIFICATION.txt` overstates this as a security property.
- **C3 redirects.** `urllib.request.urlopen` follows redirects, `https:` → `http:`
  included, on a file RPCS3 later interprets. Constraining the redirect scheme
  is a three-line fix.
- **No physical bench.** Everything above is a repository/regression result. No
  controller, GPU or gameplay behaviour was exercised: nothing was installed, no
  service was restarted, and the 17 RetroArch packs' `pacman` artifacts
  (`retroarch`, `libretro-*`) are **not installed on this box**. Their launchers
  are unproven against a real binary.
- **Fixture coverage is still uneven.** The 18 new packs ship 20 scenario
  fixtures each, but `azahar`, `cemu`, `mgba`, `gopher64`, `ppsspp`, `xenia` and
  `shadps4` still ship none. That is a pre-existing gap, untouched here.

## 6. Tests run on this branch, after the port

| command | result |
|---|---|
| `pytest backend/tests catalog -q -m "not network"` (before) | `1963 passed, 6 skipped, 4 deselected` — 1969 cases, 0 failing |
| `GAMECORE_UPDATE_FIXTURES=1 pytest test_controller_characterisation.py` | `9 passed, 40 skipped` (one regeneration, all three payloads present) |
| `scripts/check-catalog.py` | `check-catalog: 35 pack(s) OK` |
| `scripts/gen-catalog.py --check` | `gen-catalog: 35 pack(s), .dist up to date` |
| `pytest test_controller_characterisation.py` ×2 | `49 passed` / `49 passed`; fixture digest identical before and after |
| `pytest backend/tests catalog -q -m "not network"` (after) | `2247 passed, 23 skipped, 4 deselected` — 2270 cases, **0 failing** |
| `compare-junit.py` before→after | `PASS: no new FAIL/ERROR node relative to baseline` |
| `pytest test_catalog_consumers.py` | `23 passed, 4 skipped` |
| `pytest test_systems_extensions test_bezels test_launch_args_roots test_controller_stale_slots test_pergame test_pergame_router` | `205 passed` |

+284 passing tests, +301 collected cases, zero new failures.

## 7. The catalogue this leaves behind — 31 `kind=emulator` packs

Produced by walking `catalog/*/pack.json` and filtering `kind == "emulator"`;
no list was copied from any earlier document. 13 packs existed before the port,
18 arrived with it.

The Store's ingestion matrix should note the shape change: before this port every
emulator came from `flatpak`, `github-asset` or `github-archive`; **17 of the 18
new packs install through `pacman`** (`retroarch` + a `libretro-*` core), which
is a provider dimension no emulator pack previously exercised.

TOTAL kind=emulator packs: 31

| order | id | label | platform | family | emulator | provider | artifact | roms.dir | maxPlayers | seed | generator | fixtures |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | `azahar` | Nintendo 3DS | 3DS | Nintendo | Azahar | flatpak | `org.azahar_emu.Azahar` | `emu/azahar` | 1 | yes | yes | 0 |
| 1 | `cemu` | Wii U | Wii U | Nintendo | Cemu | flatpak | `info.cemu.Cemu` | `emu/cemu` | 1 | yes | yes | 0 |
| 2 | `dolphin` | GameCube / Wii | GameCube/Wii | Nintendo | Dolphin | flatpak | `org.DolphinEmu.dolphin-emu` | `emu/dolphin` | 4 | yes | yes | 20 |
| 3 | `ryujinx` | Nintendo Switch | Switch | Nintendo | Ryujinx | flatpak | `io.github.ryubing.Ryujinx` | `emu/ryujinx` | 4 | yes | yes | 20 |
| 4 | `duckstation` | PlayStation | PS1 | Sony | DuckStation | github-asset | — | `emu/duckstation` | 4 | yes | yes | 20 |
| 5 | `pcsx2` | PlayStation 2 | PS2 | Sony | PCSX2 | flatpak | `net.pcsx2.PCSX2` | `emu/pcsx2` | 4 | yes | yes | 20 |
| 6 | `rpcs3` | PlayStation 3 | PS3 | Sony | RPCS3 | flatpak | `net.rpcs3.RPCS3` | `emu/rpcs3` | 4 | yes | yes | 20 |
| 7 | `ppsspp` | PlayStation Portable | PSP | Sony | PPSSPP | flatpak | `org.ppsspp.PPSSPP` | `emu/ppsspp` | 0 | yes | no | 0 |
| 8 | `gopher64` | Nintendo 64 | N64 | Nintendo | Rosalie's Mupen GUI | flatpak | `com.github.Rosalie241.RMG` | `emu/gopher64` | 4 | no | yes | 0 |
| 9 | `melonds` | Nintendo DS | DS | Nintendo | melonDS | flatpak | `net.kuribo64.melonDS` | `emu/melonds` | 1 | yes | yes | 20 |
| 10 | `mgba` | Game Boy Advance | GBA | Nintendo | mGBA | flatpak | `io.mgba.mGBA` | `emu/mgba` | 1 | yes | yes | 0 |
| 11 | `xenia` | Xbox 360 | X360 | Microsoft | Xenia Canary | github-archive | — | `emu/xenia` | 0 | no | no | 0 |
| 12 | `shadps4` | PlayStation 4 | PS4 | Sony | shadPS4 | flatpak | `net.shadps4.shadPS4` | `emu/shadps4` | 0 | no | no | 0 |
| 19 | `snes9x` | Super Nintendo | SNES | Nintendo | Snes9x | flatpak | `com.snes9x.Snes9x` | `emu/snes9x` | 2 | yes | yes | 20 |
| 20 | `nes` | Nintendo Entertainment System | NES | Nintendo | RetroArch / mesen | pacman | `retroarch,libretro-mesen` | `emu/nes` | 2 | yes | yes | 20 |
| 21 | `fds` | Family Computer Disk System | FDS | Nintendo | RetroArch / mesen | pacman | `retroarch,libretro-mesen` | `emu/fds` | 2 | yes | yes | 20 |
| 22 | `mastersystem` | Sega Master System | Master System | Sega | RetroArch / genesis-plus-gx | pacman | `retroarch,libretro-genesis-plus-gx` | `emu/mastersystem` | 2 | yes | yes | 20 |
| 23 | `gamegear` | Sega Game Gear | Game Gear | Sega | RetroArch / genesis-plus-gx | pacman | `retroarch,libretro-genesis-plus-gx` | `emu/gamegear` | 1 | yes | yes | 20 |
| 24 | `sg1000` | Sega SG-1000 | SG-1000 | Sega | RetroArch / genesis-plus-gx | pacman | `retroarch,libretro-genesis-plus-gx` | `emu/sg1000` | 2 | yes | yes | 20 |
| 25 | `megadrive` | Sega Mega Drive / Genesis | Mega Drive | Sega | RetroArch / genesis-plus-gx | pacman | `retroarch,libretro-genesis-plus-gx` | `emu/megadrive` | 2 | yes | yes | 20 |
| 26 | `megacd` | Sega Mega-CD / Sega CD | Mega-CD | Sega | RetroArch / genesis-plus-gx | pacman | `retroarch,libretro-genesis-plus-gx` | `emu/megacd` | 2 | yes | yes | 20 |
| 27 | `sega32x` | Sega Mega Drive 32X | 32X | Sega | RetroArch / picodrive | pacman | `retroarch,libretro-picodrive` | `emu/sega32x` | 2 | yes | yes | 20 |
| 28 | `saturn` | Sega Saturn | Saturn | Sega | RetroArch / kronos | pacman | `retroarch,libretro-kronos` | `emu/saturn` | 2 | yes | yes | 20 |
| 29 | `dreamcast` | Sega Dreamcast | Dreamcast | Sega | RetroArch / flycast | pacman | `retroarch,libretro-flycast` | `emu/dreamcast` | 4 | yes | yes | 20 |
| 30 | `naomi` | Sega Naomi | Naomi | Sega | RetroArch / flycast | pacman | `retroarch,libretro-flycast` | `emu/naomi` | 2 | yes | yes | 20 |
| 31 | `naomigd` | Sega Naomi GD-ROM | Naomi GD-ROM | Sega | RetroArch / flycast | pacman | `retroarch,libretro-flycast` | `emu/naomigd` | 2 | yes | yes | 20 |
| 32 | `atomiswave` | Sammy Atomiswave | Atomiswave | Sega | RetroArch / flycast | pacman | `retroarch,libretro-flycast` | `emu/atomiswave` | 2 | yes | yes | 20 |
| 33 | `pcengine` | NEC PC Engine / TurboGrafx-16 | PC Engine | NEC | RetroArch / beetle-pce | pacman | `retroarch,libretro-beetle-pce` | `emu/pcengine` | 1 | yes | yes | 20 |
| 34 | `pcenginecd` | NEC PC Engine CD / TurboGrafx-CD | PC Engine CD | NEC | RetroArch / beetle-pce | pacman | `retroarch,libretro-beetle-pce` | `emu/pcenginecd` | 1 | yes | yes | 20 |
| 35 | `supergrafx` | NEC PC Engine SuperGrafx | SuperGrafx | NEC | RetroArch / beetle-pce | pacman | `retroarch,libretro-beetle-pce` | `emu/supergrafx` | 1 | yes | yes | 20 |
| 36 | `mame` | Arcade (MAME) | Arcade | Arcade | RetroArch / mame | pacman | `retroarch,libretro-mame` | `emu/mame` | 4 | yes | yes | 20 |

`order` is the curated grid position, not a rank; the gap at 13–18 is the
bundle's own numbering and costs nothing (`pack.schema.json`: absent order means
last, never dropped).

## 8. Production was not touched, and how to undo this

Nothing outside the development clone was written. `/opt`, `/userdata`,
`/var/lib/gamecore`, `/etc`, `/usr/local/bin` and `~/.var/app` were never
written, chmod'd or backed up. No service was started, stopped or restarted; no
Flatpak, pacman package, systemd unit, udev rule or sudoers entry was installed
or removed; `install/arch.sh`, `install/uninstall.sh` and `update/linux.sh` were
never run, `--dry-run` included; `gamecore-emu install` was never run. The
17 RetroArch packs' pacman artifacts remain uninstalled.

The suite could not have reached the live box even by accident:
`backend/tests/conftest.py` sets — never defaults — `GAMECORE_PATH`,
`GAMECORE_DATA`, `HOME` and `XDG_RUNTIME_DIR` to a throwaway tree, and
neutralises `standby._run_cmd` and `desktop_power._run`. That mechanism was not
worked around.

Two changes inside the clone are worth declaring because they are not part of
the port:

- `.venv/` was created to get a pytest (the system `python3` has none). It is
  gitignored and not in the commit.
- the clone had **no git identity at all** — the first commit attempt died on
  `unable to auto-detect email address (got 'pavic@GameCore.(none)')`. A
  **repo-local** `user.name`/`user.email` was set to
  `p4v1c <p4v1c@users.noreply.github.com>`, the identity 10 of the last 12
  commits on this branch already carry (`git log --format='%an <%ae>'`).
  Nothing global was changed. Undo with
  `git config --local --unset user.name && git config --local --unset user.email`.

To undo the port itself: it is one commit on `feature/gamecore-store` and it was
not pushed. `git revert` it, or `git reset --hard 59ea18d`. The throwaway
artefacts live outside the repo, in
`/home/pavic/src/gamecore-store-work/{gate-clone,bundle-gate-copy}`, and can be
deleted outright — they are kept for now only so the two gate runs of §2 and §3
can be replayed.
