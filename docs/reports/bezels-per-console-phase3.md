# Phase 3 — what to verify on the box, and how to migrate it

I cannot see a bezel. I can prove it resolves for the right console, that its
hole comes from the right alpha channel, that the cache keys differ — the
tests do that. **The rest is judged by eye, from three metres**, and that is
what this document is for.

> Historical note: this protocol was written for the owner on 2026-08-18,
> before the migration to `/userdata`. Paths that say `/opt/GameCore` describe
> the box as it was that evening; on the migrated box the data root is
> `/userdata`. The protocol itself was followed the same night and the
> per-console cascade has been verified live since.

## What a correct bezel looks like

The only thing to look at, and it is not obvious unless somebody says it:

> The decorative frame **hugs the black bars**. It does not bite into the
> picture — no piece of artwork on top of the game — and it leaves **no black
> band between the picture and the frame**.

Both defects show at the same place, the picture/artwork boundary, and they
are opposites: too much frame eats the game, too little lets black through.

---

# 1. Non-regression — first

**The most important test, and the only one that can invalidate the whole
delivery.** The box has only system-level bezels. None of them must move.

Without launching a single game:

```bash
cd /opt/GameCore && .venv/bin/python - <<'PY'
import sys, json; sys.path.insert(0, '.')
from backend.services import bezels
for sid in ("azahar", "melonds", "duckstation", "pcsx2", "gopher64", "mgba"):
    o = bezels.for_launch(sid, "Some Game (USA).iso")
    print(f"{sid:12s} source={o['source']:9s} console={o['console']} hole={o['hole']}")
PY
```

Write these six lines down **before** the update and compare after. For the
five mono-console packs, `console` must be `None` and everything else
**character-for-character identical**. If a single line moves, stop and say
so: that is a regression, not a side effect.

Then, by eye: launch one PS1, one PS2, one 3DS, one DS game. Each must look
exactly as before.

A case not to mistake for a regression: `duckstation`, `gopher64`, `pcsx2` and
`mgba` have **no PNG on the box today** — they display nothing, before and
after. That is the current state, not a consequence of this work.

---

# 2. The case that motivated the work — mgba

## 2.1 Without depositing anything

After the update, **before** supplying any PNG:

```bash
cd /opt/GameCore && .venv/bin/python - <<'PY'
import sys; sys.path.insert(0, '.')
from backend.services import bezels
for rom in ("Tetris (World).gb", "Pokemon Emerald (USA).gba"):
    o = bezels.for_launch("mgba", rom)
    print(f"{rom:28s} console={o['console']!r:7s} hole={o['hole']} measure={o['measure']}")
PY
```

Expected: `console='gb'` and `console='gba'` — **two different answers**,
where before they were byte-identical. And `measure=True` for both: the old
`mgba@1:1` correction is no longer reachable, so the box will relearn, **once
per console**.

## 2.2 By playing

Launch a Game Boy game, quit, then a Game Boy Advance game, quit. Then reread
the cache:

```bash
cat /opt/GameCore/config/bezel-corrections.json
```

Expected, **two distinct entries**:

```json
{
  "mgba/gb@1:1":  { "x": 360, "y": 0, "w": 1200, "h": 1080 },
  "mgba/gba@1:1": { "x": 150, "y": 0, "w": 1620, "h": 1080 }
}
```

Exact figures will vary by a few pixels — it is a screen measurement. What
matters is **two keys** and two clearly different widths: around 1200 for the
Game Boy (10:9), around 1620 for the GBA (3:2).

The old `mgba@1:1` line is still there and **that is intended**: it is dead,
nothing can read it any more, and leaving it is what makes a clean rollback
possible. You may delete it later, not now.

> ⚠️ **What this fixes and what it does not.** The **hole** becomes right per
> console — the game is fully visible in both cases. The **artwork** is still
> the single 1:1 `mgba.png`, which matches neither machine. For the frame to
> truly hug the picture you need one PNG per console: that is step 2.3, and
> the images are yours to supply.

## 2.3 By depositing one bezel per console

The naming convention, in `/opt/GameCore/assets/overlays/`:

| file | for |
|---|---|
| `mgba.png` | all of mGBA — the fallback, as today |
| `mgba.gb.png` | Game Boy (10:9) |
| `mgba.gbc.png` | Game Boy Color (10:9) |
| `mgba.gba.png` | Game Boy Advance (3:2) |
| `dolphin.gamecube.png` | GameCube |
| `dolphin.wii.png` | Wii |

`<system>.<console>.png`, beside the system bezel. The console ids are the
ones the pack declares, and you can read them:

```bash
/opt/GameCore/.venv/bin/python -c "
import json
for s in json.load(open('/opt/GameCore/config/systems.json')):
    if s.get('consoles'): print(s['id'], [c['id'] for c in s['consoles']])"
```

Drop a file, then check it is picked up **without launching a game**:

```bash
cd /opt/GameCore && .venv/bin/python -c "
import sys; sys.path.insert(0,'.')
from backend.services import bezels
print(bezels.for_launch('mgba','Pokemon Emerald (USA).gba'))"
```

Expected: `source='console'` and `asset='/assets/overlays/mgba.gba.png'`.

⚠️ **A hand-copied PNG is not validated.** The validation (an image with no
transparent area is refused) sits on the upload route, not on the filesystem.
If you `cp` a file, nothing will tell you it is opaque. The check above tells
you indirectly: `source` stays `system` or `none` if the hole is unreadable.

## 2.4 Refusing an image with no hole

Through the route this time:

```bash
curl -k -X POST https://localhost:8443/api/overlays/mgba/consoles/gba \
     -F "file=@some-image-without-transparency.png"
```

Expected: **422**, with a message saying a bezel needs a transparent area. And
the file already in place, if any, **was not touched**.

---

# 3. The second multi-console pack — dolphin

Nothing should overflow: GameCube and Wii share 4:3. **This is not a fix, it
is a capability** — two bezels for two different machines.

```bash
cd /opt/GameCore && .venv/bin/python - <<'PY'
import sys; sys.path.insert(0, '.')
from backend.services import bezels
for rom in ("Zelda Wind Waker (USA).gcm", "Wii Sports (USA).wbfs",
            "Mario Kart (USA).iso"):
    print(f"{rom:30s} console={bezels.for_launch('dolphin', rom)['console']!r}")
PY
```

Expected: `'gamecube'`, `'wii'`, then **`None`** for the `.iso`.

**That `None` is intended, not an omission.** `.iso`, `.rvz` and `.zip` can
hold either machine — `.rvz` is Dolphin's own container, and the scraper
already paid for guessing: every Dolphin game was looked up as GameCube and
Mario Kart Wii quietly matched Double Dash. An ambiguous extension stays at
the system level rather than guessing. In practice most Dolphin dumps are
`.iso` or `.rvz`, so **most Dolphin games will stay at the system level** —
that is normal.

---

# 4. Every level of the cascade

Six states, in order: **off → game → console → system → declared → none**.

| what you do | what you must see |
|---|---|
| a GBA game, with `mgba.gba.png` and `mgba.png` | the **console** bezel |
| the same, plus `mgba/Pokemon Emerald (USA).png` | the **game's** bezel |
| a GB game, with only `mgba.png` | the **system** bezel |
| overlay switched off for that game (options screen) | **nothing**, even though it has a console bezel |
| a system with no PNG at all | **nothing** — and above all no black bars |

The last line is the one to watch. Black bars over a game that filled the
screen correctly is the defect the cascade exists to prevent.

To check "off" without a gamepad:

```bash
cd /opt/GameCore && .venv/bin/python -c "
import sys; sys.path.insert(0,'.')
from backend.services import bezels
bezels.set_preference('mgba','Pokemon Emerald (USA).gba','off')
print(bezels.for_launch('mgba','Pokemon Emerald (USA).gba'))
bezels.set_preference('mgba','Pokemon Emerald (USA).gba', None)   # put it back"
```

Expected: `source='off'`, `asset=None`, `hole=None`. **The second line
restores automatic** — do not forget it.

---

# 5. Migrating the box

`assets/overlays/` and `config/` are excluded from the OTA rsync. **The
release will touch neither your images nor your records.** Here is what
happens anyway, and what does not.

## What happens on its own

`update/linux.sh` already runs `merge_file()` on `config/systems.json` after
the rsync — the mechanism originally built to repair the N64 launcher. The
`consoles` fill-in is attached to the same spot, with the same conservative
rule: **filled only when the box has none, never overwritten.**

So `config/systems.json` will gain `consoles` for `mgba` and `dolphin`
**without you typing anything**. Dry-run verified against a copy of the box's
real `systems.json`:

```
dolphin: consoles filled in (gamecube, wii)
mgba: consoles filled in (gba, gbc, gb)
```

## What does not happen on its own

The **images**. The new code makes a per-console bezel possible; it supplies
none. If you want the GBA's frame to hug a 3:2 picture, you must deposit
`mgba.gba.png`.

## 5.1 The backup — first, always

A few tens of kilobytes. Without it there is no way back.

```bash
B=~/bezel-backup-$(date +%F-%H%M)
mkdir -p "$B"
cp -a /opt/GameCore/assets/overlays "$B"/overlays
cp -a /opt/GameCore/config/systems.json "$B"/
cp -a /opt/GameCore/config/overlays.json "$B"/
cp -a /opt/GameCore/config/bezel-holes.json "$B"/ 2>/dev/null
cp -a /opt/GameCore/config/bezel-corrections.json "$B"/ 2>/dev/null
cp -a /opt/GameCore/config/bezel-choices.json "$B"/ 2>/dev/null
echo "$B" > ~/.last-bezel-backup
ls -la "$B"
```

(`bezel-choices.json` does not exist on the box today — the `2>/dev/null` is
for that, not an error.)

## 5.2 What to do — one command per line

**Nothing is mandatory.** The box works unmigrated; see 5.5.

```bash
# a) See what the box understood about consoles (nothing to type if correct).
/opt/GameCore/.venv/bin/python -c "
import json
for s in json.load(open('/opt/GameCore/config/systems.json')):
    if s.get('consoles'): print(s['id'], [c['id'] for c in s['consoles']])"

# b) If (a) prints nothing, the OTA merge did not run. Re-run it:
cd /opt/GameCore && .venv/bin/python - <<'PY'
import sys; from pathlib import Path
root = Path("/opt/GameCore"); sys.path.insert(0, str(root))
from backend.services.catalog import load_catalog
from backend.services.catalog.merge import merge_file
for n in merge_file(root/"config"/"systems.json",
                    load_catalog(root/"catalog", root/"config"/"catalog.d"),
                    root):
    print(" ", n)
PY

# c) Deposit one bezel per console — YOUR images, which I cannot fabricate.
#    The name is <system>.<console>.png, beside the system bezel.
cp /path/to/your-gba-frame.png /opt/GameCore/assets/overlays/mgba.gba.png
cp /path/to/your-gb-frame.png  /opt/GameCore/assets/overlays/mgba.gb.png

# d) OPTIONAL, and only after verifying point 2.2: erase the old, now-dead
#    correction. It does no harm, it is just unreadable now. Only once
#    everything else works.
/opt/GameCore/.venv/bin/python - <<'PY'
import json
from pathlib import Path
p = Path("/opt/GameCore/config/bezel-corrections.json")
d = json.loads(p.read_text())
dead = [k for k in d if "/" not in k and k.split("@")[0] in ("mgba", "dolphin")]
for k in dead:
    print("removed:", k, d.pop(k))
p.write_text(json.dumps(d, indent=2, sort_keys=True))
PY
```

**There is nothing to rename and nothing to flush.** That was the brief's
assumption; measurement proved it wrong, and that is good news: the hole cache
is keyed by file path, so an added PNG is measured on its own, and the
correction keys change by themselves.

## 5.3 Verifying it took — before launching a game

```bash
cd /opt/GameCore && .venv/bin/python - <<'PY'
import sys; sys.path.insert(0, '.')
from backend.services import bezels, consoles
print("mgba declared consoles:", [c["id"] for c in consoles.declared("mgba")])
for rom in ("Tetris (World).gb", "Pokemon Emerald (USA).gba"):
    o = bezels.for_launch("mgba", rom)
    print(f"  {rom:28s} console={o['console']!r:7s} source={o['source']:8s} asset={o['asset']}")
print("pcsx2 (mono-console):", bezels.for_launch("pcsx2", "God of War.iso")["console"])
PY
```

Three things to read:

1. `mgba declared consoles: ['gba', 'gbc', 'gb']` — the merge worked;
2. the two ROMs give **two different `console` values** — the level exists;
3. `pcsx2 (mono-console): None` — nothing moved for the eleven other packs.

## 5.4 The way back — written before it is needed

```bash
B=$(cat ~/.last-bezel-backup)
rm -rf /opt/GameCore/assets/overlays
cp -a "$B"/overlays /opt/GameCore/assets/overlays
cp -a "$B"/systems.json           /opt/GameCore/config/systems.json
cp -a "$B"/overlays.json          /opt/GameCore/config/overlays.json
cp -a "$B"/bezel-holes.json       /opt/GameCore/config/ 2>/dev/null
cp -a "$B"/bezel-corrections.json /opt/GameCore/config/ 2>/dev/null
cp -a "$B"/bezel-choices.json     /opt/GameCore/config/ 2>/dev/null
```

Then reread the non-regression block from step 1: the six lines must be the
ones from before.

To also revert the **code**, `git revert` the branch: the old `mgba@1:1` key
becomes readable again, and since it was never deleted (unless you did 5.2.d),
the box recovers exactly its original behaviour.

## 5.5 What you lose by doing nothing

**Nothing breaks.** The new code works on an unmigrated box. A migration that
is mandatory for the box to stay usable would be a defect, not a step.

Precisely:

| you do nothing | what it gives |
|---|---|
| you skip the OTA | everything as today |
| you apply the OTA, deposit no PNG | mgba **relearns its correction per console**: the hole becomes right for GB and GBA separately. The artwork stays the 1:1 frame, so it still does not hug — but the game is fully visible |
| you deposit no dolphin bezel | dolphin stays at the system level, as today |
| you keep `mgba@1:1` | nothing: the line is dead, nothing reads it |

The only thing you durably lose by doing nothing is **the frame that hugs the
picture** — and that needs images I do not have.
