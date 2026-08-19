# Phase 1 — what was measured, before anything was changed

Measured on 2026-08-18 on the `~/Downloads/GamecoreRenew` clone at `main`
(7bf7a76), and read-only against `/opt/GameCore`.

## 1.1 — The demonstration: **the defect is confirmed**

`for_launch("mgba", …)` on three ROMs from three different consoles:

```
Tetris (World).gb          -> hole {"x":420,"y":0,"w":1080,"h":1080}  source system  measure true
Pokemon Emerald (USA).gba  -> hole {"x":420,"y":0,"w":1080,"h":1080}  source system  measure true
Zelda Oracle (USA).gbc     -> hole {"x":420,"y":0,"w":1080,"h":1080}  source system  measure true
```

**Byte-for-byte identical answers.** The system does not distinguish the
consoles of one pack. The brief's premise holds.

## 1.2 — What the alpha channel actually measures

The six shipped PNGs, hole derived from their alpha:

| pack | measured hole | ratio | declared | agree |
|---|---|---|---|---|
| azahar | `900x1080+510+0` | **5:6** (0.833) | same | ✅ |
| duckstation | `1440x968+240+52` | **180:121** (1.488) | same | ✅ |
| gopher64 | `1440x1080+240+0` | **4:3** (1.333) | same | ✅ |
| melonds | `720x1080+600+0` | **2:3** (0.667) | same | ✅ |
| mgba | `1080x1080+420+0` | **1:1** (1.000) | same | ✅ |
| pcsx2 | `1440x1080+240+0` | **4:3** (1.333) | same | ✅ |

All six agree with `config/overlays.json`: `test_bezels.py` is doing its job;
the historical `gopher64` drift is fixed in the repository.

### mGBA's hole is cut for none of its three consoles

The brief assumed a frame cut for the Game Boy. The measurement says
otherwise, and it is worse:

| console | ratio | width of a 1080-tall picture | mgba's hole |
|---|---|---|---|
| Game Boy / Color | 10:9 (1.111) | 1200 px | 1080 px |
| Game Boy Advance | 3:2 (1.500) | 1620 px | 1080 px |

**1:1 is neither.** The label in `config/overlays.json` half-admits it:
`"label": "Game Boy Advance (Cadre Total)"` — a compromise frame, not a
console's frame.

### The other packs: one latent defect

- **duckstation `180:121` (1.488)** matches no console it emulates. The
  PlayStation renders 4:3 (1.333); at 968 tall a 4:3 picture is 1291 px wide,
  not 1440. The hole is **149 px too wide**. Nobody complains because the hole
  is *larger* than the picture — you see black bars inside the frame rather
  than a frame biting the game. Flagged, out of scope for this work.
- **azahar 5:6** and **melonds 2:3** are coherent: stacked dual screens
  (3DS 400x480, DS 256x384), not single-console ratios. ✅
- **gopher64 4:3** and **pcsx2 4:3** are right. ✅

## 1.3 — What the caches hold

`/opt/GameCore/config/bezel-holes.json` — six entries, one per PNG, keyed by
absolute path. Nothing to fault: path key, `mtime:size` signature.

`/opt/GameCore/config/bezel-corrections.json` — **a single entry**:

```json
{ "mgba@1:1": { "h": 1080, "w": 1234, "x": 343, "y": 0 } }
```

**The key is `mgba@1:1`.** The ratio is the announced hole's — 1:1 — so
**one key for all three consoles**, exactly as the brief anticipated.

### The 1.3 hypothesis is verified, and the result is quantified

The learned correction is **1234x1080**, ratio **1.143**. That is the
signature of a Game Boy or Game Boy Color (1200 px expected at 1080 tall),
not of a Game Boy Advance (1620 px).

| console played | real width | corrected hole | error |
|---|---|---|---|
| Game Boy / Color | 1200 px | 1234 px | −34 px (−17 px per side) |
| **Game Boy Advance** | **1620 px** | **1234 px** | **+386 px (+193 px per side)** |

**The frame bites 193 px off each side of a GBA game.** That is the reported
symptom, now measured rather than deduced.

And `for_launch()` carries `"measure": fixed is None`: with the correction in
place, `measure` is **false** for all three consoles. **The box will never
measure mgba again.** The first console measured locked the correction for all
three, permanently. Hypothesis confirmed.

### The box's real state, which was not in the brief

`/opt/GameCore/assets/overlays/` holds only **`azahar.png` and `melonds.png`**.
The other four PNGs — `mgba.png` included — are gone from disk, while
`bezel-holes.json` still caches them and `config/overlays.json` still declares
them.

The consequence, simulated with the box's paths: the `declared`-without-asset
case. **Checked rather than assumed**: the React renderer
(`frontend/src/components/OverlayScreen/index.tsx`) guards both branches with
`asset &&`, so **nothing is drawn at all** — no artwork and no black bars. The
component's comment even says `!asset ||` was the bug and `asset &&` the fix.
So the box has no black bars today; it simply no longer has a bezel for mgba,
gopher64, duckstation and pcsx2. The emulator window is still forced to
`window_rect`.

Chronology, from mtimes: `bezel-corrections.json` is from Aug 17 18:20; the
`assets/overlays/` directory from Aug 18 11:53. **The correction was learned
while `mgba.png` was still there**, and the PNGs disappeared afterwards. The
reported symptom is therefore real, predates that clean-up, and will come back
as-is the day the PNGs are restored — the correction stayed behind.

And for dolphin: `source "none"`, nothing drawn — correct.

## 1.4 — Multi-console packs (survey redone, `config/systems.json`)

13 systems. The brief's survey holds:

- **`mgba`: 3 consoles** — GBA, GBC, GB
- **`dolphin`: 2 consoles** — GameCube, Wii
- 10 packs declare **exactly one**
- **`shadps4` declares zero**: `"libretroSystems": []`, and `"extensions": []`
  with it. `rpcs3` also has `"extensions": []` but does declare its console.
  The catalogue hole is therefore **`shadps4`**, and it is double.

### The console → extension mapping is indeed implicit, and indeed fragile

```
mgba     libretroSystems [GBA, GBC, GB]      extensions [*.gba, *.gbc, *.gb, *.zip]
dolphin  libretroSystems [GameCube, Wii]     extensions [*.iso,*.gcm,*.rvz,*.wbfs,*.wad,*.zip]
```

The order coincides **for mgba only**, and by accident. For dolphin it means
nothing: 6 extensions for 2 consoles, `.iso` and `.zip` serve both,
`.gcm`/`.rvz` are GameCube, `.wbfs`/`.wad` are Wii. **No ordering rule can
produce that.** The mapping must be written down, not derived.

## My reading: causal chain **confirmed**

One PNG per pack → one hole per pack → one ratio per pack → **one correction
key per pack**, while the pack serves three consoles of different shapes. The
first console played fixes the correction and `measure: false` freezes it.
Measured at every link, not deduced.

Three things do not match the brief, and I proceed anyway:

1. **mGBA's hole is not "cut for the Game Boy"** — it is 1:1, wrong for all
   three. A console level makes the fix *possible*; it is not sufficient, PNGs
   are also needed. See "what this phase does not do".
2. **duckstation carries a latent defect** (180:121 for a 4:3 console),
   unrelated to multi-console. Flagged, not fixed.
3. **Four PNGs are gone from the box**, which therefore renders nothing for
   them. That changes the migration procedure: there is housekeeping to do on
   top of the renaming.
