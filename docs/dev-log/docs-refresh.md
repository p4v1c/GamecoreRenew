# Docs and website refresh — dev log

Branch `claude/docs-refresh`, from `main` at `cbe9b08`. The owner's complaint:
docs are updated but not properly, a theme changed and its screenshots stayed,
the website was never updated.

## Status

- [x] Audit (below)
- [x] One command that re-shoots the website and theme previews
- [x] Website text and screenshots
- [x] Theme previews for every theme (Orbit, Shelf, Summer, Jelly bumped)
- [x] README / runtime-topology / theme doc fixes found by the audit
- [x] Clean-up (list below)
- [x] Skills: the rows that make it stick, and a check in `check-docs.py`

## Audit

`python3 scripts/check-docs.py --all` passes on `main`: every named path and
link resolves. It does not catch facts that went stale, which is what this
audit is about. Each row was checked against the code named in it.

### Website (`docs/index.html`)

| Claim on the page | What the code says | Verdict |
|---|---|---|
| "plus 29 more systems", "34 systems" (title, meta, og, twitter, lede, section) | `install/generated/systems.json.dist` has 35 systems: PC (Lutris) was added | stale |
| Systems table | no PC row | stale |
| "Four looks, one console" | five themes: Default + `config/themes/{jelly,orbit,shelf,summer}` | stale, Jelly missing |
| Controller screenshots per theme | every theme now opens the same "Your controller." screen (live pad diagram, quick guide); the shots show the old per-theme screens | stale images |
| `shelf-home.webp` | Shelf's home is now the Studio home (console picked large, games below) | stale image |
| `jelly-home.webp` | real commercial box art (Mario Kart 7, Crash…), against the page's own rule "no commercial cover art" | must go |
| `social.jpg` | old Orbit shot, "34 consoles" | stale image |
| No mention of Rest mode, pad wake, standby screens, profiles, PC games, per-game bezels | all shipped (README, CHANGELOG "Unreleased") | missing |
| "SDDM auto-login and a KDE Plasma X11 session" | the box auto-logs into GameCore's own `gamecore` X11 session (`install/arch.sh`, `install/bin/gamecore-session-select`); Plasma is the desktop you leave to | imprecise |
| Retro: "17 systems through RetroArch" | 17 `RetroArch / …` packs | correct |
| N64 = Rosalie's Mupen GUI | `catalog/gopher64/pack.json` | correct |
| `sitemap.xml` lastmod | 2026-10-01 | update with the page |

### Theme previews (`config/themes/<id>/preview.*`)

The preview is shown in a profile's theme picker (`frontend/src/settings/profileDetail.js`,
via `preview` in `GET /api/themes`; `backend/services/themes.py` defaults it to `preview.png`).

| Theme | File | Verdict |
|---|---|---|
| Shelf | `preview.png`, 640x360 | current Studio home, but real cover art (Mario Kart 7) |
| Summer | `preview.png`, 640x360 | an early mockup: "Keyboard stand-in" bar, a private LAN IP (`10.189.1.233`), no longer what Summer draws |
| Orbit | `preview.svg` | hand-drawn mockup, not the theme |
| Jelly | `preview.svg` | hand-drawn mockup, not the theme |
| Default | built in, no folder | the picker draws its own tile; nothing to do |

Decision: every theme gets a real `preview.png` (640x360) shot from the theme,
the two SVG mockups go, and `"preview"` leaves the two manifests (the default
is `preview.png`).

### README (user manual)

| Section | Problem |
|---|---|
| Intro | "A retro gaming frontend": the project leads with PS3/PS4/Switch/Wii U/Xbox 360 |
| Table of contents | two "5."; no Addons, Cover art, Standby entries |
| "Supported emulators" | 16 of the 35 systems; no Super Nintendo, PC, nor any RetroArch system (the ROM table below has them all) |
| Installation | "SDDM auto-login into that user's KDE Plasma X11 session, with the kiosk drawn over it" and "There is one session, so this changes no login configuration" — the box logs into its own `gamecore` session, and `gamecore-session-select desktop` rewrites the auto-login |
| First launch | "Home shows your recently played games… Library" — describes the old default UI only |
| Settings | list misses Display, Controllers, Emulators & apps, BIOS; Update and Standby are under System now |
| Standby | "(Settings → Standby)" — it is Settings → System |
| Themes | images: see website (same files) |

### Architecture and theme docs

| Doc | Problem |
|---|---|
| `docs/architecture/01-runtime-topology.md` "The session the kiosk runs in" | same stale session story as the README (auto-login into the desktop session, "only one session") |
| `docs/themes/README.md` | `preview.png` is "thumbnail for the settings page": it is the profile theme picker |
| `.claude/skills/gamecore-legibility`, `gamecore-visual-review` | theme loops list four themes (no Jelly) |

### Reports, dev logs, screenshot sets

| Item | Readers | Verdict |
|---|---|---|
| `shots-profiles/` (repo root, 75 MB, 50+ PNGs) | none; not tracked (`.git/info/exclude`) | delete locally |
| `docs/reports/session-console-investigation-2026-09-08.md` | none; not in the reports index; the state of one box on one morning | remove |
| `docs/reports/all-packs-v7-port-2026-09-12.md` | none; porting a bundle onto a branch that is gone, "31 packs" | remove |
| `docs/reports/review-fixes-2026-09-07.md` | linked from two reports, missing from the index | keep, add to the index |
| `docs/dev-log/rest-mode-tools/shots/` (30 PNGs) | `rest-mode.md` names 4 of them and two patterns | keep the named ones and one per pattern |
| `docs/dev-log/pc-pack-tools/shots/` (8 PNGs) | each one listed in `pc-pack.md` | keep |
| `docs/reports/img/` | every file linked from its report | keep |
| `docs/dev-log/shelf-studio-home-tools/push.sh` | none; pushes to a branch merged long ago | remove |
| `docs/dev-log/shelf-studio-home-tools/sync.sh` | named in "How to test" of `shelf-studio-home.md` | keep |

## Decisions

- **Made-up data, not a real box.** The shots use invented titles ("Lantern
  Keep", "Harbor Lights"…), jackets drawn by the script (a title on a flat
  colour), covers and media requests answered by the script so nothing is
  scraped, and fake pads. The old Jelly shot and Shelf preview carried real
  box art; the old Summer preview carried a LAN IP.
- **A clock that runs from a fixed afternoon** (2026-07-14 16:20, Paris),
  not a frozen one: `page.clock.setFixedTime` froze Summer's entry motion and
  its home came out as empty sky. Date is shifted instead, so Summer's sun
  and "played 2 h ago" are the same on every run.
- **Orbit's home is its Consoles tab** (as before, and for social.jpg): the
  Games tab with drawn jackets says less than the console renders.
- **Controller shots hold ✕** so the live diagram shows a lit button.
- **Real `preview.png` for every theme**, the SVG mockups removed, and
  `"preview"` dropped from the two manifests (the backend defaults to
  `preview.png`). Default has no folder and no preview: the picker draws it.
- **Images re-encoded by Chromium** (canvas `toDataURL`): webp q0.82 at
  1280x720 (16 to 95 KB each), PNG at 640x360, JPEG q0.86 at 1200x630. No
  image library needed.
- **Site wording**: "34 systems, and your PC games" (34 emulated + PC through
  Lutris = 35 in `systems.json.dist`), five themes, a "Day to day" section,
  one more limit (pad wake depends on the hardware). Session wording follows
  `install/bin/gamecore-session-select`.
- **The check** (`check-docs.py --all`, run by pytest): every shipped theme
  has both site shots, appears on the site and in the README, and has a
  `preview.png`; no page shows a theme that is gone; the site says
  "<n> systems" and "<n-5> more systems" for the catalogue's count. All read
  from git and committed files, nothing rendered, so it cannot flake. It does
  not know whether a shot is *recent*: that is the skill rows' job.

## Removed

| What | Why |
|---|---|
| `shots-profiles/` (repo root, local only) | 75 MB of profile-screen captures from 2026-10-07, untracked (`.git/info/exclude`), no reader |
| `config/themes/orbit/preview.svg`, `config/themes/jelly/preview.svg` | hand-drawn mockups, replaced by real `preview.png` |
| `docs/reports/session-console-investigation-2026-09-08.md` | one box's state on one morning; not indexed, not linked |
| `docs/reports/all-packs-v7-port-2026-09-12.md` | porting a bundle onto a branch that is gone; its "31 packs" is wrong today; not linked from anything but the index (row removed) |
| `docs/dev-log/shelf-studio-home-tools/push.sh` | pushes to a merged branch; not referenced |
| 24 of 30 PNGs in `docs/dev-log/rest-mode-tools/shots/` | the full theme × state set; kept the six `rest-mode.md` names (default theme, wake black frame, Orbit's splash start), the log now says the scripts regenerate the rest |

Kept on purpose: the dev-log capture scripts, `pc-pack-tools/shots/` (each
image is described in `pc-pack.md`), `docs/reports/img/` (each linked from its
report), `docs/reports/review-fixes-2026-09-07.md` (linked from two reports;
now in the index), `frontend/shot/` and `frontend/scripts/shot-settings.mjs`
(Shelf settings darkroom, still builds).

## Regenerating the shots

```bash
node scripts/shoot-site.mjs                  # all five themes, about 2 min
node scripts/shoot-site.mjs --themes jelly   # one theme
node scripts/shoot-site.mjs --no-build       # reuse frontend/dist
```

Needs python3 with `backend/requirements.txt` and Playwright with Chromium
(`PLAYWRIGHT_MODULE` if it is not resolvable; here it is
`/opt/node22/lib/node_modules/playwright`). Port 8766 must be free. Then look
at what it wrote, bump the version of each theme whose `preview.png` you keep,
and `git checkout` the others.

## Not done

- No visual change to any theme. The shots show the themes as they are.
- The architecture docs were checked where the audit pointed (session,
  previews); the other 6000 lines were not re-read claim by claim.
- Shelf's console rail once came out without its Wii render (the image
  arrived late); a re-run had it. The script now waits for network idle and
  image decode, and the skill says to look before committing.
