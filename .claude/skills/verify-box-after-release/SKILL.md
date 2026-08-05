---
name: verify-box-after-release
description: Merge a green branch, wait for the release, update this box over OTA, and prove the box still works — grid, launchers, overlays, and a full scrape from an emptied cache. Use after merging anything that ships to the fleet, or when asked to check a box for bugs after an update.
---

# Verifying a box after a release

Every push to `main` publishes a release that installed boxes pick up over the
air. CI proves the code compiles and the tests pass; it proves nothing about a
box. This is the procedure that does.

**The rule that outranks the rest: do not break the box.** It is someone's
living room. Every step below is either reversible or verified before the next
one starts.

## 0. Before touching anything

```bash
git branch --show-current                     # never run this from main
```

Run the six baseline commands and require green. Never merge on a red baseline,
and never "fix it after the merge" — the merge is the publish.

```bash
ruff check .
shellcheck -S warning $(git ls-files '*.sh') install/bin/*
python3 scripts/check-catalog.py
python3 scripts/gen-catalog.py --check
python3 -m pytest backend/tests catalog -q -m "not network"
cd frontend && npm ci && npm run test:run && npm run build && cd ..
```

## 1. Snapshot the box first

The comparison after the update is only worth what the "before" is worth. An
OTA can jump many releases at once, so **a bug found afterwards is not
necessarily the one just merged** — the snapshot is what tells the two apart.

```bash
curl -s http://127.0.0.1:8765/api/sysinfo   # version, ip, disk
curl -s http://127.0.0.1:8765/api/systems   # the grid: ids, launchers, icons
systemctl is-active gamecore-backend gamecore-ui caddy
journalctl -u gamecore-backend --since "24 hours ago" -p err --no-pager | tail
```

Read that journal properly. On the reference box it was already reporting
`sudo: a password is required ; COMMAND=/usr/bin/cpupower` — a feature dead for
months, visible nowhere else.

`update/linux.sh` snapshots the code to `${GAMECORE_PATH}.prev` and prints the
restore command, but it **excludes `config/`**. Back that up yourself: it holds
the grid, the web password and the overlays.

```bash
BK=/opt/GameCore/backups/pre-update-$(date +%Y%m%d-%H%M%S)
mkdir -p "$BK" && cp -a /opt/GameCore/config "$BK/config"
```

## 2. Merge, then wait for the release to actually exist

```bash
git checkout main && git merge --ff-only <branch> && git push origin main
gh run watch $(gh run list --branch main --limit 1 --json databaseId --jq '.[0].databaseId') --exit-status
gh release view --json tagName --jq .tagName
```

The run list lags a push by a few seconds — match on `headSha` rather than
taking `--limit 1`, or you will watch the previous run and believe you are done.

**Never `workflow_dispatch` this workflow from a branch.** The publish step has
no `if:` guard: `tag_name` falls back to `github.ref_name`, so it would publish
a release named after the branch, and boxes polling `/releases/latest` would
install it.

## 3. Update the box

Runs as the backend's user, without stopping the backend; services are
restarted by the detached `gamecore-restart.service`.

```bash
GAMECORE_PATH=/opt/GameCore bash /opt/GameCore/update/linux.sh
```

First check that your own shell is not a child of `gamecore-ui` — restarting it
would kill the session mid-update:

```bash
cat /proc/$$/cgroup        # must not be under gamecore-ui.service
```

**The updater updates itself.** A change to `update/linux.sh` takes effect on
the update *after* the one that ships it — the running script is the one loaded
at start. Do not report the new behaviour as missing.

## 4. Prove the box still works

Compare against the snapshot rather than eyeballing it.

- **Grid**: same ids, no tile lost. An id only the box has must survive — the
  merge keeps it. An id in `config/catalog-removed.json` must NOT come back:
  "nothing to change" is correct there, not a failure.
- **Logos**: fetch every `iconPath`. All 200, all non-empty. Blank tiles on a
  fresh install shipped once already.
- **Launchers**: every `path` is `flatpak`, on `PATH`, or a file that exists.
- **Overlays**: each `overlay_asset` in `config/overlays.json` is on disk.
- **Journal**: zero `error|exception|traceback` since the restart.

## 5. The scrape, from an emptied cache

This is the only test that exercises the media pipeline end to end, and it is
the one that catches a refactor that "passed all the tests".

Move — never delete — all three caches. They are separate and it is easy to
miss one:

```bash
BK=/opt/GameCore/backups/cache-$(date +%Y%m%d-%H%M%S); mkdir -p "$BK"
mv /opt/GameCore/emu/gamemedia "$BK/"   # manifests + downloaded media
mv /opt/GameCore/emu/covers    "$BK/"   # the cover the grid draws
mv /opt/GameCore/emu/metadata  "$BK/"   # titles, synopses, genres
```

`emu/gamescrape/` is **not** a cache — it is the 234 MB LaunchBox index. Leave
it, or the next step has no offline tier.

Then drive both pipelines over the whole library:

```
GET /api/covers/{system}/{filename}     → every game, expect 200
GET /api/metadata/{system}/{filename}   → every game, expect a title
```

Expect 100 %. On the reference box: 50/50 covers and 50/50 titles from an empty
cache, in about three minutes.

**Read the differences, do not just count them.** Three showed up, and all
three were explained rather than assumed:

- fewer `game.json` than games — correct. Systems whose pack declares a
  `localMedia` format with an icon (ps3, psp) get their cover extracted from
  the dump, so the pipeline short-circuits and writes no manifest.
- a much smaller cache — correct. Media beyond the cover are `deferred
  (fetched on demand)`; the old cache had accumulated them over months.
- **a title that changed** — this is the one to chase. On the reference box
  `Mario Kart Wii.rvz` had been cached as *Mario Kart: Double Dash!!*. Reading
  the disc id from the ROM settled it: `RMCP01` is Mario Kart Wii. The old
  cache was wrong and the re-scrape corrected it. A changed title is not
  automatically a regression — prove which side is right, from the ROM.

## 6. Privileges, the failure class that hides best

Sudoers rules are written **once, at install time**. An OTA cannot grant
anything: it runs as the backend's user. So every rule a later release adds is
absent for ever on a box installed before it, and the feature it gates is dead
in silence.

```bash
sudo -n -l          # read the NOPASSWD entries themselves
```

Do **not** use `sudo -n -l <command>`: on a box whose owner is in wheel,
`(ALL) ALL` makes every command "permitted" — with a password. The backend
always calls `sudo -n`, which never prompts, so only NOPASSWD counts. That
mistake reported the CPU governor as working on a box where it was not.

`update/linux.sh` now derives the expected rules from the installers it ships
and names what is missing. It cannot repair them — that needs root, which is
the point of the rule. Report them to the owner with the one command that fixes
it, and do not attempt to edit sudoers unattended.

## 7. If something is wrong

Branch, fix, test, merge — never patch the box by hand and leave the repo
disagreeing with it. A hand-fixed box is a box whose next update undoes the fix
and whose owner cannot reproduce anything.

The only hand-changes that are legitimate are ones the repo cannot express:
moving user data, and applying a root-owned rule the owner has approved.

## Rolling back

```bash
sudo rsync -a /opt/GameCore.prev/ /opt/GameCore/     # no --delete
sudo systemctl restart gamecore-backend gamecore-ui
cp -a "$BK/config" /opt/GameCore/config              # if config changed
```

The caches move back the same way they moved out.
