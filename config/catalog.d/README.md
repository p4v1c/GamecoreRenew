# `config/catalog.d/` — local packs

Drop a pack directory here to add an emulator or an application to **this box
only**, without it going through the public repository.

```
config/catalog.d/myemu/
  pack.json
  logo.png
  seed/…
```

The layout is exactly the one under `catalog/` — same `pack.json`, same schema
(`catalog/_schema/pack.schema.json`). Removing a pack is `rm -rf`.

## Why this directory survives an update

`update/linux.sh` excludes `config/` wholesale from its rsync, so everything in
here is preserved across every OTA. `catalog/` is the opposite: it is shipped
content and **is** overwritten by each release — that is what finally lets a
corrected logo or seed reach an installed box.

An id present in both places: **the local pack wins entirely.** Not a
field-by-field merge — a replacement. The origin of every pack is logged at
load time:

```
journalctl -u gamecore-backend | grep catalog
```

## Data only, by default

A pack shipped in `catalog/` may carry a `generator.py`: it is project code, it
goes through review and CI.

A pack dropped **here** is data only. Five blocks are ignored, with a warning
on every load:

| Ignored | Why |
|---|---|
| `generator.py` | runs Python inside the backend |
| `postInstall` | runs a shell script |
| `services` | installs a systemd unit |
| `sources` | clones a git repository onto the machine |
| `packages` | installs system packages |

All five execute code or change the system outside the pack directory. Without
this rule, "drop a directory" would mean arbitrary code execution — and the
install CLI turns that into something triggerable from the interface.

A local pack can still describe its launch, its seed, its files under `@HOME@`
and its installation by a provider. That covers the ordinary case.

## Lifting the restriction

On your own machine, and knowing what it means:

```bash
sudo systemctl edit gamecore-backend
# [Service]
# Environment=GAMECORE_TRUST_LOCAL_PACKS=1
```

It is logged as a warning at **every** load, not once. That is deliberate: an
operator who turned this on months ago must keep being told that a directory
dropped in here can run code.

## Checking a pack before trusting it

```bash
python3 scripts/check-catalog.py myemu
```

Schema, symmetry (a logo, a ROM directory, a `config.dest` exactly when there
is a `seed/`), and the seed rules — including `seedMustNotContain`, which
refuses a seed that names a physical controller. A seed that pins one pad model
is how players 2 to 4 stayed dead for a week.
