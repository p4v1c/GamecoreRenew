---
name: gamecore-catalog-pack
description: Add or change an emulator, system or application pack in GameCore's catalog/<id>/ (pack.json, generator.py, seed, files, steps, tests). Use whenever a new console, emulator, app (Stremio, YouTube, Twitch…) or pack field is involved in GamecoreRenew.
---

# GameCore catalog pack

A system or app is **one directory**. Nothing else in the tree should change
except what `gen-catalog.py` regenerates.

```
catalog/<id>/
├── pack.json     declaration — catalog/_schema/pack.schema.json
├── logo.png      tile
├── seed/         curated emulator config (optional)
├── generator.py  controller bindings (optional)
├── files/        what `files` / `services` refer to
├── steps/        what `postInstall` refers to
└── tests/        test_*.py — collected by CI
```

## Steps

1. Copy the closest existing pack (same provider: flatpak / pacman / AUR /
   download). Read `docs/architecture/10-catalog-and-install.md` §2 for each block.
2. `id` = directory name, lowercase, no separator.
3. `perGame` is **required** on emulator packs (§2 explains why).
4. Controller: prefer an existing generator strategy; `generator.py`
   re-exports what the dispatcher calls (F401 is ignored there on purpose).
5. Daemons in `files/` run on system python3 → **stdlib only**, English
   comments, split if > 600 lines (`gamecore-file-size`).
6. Regenerate and validate:
   ```bash
   python3 scripts/gen-catalog.py
   python3 scripts/check-catalog.py
   python3 scripts/gen-catalog.py --check
   python3 -m pytest catalog/<id> -m "not network"
   ```
7. Commit the pack **and** the regenerated files together.

## Red flags

- You need a line in `install/arch.sh` → the pack model is missing a feature.
  Say so in the PR instead.
- You hardcode `/opt/GameCore` or `~/…` → use the template vars / `paths.py`.
- The system appears nowhere in the installer → you forgot `gen-catalog.py`.
- The tile shows before the emulator is installed → see fix 700d86c.
