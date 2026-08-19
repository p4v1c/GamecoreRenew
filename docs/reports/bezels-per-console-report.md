# Per-console overlays — report

Branch **`feat/bezels-par-console`**, pushed, **not merged**, no PR.
Base: `main` at `7bf7a76`. (Since merged; kept as the decision record.)

---

# Decisions taken alone

The owner was away; each call preferred the most reversible option. The six,
each with its reason and **how to undo it**.

### 1. Consoles are declared in `roms.consoles`, not in `libretroSystems`

**Reason — measured, not assumed.** `melonds` declares **two** libretro
entries (`Nintendo - Nintendo DS` and `Nintendo - Nintendo DS (Download
Play)`) for **one machine**. `libretroSystems` is therefore not a console
list; it is a list of names in libretro's database. Keyed on it, melonDS would
grow a phantom console. And `shadps4` declares zero while having a
`mediaAlias`: the libretro list is incomplete on top of being wrong.

`scraper.mediaAlias` was considered too — it really is one entry per console.
Rejected anyway: it is ScreenScraper's vocabulary (`"nintendo 64"`,
`"xbox 360"`, spaces included), someone else's name to rename, and unusable in
a filename.

**To undo:** remove the `consoles` block from the schema and the two packs.
The code falls back to the system level on its own — `consoles.declared()`
returns `[]`.

### 2. `.iso`, `.rvz` and `.zip` are attached to no console

**Reason.** They are genuinely ambiguous. `.rvz` is Dolphin's own container
holding GameCube and Wii alike; the scraper already paid for guessing —
`gamemedia/registry.py` records that every Dolphin game was looked up as
GameCube and Mario Kart Wii quietly matched Double Dash. The brief said not to
invent: nothing was invented.

An ambiguous extension resolves to `None` and the console level is simply
skipped. **The failure is visible** in two ways: `check-catalog.py` refuses at
build time an extension claimed by two consoles, and at runtime
`consoles.for_rom()` logs before falling back.

**Consequence worth knowing:** most Dolphin dumps are `.iso` or `.rvz`, so
**most Dolphin games stay at the system level**. Honest, not satisfying.

**To undo:** add `*.iso` under one console in `catalog/dolphin/pack.json` —
but `check-catalog` will refuse it under both. The real way out is reading the
disc header (`gameid.identify()` already knows how); not done here — it is
I/O in front of a starting game.

### 3. The correction key carries the console — explicitly, not by accident

The brief noted the elegant case: one PNG per console ⇒ different holes ⇒
different ratios ⇒ different keys, naturally. **True and not enough**, because
it only holds once the PNGs exist. While there is one PNG, the three consoles
share one ratio — exactly the state the box was found in.

So: `<system>/<console>@<ratio>` for a pack that declares consoles,
`<system>@<ratio>` for the other eleven, **byte-identical to before**.

**To undo:** return `key_for()` to its original form. The old entries are
still on disk; they become readable again immediately.

### 4. Existing cached corrections are **kept but made unreachable**

The brief asked to choose between keeping and deleting. Neither, exactly:
`mgba@1:1` stays on disk, but no computed key can find it any more — a pack
with consoles always carries a console segment, `-` included when the
extension did not say.

**Reason.** Keeping them meant applying one console's measurement to three,
which is the bug. Deleting them made rollback impossible. Leaving them dead
costs a re-learn — two launches — and **destroys nothing**, which is the
property that mattered.

**To undo:** nothing to do, precisely. `git revert` the branch and the old key
is readable as-is.

### 5. Naming: `<system>.<console>.png`

`mgba.gba.png` beside `mgba.png`. Guessable without documentation: the system
bezel is `mgba.png`, a console's adds its name. Beside the system file rather
than inside `assets/overlays/mgba/`, because that directory is the per-game
pack and an unpacked Bezel Project archive would sit next to files that are
not games.

Console ids forbid dots (`^[a-z0-9][a-z0-9-]{0,31}$`), or `mgba.gb.c.png`
could not be parsed back.

**To undo:** change `bezels.console_png()`, one line. And rename any deposited
PNGs.

### 6. Deposits go through a core route, and an opaque image is refused

`POST /api/overlays/<system>/consoles/<console>`. **Not a widening of the
addon contract**: `api: 1` says an addon writes inside its own data directory.
Opening `assets/overlays/` to addons for one feature would open it to all.
ROM Manager calls; the core validates the console against `roms.consoles` and
decides where to write. `docs/SECURITY.md`: `/api/*` answers 403 from the LAN,
so the route is reachable from the box, not from a phone.

**Adjacent decision, the least certain one:** the refusal of an image with no
transparent area applies **to the existing system route too**, not only the
new one. An opaque image is a rectangle painted over the whole game whatever
the level — but it changes behaviour on a pre-existing endpoint. **In practice
it makes JPEG unusable** (JPEG cannot carry alpha), which is correct but
stricter than before.

**To undo:** move the `hole is None` block from `_receive_bezel()` into the
console route alone.

---

# Phase 1 — the state, in three lines

Details in [bezels-per-console-phase1.md](bezels-per-console-phase1.md),
written before phase 2 and untouched since, except one flagged correction.

**1.1 — the defect is demonstrated.** `for_launch("mgba", …)` returned the
same answer **byte for byte** for `.gb`, `.gbc` and `.gba`.

**And it was worse than that.** `mgba.png`'s hole measures `1080x1080` — a
**1:1** square, neither the Game Boy (10:9) nor the GBA (3:2). The
`config/overlays.json` label half-admitted it: `"Game Boy Advance (Cadre
Total)"`.

**The box's cache carried the mechanism's proof**, a single line:

```json
{ "mgba@1:1": { "h": 1080, "w": 1234, "x": 343, "y": 0 } }
```

1234/1080 = **1.14**: a Game Boy. A GBA picture 1080 tall is **1620** wide.
**The frame ate 193 px per side** — and `"measure": fixed is None` being
false, the box would never look again. The first console played had locked all
three, permanently.

Three mismatches with the brief, written down rather than silenced:

1. The PNG is not "cut for the Game Boy"; it is wrong for all three.
2. **duckstation carries a latent defect**: a 180:121 hole for a 4:3 console.
   Unrelated to multi-console; flagged, not fixed.
3. **Four PNGs had vanished from the box** — the correction predates that
   clean-up and will return as-is the day the PNGs are restored.

**1.4** — survey redone: `mgba` (3), `dolphin` (2), ten single-console packs,
and `shadps4` at **zero** (with `"extensions": []` on top). The catalogue hole
is double, flagged without being filled.

---

# Phase 2 — what was built

| file | what it does |
|---|---|
| `backend/services/consoles.py` | **new** — which console of a pack a ROM is |
| `backend/services/bezels.py` | the `console` level in `resolve()`, `console_png()`, `hole_of()` |
| `backend/services/bezel_capture.py` | `key_for/correction_for/record` take the console |
| `backend/routers/overlays.py` | per-console deposit route, opaque-image refusal |
| `catalog/_schema/pack.schema.json` | `roms.consoles` |
| `catalog/{mgba,dolphin}/pack.json` | the five consoles declared |
| `backend/services/catalog/{tiles,merge}.py` | carried into `systems.json`, **and to the box** |
| `scripts/check-catalog.py` | refuses an incoherent declaration |
| `electron/main.js` | sends the console back with the measurement |
| `frontend/src/…` | the options screen names the console |

**No console list is written in code.** The WHAT stays declarative, the HOW in
the generator: a pack added tomorrow works without the core knowing it.

## The four 2.5 verifications

**① The 1.1 demonstration, replayed.** Three **different** answers:

```
Tetris (World).gb          console='gb'
Zelda Oracle (USA).gbc     console='gbc'
Pokemon Emerald (USA).gba  console='gba'
```

And the correction keys separate: `mgba/gb@1:1`, `mgba/gba@1:1`, `mgba/-@1:1`
— the old `mgba@1:1` unreachable, `pcsx2@4:3` unchanged.

**② A test red before the fix.** `test_bezels_consoles.py` was written first
and run against the old code:

```
>       assert (gb_level, gba_level) == ("console", "console")
E       AssertionError: assert ('system', 'system') == ('console', 'console')
```

Not an `ImportError` — a behavioural failure, on the exact defect. Five red
tests, this one included.

**③ Non-regression, measured against the actually deployed code.** The old
code (`/opt/GameCore`) and the new (the clone) were run **on the same data**
and `for_launch` outputs compared for six mono-console systems:

```
✅ IDENTICAL — mono-console packs do not move by one byte (console field aside)
```

Plus a test comparing `describe()` wholesale, and one pinning
`key_for("pcsx2", …) == "pcsx2@180:121"`.

**④ `check-catalog.py` validates the new shape and fails an incoherent one.**
Both directions verified:

```
check-catalog: mgba: *.gba is claimed by both 'gba' and 'gbc' — an extension names one console or none
check-catalog: mgba: console 'gbc' claims *.sgb but roms.extensions does not list it
check-catalog: 2 problem(s)
```

## The six commands

| | before | after |
|---|---|---|
| `ruff check .` | ✅ | ✅ |
| `shellcheck` | ✅ | ✅ |
| `check-catalog.py` | 17 packs OK | 17 packs OK |
| `gen-catalog.py --check` | in sync | in sync |
| `pytest` | **1634** passed, 5 skipped | **1659** passed, 5 skipped |
| `npm run build` | ✅ | ✅ |

+25 tests, no fixture touched, `config/overlays.json` unchanged.

---

# Phase 3 — the protocol

In [bezels-per-console-phase3.md](bezels-per-console-phase3.md):
non-regression first, mgba, dolphin, every cascade level, the deposit, and the
migration with backup and way back.

**The most useful point in it:** `update/linux.sh` already runs `merge_file()`
on `config/systems.json` after the rsync — the mechanism built to repair the
N64 launcher. `consoles` was attached to the same spot, with the same
conservative rule (filled when the box has none, never overwritten). Dry-run
verified on a copy of the box's real `systems.json`:

```
dolphin: consoles filled in (gamecube, wii)
mgba: consoles filled in (gba, gbc, gb)
```

**So there is nothing to rename, move or flush.** The brief assumed otherwise;
measurement said no, and that is good news. One manual thing remains, the one
nobody else can do: **deposit the images**.

---

# What this phase does not do

**It makes a per-console bezel possible. It supplies none.**

No PNG is added by this work. The deposit is the owner's, and it is image
work, not code work.

What improves anyway, **without depositing anything**: the drift correction is
now learned **per console**. A GB game will learn `mgba/gb@1:1` ≈ 1200x1080
and a GBA game `mgba/gba@1:1` ≈ 1620x1080. **The hole becomes right per
console** and the game fully visible. The artwork stays the 1:1 frame that
matches neither: it will no longer bite, it will leave black. A frame that
**hugs** the picture needs a picture-shaped frame.

And it is **not a fix for dolphin**: GameCube and Wii share 4:3, nothing
overflowed. It is a capability — two bezels for two machines.

---

# What I am not sure of

1. **The opaque-image refusal on the pre-existing system route** (decision 6).
   The only behaviour change on an existing endpoint, and it makes JPEG
   unusable in practice. Correct, but stricter than before, decided alone.
2. **`.iso` and `.rvz` unattached make the console level nearly useless for
   dolphin.** Defensible — it is the refusal to guess — but the result is a
   feature that will rarely fire on that pack.
3. **The plausibility threshold for the GBA.** `is_plausible` wants coverage
   between 0.25 and 0.995 and centring within 8 px. Computed: 1620x1080 in
   1920x1080 gives 0.84, centred at 150/150 — it passes. **Never seen passing
   on a real screen** — no X11 capture is possible here, and that module has
   no test for this reason.
4. **duckstation's latent defect** (180:121 for 4:3). Flagged, not fixed, and
   whether the PNG or the record is right was not investigated.
5. **`shadps4` with neither `libretroSystems` nor `extensions`.** Flagged,
   untouched: the brief said doubtful cases are the owner's to decide.
6. **No `gamecore-*` service was restarted**, nothing written to `~/.var/app/`,
   the ROMs or the saves, and `/opt/GameCore` was opened read-only. The only
   writes are in the clone and a temp directory.
