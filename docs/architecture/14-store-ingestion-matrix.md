# 14 — The Store ingestion matrix

The Store is a screen of the core — a backend router and a frontend page — that
downloads a game and drops it into the library. It is not a pack and not an
addon. What it needs from the catalogue is one answer, per system:

> **Between "a file arrives from the network" and "the game appears in the grid
> and launches", what must happen, what must be checked, and what must never be
> done?**

This document is that answer for the 31 `kind=emulator` packs, and it is the
contract every Store component is built against — Materializer, Inspect/Classify,
Transform, Validate, Import. It describes what the code does **today**, at
`c1a4df6`. It proposes nothing.

Read [10 — Catalogue & install](10-catalog-and-install.md) first for what a pack
is. This document answers a narrower question than that one: not "how is a
system installed" but "how does a file become a playable game on it".

**Every non-trivial claim below names its evidence** — a `file:line`, or the
command that establishes it. Every "do not do X" names the failure that taught
it. The measurements were taken by running the real `iter_rom_files` against
throwaway directories; each is reproducible with the snippet beside it.

---

## 0. The one rule

> **The strategy is keyed on the pair (system, incoming format) — never on the
> system alone, and never on the format alone.**

A single global rule ("unpack archives", "keep the descriptor") is a design bug,
because `.zip` means two incompatible things in this catalogue (§2), and `.iso`
means two more — a self-contained disc image on one system and a *track file*
owned by a descriptor on another (`_DISC_TRACKS`,
`backend/services/rom_scanner.py:19`). Thirty-one strategies is the other
failure: it is a per-system `if` chain that has to be edited every time a pack is
added, which is the exact shape
[`backend/services/local_media.py`](../../backend/services/local_media.py) was
refactored to remove.

§5 resolves this into **six ingestion classes**. The 31 rows of §3 exist so the
classes can be checked against the data, not so that anyone codes from them.

---

## 1. What the library scan actually is

Six invariants, shared by all 31 systems. Everything else in this document is a
consequence of them.

### 1.1 Listing the games *is* the scan. There is no import step.

`list_games()` resolves `romsPath`, walks the directory, and returns what it
finds — every time the grid opens.

> `backend/routers/games.py:241`, and the comment at `:264`:
> *"This listing IS the box's ROM scan, and it runs whenever the grid opens. It
> is therefore the one place that learns a game was added since boot."*

**Consequence for the Store: a correctly-placed file needs no endpoint, no
database row, and no rescan call.** Dropping the bytes in the right directory
under the right name *is* the import. Cover prefetching is queued off the same
pass (`backend/routers/games.py:269`), so a newly deposited game also starts
acquiring its media on the next grid open with nothing else called.

The corollary is the reason this document exists: **there is no validation layer
between the filesystem and the grid.** A half-downloaded file, an update `.nsp`,
and a decompressed MAME set are all "imported" the instant they land. Whatever
the Store does not check, nothing checks.

### 1.2 The scan is flat. It does not recurse.

`iter_rom_files` calls `roms_path.iterdir()` — one level, no `rglob`.

> `backend/services/rom_scanner.py:119`

```
iter_rom_files(d, ["*.nes"])  on  {sub/Game.nes, Top.nes}  ->  ['Top.nes']
```

**A game one directory deep is invisible**, unless the system is `scanDirs`, in
which case the directory itself is the game. An archive that unpacks into its own
subfolder therefore does not produce a game — it produces nothing at all.

### 1.3 ROMs live at exactly one place

`<DATA>/emu/<dir>/`, with `<dir>` from the pack's `roms.dir`.

> `backend/services/paths.py:74` maps the logical key `roms` to `emu`;
> `roms.dir` is constrained to `^emu/[a-z0-9_-]+$` by
> [`catalog/_schema/pack.schema.json`](../../catalog/_schema/pack.schema.json).

`launch_game()` re-derives that root and refuses any `rom_path` that resolves
outside it (`backend/routers/games.py:306-308`, 403). **The Store must write
inside the system's own ROM directory or the game cannot be launched even when
it is listed.**

### 1.4 Two filename filters drop files silently

```python
if f.name.startswith(".") or "example" in f.name.lower():
    continue
```

> `backend/services/rom_scanner.py:127`

```
{Example Game.nes, MY EXAMPLES.nes, Normal.nes, .hidden.nes} -> ['Normal.nes']
```

`example` is an unanchored, case-insensitive **substring** match. A legitimately
named game containing it disappears with no message anywhere. **The Store must
treat a filename matching either filter as un-ingestible and say so at download
time**, because after the write there is no surface that can report it.

### 1.5 An empty `extensions` list means "list everything" — but only when `scanDirs` is false

```python
if extensions and not matches_ext(f.name, extensions):
    continue
```

> `backend/services/rom_scanner.py:135`

```
iter_rom_files(d, [])  on  {cover.png, notes.txt, Game.iso}
  -> ['cover.png', 'Game.iso', 'notes.txt']
```

The two packs that declare no extensions (`rpcs3`, `shadps4`) are saved from this
only because they also declare `scanDirs: true`, which takes the other branch.
`backend/tests/test_systems_extensions.py:72` pins that pairing:
*"`{sid}` declares no extensions and is not scanDirs"*. **Any stray file the
Store leaves in a `scanDirs` directory is invisible rather than harmful; the same
file on a no-extension non-`scanDirs` system would become a tile.** No such pack
exists today, and that test is what keeps it that way.

### 1.6 Companion-file dedup is real, narrow, and disabled on folder systems

`shadowed_by_a_descriptor` hides a file that is part of another entry, so a disc
dump is one game and not twelve.

> `backend/services/rom_scanner.py:41-101`
> Descriptors: `.cue .gdi .m3u .ccd .mds .toc` — `:18`
> Tracks: `.bin .img .iso .raw` — `:19`

Two rules run: **what the descriptor names** (parsed out of the file) and **what
shares its stem** (for dumps renamed without updating the descriptor). It is
transitive — an `.m3u` hides its `.cue` files, and their tracks go with them.

Two limits decide most of §3:

- **A descriptor only hides things if the system declares that descriptor's
  extension** (`:72-74`). This is not a detail: it is the regression that took
  the reference box from one PS1 game to zero, and
  `backend/tests/test_systems_extensions.py:224` is the test that holds the line.
- **`scan_dirs=True` disables it entirely** — `hidden = {}` at `:124`.

---

## 2. The archive decision — the central trap

`*.zip` is declared by 15 of the 31 packs and means **two incompatible things**.

### 2.1 The archive that *is* the ROM

For `mame`, `naomi`, `naomigd` and `atomiswave`, a romset is an archive whose
**member names are significant**: the emulator opens the archive and looks up
individual ROM chips by name inside it. Unpacking it destroys the game.

Measured, on a `mame`-configured directory:

```
{sf2.zip, neogeo.zip}       -> ['neogeo.zip', 'sf2.zip']     ✓ two games
{sf2/, sf2/sf2_01.rom}      -> []                            ✗ no games at all
```

Decompressing does not degrade the entry — **it deletes it**. The set becomes a
directory, the scan is flat and `scanDirs` is false for these four packs
(§1.2, §1.6), so neither the folder nor its contents is ever yielded. The player
sees a system that lost a game with no error anywhere.

> Note: three of these four declare `*.zip` and `*.7z` and nothing else. `mame`
> declares a third extension, `*.cmd` — see
> [`catalog/mame/pack.json`](../../catalog/mame/pack.json) and the README's
> supported-formats table. It is not an archive and nothing in this repository
> explains what it is for, so do not assume the four are interchangeable —
> logged in §7.

### 2.2 The archive that is packaging

For `snes9x`, `melonds`, `mgba`, `azahar`, `gopher64`, `dolphin`, `cemu`,
`pcsx2`, `ppsspp`, `duckstation` and `ryujinx`, `*.zip` is a convenience wrapper
the emulator or core usually reads directly. The member names carry no meaning
beyond the single game file inside.

### 2.3 The third case, which is the one that bites

**A system that does *not* declare `*.zip` cannot see a `.zip` at all.**

```
nes     exts=['*.nes','*.unf','*.unif']      {Mario.zip} -> []          ✗ invisible
snes9x  exts=[...,'*.zip',...]               {Mario.zip} -> ['Mario.zip'] ✓
```

Sixteen packs are in this position: `dreamcast`, `fds`, `gamegear`,
`mastersystem`, `megacd`, `megadrive`, `nes`, `pcengine`, `pcenginecd`, `rpcs3`,
`saturn`, `sega32x`, `sg1000`, `shadps4`, `supergrafx`, `xenia`. For these, a
downloaded archive **must** be unpacked or the download is silently wasted.

### 2.4 The decision, mechanised

Three outcomes, decidable from `roms.extensions` plus a listing of the archive —
no hardcoded system list:

| Condition | Decision |
|---|---|
| The archive's own extension **is declared**, and no member carries a declared non-archive extension | **NEVER DECOMPRESS.** The archive is the ROM (§2.1). |
| The archive's own extension **is declared**, and members do carry declared non-archive extensions | **DO NOT DECOMPRESS.** It is packaging the core reads (§2.2); unpacking is merely pointless, and risks §1.2 if it creates a folder. |
| The archive's own extension **is not declared** | **DECOMPRESS, but only if** a member carries a declared, non-archive extension, and only flat into the ROM directory. If no member qualifies, the download is not ingestible for this system — reject it, do not write it (§2.3). |

The predicate that separates the first two rows is *"does anything inside carry
an extension this pack declares"*, which is exactly what distinguishes a romset
(`sf2_01.rom` — undeclared) from packaging (`Mario.sfc` — declared). It needs no
list of arcade systems and stays correct when a pack is added.

**Flat, always.** Even when decompression is correct, extracting into a
subdirectory produces zero games (§1.2). The members must land beside their
siblings in `<DATA>/emu/<dir>/`.

---

## 3. The matrix

Seventeen columns in one table is not readable, so they are split across four
tables keyed on `PACK ID`: identity, what the scanner sees, the formats, and the
ingestion contract itself. Every one of the thirty-one packs appears in all four.

Sources for every cell: `catalog/<id>/pack.json`, read with
`.venv/bin/python scripts/check-catalog.py` (35 packs OK) and by direct load.
The behavioural columns are derived from §1 and §2 and are measured, not assumed.

### 3.1 Identity — SYSTEM · PACK ID · EMULATOR · PLATFORM · FAMILY · ROMS.DIR

| SYSTEM | PACK ID | EMULATOR | PLATFORM | FAMILY | ROMS.DIR | install |
|---|---|---|---|---|---|---|
| Sammy Atomiswave | `atomiswave` | RetroArch / flycast | Atomiswave | Sega | `emu/atomiswave` | pacman |
| Nintendo 3DS | `azahar` | Azahar | 3DS | Nintendo | `emu/azahar` | flatpak |
| Wii U | `cemu` | Cemu | Wii U | Nintendo | `emu/cemu` | flatpak |
| GameCube / Wii | `dolphin` | Dolphin | GameCube/Wii | Nintendo | `emu/dolphin` | flatpak |
| Sega Dreamcast | `dreamcast` | RetroArch / flycast | Dreamcast | Sega | `emu/dreamcast` | pacman |
| PlayStation | `duckstation` | DuckStation | PS1 | Sony | `emu/duckstation` | github-asset |
| Family Computer Disk System | `fds` | RetroArch / mesen | FDS | Nintendo | `emu/fds` | pacman |
| Sega Game Gear | `gamegear` | RetroArch / genesis-plus-gx | Game Gear | Sega | `emu/gamegear` | pacman |
| Nintendo 64 | `gopher64` | Rosalie's Mupen GUI | N64 | Nintendo | `emu/gopher64` | flatpak |
| Arcade (MAME) | `mame` | RetroArch / mame | Arcade | Arcade | `emu/mame` | pacman |
| Sega Master System | `mastersystem` | RetroArch / genesis-plus-gx | Master System | Sega | `emu/mastersystem` | pacman |
| Sega Mega-CD / Sega CD | `megacd` | RetroArch / genesis-plus-gx | Mega-CD | Sega | `emu/megacd` | pacman |
| Sega Mega Drive / Genesis | `megadrive` | RetroArch / genesis-plus-gx | Mega Drive | Sega | `emu/megadrive` | pacman |
| Nintendo DS | `melonds` | melonDS | DS | Nintendo | `emu/melonds` | flatpak |
| Game Boy Advance | `mgba` | mGBA | GBA | Nintendo | `emu/mgba` | flatpak |
| Sega Naomi | `naomi` | RetroArch / flycast | Naomi | Sega | `emu/naomi` | pacman |
| Sega Naomi GD-ROM | `naomigd` | RetroArch / flycast | Naomi GD-ROM | Sega | `emu/naomigd` | pacman |
| Nintendo Entertainment System | `nes` | RetroArch / mesen | NES | Nintendo | `emu/nes` | pacman |
| NEC PC Engine / TurboGrafx-16 | `pcengine` | RetroArch / beetle-pce | PC Engine | NEC | `emu/pcengine` | pacman |
| NEC PC Engine CD / TurboGrafx-CD | `pcenginecd` | RetroArch / beetle-pce | PC Engine CD | NEC | `emu/pcenginecd` | pacman |
| PlayStation 2 | `pcsx2` | PCSX2 | PS2 | Sony | `emu/pcsx2` | flatpak |
| PlayStation Portable | `ppsspp` | PPSSPP | PSP | Sony | `emu/ppsspp` | flatpak |
| PlayStation 3 | `rpcs3` | RPCS3 | PS3 | Sony | `emu/rpcs3` | flatpak |
| Nintendo Switch | `ryujinx` | Ryujinx | Switch | Nintendo | `emu/ryujinx` | flatpak |
| Sega Saturn | `saturn` | RetroArch / kronos | Saturn | Sega | `emu/saturn` | pacman |
| Sega Mega Drive 32X | `sega32x` | RetroArch / picodrive | 32X | Sega | `emu/sega32x` | pacman |
| Sega SG-1000 | `sg1000` | RetroArch / genesis-plus-gx | SG-1000 | Sega | `emu/sg1000` | pacman |
| PlayStation 4 | `shadps4` | shadPS4 | PS4 | Sony | `emu/shadps4` | flatpak |
| Super Nintendo | `snes9x` | Snes9x | SNES | Nintendo | `emu/snes9x` | flatpak |
| NEC PC Engine SuperGrafx | `supergrafx` | RetroArch / beetle-pce | SuperGrafx | NEC | `emu/supergrafx` | pacman |
| Xbox 360 | `xenia` | Xenia Canary | X360 | Microsoft | `emu/xenia` | github-archive |

Providers: **17 pacman** (always `retroarch` + one `libretro-*` core), **12
flatpak**, **1 github-asset** (`duckstation`), **1 github-archive** (`xenia`).
The 17 pacman packs are exactly the 17 that share
`overlay.wmClass.linux = ["retroarch","RetroArch"]` — see §5.7.

### 3.2 What the scanner sees — SCANDIRS · DECLARED EXTENSIONS · LIBRARY SCAN METHOD

`LIBRARY SCAN METHOD` is the same mechanism for all 31 — `iter_rom_files` via
`list_games()` on every grid open (§1.1) — so the column records the **branch**
each pack takes and the dedup it gets.

| PACK ID | SCANDIRS | DECLARED EXTENSIONS | LIBRARY SCAN METHOD (branch · dedup) |
|---|---|---|---|
| `atomiswave` | false | `*.zip *.7z` | file · **no dedup** (no descriptor declared) |
| `azahar` | false | `*.3ds *.cia *.zip` | file · no dedup |
| `cemu` | false | `*.wux *.rpx *.iso *.zip` | file · **no dedup**, though `.iso` is a track ext |
| `dolphin` | false | `*.iso *.gcm *.rvz *.wbfs *.wad *.zip` | file · **no dedup**, though `.iso` is a track ext |
| `dreamcast` | false | `*.chd *.cdi *.cue *.gdi *.m3u` | file · descriptor-only dedup (no track ext declared) |
| `duckstation` | false | `*.bin *.iso *.img *.cue *.chd *.pbp *.zip` | file · **full dedup** (`.cue` over `.bin`/`.iso`/`.img`) |
| `fds` | false | `*.fds` | file · no dedup (none needed) |
| `gamegear` | false | `*.gg` | file · no dedup (none needed) |
| `gopher64` | false | `*.n64 *.z64 *.v64 *.zip` | file · no dedup (none needed) |
| `mame` | false | `*.zip *.7z *.cmd` | file · no dedup (none needed) |
| `mastersystem` | false | `*.sms *.bms` | file · no dedup (none needed) |
| `megacd` | false | `*.cue *.iso *.chd *.m3u` | file · **full dedup** (`.m3u`/`.cue` over `.iso`) |
| `megadrive` | false | `*.md *.mdx *.smd *.gen *.68k` | file · no dedup (none needed) |
| `melonds` | false | `*.nds *.zip` | file · no dedup (none needed) |
| `mgba` | false | `*.gba *.gbc *.gb *.zip` | file · no dedup; `roms.consoles` = gba/gbc/gb |
| `naomi` | false | `*.zip *.7z` | file · no dedup (none needed) |
| `naomigd` | false | `*.zip *.7z` | file · no dedup (none needed) |
| `nes` | false | `*.nes *.unf *.unif` | file · no dedup (none needed) |
| `pcengine` | false | `*.pce` | file · no dedup (none needed) |
| `pcenginecd` | false | `*.cue *.ccd *.chd *.toc *.m3u` | file · descriptor-only dedup (no track ext declared) |
| `pcsx2` | false | `*.iso *.bin *.chd *.zip` | file · **NO DEDUP AND IT IS NEEDED** — see §4.2 |
| `ppsspp` | false | `*.iso *.cso *.pbp *.zip` | file · no dedup, though `.iso` is a track ext |
| `rpcs3` | **true** | *(none)* | **directory** · dedup disabled by `:124`; loose files invisible |
| `ryujinx` | false | `*.xci *.nsp *.zip` | file · no dedup — see §4.5 |
| `saturn` | false | `*.ccd *.chd *.cue *.iso *.mds *.m3u` | file · **full dedup** (`.m3u`/`.cue`/`.ccd`/`.mds` over `.iso`) |
| `sega32x` | false | `*.32x` | file · no dedup (none needed) |
| `sg1000` | false | `*.sg *.sgd` | file · no dedup (none needed) |
| `shadps4` | **true** | *(none)* | **directory** · dedup disabled by `:124`; loose files invisible |
| `snes9x` | false | `*.sfc *.smc *.fig *.swc *.jma *.zip *.gd3 *.gz *.bs` | file · no dedup (none needed) |
| `supergrafx` | false | `*.sgx` | file · no dedup (none needed) |
| `xenia` | false | `*.iso *.xex` | file · no dedup, though `.iso` is a track ext |

### 3.3 Formats — MULTI-FILE · FOLDER · DISC IMAGE · UPDATE/DLC

| PACK ID | MULTI-FILE FORMAT | FOLDER FORMAT | DISC IMAGE FORMAT | UPDATE/DLC CASES |
|---|---|---|---|---|
| `atomiswave` | archive members (opaque, §2.1) | — | — | — |
| `azahar` | — | — | — | `.cia` is an installable title, not a disc; update/DLC CIAs exist |
| `cemu` | extracted dump `code/ content/ meta/` — **unreachable, §4.4** | not scanned (`scanDirs` false) | `.wux` / `.iso` self-contained | update & DLC are separate title dirs; **no filter** |
| `dolphin` | — | — | `.iso .gcm .rvz .wbfs` self-contained; `.wad` = channel/VC title | `.wad` installs a title, is not a disc game |
| `dreamcast` | `.gdi` + tracks; `.cue` + `.bin` | — | `.chd`, `.cdi` self-contained | — |
| `duckstation` | `.cue` + `.bin` tracks | — | `.chd`, `.pbp` self-contained; bare `.bin`/`.iso`/`.img` | — |
| `fds` | — | — | — | — |
| `gamegear` | — | — | — | — |
| `gopher64` | — | — | — | — |
| `mame` | archive members (opaque, §2.1); parent/BIOS sets | — | — | parent/clone & BIOS sets are separate archives |
| `mastersystem` | — | — | — | — |
| `megacd` | `.cue` + `.bin`/`.iso` | — | `.chd` self-contained | — |
| `megadrive` | — | — | — | — |
| `melonds` | — | — | — | DSiWare exists; nothing distinguishes it |
| `mgba` | — | — | — | — |
| `naomi` | archive members (opaque, §2.1) | — | — | per-title BIOS archives live in the BIOS dir, not here |
| `naomigd` | archive members (opaque, §2.1) | — | — | — |
| `nes` | — | — | — | — |
| `pcengine` | — | — | — | — |
| `pcenginecd` | `.cue`/`.ccd`/`.toc` + tracks | — | `.chd` self-contained | — |
| `pcsx2` | `.cue` + `.bin` — **descriptor not declared, §4.2** | — | `.iso`, `.chd` self-contained | — |
| `ppsspp` | — | extracted PSP dumps exist but are **not scanned** | `.iso`, `.cso` self-contained; `.pbp` = EBOOT | DLC/saves live in PPSSPP's own tree |
| `rpcs3` | — | **the game IS the folder** (`PS3_GAME/`, `PARAM.SFO`) | — | updates/DLC are `.pkg`, installed **via the rpcs3-manager addon**, never dropped here (README:260) |
| `ryujinx` | — | — | — | **`.nsp` is base, update AND DLC** — indistinguishable, §4.5 |
| `saturn` | `.cue`/`.ccd`/`.mds` + tracks | — | `.chd`, `.iso` self-contained | — |
| `sega32x` | — | — | — | — |
| `sg1000` | — | — | — | — |
| `shadps4` | — | **the game IS the folder** (`sce_sys/param.sfo`) | — | patches exist; no declared layout |
| `snes9x` | — | — | — | — |
| `supergrafx` | — | — | — | — |
| `xenia` | `.xex` normally sits in an extracted tree — **unreachable, §1.2** | not scanned | `.iso` self-contained | title updates are separate; saves live in `lib/xenia` (issue #36) |

### 3.4 The contract — TRANSFORMATION · VALIDATION · FINAL REPRESENTATION · GAME ID METHOD

`GAME ID METHOD` is what names the game downstream. Three different identities
exist and they are not interchangeable:

- **display** — `local_media.get_title()` when `scanDirs`, else
  `clean_name(filename)` (`backend/routers/games.py:230-233`). `clean_name`
  strips the extension and every `(...)`/`[...]` group via `TAG_RE`
  (`backend/utils.py:9`).
- **settings/bezel** — `gameid.identify(perGame.key, rom)`, registry at
  `backend/services/gameid.py:200-209`; `bezels.rom_key()` delegates to the same
  `from_filename` so a game cannot be one thing to its overlay and another to
  its settings (`backend/services/bezels.py:82-103`).
- **scraper** — `localMedia.format` readers where declared
  (`backend/services/local_media.py`), else the filename parser; the metadata
  cache is keyed on the file stem (`backend/services/metadata.py` docstring).

| PACK ID | TRANSFORMATION | VALIDATION | FINAL REPRESENTATION | GAME ID METHOD |
|---|---|---|---|---|
| `atomiswave` | **none — never unpack** | archive opens; magic `PK`/`7z` | the `.zip`/`.7z`, byte-identical | display: filename · id: `filename` |
| `azahar` | none (`.zip` declared) | magic; `.cia` vs `.3ds` distinction | single file | display: filename · id: `filename` |
| `cemu` | none; **reject extracted trees** (§4.4) | magic; `keys.txt` optional (BIOS block) | single `.wux`/`.rpx`/`.iso` at top level | display: filename · `perGame.supported: false` since §7.1 — no title id is reachable (§4.4) |
| `dolphin` | none (`.zip` declared) | 6-char disc id readable at header | single file | id: `gcwii` disc header · scraper: `gcwii` |
| `dreamcast` | unpack if archived (`.zip` undeclared) | **`.gdi`/`.cue` + every track present** (§4.2) | descriptor + tracks flat, or one `.chd` | display: filename · id: `filename` |
| `duckstation` | none (`.zip` declared) | **`.cue` + every `FILE` it names** | `.cue` listed, tracks hidden | scraper: `playstation` serial from SYSTEM.CNF |
| `fds` | **unpack** (`.zip` undeclared) | `disksys.rom` **required** (BIOS block) | single `.fds` | display: filename · id: `filename` |
| `gamegear` | **unpack** | magic | single `.gg` | display: filename · id: `filename` |
| `gopher64` | none (`.zip` declared) | byte order (`.z64`/`.n64`/`.v64`) | single file | display: filename · id: `filename` |
| `mame` | **none — never unpack** (§2.1) | archive opens; set name = expected romset name | the `.zip`/`.7z`, byte-identical, name preserved | display: filename · id: `filename` |
| `mastersystem` | **unpack** | magic | single `.sms`/`.bms` | display: filename · id: `filename` |
| `megacd` | **unpack** | **`.cue` + tracks**; regional BIOS optional | `.cue`+tracks, or `.chd` | display: filename · id: `filename` |
| `megadrive` | **unpack** | magic | single file | display: filename · id: `filename` |
| `melonds` | none (`.zip` declared) | magic | single `.nds` | display: filename · id: `filename` |
| `mgba` | none (`.zip` declared) | extension decides the console (`roms.consoles`) | single file | display: filename · id: `filename` |
| `naomi` | **none — never unpack** | archive opens | the archive, byte-identical | display: filename · id: `filename` |
| `naomigd` | **none — never unpack** | archive opens | the archive, byte-identical | display: filename · id: `filename` |
| `nes` | **unpack** (`.zip` undeclared — proven §2.3) | iNES header | single `.nes` | display: filename · id: `filename` |
| `pcengine` | **unpack** | magic | single `.pce` | display: filename · id: `filename` |
| `pcenginecd` | **unpack** | **descriptor + tracks**; `syscard3.pce` **required** | `.cue`/`.ccd`/`.toc`+tracks, or `.chd` | display: filename · id: `filename` |
| `pcsx2` | none (`.zip` declared) | **prefer `.iso`/`.chd`; a `.cue` set is mis-listed** (§4.2) | one `.iso`/`.chd` **strongly preferred** | scraper: `playstation` serial · id: `filename` |
| `ppsspp` | none (`.zip` declared) | `.iso` readable by `Iso9660` | single `.iso`/`.cso`/`.pbp` | scraper: `psp` PARAM.SFO inside the ISO |
| `rpcs3` | **none — never flatten the folder** | `PS3_GAME/PARAM.SFO` present; `liblv2.sprx` **required** | **a directory** at the top level | `perGame.key = ps3` → `TITLE_ID` · display: SFO `TITLE` |
| `ryujinx` | none (`.zip` declared) | `prod.keys` **required**; **base vs update vs DLC undecidable from the file**, §4.5 | single `.nsp`/`.xci` | display: `clean_name` — **collides across update/base**, §4.5 |
| `saturn` | **unpack** | **descriptor + tracks**; `saturn_bios.bin` **required** | descriptor+tracks, or `.chd` | display: filename · id: `filename` |
| `sega32x` | **unpack** | magic | single `.32x` | display: filename · id: `filename` |
| `sg1000` | **unpack** | magic | single `.sg`/`.sgd` | display: filename · id: `filename` |
| `shadps4` | **none — never flatten the folder** | `sce_sys/param.sfo` present | **a directory** at the top level | scraper/display: `ps4` PARAM.SFO `TITLE` |
| `snes9x` | none (`.zip` declared) | magic; header/no-header | single file or `.zip` | display: filename · id: `filename` |
| `supergrafx` | **unpack** | magic | single `.sgx` | display: filename · id: `filename` |
| `xenia` | **unpack** (`.zip` undeclared) | `.iso` or a **top-level** `.xex` | single file, flat (§1.2) | display: filename · id: `filename` |

> `VALIDATION` above lists what the **Store** must check. The box itself checks
> exactly one thing before a launch — required BIOS files, by presence and never
> by hash (`backend/services/bios.py:194-206`, gate at
> `backend/routers/games.py:338`). It never checks that a ROM is complete,
> well-formed, or that its companions exist. That is the whole reason the
> `VALIDATION` column is the Store's problem.

---

## 4. The six cases that break a naive importer

### 4.1 Native archive vs packaging archive

Resolved in §2. The decision table in §2.4 is the deliverable; §2.1's
`{sf2/} -> []` measurement is the failure that forbids the global rule.

### 4.2 Disc images with companion files

A `.cue` without its `.bin`, a `.gdi` without its tracks, a `.ccd` without its
`.img` — each produces **a visible, unplayable entry**: the descriptor is listed
(it matches an extension), it hides nothing that is missing, and the launch
reaches an emulator that cannot open it. An incomplete download is therefore
indistinguishable from a working game until someone presses A.

**Minimal file set, per format:**

| Format | Minimal complete set | Notes |
|---|---|---|
| `.cue` | the `.cue` **plus every path in a `FILE "…"` line** | parsed by `_REF_RE`, `backend/services/rom_scanner.py:25` |
| `.gdi` | the `.gdi` plus every track it lists (`.bin`/`.raw`) | Dreamcast; tracks are usually `track01.bin`… |
| `.ccd` | `.ccd` + `.img` + `.sub` | the `.sub` is not referenced by the scanner and cannot be checked from it |
| `.mds` | `.mds` + `.mdf` | Saturn. `.mdf` is in neither `_DISC_TRACKS` nor `_REF_RE`, so the scanner can neither list it nor verify it |
| `.toc` | `.toc` + its data file | PC Engine CD. Same blind spot as `.mds` unless the data file is `.bin`/`.img`/`.iso`/`.raw` |
| `.chd` | **the `.chd` alone** | self-contained — the safest ingest target for every CD system |
| `.iso`, `.cso`, `.rvz`, `.wbfs`, `.gcm`, `.pbp`, `.wux` | **the file alone** | self-contained |

**`pcsx2` is the broken member and must be treated specially.** It declares
`.iso` and `.bin` (both *track* extensions) but **no descriptor at all**, so
`shadowed_by_a_descriptor` returns `{}` for it (`:72-74`). Measured:

```
pcsx2, {SOTC.cue, SOTC (Track 01).bin, SOTC (Track 02).bin}
  -> ['SOTC (Track 01).bin', 'SOTC (Track 02).bin']    ✗ two tiles, no .cue
pcsx2, {Game.cue, Game.bin}
  -> ['Game.bin']                                      ✗ the .cue is unreachable
```

A multi-track PS2 dump yields **one tile per track and no launchable
descriptor**. The Store must therefore **prefer `.iso` or `.chd` for PS2** and
treat a `.cue`-based PS2 download as not ingestible in its downloaded shape.
`cemu`, `dolphin`, `ppsspp` and `xenia` are in the same structural position —
track extensions declared, no descriptor — but for them no multi-track format is
in normal use, so the risk is theoretical rather than measured.

`dreamcast` and `pcenginecd` are the inverse and are **safe by construction**:
they declare descriptors but no track extensions, so the companion files are
filtered out by `matches_ext` before dedup is ever needed.

```
dreamcast, {Shenmue.gdi, track01.bin, track02.raw} -> ['Shenmue.gdi']   ✓
pcenginecd, {Ys.cue, Ys.bin}                       -> ['Ys.cue']        ✓
```

### 4.3 Multi-disc and `.m3u`

**Nothing in this repository writes an `.m3u`.** `rom_scanner` only ever reads
one — `grep -rn "m3u" backend --include="*.py"` returns nothing outside
`backend/services/rom_scanner.py` and its tests. So the playlist arrives with the
download, or the Store writes it, or there is none.

Its content is one path per line; blank lines and `#` comments are skipped, and
each line is read **whole** rather than tokenised, because disc names contain
spaces (`backend/services/rom_scanner.py:30-38`). A line may point into a
subdirectory — only the basename is used for hiding (`:89-90`).

The mechanism is transitive and it works:

```
saturn, {PD.m3u, PD (Disc 1).cue, PD (Disc 2).cue, + their .bin} -> ['PD.m3u']  ✓ one tile
dreamcast, {Shenmue.m3u, 3 × .gdi}                               -> ['Shenmue.m3u'] ✓
```

**Only four packs declare `*.m3u`: `dreamcast`, `megacd`, `pcenginecd`,
`saturn`.** And the consequence is the finding of this section:

```
duckstation, {FF9.m3u, FF9 (Disc 1..3).cue, + tracks}
  -> ['FF9 (Disc 1).cue', 'FF9 (Disc 2).cue', 'FF9 (Disc 3).cue']   ✗ three tiles
with *.m3u added to the extension list
  -> ['FF9.m3u']                                                     ✓ one tile
```

**PlayStation 1 — the system with the most multi-disc games in the catalogue —
cannot present a three-disc game as one tile**, because `duckstation` does not
declare `*.m3u`. Writing an `.m3u` into `<DATA>/emu/duckstation/` does not help:
it is not scanned, so by the §1.6 rule it hides nothing and the three `.cue`
files stay listed. The playlist is inert there. This is a catalogue gap, not a
Store bug, and it is logged in §7 — the Store cannot work around it.

### 4.4 Folder games — `rpcs3` and `shadps4`

The root of a game is **the directory itself**, and `scanDirs: true` is what
makes it visible: `iter_rom_files` yields `f` when `f.is_dir()` and yields
nothing else (`backend/services/rom_scanner.py:129-131`).

```
rpcs3, {BLES01234/, update.pkg} -> ['BLES01234']    ✓ the loose file is invisible
shadps4, {CUSA12345/}           -> ['CUSA12345']    ✓
```

That invisibility is protective — a stray `.pkg` cannot become a tile — and it is
also a trap: **anything the Store writes as a loose file into these two
directories is silently ignored.** There is no error and no log line.

**Declaring zero extensions is not an oversight.** A directory has no extension
to match, and `backend/tests/test_systems_extensions.py:72` asserts the pairing
explicitly: a pack with no extensions must be `scanDirs`. The README's rows for
these two are prose rather than a format list for the same reason
(`:69-73` of that test).

The folder is also where identity comes from: `local_media.get_title()` is called
**only** when `scanDirs` is set (`backend/routers/games.py:230`), so the tile
shows the game's real name out of `PARAM.SFO` instead of `BLES01234`. The Store
must therefore preserve the internal tree — `PS3_GAME/PARAM.SFO` for PS3,
`sce_sys/param.sfo` for PS4 (`backend/services/gamemedia/identity.py:37`) — or
the game imports with a serial for a name and scrapes nothing.

**The Wii U case is the one that does not work.** `cemu` is `scanDirs: false`,
so the real extracted layout is invisible:

```
cemu, {MyGame/code/game.rpx, MyGame/meta/meta.xml} -> []          ✗ nothing at all
cemu, {game.rpx}                                   -> ['game.rpx'] ✓ listed
```

And the per-game id reader points the other way. `_wiiu_title_id` looks for
`rom.parent/meta/meta.xml` and `rom.parent.parent/meta/meta.xml` — i.e. it
expects to be handed `<game>/code/foo.rpx`
(`backend/services/gameid.py:129-136`). Measured:

```
identify('wiiu', <game>/code/game.rpx) -> '0005000010143500'   reader works
identify('wiiu', <game>/  as a dir)    -> '0005000010143500'   reader works
identify('wiiu', flat.rpx)             -> None                 the only listable shape
```

**`cemu` declared `perGame.supported: true` with `key: wiiu`, and that key cannot
resolve for any ROM the scanner is able to list.** The reader supports exactly
the two layouts `scanDirs: false` forbids.

That was the state this matrix was written against. It has since been closed the
honest way — the pack declares `supported: false` with its reason rather than a
capability it cannot reach — and **the measurements above still hold**: a Wii U
dump in its real extracted layout is still invisible to the grid. Only the
promise was withdrawn, not the limitation. See §7.1 for why `scanDirs: true`
would have cost more than it bought.

### 4.5 Updates and DLC

`rpcs3` has the model answer and it is **not** the ROM directory: updates and DLC
are `.pkg` files installed through the rpcs3-manager addon (README:260), and
§4.4 shows a loose `.pkg` in `<DATA>/emu/rpcs3/` is invisible anyway. The Store
should route PS3 updates there and never into the library.

`ryujinx` has no such answer. **Base games, updates and DLC are all `.nsp`**, all
match `*.nsp`, and all become tiles:

```
ryujinx, {Zelda [..6000][v0].nsp, Zelda [..6800][v131072].nsp, Zelda DLC [..7000].nsp}
  -> all three listed                                          ✗ three tiles
```

And the display names collide, because `clean_name` strips every bracketed group
(`backend/utils.py:9`):

```
clean_name('FIFA 22 [0100216014472000][v0][US].nsp')      -> 'FIFA 22'
clean_name('FIFA 22 [0100216014472800][v131072][US].nsp') -> 'FIFA 22'
```

**Two tiles, the same name, and only one of them starts.** What would separate
them — the differing title id, the `v` field — sits in the filename and is thrown
away precisely by the normalisation that makes scraping work. (The widely-used
convention that an update's title id ends `800` is *not* asserted anywhere in
this repository and no reader parses it; see §6.2 before relying on it.)
`ryujinx` declares `perGame.supported: false`, so there is no `gameid` reader to
fall back on either.

The Store must therefore classify Switch content **before** writing: an update or
DLC `.nsp` must not be placed in `<DATA>/emu/ryujinx/`. Where it *should* go —
Ryujinx keeps its own update and DLC registry inside its Flatpak tree — is not
expressible in the catalogue today (§6.1). `cemu` and `azahar` have the same
shape (`.wux` updates, update `.cia`) with the same absence of a filter.

### 4.6 `scanDirs` vs `shadowed_by_a_descriptor`

They do not compose — the first switches the second off:

```python
hidden = {} if scan_dirs else shadowed_by_a_descriptor(entries, extensions)
```

> `backend/services/rom_scanner.py:124`

So on `rpcs3` and `shadps4` there is no dedup at all, and none is needed: only
directories are yielded, and a directory is never a disc track. Reading the code
first matters because the naive expectation — "folder games also get companion
dedup" — would lead a Store to assume a stray `.cue`/`.bin` pair inside those
directories is handled. It is not handled; it is **invisible**, which is a
different and better outcome, but only if it is known.

The matrix reflects this as *"dedup disabled by `:124`; loose files invisible"*
rather than as a dedup column, because for these two packs the question does not
arise.

---

## 5. Transversal synthesis — six ingestion classes

**This is the part that dictates the number of Store strategies.** Thirty-one
would be a design failure; one would be wrong. It is six — and the class is a
property of the **(system, incoming format)** pair, which is why a single system
can appear in more than one row.

### 5.1 The classes

| # | Class | Members (system · format) | Transform | Validate | Final shape |
|---|---|---|---|---|---|
| **A** | **Plain file, archive undeclared** | `nes` `fds` `megadrive` `mastersystem` `gamegear` `sg1000` `sega32x` `pcengine` `supergrafx` · any | **unpack if archived**, flat | one member with a declared extension | one file |
| **B** | **Plain file, archive declared** | `snes9x` `melonds` `mgba` `azahar` `gopher64` `ryujinx` · their single-file formats | **none** | magic bytes | one file, possibly still `.zip` |
| **C** | **Archive IS the ROM** | `mame` `naomi` `naomigd` `atomiswave` · `.zip`/`.7z` | **NEVER unpack** | archive opens; name preserved | the archive, byte-identical |
| **D** | **Self-contained disc image** | `duckstation` `pcsx2` `ppsspp` `dolphin` `xenia` `megacd` `saturn` `dreamcast` `pcenginecd` `cemu` · `.chd .iso .cso .rvz .wbfs .gcm .pbp .wux .cdi` | unpack only if the container extension is undeclared | header readable | one file |
| **E** | **Disc image with companions** | `duckstation` `dreamcast` `megacd` `saturn` `pcenginecd` · `.cue .gdi .ccd .mds .toc` (+ `.m3u`) | keep the set together, flat | **descriptor + every file it names** | descriptor + tracks |
| **F** | **Game is a directory** | `rpcs3` `shadps4` · folder | **never flatten, never unpack into a subdir** | the identity file (`PARAM.SFO` / `param.sfo`) | a top-level directory |

Three systems are **deliberately not assigned a class for one of their
formats**, because the code cannot currently carry them:

- `pcsx2` + `.cue` → would be class E, but `pcsx2` declares no descriptor (§4.2).
  Reject; ingest as D instead.
- `cemu` + extracted tree and `xenia` + extracted `.xex` tree → would be class F,
  but both are `scanDirs: false` (§4.4, §1.2). Reject; ingest as D.

### 5.2 Why six and not more

The classes are distinguished by **what the ingest must physically do**, and
nothing else:

- A vs B is one predicate: *is the archive extension declared?* (§2.3)
- B vs C is one predicate: *does any member carry a declared non-archive
  extension?* (§2.4)
- D vs E is one predicate: *is the extension in `_DISC_DESCRIPTORS`
  (`backend/services/rom_scanner.py:18`) and declared by this pack?*
- F is one predicate: *`roms.scanDirs`.*

All four predicates read the pack plus a listing of the download. None needs a
per-system table, and a new pack lands in the right class without an edit — which
is the property that makes this a contract rather than a snapshot.

### 5.3 The cross-cutting rules, which are not classes

Four rules apply to every class and must not be folded into one:

1. **Write flat, into `<DATA>/emu/<dir>/`** — §1.2, §1.3. Any subdirectory on a
   non-`scanDirs` system produces zero games.
2. **Never emit a name starting with `.` or containing `example`** — §1.4. The
   file is dropped silently.
3. **Nothing downstream validates completeness** — §1.1. If the Store does not
   check it, the failure surfaces as a black screen after the player presses A.
4. **Required BIOS is a launch blocker, not an ingest blocker** — the box refuses
   the launch and names the file (`backend/services/bios.py:222-250`). Seven
   systems have a `required: true` file: `fds`, `pcenginecd`, `pcsx2`, `rpcs3`,
   `ryujinx`, `saturn`, and `duckstation` (via `anyFile`). A Store that imports a
   Saturn game onto a box with no `saturn_bios.bin` produces a correct import and
   an unplayable tile — worth surfacing at download time, but it is not a reason
   to refuse the write.

### 5.4 The RetroArch tier, and what it does not change

Seventeen of the 31 packs are `pacman` installs of `retroarch` plus one
`libretro-*` core, launched through
[`scripts/gamecore-retroarch-launch.py`](../../scripts/gamecore-retroarch-launch.py).
They are seventeen of the eighteen packs added at `c1a4df6` — `snes9x` is the
eighteenth and is a Flatpak — so this whole tier is new, and
**all seventeen share
`overlay.wmClass.linux = ["retroarch","RetroArch"]`**: `atomiswave` `dreamcast`
`fds` `gamegear` `mame` `mastersystem` `megacd` `megadrive` `naomi` `naomigd`
`nes` `pcengine` `pcenginecd` `saturn` `sega32x` `sg1000` `supergrafx`.

**Window identification cannot tell these seventeen systems apart.** That is a
fact about overlays and bezels, not about ingestion — the Store is unaffected,
since it never looks at a window. It is recorded here because it is the one
property the new tier introduced that a reader of this matrix will otherwise
assume ingestion shares: it does not. Ingestion is keyed on `roms.dir`, which is
distinct for all 31 packs.

Their BIOS root is shared too —
`~/.config/gamecore-retroarch/system`, set as `LIBRETRO_SYSTEM_DIRECTORY` by the
launcher — which is why `dreamcast`, `naomi` and `atomiswave` all reference
`dc/…` paths inside it.

---

## 6. What this matrix cannot decide without material

Each of these needs a real file, a real box, or a decision — not more reading.

1. **Switch update/DLC routing.** §4.5 establishes that an update `.nsp` must not
   be written to `<DATA>/emu/ryujinx/`. It does not establish where it *should*
   go: Ryujinx's update and DLC registries live inside its Flatpak tree, no
   catalogue field names them, and no `@FLATPAK_*@` expansion is declared for
   them. **Needs a real update `.nsp` and a look at an installed Ryujinx.**
2. **Distinguishing a base `.nsp` from an update `.nsp` without external data.**
   The title-id convention (a `800` update suffix) is widely used but is not
   asserted anywhere in this repository, and no reader in
   `backend/services/gameid.py` parses it. **Needs a decision on whether the
   Store trusts the convention, the download source's metadata, or neither.**
3. **`mame` romset naming.** A MAME set only runs if the archive keeps the exact
   name the core expects, and parent/clone/BIOS sets must all be present. Nothing
   in the catalogue records which romset version the shipped `libretro-mame`
   wants. **Needs the core's version and its romset list.**
4. **What `*.cmd` is on `mame`.** Declared in
   [`catalog/mame/pack.json`](../../catalog/mame/pack.json) and in the README
   table, explained nowhere in the repository. Until it is known, the Store
   should neither produce nor rewrite one.
5. **`.ccd` and `.mds` companion checking.** §4.2 gives the minimal sets from
   format knowledge, but `_REF_RE` only parses `.cue`-style and `.gdi`-style
   references (`backend/services/rom_scanner.py:25`); a `.ccd`'s `.img`/`.sub`
   and a `.mds`'s `.mdf` are matched by the *stem* rule alone. **Needs a real
   `.ccd` and `.mds` set to confirm the stem rule is sufficient.**
6. **Multi-disc on PS1.** §4.3 shows `duckstation` cannot show a 3-disc game as
   one tile. Adding `*.m3u` to its extensions is a one-line pack change, but it
   is not a documentation fix: the `.dist`, the README table and the test that
   pins them to each other all move with it
   (`backend/tests/test_systems_extensions.py:57`). **Needs a decision.**
7. **Free space and filesystem.** External disks are exFAT/NTFS in practice, and
   `07-config-and-data.md` records that ROMs are fine there but saves are not.
   Whether the Store may target a `volumes/` symlink, and what it does when the
   disk is pulled mid-download, is undecided. **Needs the storage decision.**
8. **Concurrency with the scan.** `list_games()` runs on every grid open (§1.1)
   and there is no lock. A partially-written file with its final name becomes a
   tile mid-download. A `.part`-then-rename discipline is the obvious answer — the
   installer already uses exactly that for its own downloads
   (`10-catalog-and-install.md`, the `install` provider notes) — but nothing
   enforces it for ROMs. **Needs confirming against a real slow download.**

---

## 7. Inconsistencies found and deliberately not fixed

Found while writing this document, recorded rather than corrected: each needs a
decision and a test change, and none of them is a documentation fix. Item 1 was
decided by the owner immediately afterwards and is now closed; items 2 to 5 are
still open, and no other `pack.json` has been modified.

1. ~~**`cemu` promises per-game settings it cannot deliver.**~~ **Closed.**
   `perGame.supported: true` with `key: wiiu`, against a reader that resolves
   only for layouts `scanDirs: false` makes unlistable (§4.4). Of the three
   available answers — `scanDirs: true`, a flat-`.rpx` path in
   `_wiiu_title_id`, or an honest `supported: false` — the owner chose the
   third, and `catalog/cemu/pack.json` now declares it with its reason.

   `scanDirs: true` was the tempting one and it was the trap: `iter_rom_files`
   yields **only directories** in that mode and ignores `extensions` entirely
   (`rom_scanner.py:129-131`), so it would have made every `.wux`, `.iso`,
   `.zip` and flat `.rpx` on a real box disappear from the grid. Trading a
   promise nobody could keep for a library nobody can see is not a fix.

   One documented side effect: `settingsArgs` — the button that opens Cemu's
   **own** settings window, which needs no title id at all — is gated on the
   same flag (`pergame.py:656`, `if not args or not b.get("supported")`), so it
   goes quiet too. The field is kept in the pack because it states something
   true about Cemu; ungating it is a code change, not a data one.
2. **`pcsx2` declares track extensions and no descriptor** (§4.2), so a `.cue`
   set lists one tile per track. Adding `*.cue` would turn on dedup — and would
   also change what an existing box lists, which is the exact class of change
   `test_a_descriptor_the_system_does_not_scan_hides_nothing` exists to guard.
3. **`duckstation` does not declare `*.m3u`** (§4.3), so PS1 multi-disc games
   cannot be one tile on the system that needs it most.
4. **`mame` declares `*.cmd` with no explanation anywhere** (§6.4).
5. **The `"example"` filter is an unanchored substring** (§1.4) and can drop a
   legitimately-named game with no diagnostic.

Only item 4 arrived with the 18-pack integration at `c1a4df6` — `mame` is one of
those eighteen (`git show --name-status c1a4df6 -- catalog/`). Items 1, 2, 3 and
5 all predate it: `cemu`, `pcsx2` and `duckstation` were already in the catalogue
at `5af5d21`, and the `"example"` filter is older still.

---

## 8. Verification

Every command below was run at `c1a4df6` on the branch that carries this
document.

| Command | Result |
|---|---|
| `.venv/bin/python scripts/check-catalog.py` | `check-catalog: 35 pack(s) OK` |
| `.venv/bin/python -m pytest backend/tests/test_catalog_consumers.py -q` | 23 passed, 4 skipped |
| `.venv/bin/python -m pytest backend/tests/test_systems_extensions.py -q` | 53 passed |
| `.venv/bin/python -m pytest backend/tests catalog -q -m "not network"` | **2247 passed**, 23 skipped, 4 deselected |

`.venv/bin/python -m pytest backend/tests -q -m "not network" -k "rom or scan"`
reports `1 failed, 164 passed` — `test_standby_launch.py::test_the_idle_clock_restarts_from_the_launch`.
**It is a pre-existing selection-order artefact, not a finding of this work.** The
same test passes in the full run above and passes when its own file is run whole;
it fails only when `-k` deselects its six siblings, because it then pays the
app's first-request startup cost (~9 s of `/dev/input` probing) inside its own
5-second tolerance. Nothing in this document depends on it, and no source file
was modified.

**No claim in this matrix contradicts a test.** Where a claim touches behaviour a
test already pins, the test is cited rather than restated:
`backend/tests/test_systems_extensions.py:224` for the descriptor rule,
`:72` for the `scanDirs`/no-extensions pairing, `:190` for the transitive `.m3u`.
