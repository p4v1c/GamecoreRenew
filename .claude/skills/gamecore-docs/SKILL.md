---
name: gamecore-docs
description: Keep GameCore docs in sync with code. Use whenever a feature, endpoint, WebSocket event, config file, pack field, theme SDK surface, service, CLI, or behaviour is added, renamed, moved or removed in GamecoreRenew — and before opening a PR. Maps each code area to the doc that must change in the same commit.
---

# GameCore docs

Rule: **a feature lives somewhere in the code, so it is documented where
that code area is documented — in the same commit.** A stale map is worse
than no map.

## Where to write — code area → doc

| You changed | Update |
|---|---|
| process, port, systemd unit, boot, session | `docs/architecture/01-runtime-topology.md` |
| a flow across processes (launch, kill, OTA, standby, auth…) | `docs/architecture/02-request-flows.md` |
| `backend/routers/**` (endpoint added/renamed/removed) | `docs/architecture/03-backend-routers.md` |
| `backend/services/**`, `backend/utils.py`, `ws.py`, `db.py` | `docs/architecture/04-backend-services.md` |
| `frontend/src/**` (store, hooks, bus, WS events, api groups) | `docs/architecture/05-frontend.md` |
| `electron/**`, overlays, bezels window | `docs/architecture/06-electron-and-overlays.md` |
| `config/*.json` schema, paths, SQLite, caches | `docs/architecture/07-config-and-data.md` |
| controllers, SDL, configgen | `docs/architecture/08-controller-pipeline.md` (+ `docs/CONTROLLER_MODELS.md`) |
| an invariant that is easy to break | `docs/architecture/09-gotchas.md` |
| `catalog/**`, `pack.json` fields, install pipeline | `docs/architecture/10-catalog-and-install.md` |
| `install/arch.sh`, `uninstall.sh` phases | `docs/architecture/11-install-script-seams.md` |
| addon hook / `api` version | `docs/architecture/12-addon-contract.md` |
| `release.yml`, `update/`, OTA content | `docs/architecture/13-release-and-ota.md` |
| theme SDK / `config/themes/**` | `docs/themes/README.md` |
| tests, markers, conftest | `docs/TESTING.md` |
| user-visible feature added, changed or removed | `README.md` (user manual) + `docs/index.html` (the website: claims, counts, "Day to day", "What it does not do") + `CHANGELOG.md` |
| a theme's look (`config/themes/<id>/**` CSS, views, home) | re-shoot with `node scripts/shoot-site.mjs --themes <id>`: its `preview.png` and the website/README shots, **same PR**, theme version bumped |
| a theme added or removed | the above, plus its row in `docs/index.html` (Themes) and the README gallery; `check-docs.py --all` fails until they match |
| a system added or removed (`catalog/`) | the counts and systems table in `docs/index.html`, the README ROM table |
| a session's decisions / measurements | new `docs/reports/<topic>-YYYY-MM-DD.md` + row in `docs/reports/README.md` |

New area with no home? Add a numbered file in `docs/architecture/` and a row
in `docs/architecture/README.md` ("Read in this order" + "Looking for").

## How to write

- **English.** Direct. Tables and lists over paragraphs.
- Lead each section with what the reader needs to act; the reason after, in
  one or two sentences.
- **Name files as inline code** (`backend/services/paths.py`) — that is what
  `scripts/check-docs.py` verifies.
- **No line counts** in headings (`games.py (138 l.)`): they rot silently
  (games.py is 575 l. today). Name the file, not its size.
- **No duplication.** Link the doc that owns the fact
  (`[store](05-frontend.md#store--storeindexts)`); never copy a table.
- One fact, one place — same rule as the code.
- Every "do not do X" names the failure that taught it, in one line.
- Mermaid for flows, not ASCII art.

## Screenshots

- **Website, README gallery, theme previews**: only from
  `node scripts/shoot-site.mjs` (made-up games, drawn jackets, fixed time,
  no real box data). Never hand-made, never from a real box. Look at every
  image it wrote before committing: a console render can arrive late, re-run
  that theme. `git checkout` the `preview.png` of a theme you did not change.
- **`docs/dev-log/`, `docs/reports/`**: scratch. Commit the capture script and
  a few representative PNGs the log names (one theme, the key states), not
  the full theme × state set; the script regenerates the rest. Large sets
  stay in `~/Downloads/<topic>/shots/`.
- A doc that stops being true is fixed or deleted, not left: a report whose
  subject is gone (a branch, a box's state on one day) goes, with a line in
  the PR saying why.

## Checks

```bash
python3 scripts/check-docs.py --all     # every named path and link resolves;
                                        # every shipped theme has its site shots,
                                        # its preview.png, and the site's system count is right
```

Then read the diff: every new public name (endpoint, WS event, config key,
pack field, SDK surface) appears in its doc table? If not, the PR is not done.
