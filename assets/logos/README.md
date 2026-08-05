# assets/logos/ — operator overrides only

This directory is **empty on purpose**. A system's logo ships with its pack, at
`catalog/<id>/logo.png`.

`backend/routers/systems.py:serve_logo()` resolves `/assets/logos/<file>` in two
steps:

1. `assets/logos/<file>` — a logo the operator replaced by hand, typically
   uploaded through the ROM manager. This directory is excluded from the OTA
   rsync and from `install/arch.sh`'s copy, so that replacement survives every
   update. That is the whole reason it exists.
2. `catalog/<id>/logo.png` — the shipped one, matched by pack id against the
   file name. Not excluded from the OTA, so a corrected logo does reach an
   installed box.

So a file appearing here means someone overrode something. Nothing is meant to
be committed here — `nes.png` and `snes.png` were, left over from before the
logos moved into the packs, and they were the only two that could never be
served from a pack because no `nes` or `snes` pack exists.

Same arrangement for `assets/overlays/`, one level up.
