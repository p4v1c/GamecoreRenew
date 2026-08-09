# 12 — The addon contract (`api: 1`)

**This is a public contract.** Unlike everything else in this folder, it is
addressed to people outside this repository: it is what a third-party addon
author has to satisfy, and changing it breaks software this project does not
control and cannot fix.

Implementation: `install/bin/gamecore-addon` (the CLI), `backend/routers/addons.py`
(the screen), the registry at `<DATA>/config/addons.json`.

## The one rule

> **Write under `GAMECORE_DATA`. Never under `GAMECORE_PATH`.**

Everything below is a consequence of it.

`GAMECORE_PATH` is the installation — code, venv, frontend build, catalogue. It
is aiming at being a read-only mount, and the OTA replaces it wholesale on every
release. `GAMECORE_DATA` is everything the player owns, and it is what a backup
copies and what the updater's rsync is careful to leave alone. See
[7](07-config-and-data.md) for the two roots themselves.

An addon that writes into the install root loses its data at the next update, and
fails outright the day the root goes read-only.

## Why there is a version at all

Addons written before the split assumed `$GAMECORE_PATH` was writable. On a box
with a read-only root, such an addon fails **at install time, in somebody's
living room, with the Addons screen showing a shell script's stderr.**

So the CLI refuses it *before running anything*, by name, and prints the porting
instructions. The audience for that message is a player holding a gamepad in
front of a television, not the addon's author — which is why it says what to do
rather than what went wrong.

```json
{
  "id": "save-manager",
  "name": "Save Manager",
  "version": "1.2.0",
  "api": 1
}
```

`GCA_API_VERSION` in the CLI is the version GameCore speaks. A mismatch in either
direction is refused: an addon declaring `2` against a box speaking `1` is just as
broken as one declaring nothing, and failing loudly beats running half of it.

## What a hook receives

`install.sh` and `uninstall.sh` are run with:

| Variable | Meaning |
|---|---|
| `GAMECORE_DATA` | the data root. **Write here.** |
| `ADDON_DATA_DIR` | `<DATA>/addons/<id>/`, **created before the hook runs**. An addon should not have to know the layout to keep one config file |
| `GAMECORE_PATH` | the install root. **Read-only.** Passed so an addon can find shipped code — never so it can write |
| `GAMECORE_ADDON_API` | the version the CLI speaks, so a hook can branch instead of guessing |
| `ADDON_DIR` | the addon's own directory |
| `USER_NAME` | the box's user |
| `GAMECORE_BACKEND_PORT` | where the core listens |
| `OFFLINE` | set when the install must not reach the network |
| `PAYLOAD_DIR` | files shipped alongside the addon |

`ADDON_DATA_DIR` existing before the hook runs is deliberate: the most common
thing an addon does is keep one small file, and requiring every author to
`mkdir -p` a path they had to derive is how they end up deriving it *wrong* —
under the install root, which is the failure this contract exists to prevent.

## The gate is on install and update — never on remove

`check_api` is called from `cmd_install` and `cmd_update`. It is deliberately
**not** called from `cmd_remove`.

A box updated to this release already has addons installed by the old CLI, none
of which declares a version. Refusing to *remove* them would strand the player
with something they cannot uninstall from the very screen that installed it —
the update would have taken away the exit. An addon on its way out does not need
to satisfy a contract about how it writes.

## Where addon code lives — the fourth category

The addon checkout is git-managed code, but the player installs and removes it at
runtime. So it can live on neither a read-only root nor the OTA: it is **mutable
code**, which the code/data split had no name for, and it belongs on the data
side.

| | |
|---|---|
| new installs | `<DATA>/addons/_repo` |
| boxes installed before this release | `/opt/gamecore-addons`, and it keeps being used |

Addon ids may not start with `_`, so `_repo` cannot collide with an addon's own
directory. The old location is left alone on purpose: boxes have services already
pointing into it, relocating it from under them would break running addons for no
gain, and the player would have no way to tell why.

## Where an addon may listen

Addons run as **systemd user units** and bind their own ports (`:8770`, `:8771`,
`:8772` today). They are reachable from the LAN only through Caddy, which
authenticates; the core's `/api/*` is 403 through that path. An addon talks back
to the core with `POST /api/addons/notify`.

That endpoint feeds HUD toast text, and **any addon can call it** — so the text
is untrusted. The UI escapes it (`escHtml()`, `safeColor()`). If you are adding a
surface that renders addon-supplied strings, escape there too; see
[9](09-gotchas.md).

## Porting checklist

1. Add `"api": 1` to `addon.json` — but only after the rest.
2. Replace every write under `$GAMECORE_PATH` with `$ADDON_DATA_DIR`.
3. Do not `mkdir` `$ADDON_DATA_DIR`; it is already there.
4. Keep reads of `$GAMECORE_PATH` if you need shipped code — that is allowed.
5. Check `uninstall.sh` removes what `install.sh` wrote, and nothing else.
