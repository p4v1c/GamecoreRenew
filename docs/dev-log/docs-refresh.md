# Docs and website refresh — dev log

Branch `claude/docs-refresh`, from `main` at `cbe9b08`. The owner's complaint:
docs are updated but not properly, a theme changed and its screenshots stayed,
the website was never updated.

## Status

- [x] Audit (below)
- [ ] One command that re-shoots the website and theme previews
- [ ] Website text and screenshots
- [ ] Theme previews for every theme
- [ ] README / theme doc fixes found by the audit
- [ ] Clean-up (list below)
- [ ] Skills: the rows that make it stick, and a check in `check-docs.py`

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

## Removed

## Regenerating the shots
